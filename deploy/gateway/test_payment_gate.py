#!/usr/bin/env python3
"""
Tests for payment_gate.py — one test per PG invariant, using the real
smartscale (SYNC process — the convention-preservation regression the
selftest caught) + metering cores and the real StateStore (quota
persistence across restarts is part of the contract).

Run:  pytest deploy/gateway/test_payment_gate.py -q
"""
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from payment_gate import PaymentGate, GATE_ATTR, PRICE_MINOR, SEAT_PLANS  # noqa: E402
from state_store import StateStore                # noqa: E402


def _load_pkg(agent_dir: str):
    """Load an agent core the way its adapter does: as a real src package
    (smartscale's core imports src.validation)."""
    for m in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
        del sys.modules[m]
    ps = importlib.util.spec_from_file_location(
        "src", ROOT / agent_dir / "src" / "__init__.py",
        submodule_search_locations=[str(ROOT / agent_dir / "src")])
    pkg = importlib.util.module_from_spec(ps)
    sys.modules["src"] = pkg
    ps.loader.exec_module(pkg)
    cs = importlib.util.spec_from_file_location(
        "src.core", ROOT / agent_dir / "src" / "core.py")
    mod = importlib.util.module_from_spec(cs)
    sys.modules["src.core"] = mod
    cs.loader.exec_module(mod)
    return mod


SMARTSCALE = _load_pkg("smartscale-agent")
METERING = _load_pkg("agent-metering-agent")
METERING_MODULES = {
    name: module for name, module in sys.modules.items()
    if name == "src" or name.startswith("src.")
}


def call(core, payload):
    """Invoke process() regardless of the core's calling convention."""
    result = core.process(payload)
    if asyncio.iscoroutine(result):
        return asyncio.get_event_loop_policy().new_event_loop() \
            .run_until_complete(result)
    return result


def build(db, free=2):
    store = StateStore(db)
    scale = SMARTSCALE.SmartScaleCore()
    meter = METERING.build()
    store.register_modules("metering", METERING_MODULES)
    store.attach("smartscale", scale)
    store.attach("metering", meter)
    gate = PaymentGate(store, meter, free_calls_per_day=free)
    gate.attach("smartscale", scale)
    return store, gate, scale, meter


CALL = {"action": "measure_from_credit_card", "image_id": "img-1",
        "credit_card_pixel_width": 856.0,
        "objects": [{"label": "box", "pixel_width": 428.0,
                     "pixel_height": 214.0}]}


class SyncPreflightCore:
    READ_ACTIONS = frozenset()
    KNOWN_ACTIONS = frozenset({"solve"})

    def __init__(self, decision):
        self.decision = decision
        self.calls = 0

    def _paid_preflight(self, _payload):
        if isinstance(self.decision, Exception):
            raise self.decision
        return self.decision

    def process(self, _payload):
        self.calls += 1
        return {"status": "ok"}


class AsyncPreflightCore(SyncPreflightCore):
    async def _paid_preflight(self, _payload):
        if isinstance(self.decision, Exception):
            raise self.decision
        return self.decision

    async def process(self, _payload):
        self.calls += 1
        return {"status": "ok"}


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "state.db")


def test_sync_convention_preserved(db):
    """Regression: smartscale's adapter calls process() WITHOUT await —
    wrappers must return a dict, never a coroutine."""
    _, _, scale, _ = build(db, free=2)
    result = scale.process(dict(CALL))
    assert isinstance(result, dict)
    assert result["status"] == "ok"


def test_pg1_free_tier_calls_succeed(db):
    _, _, scale, _ = build(db, free=2)
    for _ in range(2):
        assert call(scale, dict(CALL))["status"] == "ok"


def test_pg1_zero_free_tier_requires_payment_on_first_call(db):
    _, _, scale, _ = build(db, free=0)
    refused = call(scale, dict(CALL))
    assert refused["status"] == "error"
    assert refused["error_type"] == "payment_required"
    assert getattr(scale, GATE_ATTR)["used"] == 0


