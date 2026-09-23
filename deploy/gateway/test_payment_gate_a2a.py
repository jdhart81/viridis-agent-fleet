#!/usr/bin/env python3
"""
Tests for the a2a escrow settlement rail (PG13-PG16, PG22) — one test per
invariant plus replay / persistence / concurrency checks, mirroring the
Stripe-path coverage in test_payment_gate.py. Uses the real smartscale
(SYNC core), real metering, real escrow core (E9 sync surface), and the
real StateStore.

The default custody=None fixture preserves the isolated legacy composition.
PG22 tests explicitly wire a custody-state funded registry to distinguish
real backing from the escrow core's bookkeeping-only fund transition.

Run:  pytest deploy/gateway/test_payment_gate_a2a.py -q
"""
import asyncio
import importlib.util
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from payment_gate import PaymentGate, GATE_ATTR, PRICE_MINOR   # noqa: E402
from state_store import StateStore                # noqa: E402


def _load_pkg(agent_dir: str):
    """Load an agent core as a real src package (adapter-faithful), and
    capture its module dict for StateStore.register_modules."""
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
    modules = {m: sys.modules[m] for m in list(sys.modules)
               if m == "src" or m.startswith("src.")}
    return mod, modules


SMARTSCALE, SMARTSCALE_MODULES = _load_pkg("smartscale-agent")
METERING, METERING_MODULES = _load_pkg("agent-metering-agent")
ESCROW, ESCROW_MODULES = _load_pkg("agent-escrow-agent")

PRICE = PRICE_MINOR["smartscale"]

CALL = {"action": "measure_from_credit_card", "image_id": "img-1",
        "credit_card_pixel_width": 856.0,
        "objects": [{"label": "box", "pixel_width": 428.0,
                     "pixel_height": 214.0}]}


def call(core, payload):
    result = core.process(payload)
    if asyncio.iscoroutine(result):
        return asyncio.get_event_loop_policy().new_event_loop() \
            .run_until_complete(result)
    return result


def build(db, free=0, with_escrow=True, custody=None,
          market_funding_verifier=None):
    store = StateStore(db)
    scale = SMARTSCALE.SmartScaleCore()
    meter = METERING.build()
    escrow = ESCROW.build() if with_escrow else None
    store.register_modules("smartscale", SMARTSCALE_MODULES)
    store.register_modules("metering", METERING_MODULES)
    store.attach("smartscale", scale)
    store.attach("metering", meter)
    if escrow is not None:
        store.register_modules("escrow", ESCROW_MODULES)
        store.restore("escrow", escrow)
    gate = PaymentGate(store, meter, free_calls_per_day=free,
                       escrow_core=escrow, custody=custody,
                       market_funding_verifier=market_funding_verifier)
    gate.attach("smartscale", scale)
    return store, gate, scale, meter, escrow


def custody_fixture(*cash_escrow_ids):
    return SimpleNamespace(state=SimpleNamespace(
        funded={eid: {"session_id": f"cs_{eid}"}
                for eid in cash_escrow_ids}))


def fund_escrow(escrow, amount=PRICE, payee="viridis:smartscale",
                currency="USD"):
    opened = escrow.process_sync({
        "action": "open", "payer": "agent:caller-1", "payee": payee,
        "amount_minor": amount, "currency": currency,
        "terms": "1 smartscale measurement"})
    eid = opened["data"]["escrow_id"]
    escrow.process_sync({"action": "fund", "escrow_id": eid,
                         "payment_ref": "test-funding"})
    return eid


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "state.db")


