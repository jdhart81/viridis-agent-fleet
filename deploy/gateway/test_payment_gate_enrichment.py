"""PG12 tests — the payment gate stamps server-derived caller classification
onto every metered event, and gate-created meters are write-protected.

Uses the real metering core + real StateStore + real smartscale core, the
same harness as test_payment_gate.py.
"""
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from payment_gate import PaymentGate, GATE_ATTR          # noqa: E402
from request_context import request_context               # noqa: E402
from state_store import StateStore                        # noqa: E402


def _load_pkg(agent_dir: str):
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

CALL = {"action": "measure_from_credit_card", "image_id": "img-1",
        "credit_card_pixel_width": 856.0,
        "objects": [{"label": "box", "pixel_width": 428.0,
                     "pixel_height": 214.0}]}

EXTERNAL_CTX = {"consumer_class": "external", "channel": "smithery-proxy",
                "caller": "ext:abcdef123456", "is_test": False}
INTERNAL_CTX = {"consumer_class": "internal", "channel": "internal",
                "caller": "internal:nightkeeper-selftest", "is_test": True}


@pytest.fixture
def rig(tmp_path):
    store = StateStore(str(tmp_path / "state.db"))
    scale = SMARTSCALE.SmartScaleCore()
    meter = METERING.build()
    store.attach("smartscale", scale)
    store.attach("metering", meter)
    gate = PaymentGate(store, meter, free_calls_per_day=5)
    gate.attach("smartscale", scale)
    return gate, scale, meter


def _drain(meter):
    """Let fire-and-forget metering tasks complete, then read all events."""
    async def _read():
        await asyncio.sleep(0)   # yield so create_task-scheduled coros run
        return await meter.process({"action": "list_events",
                                    "include_test": True, "limit": 500})
    return asyncio.run(_read())["data"]["events"]


def test_PG12_events_carry_transport_classification(rig):
    gate, scale, meter = rig
    with request_context(dict(EXTERNAL_CTX)):
        r = scale.process(dict(CALL))
        assert r["status"] == "ok"
    events = _drain(meter)
    assert len(events) == 1
    e = events[0]
    assert e["consumer_class"] == "external"
    assert e["channel"] == "smithery-proxy"
    assert e["caller"] == "ext:abcdef123456"
    assert e["is_test"] is False


def test_PG12_internal_selftest_is_flagged_and_excluded(rig):
    gate, scale, meter = rig
    with request_context(dict(INTERNAL_CTX)):
        scale.process(dict(CALL))
    with request_context(dict(EXTERNAL_CTX)):
        scale.process(dict(CALL))
    events = _drain(meter)
    assert len(events) == 2
    by_class = {e["consumer_class"]: e for e in events}
    assert by_class["internal"]["is_test"] is True
    assert by_class["internal"]["caller"] == "internal:nightkeeper-selftest"
    # Statistics views hide the self-test by default (G7)...
    stats = asyncio.run(meter.process({"action": "usage_timeseries"}))["data"]
    assert sum(b["events"] for b in stats["series"]) == 1
    assert stats["series"][0]["by_consumer_class"] == {"external": 1}
    # ...but billing counts both (G7 second clause).
    mid = events[0]["meter_id"]
    summary = asyncio.run(meter.process(
        {"action": "usage_summary", "meter_id": mid}))["data"]
    assert summary["event_count"] == 2


def test_PG12_absent_context_degrades_to_unknown(rig):
    gate, scale, meter = rig
    scale.process(dict(CALL))                    # no request context bound
    events = _drain(meter)
    assert events[0]["consumer_class"] == "unknown"
    assert events[0]["channel"] == "unknown"
    assert events[0]["caller"] is None


def test_PG12_gate_meters_are_gateway_origin_and_protected(rig):
    gate, scale, meter = rig
    with request_context(dict(EXTERNAL_CTX)):
        scale.process(dict(CALL))
    _drain(meter)
    listed = asyncio.run(meter.process({"action": "list_meters"}))["data"]
    assert listed["count"] == 1
    m = listed["meters"][0]
    assert m["origin"] == "gateway"
    # A public caller who learned the meter_id from list_meters cannot
    # inflate the billing ledger (G6).
    spoof = asyncio.run(meter.process({
        "action": "record_usage", "meter_id": m["meter_id"],
        "event_id": "spoof-1", "quantity": 500}))
    assert spoof["status"] == "error"
    summary = asyncio.run(meter.process(
        {"action": "usage_summary", "meter_id": m["meter_id"]}))["data"]
    assert summary["total_quantity"] == 1.0


def test_PG12_accrual_identity_with_and_without_context(rig):
    """G1 through the gate: classification never changes what is billed."""
    gate, scale, meter = rig
    with request_context(dict(EXTERNAL_CTX)):
        scale.process(dict(CALL))
    scale.process({**CALL, "image_id": "img-2"})
    _drain(meter)
    listed = asyncio.run(meter.process({"action": "list_meters"}))["data"]
    summary = asyncio.run(meter.process(
        {"action": "usage_summary",
         "meter_id": listed["meters"][0]["meter_id"]}))["data"]
    assert summary["event_count"] == 2
    assert summary["accrued_minor"] == summary["event_count"] * 50  # smartscale $0.50