def test_pg2_beyond_free_tier_payment_required_envelope(db):
    _, _, scale, _ = build(db, free=1)
    assert call(scale, dict(CALL))["status"] == "ok"
    refused = call(scale, dict(CALL))
    assert refused["status"] == "error"
    assert refused["error_type"] == "payment_required"
    assert refused["http_equivalent"] == 402
    assert refused["amount_minor"] == PRICE_MINOR["smartscale"]
    assert "stripe_checkout" in str(refused["payment"]["human"])
    assert "x402" in str(refused["payment"]["a2a"])


def test_pg3_read_actions_never_gated_or_counted(db):
    _, _, scale, _ = build(db, free=1)
    call(scale, dict(CALL))                            # exhaust free tier
    for _ in range(3):                                 # reads still fine
        r = call(scale, {"action": "list_reports"})
        assert r.get("error_type") != "payment_required"
    assert getattr(scale, GATE_ATTR)["used"] == 1      # reads not counted


@pytest.mark.parametrize("core_type", [SyncPreflightCore, AsyncPreflightCore])
def test_pg25_agent_preflight_refuses_before_every_billing_path(
        db, core_type):
    store = StateStore(db)
    meter = METERING.build()
    core = core_type({
        "status": "error",
        "error_type": "ValidationError",
        "field": "budget_minor",
        "message": "fixed paid profile required",
    })
    gate = PaymentGate(store, meter, free_calls_per_day=1)
    gate.attach("preflight-test", core)
    state = getattr(core, GATE_ATTR)
    state["credits"] = 1
    before = {
        key: state[key] for key in (
            "used", "refused", "credits", "subscription_waived",
            "subscription_overage")
    }

    refused = call(core, {
        "action": "solve", "budget_minor": 499,
        "payment_ref": "escrow_should_not_be_touched",
    })

    assert refused["status"] == "error"
    assert refused["field"] == "budget_minor"
    assert refused["payment_required"] is False
    assert core.calls == 0
    assert {
        key: state[key] for key in before
    } == before
    assert "preflight-test" not in store.status()["snapshots"]


@pytest.mark.parametrize("core_type", [SyncPreflightCore, AsyncPreflightCore])
def test_pg25_agent_preflight_exception_fails_closed_without_billing(
        db, core_type):
    store = StateStore(db)
    meter = METERING.build()
    core = core_type(RuntimeError("provider probe broke"))
    gate = PaymentGate(store, meter, free_calls_per_day=1)
    gate.attach("preflight-test", core)

    refused = call(core, {"action": "solve"})

    assert refused["status"] == "error"
    assert refused["error_type"] == "ServiceUnavailable"
    assert refused["payment_required"] is False
    assert core.calls == 0
    state = getattr(core, GATE_ATTR)
    assert state["used"] == 0
    assert state["refused"] == 0
    assert "preflight-test" not in store.status()["snapshots"]


def test_pg25_preflight_refusal_releases_pending_idempotency_reservation(db):
    store = StateStore(db)
    meter = METERING.build()
    core = AsyncPreflightCore({
        "status": "error",
        "error_type": "ValidationError",
        "field": "budget_minor",
        "message": "fixed paid profile required",
    })
    gate = PaymentGate(store, meter, free_calls_per_day=1)
    gate.attach("preflight-test", core)

    refused = call(core, {
        "action": "solve", "budget_minor": 499,
        "request_id": "preflight-refusal-retry-key",
    })

    assert refused["status"] == "error"
    assert refused["payment_required"] is False
    assert getattr(core, GATE_ATTR)["idempotent_requests"] == {}
    assert core.calls == 0


def test_pg4_every_call_is_metered_on_the_fleets_own_meter(db):
    _, _, scale, meter = build(db, free=1)
    call(scale, dict(CALL))                            # ok -> metered
    call(scale, dict(CALL))                            # refused -> metered
    mid = getattr(scale, GATE_ATTR)["meter_id"]
    assert mid
    summary = call(meter, {"action": "usage_summary", "meter_id": mid})
    assert summary["status"] == "ok"
    assert summary["data"]["event_count"] == 2         # allowed + refused


