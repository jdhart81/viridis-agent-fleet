#!/usr/bin/env python3
"""
Tests for PG18 — per-caller free tiers. Uses the real smartscale + metering
cores and the request_context contextmanager to simulate transport-derived
caller identities (never payload-derived, PG12).

Run:  pytest deploy/gateway/test_payment_gate_pg18.py -q
"""
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from payment_gate import PaymentGate, GATE_ATTR, ANON_POOL_MULTIPLIER  # noqa: E402
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


def call(core, payload, caller=None):
    ctx = None
    if caller is not None:
        ctx = {"consumer_class": "external", "channel": "script",
               "caller": caller, "is_test": False}
    with request_context(ctx):
        result = core.process(dict(payload))
    if asyncio.iscoroutine(result):
        return asyncio.get_event_loop_policy().new_event_loop() \
            .run_until_complete(result)
    return result


def build(db, free=2):
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


def test_pg18_distinct_callers_get_their_own_free_tier(db):
    """The scraper problem: caller A exhausting its tier must never starve
    caller B."""
    _, _, scale = build(db, free=2)
    for _ in range(2):
        assert call(scale, CALL, caller="ext:aaaa")["status"] == "ok"
    refused = call(scale, CALL, caller="ext:aaaa")
    assert refused["error_type"] == "payment_required"      # A exhausted
    assert call(scale, CALL, caller="ext:bbbb")["status"] == "ok"  # B fine
    assert call(scale, CALL, caller="internal:nightkeeper")["status"] == "ok"


def test_pg18_contextless_calls_share_unknown_pool_pre_pg18_behavior(db):
    """No transport context (tests, in-process) -> single shared pool of N,
    exactly the old global semantics: PG1/PG2 unchanged."""
    _, _, scale = build(db, free=2)
    assert call(scale, CALL)["status"] == "ok"
    assert call(scale, CALL)["status"] == "ok"
    assert call(scale, CALL)["error_type"] == "payment_required"


def test_pg18_anonymous_aggregate_capped_against_rotation(db):
    """Rotating fingerprints get at most multiplier x N free calls total."""
    _, _, scale = build(db, free=1)
    cap = 1 * ANON_POOL_MULTIPLIER
    granted = 0
    for i in range(cap + 3):                # more identities than the cap
        r = call(scale, CALL, caller=f"ext:rot{i:04d}")
        if r.get("status") == "ok":
            granted += 1
    assert granted == cap                   # bound holds exactly
    # identified (non-anon) callers are NOT starved by the anon cap:
    assert call(scale, CALL, caller="internal:justin")["status"] == "ok"


def test_pg18_identity_from_transport_never_from_payload(db):
    """A payload claiming a caller must not mint a fresh free tier."""
    _, _, scale = build(db, free=1)
    assert call(scale, CALL)["status"] == "ok"          # unknown pool spent
    spoof = dict(CALL, caller="ext:spoofed", consumer_class="internal")
    refused = call(scale, spoof)                        # still context-less
    assert refused["error_type"] == "payment_required"


def test_pg18_per_caller_counters_survive_restart(db):
    _, _, scale = build(db, free=1)
    assert call(scale, CALL, caller="ext:aaaa")["status"] == "ok"

    store2 = StateStore(db)
    scale2 = SMARTSCALE.SmartScaleCore()
    meter2 = METERING.build()
    store2.restore("smartscale", scale2)
    store2.attach("smartscale", scale2)
    store2.attach("metering", meter2)
    gate2 = PaymentGate(store2, meter2, free_calls_per_day=1)
    gate2.attach("smartscale", scale2)

    refused = call(scale2, CALL, caller="ext:aaaa")     # remembered
    assert refused["error_type"] == "payment_required"
    assert call(scale2, CALL, caller="ext:bbbb")["status"] == "ok"


def test_pg18_credits_ride_above_the_per_caller_tier(db):
    """PG9 unchanged: an exhausted caller with prepaid credits is served."""
    _, gate, scale = build(db, free=1)
    assert call(scale, CALL, caller="ext:aaaa")["status"] == "ok"
    getattr(scale, GATE_ATTR)["credits"] = 1
    assert call(scale, CALL, caller="ext:aaaa")["status"] == "ok"   # credit
    assert call(scale, CALL, caller="ext:aaaa")["error_type"] == \
        "payment_required"


def test_pg18_status_reports_policy_and_caller_counts(db):
    _, gate, scale = build(db, free=2)
    call(scale, CALL, caller="ext:aaaa")
    call(scale, CALL, caller="ext:bbbb")
    s = gate.status()["free_tier_policy"]
    assert s["per_caller"] is True
    assert s["callers_seen_today"]["smartscale"] == 2