# --------------------------- PG13 -------------------------------------- #
def test_pg13_funded_escrow_grants_credits_and_serves_call(db):
    _, gate, scale, _, escrow = build(db, free=0)
    eid = fund_escrow(escrow, amount=PRICE)
    r = call(scale, dict(CALL, payment_ref=eid))
    assert r["status"] == "ok"                       # served, not refused
    g = getattr(scale, GATE_ATTR)
    assert g["consumed_escrows"][eid]["credits"] == 1
    assert g["credits"] == 0                          # 1 granted, 1 spent
    esc = escrow.process_sync({"action": "status", "escrow_id": eid})
    assert esc["data"]["state"] == "RELEASED"         # consumed via E6, not bypassed


def test_mh_verified_market_hold_runs_exact_call_without_early_release(db):
    """A Hub-verified Market escrow backs exactly one solve while remaining
    FUNDED for buyer acceptance/dispute semantics."""
    seen = []

    def verify(name, binding):
        seen.append((name, dict(binding)))
        return {"verified": binding["work_id"] == "work_external_123"}

    custody = custody_fixture()
    _, gate, scale, _, escrow = build(
        db, free=1, custody=custody,
        market_funding_verifier=verify)
    eid = fund_escrow(escrow, amount=PRICE)
    custody.state.funded[eid] = {
        "session_id": "cs_live_market",
        "amount_total": PRICE,
        "livemode": True,
    }
    binding = {
        "work_id": "work_external_123",
        "escrow_id": eid,
        "funding_event_id": "funding_" + "a" * 64,
        "event_sha256": "b" * 64,
        "amount_minor": PRICE,
        "currency": "USD",
        "payee": "viridis:smartscale",
    }
    reserved = gate.reserve_market_payment(
        "smartscale", binding, dict(CALL))
    assert reserved["status"] == "ok"
    assert reserved["money_movement"] == "none"

    payload = dict(
        CALL, request_id="market-work-exact-call",
        _market_payment_token=reserved["token"])
    first = call(scale, payload)
    assert first["status"] == "ok"
    replay = call(scale, payload)
    assert replay == first
    state = getattr(scale, GATE_ATTR)
    assert state["market_holds"]["work_external_123"]["state"] == "COMPLETED"
    assert state["used_by_caller"] == {}
    assert state["credits"] == 0
    assert escrow.process_sync(
        {"action": "status", "escrow_id": eid})["data"]["state"] == "FUNDED"
    assert len(seen) == 2  # reserve and immediate pre-execution recheck


def test_mh_wrong_payload_and_reused_escrow_fail_before_core(db):
    custody = custody_fixture()
    _, gate, scale, _, escrow = build(
        db, free=0, custody=custody,
        market_funding_verifier=lambda _name, _binding: {"verified": True})
    eid = fund_escrow(escrow, amount=PRICE)
    custody.state.funded[eid] = {"session_id": "cs_live_market"}
    binding = {
        "work_id": "work_external_456",
        "escrow_id": eid,
        "funding_event_id": "funding_" + "c" * 64,
        "event_sha256": "d" * 64,
        "amount_minor": PRICE,
        "currency": "USD",
        "payee": "viridis:smartscale",
    }
    reserved = gate.reserve_market_payment(
        "smartscale", binding, dict(CALL))
    wrong = dict(
        CALL, image_id="different", request_id="wrong-market-payload",
        _market_payment_token=reserved["token"])
    refused = call(scale, wrong)
    assert refused["error_type"] == "payment_required"
    assert refused["a2a"]["refusal_reason"] == "market_payload_mismatch"
    assert getattr(scale, GATE_ATTR)["market_holds"][
        "work_external_456"]["state"] == "RESERVED"

    conflict = gate.reserve_market_payment(
        "smartscale",
        {**binding, "work_id": "work_external_other"},
        dict(CALL))
    assert conflict["status"] == "error"
    assert conflict["reason"] == "escrow_already_bound"
    assert escrow.process_sync(
        {"action": "status", "escrow_id": eid})["data"]["state"] == "FUNDED"