def test_pg24_gate_persists_metering_under_its_own_key(tmp_path):
    """Meter durability must not depend on StateStore wrapping meter.process.

    This is the production regression: the gated agent snapshot advanced while
    the metering snapshot stayed frozen, so health showed traffic that would
    disappear on restart.
    """
    db = tmp_path / "state.db"
    store = StateStore(db)
    scale = SMARTSCALE.SmartScaleCore()
    meter = METERING.build()
    store.register_modules("metering", METERING_MODULES)
    store.attach("smartscale", scale)
    # Deliberately do not attach StateStore to meter.process. PaymentGate owns
    # PG24 and must explicitly save the metering core after its mutation.
    gate = PaymentGate(store, meter, free_calls_per_day=1)
    gate.attach("smartscale", scale)

    call(scale, dict(CALL))
    first_snapshot = store.status()["snapshots"]["metering"]
    assert first_snapshot["seq"] == 1

    meter2 = METERING.build()
    store2 = StateStore(db)
    store2.register_modules("metering", METERING_MODULES)
    assert store2.restore("metering", meter2) is True
    mid = getattr(scale, GATE_ATTR)["meter_id"]
    summary = call(meter2, {"action": "usage_summary", "meter_id": mid})
    assert summary["status"] == "ok"
    assert summary["data"]["event_count"] == 1


def test_pg5_quota_survives_restart(db):
    _, _, scale, _ = build(db, free=1)
    call(scale, dict(CALL))                            # free tier used up

    # ---- restart: fresh cores, fresh store, same db ----
    store2 = StateStore(db)
    scale2 = SMARTSCALE.SmartScaleCore()
    meter2 = METERING.build()
    store2.restore("smartscale", scale2)
    store2.restore("metering", meter2)
    store2.attach("smartscale", scale2)
    store2.attach("metering", meter2)
    gate2 = PaymentGate(store2, meter2, free_calls_per_day=1)
    gate2.attach("smartscale", scale2)

    refused = call(scale2, dict(CALL))                 # quota remembered
    assert refused.get("error_type") == "payment_required"


def test_pg6_only_attached_agents_are_gated(db):
    store = StateStore(db)
    meter = METERING.build()
    store.attach("metering", meter)
    PaymentGate(store, meter, free_calls_per_day=0)    # nothing attached
    r = call(meter, {"action": "create_meter", "provider": "a",
                     "consumer": "b", "unit": "call",
                     "price_minor_per_unit": 1})
    assert r["status"] == "ok"


def test_pg7_day_rollover_freezes_an_invoice(db):
    _, gate, scale, meter = build(db, free=5)
    call(scale, dict(CALL))
    call(scale, dict(CALL))
    g = getattr(scale, GATE_ATTR)
    g["day"] = "2000-01-01"                            # force rollover
    call(scale, dict(CALL))                            # triggers rollover
    assert g["day"] != "2000-01-01"
    assert g["used"] == 1                              # fresh day count
    assert len(g["invoices"]) == 1
    assert g["invoices"][0]["amount_minor"] == 2 * PRICE_MINOR["smartscale"]  # yesterday's 2 calls


def test_pg8_metering_failure_never_blocks_the_service_call(db):
    store = StateStore(db)
    scale = SMARTSCALE.SmartScaleCore()
    store.attach("smartscale", scale)

    class BrokenMeter:
        async def process(self, _):
            raise RuntimeError("meter down")

    gate = PaymentGate(store, BrokenMeter(), free_calls_per_day=2)
    gate.attach("smartscale", scale)
    r = call(scale, dict(CALL))
    assert r["status"] == "ok"                         # service unaffected
    assert "smartscale" in gate.status()["errors"]     # failure surfaced


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


# --- PG9/PG10/PG11: the paid-credit loop (pay -> redeem -> call) -------------- #
def _paid_verify(amount=150, status="paid", live=False):
    def v(session_id):
        return {"status": "ok", "session_id": session_id,
                "payment_status": status, "amount_total": amount,
                "currency": "usd", "livemode": live}
    return v


def test_PG10_redeem_grants_credits_and_is_idempotent(tmp_path):
    store, gate, scale, meter = build(tmp_path / "s.db", free=1)
    price = PRICE_MINOR["smartscale"]
    r1 = gate.redeem("cs_test_1", "smartscale", _verify=_paid_verify(amount=3 * price))
    assert r1["status"] == "ok" and r1["credits_granted"] == 3
    r2 = gate.redeem("cs_test_1", "smartscale", _verify=_paid_verify(amount=3 * price))
    assert r2["duplicate"] is True and r2["credits_granted"] == 3
    assert getattr(scale, GATE_ATTR)["credits"] == 3   # never double-credited


