import asyncio

from payment_gate import GATE_ATTR, PaymentGate


class FailingCompletionStore:
    def __init__(self):
        self.hive_saves = 0

    def save(self, name, core):
        if name == "hive":
            self.hive_saves += 1
            # reservation, idempotency reservation, and EXECUTING are durable;
            # only the final result+COMPLETED snapshot fails.
            return self.hive_saves != 4
        return True


class Meter:
    async def process(self, payload):
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


def test_completion_save_failure_never_acknowledges_or_reexecutes_paid_work():
    store, hive = FailingCompletionStore(), Hive()
    gate = PaymentGate(
        store, Meter(), free_calls_per_day=0,
        market_funding_verifier=lambda _name, _item: {"verified": True})
    gate.attach("hive", hive)
    payload = {
        "action": "solve",
        "problem": "Review this external buyer decision.",
        "budget_minor": 500,
    }
    held = gate.reserve_market_payment("hive", {
        "work_id": "work_external_123",
        "escrow_id": "esc_live_123",
        "funding_event_id": "funding_" + "a" * 64,
        "event_sha256": "b" * 64,
        "amount_minor": 500,
        "currency": "USD",
        "payee": "viridis:hive",
    }, payload)
    assert held["status"] == "ok"

    request = {
        **payload,
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