def test_pg13_credits_are_floor_of_amount_over_price(db):
    """A 3.5x-funded escrow grants floor(3.5) = 3 credits: the first call is
    served and two prepaid credits remain (PG9/PG11 path)."""
    _, _, scale, _, escrow = build(db, free=0)
    eid = fund_escrow(escrow, amount=PRICE * 3 + PRICE // 2)
    assert call(scale, dict(CALL, payment_ref=eid))["status"] == "ok"
    g = getattr(scale, GATE_ATTR)
    assert g["consumed_escrows"][eid]["credits"] == 3
    assert g["credits"] == 2
    assert call(scale, dict(CALL))["status"] == "ok"  # rides remaining credit
    assert call(scale, dict(CALL))["status"] == "ok"
    assert call(scale, dict(CALL))["error_type"] == "payment_required"


def test_pg13_metered_ok_exactly_once_per_served_call(db):
    _, _, scale, meter, escrow = build(db, free=0)
    eid = fund_escrow(escrow, amount=PRICE)
    call(scale, dict(CALL, payment_ref=eid))
    mid = getattr(scale, GATE_ATTR)["meter_id"]
    summary = call(meter, {"action": "usage_summary", "meter_id": mid})
    assert summary["data"]["event_count"] == 1


def test_pg13_async_core_variant(db):
    """The a2a rail works identically when the gated core is async."""
    class AsyncEcho:
        KNOWN_ACTIONS = frozenset({"echo"})
        READ_ACTIONS = frozenset()

        async def process(self, input_data):
            return {"status": "ok", "echo": dict(input_data)}
    store = StateStore(db)
    meter = METERING.build()
    escrow = ESCROW.build()
    store.attach("metering", meter)
    gate = PaymentGate(store, meter, free_calls_per_day=0,
                       escrow_core=escrow)
    core = AsyncEcho()
    gate.attach("smartscale", core)      # priced as smartscale
    eid = fund_escrow(escrow, amount=PRICE)
    r = call(core, {"action": "echo", "payment_ref": eid})
    assert r["status"] == "ok"
    assert "payment_ref" not in r["echo"]             # PG16: stripped


# --------------------------- PG14 -------------------------------------- #
@pytest.mark.parametrize("setup,expected_reason", [
    ("unknown", "unknown_escrow"),
    ("unfunded", "unfunded"),
    ("refunded", "refunded"),
    ("underfunded", "underfunded"),
    ("wrong_payee", "wrong_payee"),
    ("currency", "currency_mismatch"),
])
def test_pg14_bad_escrows_are_refused_with_reason(db, setup, expected_reason):
    _, _, scale, _, escrow = build(db, free=0)
    if setup == "unknown":
        ref = "esc_does_not_exist"
    elif setup == "unfunded":
        ref = escrow.process_sync({
            "action": "open", "payer": "a", "payee": "viridis:smartscale",
            "amount_minor": PRICE})["data"]["escrow_id"]
    elif setup == "refunded":
        ref = fund_escrow(escrow)
        escrow.process_sync({"action": "refund", "escrow_id": ref})
    elif setup == "underfunded":
        ref = fund_escrow(escrow, amount=PRICE - 1)
    elif setup == "wrong_payee":
        ref = fund_escrow(escrow, payee="viridis:protogen")
    elif setup == "currency":
        ref = fund_escrow(escrow, currency="EUR")
    r = call(scale, dict(CALL, payment_ref=ref))
    assert r["status"] == "error"
    assert r["error_type"] == "payment_required"      # never a free pass
    assert r["a2a"]["refusal_reason"] == expected_reason
    assert getattr(scale, GATE_ATTR)["credits"] == 0  # never a partial grant


def test_pg14_wrong_payee_escrow_is_not_released(db):
    """A refusal must leave the escrow untouched for its real payee."""
    _, _, scale, _, escrow = build(db, free=0)
    ref = fund_escrow(escrow, payee="viridis:protogen")
    call(scale, dict(CALL, payment_ref=ref))
    esc = escrow.process_sync({"action": "status", "escrow_id": ref})
    assert esc["data"]["state"] == "FUNDED"


# --------------------------- PG15 -------------------------------------- #
def test_pg15_no_escrow_rail_refuses_never_crashes(db):
    _, gate, scale, _, _ = build(db, free=0, with_escrow=False)
    r = call(scale, dict(CALL, payment_ref="esc_000001"))
    assert r["error_type"] == "payment_required"
    assert r["a2a"]["refusal_reason"] == "a2a_rail_unavailable"
    assert "a2a_rail_unavailable" in str(
        gate.status()["a2a_escrow"]["errors"])


def test_pg15_escrow_core_raising_refuses_never_grants(db):
    class Explosive:
        def process_sync(self, _):
            raise RuntimeError("escrow agent unreachable")
    store = StateStore(db)
    meter = METERING.build()
    store.attach("metering", meter)
    gate = PaymentGate(store, meter, free_calls_per_day=0,
                       escrow_core=Explosive())
    scale = SMARTSCALE.SmartScaleCore()
    store.register_modules("smartscale", SMARTSCALE_MODULES)
    store.attach("smartscale", scale)
    gate.attach("smartscale", scale)
    r = call(scale, dict(CALL, payment_ref="esc_000001"))
    assert r["error_type"] == "payment_required"
    assert r["a2a"]["refusal_reason"] == "escrow_verify_failed"
    assert getattr(scale, GATE_ATTR)["credits"] == 0


def test_pg15_persistence_failure_reverts_grant_fail_closed(db):
    _, gate, scale, _, escrow = build(db, free=0)
    eid = fund_escrow(escrow, amount=PRICE * 2)
    gate.store.save_many = lambda cores: False        # durable commit fails
    r = call(scale, dict(CALL, payment_ref=eid))
    assert r["error_type"] == "payment_required"
    assert r["a2a"]["refusal_reason"] == "settlement_not_durable"
    g = getattr(scale, GATE_ATTR)
    assert g["credits"] == 0                          # grant reverted
    assert eid not in g["consumed_escrows"]


def test_pg15_metering_failure_never_blocks_a_paid_call(db):
    """PG8's side of the mirror: metering down, escrow-paid call still serves."""
    _, gate, scale, _, escrow = build(db, free=0)
    async def boom(_):
        raise RuntimeError("metering down")
    gate.metering.process = boom
    eid = fund_escrow(escrow, amount=PRICE)
    assert call(scale, dict(CALL, payment_ref=eid))["status"] == "ok"


# --------------------------- PG16 -------------------------------------- #
def test_pg16_replay_never_double_credits(db):
    _, _, scale, _, escrow = build(db, free=0)
    eid = fund_escrow(escrow, amount=PRICE)           # exactly 1 credit
    assert call(scale, dict(CALL, payment_ref=eid))["status"] == "ok"
    replay = call(scale, dict(CALL, payment_ref=eid))
    assert replay["error_type"] == "payment_required"  # no second grant
    g = getattr(scale, GATE_ATTR)
    assert g["consumed_escrows"][eid]["credits"] == 1  # original grant stands
    assert g["credits"] == 0


def test_pg16_consumption_survives_restart(db):
    """consumed_escrows persists (StateStore) — a replay after restart never
    double-credits even though the escrow core also restarts."""
    _, _, scale, _, escrow = build(db, free=0)
    eid = fund_escrow(escrow, amount=PRICE)
    assert call(scale, dict(CALL, payment_ref=eid))["status"] == "ok"

    # ---- restart: fresh cores, fresh store, same db ----
    store2 = StateStore(db)
    scale2 = SMARTSCALE.SmartScaleCore()
    meter2 = METERING.build()
    escrow2 = ESCROW.build()
    store2.register_modules("smartscale", SMARTSCALE_MODULES)
    store2.register_modules("escrow", ESCROW_MODULES)
    store2.restore("smartscale", scale2)
    store2.restore("escrow", escrow2)
    store2.attach("smartscale", scale2)
    store2.attach("metering", meter2)
    gate2 = PaymentGate(store2, meter2, free_calls_per_day=0,
                        escrow_core=escrow2)
    gate2.attach("smartscale", scale2)

    esc = escrow2.process_sync({"action": "status", "escrow_id": eid})
    assert esc["data"]["state"] == "RELEASED"          # release persisted
    replay = call(scale2, dict(CALL, payment_ref=eid))
    assert replay["error_type"] == "payment_required"
    assert getattr(scale2, GATE_ATTR)["credits"] == 0


def test_pg16_payment_ref_stripped_before_core(db):
    class RecordingCore:
        KNOWN_ACTIONS = frozenset({"run"})
        READ_ACTIONS = frozenset()

        def __init__(self):
            self.seen = []
        def process(self, input_data):
            self.seen.append(dict(input_data))
            return {"status": "ok"}
    store = StateStore(db)
    meter = METERING.build()
    escrow = ESCROW.build()
    store.attach("metering", meter)
    gate = PaymentGate(store, meter, free_calls_per_day=0,
                       escrow_core=escrow)
    core = RecordingCore()
    gate.attach("smartscale", core)
    eid = fund_escrow(escrow, amount=PRICE)
    call(core, {"action": "run", "payment_ref": eid})
    assert all("payment_ref" not in seen for seen in core.seen)


def test_pg16_concurrent_same_ref_consumes_exactly_once(db):
    """Two threads race one single-credit escrow: exactly one call serves.

    Metering is stubbed to an async no-op here: this test isolates consume
    idempotency. (_meter's asyncio.Lock is not safe under cross-thread
    event-loop contention — a pre-existing PG8-degradation hazard shared
    with the Stripe path, out of scope for the a2a rail.)"""
    _, gate, scale, _, escrow = build(db, free=0)
    async def _noop_meter(*a, **k):
        return None
    gate._meter = _noop_meter
    eid = fund_escrow(escrow, amount=PRICE)
    results = []
    def worker():
        results.append(call(scale, dict(CALL, payment_ref=eid)))
    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok = [r for r in results if r.get("status") == "ok"]
    refused = [r for r in results if r.get("error_type") == "payment_required"]
    assert len(ok) == 1 and len(refused) == 1
    assert getattr(scale, GATE_ATTR)["consumed_escrows"][eid]["credits"] == 1


# --------------------------- PG22 -------------------------------------- #
def test_pg22_cash_funded_escrow_grants_credit(db):
    custody = custody_fixture()
    _, gate, scale, _, escrow = build(db, free=0, custody=custody)
    eid = fund_escrow(escrow, amount=PRICE)
    custody.state.funded[eid] = {"session_id": "cs_paid_cash"}

    assert call(scale, dict(CALL, payment_ref=eid))["status"] == "ok"
    grant = getattr(scale, GATE_ATTR)["consumed_escrows"][eid]
    assert grant["cash_funded"] is True
    conversion = gate.status()["conversion"]["per_agent"]["smartscale"]
    assert conversion["escrows_consumed_total"] == 1
    assert conversion["escrows_consumed_cash_total"] == 1
    assert conversion["escrows_consumed_internal_total"] == 0


def test_pg22_internal_fund_refused_with_cash_and_x402_teaching(db):
    custody = custody_fixture()
    _, gate, scale, _, escrow = build(db, free=0, custody=custody)
    eid = fund_escrow(escrow, amount=PRICE)

    r = call(scale, dict(CALL, payment_ref=eid))
    assert r["error_type"] == "payment_required"
    assert r["a2a"]["refusal_reason"] == "not_cash_funded"
    teaching = r["a2a"]["how_to_pay"]
    assert teaching["stripe_cash_escrow"]["steps"] == [
        "call escrow_checkout(escrow_id)",
        "pay the returned Stripe Checkout URL",
        "call confirm_escrow_funding(escrow_id, session_id)",
        "retry the same payment_ref",
    ]
    assert teaching["x402_usdc"]["network"] == "Base mainnet"
    assert "X-PAYMENT" in teaching["x402_usdc"]["mcp_fallback"]
    assert gate.status()["a2a_escrow"]["cash_backing_enforced"] is True
    assert escrow.process_sync({"action": "status", "escrow_id": eid})[
        "data"]["state"] == "FUNDED"


def test_pg22_not_cash_refusal_keeps_seat_option(db):
    store = StateStore(db)
    meter = METERING.build()
    escrow = ESCROW.build()
    custody = custody_fixture()
    scale = SMARTSCALE.SmartScaleCore()
    store.attach("metering", meter)
    gate = PaymentGate(store, meter, free_calls_per_day=0,
                       escrow_core=escrow, custody=custody)
    gate.attach("regulatory-radar", scale)
    eid = fund_escrow(escrow, amount=PRICE_MINOR["regulatory-radar"],
                      payee="viridis:regulatory-radar")

    r = call(scale, dict(CALL, payment_ref=eid))
    assert r["a2a"]["refusal_reason"] == "not_cash_funded"
    assert r["payment"]["seat_option"]["plan_id"] == "compliance-seat"


def test_pg22_custody_none_preserves_legacy_path(db):
    _, _, scale, _, escrow = build(db, free=0, custody=None)
    eid = fund_escrow(escrow, amount=PRICE)
    assert call(scale, dict(CALL, payment_ref=eid))["status"] == "ok"
    assert getattr(scale, GATE_ATTR)["consumed_escrows"][eid][
        "cash_funded"] is False


def test_pg22_preexisting_consumed_grant_replay_is_not_clawed_back(db):
    custody = custody_fixture()
    _, _, scale, _, escrow = build(db, free=0, custody=custody)
    eid = fund_escrow(escrow, amount=PRICE)
    grant = {"credits": 1, "amount_minor": PRICE,
             "consumed_at": "2026-07-18T00:00:00Z"}
    getattr(scale, GATE_ATTR)["consumed_escrows"][eid] = dict(grant)

    replay = call(scale, dict(CALL, payment_ref=eid))
    assert replay["error_type"] == "payment_required"
    assert "a2a" not in replay
    assert getattr(scale, GATE_ATTR)["consumed_escrows"][eid] == grant


# ------------------- reporting stays honest ---------------------------- #
def test_status_reports_escrow_settlement_as_non_cash(db):
    _, gate, scale, _, escrow = build(db, free=0)
    eid = fund_escrow(escrow, amount=PRICE * 2)
    call(scale, dict(CALL, payment_ref=eid))
    s = gate.status()["a2a_escrow"]
    assert s["enabled"] is True
    assert "not cash" in s["note"]
    assert s["consumed"]["smartscale"]["escrows"] == 1
    assert s["consumed"]["smartscale"]["cash_escrows"] == 0
    assert s["consumed"]["smartscale"]["internal_escrows"] == 1
    assert s["consumed"]["smartscale"]["credits_granted"] == 2
    assert s["consumed"]["smartscale"]["amount_minor"] == PRICE * 2


def test_free_tier_call_with_payment_ref_is_not_consumed(db):
    """Inside the free tier the escrow must NOT be touched — never take
    payment for a free call (payment_ref still stripped)."""
    _, _, scale, _, escrow = build(db, free=2)
    eid = fund_escrow(escrow, amount=PRICE)
    assert call(scale, dict(CALL, payment_ref=eid))["status"] == "ok"
    esc = escrow.process_sync({"action": "status", "escrow_id": eid})
    assert esc["data"]["state"] == "FUNDED"           # untouched
    assert getattr(scale, GATE_ATTR)["credits"] == 0
