"""Invariant tests for agent-metering-agent (M1-M8) + fleet contract."""
import pytest
from src.core import build, _GENESIS


@pytest.fixture
def core():
    return build()


async def _meter(core, **over):
    payload = {"action": "create_meter", "provider": "prov-1", "consumer": "cons-1",
               "unit": "call", "price_minor_per_unit": 2.5, **over}
    r = await core.process(payload)
    assert r["status"] == "ok"
    return r["data"]["meter_id"]


async def _use(core, mid, eid, qty=1.0, outcome="ok"):
    return await core.process({"action": "record_usage", "meter_id": mid,
                               "event_id": eid, "quantity": qty, "outcome": outcome})


# --- M1 append-only ------------------------------------------------------ #
async def test_M1_append_only_monotone(core):
    mid = await _meter(core)
    counts = []
    for i in range(3):
        await _use(core, mid, f"e{i}")
        s = await core.process({"action": "usage_summary", "meter_id": mid})
        counts.append(s["data"]["event_count"])
    assert counts == [1, 2, 3]
    d = core.describe()
    for forbidden in ("edit", "delete", "remove"):
        assert not any(forbidden in c for c in d["capabilities"])


# --- M2 quantity/unit validation ----------------------------------------- #
async def test_M2_positive_quantity_required(core):
    mid = await _meter(core)
    for bad in (0, -1, float("nan"), float("inf"), "three", None, True):
        r = await _use(core, mid, "bad", qty=bad)
        assert r["status"] == "error", f"quantity={bad!r} accepted"
        assert r["error_type"] == "ValidationError"


async def test_M2_unit_fixed_per_meter(core):
    mid = await _meter(core, unit="token")
    r = await core.process({"action": "record_usage", "meter_id": mid,
                            "event_id": "e1", "quantity": 5, "unit": "call"})
    assert r["status"] == "error" and r["field"] == "unit"


# --- M3 deterministic billing -------------------------------------------- #
async def test_M3_deterministic_ceil_billing(core):
    mid = await _meter(core, price_minor_per_unit=2.5)
    await _use(core, mid, "e1", qty=3)  # 7.5 -> ceil 8
    s = await core.process({"action": "usage_summary", "meter_id": mid})
    assert s["data"]["accrued_minor"] == 8
    inv = await core.process({"action": "close_period", "meter_id": mid})
    assert inv["data"]["amount_minor"] == 8
    assert isinstance(inv["data"]["amount_minor"], int)


# --- M4 idempotency on event_id ------------------------------------------ #
async def test_M4_event_id_idempotent(core):
    mid = await _meter(core)
    r1 = await _use(core, mid, "dup", qty=2)
    r2 = await _use(core, mid, "dup", qty=999)  # replay with different qty
    assert r2["status"] == "ok" and r2["data"]["duplicate"] is True
    assert r2["data"]["quantity"] == 2  # original preserved
    s = await core.process({"action": "usage_summary", "meter_id": mid})
    assert s["data"]["event_count"] == 1 and s["data"]["total_quantity"] == 2


# --- M5 tamper-evident chain ---------------------------------------------- #
async def test_M5_hash_chain_valid_and_tamper_detected(core):
    mid = await _meter(core)
    for i in range(3):
        await _use(core, mid, f"e{i}", qty=i + 1)
    v = await core.process({"action": "verify_chain", "meter_id": mid})
    assert v["data"]["valid"] is True
    core._meters[mid].events[1]["quantity"] = 1000.0  # tamper
    v2 = await core.process({"action": "verify_chain", "meter_id": mid})
    assert v2["data"]["valid"] is False and v2["data"]["broken_at_index"] == 1


async def test_M5_first_event_commits_to_genesis(core):
    mid = await _meter(core)
    r = await _use(core, mid, "e0")
    assert r["data"]["prev_hash"] == _GENESIS


# --- M6 SLA report pure --------------------------------------------------- #
async def test_M6_sla_report_pure_and_correct(core):
    mid = await _meter(core, sla_target=0.9)
    for i in range(8):
        await _use(core, mid, f"ok{i}")
    for i in range(2):
        await _use(core, mid, f"err{i}", outcome="error")
    r = await core.process({"action": "sla_report", "meter_id": mid})
    assert r["data"]["success_rate"] == pytest.approx(0.8)
    assert r["data"]["breach"] is True
    r2 = await core.process({"action": "sla_report", "meter_id": mid})
    assert r2["data"] == r["data"]  # pure: no state change
    s = await core.process({"action": "usage_summary", "meter_id": mid})
    assert s["data"]["event_count"] == 10


# --- M7 exactly-once close ------------------------------------------------ #
async def test_M7_close_period_exactly_once(core):
    mid = await _meter(core, price_minor_per_unit=100)
    await _use(core, mid, "e1", qty=1)
    inv1 = await core.process({"action": "close_period", "meter_id": mid})
    assert inv1["data"]["duplicate"] is False
    inv2 = await core.process({"action": "close_period", "meter_id": mid})  # no new events
    assert inv2["data"]["duplicate"] is True
    assert inv2["data"]["invoice_id"] == inv1["data"]["invoice_id"]
    await _use(core, mid, "e2", qty=2)  # next period
    inv3 = await core.process({"action": "close_period", "meter_id": mid})
    assert inv3["data"]["duplicate"] is False
    assert inv3["data"]["period_index"] == 1
    assert inv3["data"]["amount_minor"] == 200


async def test_M7_no_empty_first_invoice(core):
    mid = await _meter(core)
    r = await core.process({"action": "close_period", "meter_id": mid})
    assert r["status"] == "error"


# --- M8 unknown ids -------------------------------------------------------- #
async def test_M8_unknown_meter_error_envelope(core):
    for action in ("record_usage", "usage_summary", "sla_report",
                   "close_period", "verify_chain"):
        r = await core.process({"action": action, "meter_id": "nope",
                                "event_id": "x", "quantity": 1})
        assert r["status"] == "error" and r["field"] == "meter_id"
        for key in ("error_type", "field", "value", "constraint", "message", "timestamp"):
            assert key in r


# --- fleet contract -------------------------------------------------------- #
async def test_contract_never_raises_and_unknown_action(core):
    for payload in [{}, {"action": None}, {"action": "nope"}, "not-a-dict", 42]:
        r = await core.process(payload)
        assert isinstance(r, dict) and r["status"] == "error"


async def test_contract_describe_health_consistent(core):
    d = core.describe()
    h = await core.health()
    assert d["name"] == h["agent"]
    assert d["capabilities"] and d["a2a_role"] == "metering"
    assert set(h) >= {"status", "agent", "version", "timestamp", "checks"}