def test_PG10_unpaid_dust_and_unknown_rejected(tmp_path):
    store, gate, scale, meter = build(tmp_path / "s.db")
    unpaid = gate.redeem("cs_test_u", "smartscale", _verify=_paid_verify(status="unpaid"))
    assert unpaid["status"] == "error" and unpaid["error_type"] == "not_paid"
    dust = gate.redeem("cs_test_d", "smartscale",
                       _verify=_paid_verify(amount=PRICE_MINOR["smartscale"] - 1))
    assert dust["status"] == "error" and dust["error_type"] == "insufficient_amount"
    unknown = gate.redeem("cs_test_x", "narrative-engine", _verify=_paid_verify())
    assert unknown["status"] == "error" and unknown["error_type"] == "unknown_agent"
    assert getattr(scale, GATE_ATTR)["credits"] == 0


def test_PG9_credits_consumed_after_free_tier(tmp_path):
    store, gate, scale, meter = build(tmp_path / "s.db", free=1)
    price = PRICE_MINOR["smartscale"]
    gate.redeem("cs_test_c", "smartscale", _verify=_paid_verify(amount=2 * price))
    ok1 = call(scale, CALL)                      # free call
    assert ok1.get("error_type") != "payment_required"
    ok2 = call(scale, CALL)                      # credit 1
    ok3 = call(scale, CALL)                      # credit 2
    assert ok2.get("error_type") != "payment_required"
    assert ok3.get("error_type") != "payment_required"
    refused = call(scale, CALL)                  # credits exhausted -> 402
    assert refused["error_type"] == "payment_required"
    assert "redeem_payment" in refused["payment"]["human"]["then"]
    assert getattr(scale, GATE_ATTR)["credits"] == 0


def test_PG11_credits_survive_rollover_and_restart(tmp_path):
    db = tmp_path / "s.db"
    store, gate, scale, meter = build(db, free=1)
    price = PRICE_MINOR["smartscale"]
    gate.redeem("cs_test_p", "smartscale", _verify=_paid_verify(amount=5 * price))
    # force a rollover: credits must NOT reset
    g = getattr(scale, GATE_ATTR)
    g["day"] = "2020-01-01"
    call(scale, CALL)                            # triggers rollover, uses free call
    assert getattr(scale, GATE_ATTR)["credits"] == 5
    # restart: fresh store + cores, then restore from disk (the gateway's
    # boot sequence — viridis_mcp_gateway.py calls store.restore per core)
    store2, gate2, scale2, meter2 = build(db, free=1)
    store2.restore("smartscale", scale2)
    assert getattr(scale2, GATE_ATTR).get("credits") == 5
    dup = gate2.redeem("cs_test_p", "smartscale", _verify=_paid_verify(amount=5 * price))
    assert dup["duplicate"] is True              # idempotency survives restart too


# --- PG4 under the event-loop-thread reality (prod 2026-07-12 regression) ---- #
def test_pg4_sync_core_meters_even_on_running_loop(tmp_path):
    """This MCP SDK runs sync tools ON the loop thread: asyncio.run is
    impossible there, so metering must be scheduled, not dropped (the
    'metering(sync-ctx)' gate error seen in prod)."""
    store, gate, scale, meter = build(tmp_path / "s.db", free=5)

    async def scenario():
        scale.process(dict(CALL))            # sync call ON the running loop
        for _ in range(10):                  # let the scheduled task drain
            await asyncio.sleep(0)
        return getattr(scale, GATE_ATTR)["meter_id"]

    mid = asyncio.get_event_loop_policy().new_event_loop() \
        .run_until_complete(scenario())
    assert mid, "metering was dropped in running-loop context"
    assert "smartscale" not in gate.status()["errors"]
    summary = call(meter, {"action": "usage_summary", "meter_id": mid})
    assert summary["data"]["event_count"] == 1


