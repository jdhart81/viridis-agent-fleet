#!/usr/bin/env python3
"""
Tests for PG20 — 402-conversion telemetry. The gate counts every refusal
per agent per UTC day plus the DISTINCT caller identities refused, bounded
against fingerprint rotation, surfaced additively in status(), reset at
rollover, and persisted with the ordinary gate snapshot.

Uses the real smartscale + metering cores and request_context, the same
harness as test_payment_gate_pg18.py.

Run:  pytest deploy/gateway/test_payment_gate_pg20.py -q
"""
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from payment_gate import (PaymentGate, GATE_ATTR,          # noqa: E402
                          CALLER_TABLE_MAX)
from request_context import request_context                # noqa: E402
from state_store import StateStore                         # noqa: E402


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


def call(core, caller=None):
    ctx = None
    if caller is not None:
        ctx = {"consumer_class": "external", "channel": "script",
               "caller": caller, "is_test": False}
    with request_context(ctx):
        result = core.process(dict(CALL))
    if asyncio.iscoroutine(result):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(result)
        finally:
            loop.close()
    return result


def build(db, free=1):
    store = StateStore(db)
    scale = SMARTSCALE.SmartScaleCore()
    meter = METERING.build()
    store.attach("smartscale", scale)
    store.attach("metering", meter)
    gate = PaymentGate(store, meter, free_calls_per_day=free)
    gate.attach("smartscale", scale)
    return store, gate, scale


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "state.db")


def conv(gate):
    return gate.status()["conversion"]["per_agent"]["smartscale"]


def test_pg20_refusals_and_distinct_callers_counted(db):
    """Two refusals from one caller = 2 refusals, 1 distinct caller."""
    _, gate, scale = build(db, free=1)
    assert call(scale, "ext:aaa111")["status"] == "ok"       # free call
    assert call(scale, "ext:aaa111")["error_type"] == "payment_required"
    assert call(scale, "ext:aaa111")["error_type"] == "payment_required"
    c = conv(gate)
    assert c["refusals_today"] == 2
    assert c["refused_callers_today"] == 1


def test_pg20_distinct_callers_across_identities(db):
    """Each PG18 identity that hits a 402 is counted once."""
    _, gate, scale = build(db, free=1)
    for who in ("ext:aaa111", "ext:bbb222", "ext:ccc333"):
        assert call(scale, who)["status"] == "ok"
        assert call(scale, who)["error_type"] == "payment_required"
    c = conv(gate)
    assert c["refusals_today"] == 3
    assert c["refused_callers_today"] == 3


def test_pg20_ok_calls_never_counted(db):
    _, gate, scale = build(db, free=2)
    assert call(scale, "ext:aaa111")["status"] == "ok"
    c = conv(gate)
    assert c["refusals_today"] == 0
    assert c["refused_callers_today"] == 0


def test_pg20_rollover_resets_daily_counters(db):
    """PG7: a new UTC day starts the funnel top at zero (credits and the
    cumulative denominators are untouched)."""
    _, gate, scale = build(db, free=1)
    call(scale, "ext:aaa111")
    assert call(scale, "ext:aaa111")["error_type"] == "payment_required"
    g = getattr(scale, GATE_ATTR)
    g["day"] = "2000-01-01"                       # force rollover on next call
    assert call(scale, "ext:aaa111")["status"] == "ok"   # fresh free tier
    c = conv(gate)
    assert c["refusals_today"] == 0
    assert c["refused_callers_today"] == 0


def test_pg20_rotation_bounded_overflow_bucket(db):
    """Rotating fingerprints cannot grow the refused-caller table past the
    PG18 bound: extras aggregate into one explicit overflow key."""
    _, gate, scale = build(db, free=1)
    g = getattr(scale, GATE_ATTR)
    g["refused_by_caller"] = {f"ext:{i:012x}": 1
                              for i in range(CALLER_TABLE_MAX)}
    call(scale, "ext:fresh-rotator")                    # free call
    assert call(scale, "ext:fresh-rotator")["error_type"] \
        == "payment_required"                           # refusal -> overflow
    assert len(g["refused_by_caller"]) == CALLER_TABLE_MAX + 1
    assert g["refused_by_caller"]["overflow:anon-rotation"] == 1


def test_pg20_status_additive_and_denominators_consistent(db):
    """The conversion section is additive (existing keys intact) and its
    cumulative denominators equal the PG13/PG10 sections' own counts."""
    _, gate, scale = build(db, free=1)
    call(scale, "ext:aaa111")
    call(scale, "ext:aaa111")
    s = gate.status()
    for key in ("gated_agents", "free_calls_per_day", "free_tier_policy",
                "prices_minor", "credits", "subscription_entitlements",
                "a2a_escrow", "errors"):
        assert key in s                                  # pre-PG20 shape intact
    c = s["conversion"]["per_agent"]["smartscale"]
    assert c["escrows_consumed_total"] == \
        s["a2a_escrow"]["consumed"]["smartscale"]["escrows"]
    g = getattr(scale, GATE_ATTR)
    assert c["sessions_redeemed_total"] == len(g.get("redeemed_sessions", {}))


def test_pg20_counters_persist_across_restore(db):
    """PG5: refusal telemetry survives a restart via the ordinary gate
    snapshot — the daily funnel is not amnesiac."""
    store, gate, scale = build(db, free=1)
    call(scale, "ext:aaa111")
    assert call(scale, "ext:aaa111")["error_type"] == "payment_required"

    store2 = StateStore(db)
    scale2 = SMARTSCALE.SmartScaleCore()
    meter2 = METERING.build()
    store2.restore("smartscale", scale2)
    store2.attach("smartscale", scale2)
    store2.attach("metering", meter2)
    gate2 = PaymentGate(store2, meter2, free_calls_per_day=1)
    gate2.attach("smartscale", scale2)
    c = gate2.status()["conversion"]["per_agent"]["smartscale"]
    assert c["refusals_today"] == 1
    assert c["refused_callers_today"] == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
