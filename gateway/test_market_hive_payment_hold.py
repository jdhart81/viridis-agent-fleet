import asyncio

from payment_gate import GATE_ATTR, PaymentGate


class Store:
    def __init__(self):
        self.saves = []

    def save(self, name, core):
        self.saves.append(name)
        return True


class FailingCompletionStore(Store):
    def __init__(self):
        super().__init__()
        self.hive_saves = 0

    def save(self, name, core):
        self.saves.append(name)
        if name == "hive":
            self.hive_saves += 1
            # reservation, idempotency reservation, and EXECUTING are durable;
            # only the final result+COMPLETED snapshot fails.
            return self.hive_saves != 4
        return True


class Meter:
    def __init__(self):
        self.events = []

    async def process(self, payload):
        self.events.append(dict(payload))
        if payload["action"] == "create_meter":
            return {"status": "ok", "data": {"meter_id": "meter-market"}}
        return {"status": "ok", "data": {}}


class Hive:
    KNOWN_ACTIONS = frozenset({"solve"})
    READ_ACTIONS = frozenset()

    def __init__(self):
        self.calls = 0

    async def process(self, payload):
        self.calls += 1
        assert "_market_payment_token" not in payload
        return {"status": "ok", "data": {"answer": "reviewed"}}


def binding(work_id="work_external_123", escrow_id="esc_live_123"):
    return {
        "work_id": work_id,
        "escrow_id": escrow_id,
        "funding_event_id": "funding_" + "a" * 64,
        "event_sha256": "b" * 64,
        "amount_minor": 500,
        "currency": "USD",
        "payee": "viridis:hive",
    }


def payload():
    return {
        "action": "solve",
        "problem": "Review this external buyer decision.",
        "budget_minor": 500,
    }


def test_verified_hold_executes_once_before_buyer_release():
    store, meter, hive = Store(), Meter(), Hive()
    gate = PaymentGate(
        store, meter, free_calls_per_day=0,
        market_funding_verifier=lambda name, item: {
            "verified": name == "hive"
            and item["work_id"] == "work_external_123",
        })
    gate.attach("hive", hive)
    held = gate.reserve_market_payment("hive", binding(), payload())
    assert held["status"] == "ok"
    assert held["money_movement"] == "none"

    request = {
        **payload(),
        "request_id": "market-hive-work-123",
        "_market_payment_token": held["token"],
    }
    first = asyncio.run(hive.process(request))
    replay = asyncio.run(hive.process(request))
    assert first == replay
    assert hive.calls == 1
    state = getattr(hive, GATE_ATTR)
    assert state["market_holds"]["work_external_123"]["state"] == "COMPLETED"
    assert state["credits"] == 0
    assert state["used_by_caller"] == {}


def test_live_funding_is_rechecked_immediately_before_execution():
    still_funded = {"value": True}
    store, hive = Store(), Hive()
    gate = PaymentGate(
        store, Meter(), free_calls_per_day=0,
        market_funding_verifier=lambda _name, _item: {
            "verified": still_funded["value"],
        })
    gate.attach("hive", hive)
    held = gate.reserve_market_payment("hive", binding(), payload())
    assert held["status"] == "ok"

    still_funded["value"] = False
    refused = asyncio.run(hive.process({
        **payload(),
        "_market_payment_token": held["token"],
    }))
    assert refused["error_type"] == "payment_required"
    assert refused["a2a"]["refusal_reason"] == (
        "market_funding_no_longer_verified")
    assert hive.calls == 0
    assert getattr(hive, GATE_ATTR)["market_holds"][
        "work_external_123"]["state"] == "RESERVED"


def test_work_and_escrow_bindings_cannot_be_reused_or_mutated():
    gate = PaymentGate(
        Store(), Meter(), free_calls_per_day=0,
        market_funding_verifier=lambda _name, _item: {"verified": True})
    hive = Hive()
    gate.attach("hive", hive)
    first = gate.reserve_market_payment("hive", binding(), payload())
    assert first["status"] == "ok"

    duplicate = gate.reserve_market_payment("hive", binding(), payload())
    assert duplicate["status"] == "ok"
    assert duplicate["duplicate"] is True
    assert duplicate["token"] == first["token"]

    changed = gate.reserve_market_payment(
        "hive", binding(), {**payload(), "problem": "different"})
    assert changed["status"] == "error"
    assert changed["reason"] == "work_binding_conflict"

    reused = gate.reserve_market_payment(
        "hive", binding(
            work_id="work_external_456", escrow_id="esc_live_123"),
        payload())
    assert reused["status"] == "error"
    assert reused["reason"] == "escrow_already_bound"


def test_completion_save_failure_never_acknowledges_or_reexecutes_paid_work():
    store, hive = FailingCompletionStore(), Hive()
    gate = PaymentGate(
        store, Meter(), free_calls_per_day=0,
        market_funding_verifier=lambda _name, _item: {"verified": True})
    gate.attach("hive", hive)
    held = gate.reserve_market_payment("hive", binding(), payload())
    assert held["status"] == "ok"

    request = {
        **payload(),
        "request_id": "market-hive-durability-failure",
        "_market_payment_token": held["token"],
    }
    failed = asyncio.run(hive.process(request))
    assert failed["status"] == "error"
    assert failed["error_type"] == "durable_completion_failed"
    assert "manual reconciliation" in failed["message"]
    state = getattr(hive, GATE_ATTR)
    assert state["market_holds"]["work_external_123"]["state"] == "EXECUTING"
    retry_entries = list(state["idempotent_requests"].values())
    assert len(retry_entries) == 1
    assert retry_entries[0]["request_id"] == "market-hive-durability-failure"
    assert retry_entries[0]["state"] == "pending"
    assert hive.calls == 1

    replay = asyncio.run(hive.process(request))
    assert replay["status"] == "error"
    assert replay["error_type"] == "idempotency_incomplete"
    assert hive.calls == 1