# --- PG21b: agent-specific seat upsell in the 402 envelope (2026-07-19) ----- #
def _build_named(db, name, free=1):
    """Attach a fresh SmartScaleCore under an arbitrary gate name — the
    gate prices/upsells purely off the registered name (see
    test_payment_gate_a2a.py's 'priced as smartscale' idiom), so this lets
    us exercise SEAT_PLANS entries without loading each agent's real core."""
    store = StateStore(db)
    scale = SMARTSCALE.SmartScaleCore()
    meter = METERING.build()
    store.attach(name, scale)
    store.attach("metering", meter)
    gate = PaymentGate(store, meter, free_calls_per_day=free)
    gate.attach(name, scale)
    return store, gate, scale, meter


def test_pg21b_seat_option_present_for_covered_agent(tmp_path):
    _, _, scale, _ = _build_named(tmp_path / "s.db", "regulatory-radar", free=1)
    assert call(scale, dict(CALL))["status"] == "ok"       # exhaust free tier
    refused = call(scale, dict(CALL))
    assert refused["error_type"] == "payment_required"
    seat = refused["payment"]["seat_option"]
    expected = SEAT_PLANS["regulatory-radar"]
    assert seat["plan_id"] == expected["plan_id"] == "compliance-seat"
    assert seat["price_monthly_minor"] == expected["price_monthly_minor"] == 14900
    assert seat["included_calls_per_month"] == 1000
    assert seat["checkout_url"] == "https://mcp.viridisconservation.com/seats"
    assert "compliance-seat" in seat["note"]
    assert "1,000" in seat["note"]
    assert "regulatory-radar" in seat["note"] and "disclosure-compiler" in seat["note"]


def test_pg21b_seat_option_absent_for_uncovered_agent(db):
    """smartscale has no covering seat plan in the catalog — the field
    must be absent entirely, not present-with-nulls."""
    _, _, scale, _ = build(db, free=1)
    call(scale, dict(CALL))                                # exhaust free tier
    refused = call(scale, dict(CALL))
    assert refused["error_type"] == "payment_required"
    assert "seat_option" not in refused["payment"]


def test_pg21b_absent_on_subscription_overage():
    """Never on the subscription_overage path — the caller already has a
    seat; upselling them into a second one makes no sense (same exclusion
    PG21's generic subscription_hint already applies)."""
    gate = PaymentGate.__new__(PaymentGate)   # bind-only, no I/O needed —
    gate.free_calls = 1                       # subscription_overage=True never
                                               # reads self beyond this
    envelope = PaymentGate._payment_required(
        gate, "regulatory-radar", "2026-07-19", 0,
        subscription_overage=True)
    assert "seat_option" not in envelope["payment"]


def test_pg21b_existing_envelope_fields_unchanged(db):
    """Additive only: PG2/PG14/PG19 fields keep their exact shape and
    values alongside the new field."""
    _, _, scale, _ = build(db, free=1)
    call(scale, dict(CALL))
    refused = call(scale, dict(CALL))
    assert refused["status"] == "error"
    assert refused["error_type"] == "payment_required"
    assert refused["http_equivalent"] == 402
    assert refused["amount_minor"] == PRICE_MINOR["smartscale"]
    assert refused["billing_path"] == "per_call_freemium"
    assert refused["free_tier_resets"] == "00:00 UTC"
    assert "stripe_checkout" in str(refused["payment"]["human"])
    assert "x402" in str(refused["payment"]["a2a"])


# --- PG23: caller-scoped, durable request idempotency ---------------------- #
def test_pg23_sync_replay_returns_original_without_second_charge(db):
    _, _, scale, _ = build(db, free=1)
    payload = {**CALL, "request_id": "smartscale-order-001"}
    first = call(scale, payload)
    second = call(scale, payload)

    assert second == first
    gate = getattr(scale, GATE_ATTR)
    assert gate["used"] == 1
    assert len(gate["idempotent_requests"]) == 1
    assert next(iter(gate["idempotent_requests"].values()))["state"] == \
        "completed"


