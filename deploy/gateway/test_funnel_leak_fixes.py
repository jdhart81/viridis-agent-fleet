#!/usr/bin/env python3
"""
Tests for the 2026-07-17 funnel-leak fixes:

  PB12 — OPEN escrows teach funding_next_steps; FUNDED escrows teach
         usage_next_steps (viridis payee -> payment_ref retry; other
         payees -> deliver/release/dispute)
  PG21 — >=3 same-caller refusals/day add payment.subscription_hint to
         the freemium 402 envelope

(E10 idempotent open is tested in the escrow agent's own suite.)
One test per claim; everything additive.

Run:  pytest deploy/gateway/test_funnel_leak_fixes.py -q
"""
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from participant_bridge import attach_self_teaching, PAYMENTS_MCP  # noqa: E402
from payment_gate import (PaymentGate, SEAT_HINT_REFUSALS,         # noqa: E402
                          SEATS_URL)
from request_context import request_context                        # noqa: E402
from state_store import StateStore                                 # noqa: E402


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


ESCROW = _load_pkg("agent-escrow-agent")
SMARTSCALE = _load_pkg("smartscale-agent")
METERING = _load_pkg("agent-metering-agent")

CALL = {"action": "measure_from_credit_card", "image_id": "img-1",
        "credit_card_pixel_width": 856.0,
        "objects": [{"label": "box", "pixel_width": 428.0,
                     "pixel_height": 214.0}]}


def run(x):
    if asyncio.iscoroutine(x):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(x)
        finally:
            loop.close()
    return x


# --------------------------------------------------------------- PB12 --- #

def taught_core():
    core = ESCROW.build()
    attach_self_teaching(core)
    return core


def test_pb12_open_escrow_teaches_funding_steps():
    core = taught_core()
    out = core.process_sync({"action": "open", "payer": "a", "payee": "b",
                             "amount_minor": 270})
    assert out["status"] == "ok"
    eid = out["data"]["escrow_id"]
    steps = out["funding_next_steps"]
    assert f"fund_escrow('{eid}'" in steps["a2a"]
    assert f"escrow_checkout('{eid}')" in steps["cash"]
    assert PAYMENTS_MCP in steps["cash"]
    assert "open_ref" in steps["retry_tip"]          # E10 cross-teach


def test_pb12_funded_viridis_payee_teaches_payment_ref_retry():
    core = taught_core()
    eid = core.process_sync({"action": "open", "payer": "a",
                             "payee": "viridis:regulatory-radar",
                             "amount_minor": 250})["data"]["escrow_id"]
    out = core.process_sync({"action": "fund", "escrow_id": eid,
                             "payment_ref": "t"})
    steps = out["usage_next_steps"]
    assert f"payment_ref='{eid}'" in steps["spend"]
    assert "regulatory-radar" in steps["spend"]
    assert "funding_next_steps" not in out           # state moved on


def test_pb12_funded_stranger_payee_teaches_settlement():
    core = taught_core()
    eid = core.process_sync({"action": "open", "payer": "a", "payee": "b",
                             "amount_minor": 270})["data"]["escrow_id"]
    out = core.process_sync({"action": "fund", "escrow_id": eid,
                             "payment_ref": "t"})
    steps = out["usage_next_steps"]
    assert f"release_escrow('{eid}')" in steps["settle"]
    assert f"dispute_escrow('{eid}')" in steps["settle"]


def test_pb12_additive_existing_keys_preserved():
    pure = ESCROW.build().process_sync({"action": "open", "payer": "a",
                                        "payee": "b", "amount_minor": 270})
    taught = taught_core().process_sync({"action": "open", "payer": "a",
                                         "payee": "b", "amount_minor": 270})
    stripped = {k: v for k, v in taught.items() if k != "funding_next_steps"}
    assert set(stripped) == set(pure)
    assert set(stripped["data"]) == set(pure["data"])


def test_pb12_poisoned_snapshot_flag_cannot_disable_teaching():
    """REGRESSION (observed live 2026-07-17): StateStore persists
    vars(core), so the old core-attribute guard revived on a fresh boot
    and silently disabled ALL teaching after the first restart. The guard
    now lives on the wrapped function; a restored core-attribute flag
    must neither block wrapping nor survive into the next snapshot."""
    core = ESCROW.build()
    core._self_teaching_attached = True          # simulate poisoned restore
    attach_self_teaching(core)
    out = core.process_sync({"action": "open", "payer": "a", "payee": "b",
                             "amount_minor": 270})
    assert "funding_next_steps" in out           # teaching alive
    assert "_self_teaching_attached" not in vars(core)   # scrubbed
    wrapped = core.process_sync
    attach_self_teaching(core)                   # idempotent via fn attr
    assert core.process_sync is wrapped


# --------------------------------------------------------------- PG21 --- #

def build_gate(db, free=1):
    store = StateStore(db)
    scale = SMARTSCALE.SmartScaleCore()
    meter = METERING.build()
    store.attach("smartscale", scale)
    store.attach("metering", meter)
    gate = PaymentGate(store, meter, free_calls_per_day=free)
    gate.attach("smartscale", scale)
    return scale


def call(core, caller="ext:aaa111"):
    ctx = {"consumer_class": "external", "channel": "script",
           "caller": caller, "is_test": False}
    with request_context(ctx):
        return run(core.process(dict(CALL)))


def test_pg21_hint_appears_at_threshold(tmp_path):
    scale = build_gate(str(tmp_path / "s.db"))
    assert call(scale)["status"] == "ok"             # free call
    refusals = [call(scale) for _ in range(SEAT_HINT_REFUSALS)]
    for r in refusals[:-1]:
        assert "subscription_hint" not in r["payment"]   # below threshold
    hint = refusals[-1]["payment"]["subscription_hint"]
    assert hint["seats_url"] == SEATS_URL
    assert f"{SEAT_HINT_REFUSALS} times today" in hint["note"]


def test_pg21_below_threshold_envelope_unchanged(tmp_path):
    scale = build_gate(str(tmp_path / "s.db"))
    call(scale)
    first_refusal = call(scale)
    assert first_refusal["error_type"] == "payment_required"
    assert "subscription_hint" not in first_refusal["payment"]
    assert "batch_hint" in first_refusal["payment"]["a2a"]   # PG19 intact


def test_pg21_distinct_callers_tracked_separately(tmp_path):
    scale = build_gate(str(tmp_path / "s.db"))
    for who in ("ext:aaa111", "ext:bbb222"):
        call(scale, who)                              # each spends own free
    for _ in range(SEAT_HINT_REFUSALS):
        r_a = call(scale, "ext:aaa111")
    r_b = call(scale, "ext:bbb222")                   # only 1 refusal
    assert "subscription_hint" in r_a["payment"]
    assert "subscription_hint" not in r_b["payment"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