def test_pg23_same_request_id_with_different_input_fails_closed(db):
    _, _, scale, _ = build(db, free=2)
    first = call(scale, {**CALL, "request_id": "same-key"})
    assert first["status"] == "ok"

    changed = {
        **CALL,
        "request_id": "same-key",
        "credit_card_pixel_width": 428.0,
    }
    conflict = call(scale, changed)
    assert conflict["status"] == "error"
    assert conflict["error_type"] == "idempotency_conflict"
    assert getattr(scale, GATE_ATTR)["used"] == 1


def test_pg23_invalid_request_id_never_consumes_quota(db):
    _, _, scale, _ = build(db, free=1)
    bad = call(scale, {**CALL, "request_id": "x" * 129})
    assert bad["status"] == "error"
    assert bad["error_type"] == "invalid_request_id"
    assert getattr(scale, GATE_ATTR)["used"] == 0


def test_pg23_replay_survives_restart(tmp_path):
    db = tmp_path / "s.db"
    _, _, scale, _ = build(db, free=1)
    payload = {**CALL, "request_id": "restart-safe"}
    first = call(scale, payload)

    store2 = StateStore(db)
    scale2 = SMARTSCALE.SmartScaleCore()
    meter2 = METERING.build()
    store2.restore("smartscale", scale2)
    store2.restore("metering", meter2)
    store2.attach("smartscale", scale2)
    store2.attach("metering", meter2)
    gate2 = PaymentGate(store2, meter2, free_calls_per_day=1)
    gate2.attach("smartscale", scale2)

    second = call(scale2, payload)
    assert second == first
    assert getattr(scale2, GATE_ATTR)["used"] == 1


def test_pg23_async_replay_executes_inner_once(tmp_path):
    class AsyncCore:
        KNOWN_ACTIONS = frozenset({"write"})
        READ_ACTIONS = frozenset()

        def __init__(self):
            self.executions = 0

        async def process(self, payload):
            self.executions += 1
            return {"status": "ok", "payload": payload,
                    "executions": self.executions}

    store = StateStore(tmp_path / "async.db")
    core = AsyncCore()
    meter = METERING.build()
    store.attach("async-demo", core)
    store.attach("metering", meter)
    gate = PaymentGate(store, meter, free_calls_per_day=1)
    gate.attach("async-demo", core)

    async def scenario():
        payload = {"action": "write", "value": 7, "request_id": "async-1"}
        first = await core.process(payload)
        second = await core.process(payload)
        return first, second

    first, second = asyncio.get_event_loop_policy().new_event_loop() \
        .run_until_complete(scenario())
    assert second == first
    assert core.executions == 1
    assert getattr(core, GATE_ATTR)["used"] == 1


def test_pg23_interrupted_execution_is_never_billed_twice(tmp_path):
    class FailingCore:
        KNOWN_ACTIONS = frozenset({"write"})
        READ_ACTIONS = frozenset()

        def __init__(self):
            self.executions = 0

        def process(self, payload):
            self.executions += 1
            raise RuntimeError("simulated interruption")

    store = StateStore(tmp_path / "interrupted.db")
    core = FailingCore()
    meter = METERING.build()
    store.attach("interrupted-demo", core)
    store.attach("metering", meter)
    gate = PaymentGate(store, meter, free_calls_per_day=1)
    gate.attach("interrupted-demo", core)
    payload = {"action": "write", "value": 7, "request_id": "interrupt-1"}

    with pytest.raises(RuntimeError, match="simulated interruption"):
        core.process(payload)
    retry = core.process(payload)

    assert retry["status"] == "error"
    assert retry["error_type"] == "idempotency_incomplete"
    assert core.executions == 1
    assert getattr(core, GATE_ATTR)["used"] == 1


def test_pg23_payment_refusal_releases_request_id_for_paid_retry(db):
    _, _, scale, _ = build(db, free=0)
    payload = {**CALL, "request_id": "pay-after-402"}

    refused = call(scale, payload)
    assert refused["error_type"] == "payment_required"
    gate = getattr(scale, GATE_ATTR)
    assert gate["idempotent_requests"] == {}

    gate["credits"] = 1
    paid = call(scale, payload)
    assert paid["status"] == "ok"
    assert gate["credits"] == 0
    assert len(gate["idempotent_requests"]) == 1
