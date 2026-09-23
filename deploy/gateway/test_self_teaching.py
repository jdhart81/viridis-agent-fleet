#!/usr/bin/env python3
"""
Tests for the self-teaching envelopes:

  PB9  — escrow RELEASED to a non-viridis payee teaches payee_next_steps
  PB10 — escrow DISPUTED teaches dispute_next_steps
  PG19 — payment_required envelopes teach escrow batching (batch_hint)

Uses the real escrow core + real smartscale/metering cores, the same
harness as test_payment_gate*.py. One test per claim; everything is
ADDITIVE — the pre-enrichment response shapes are asserted unchanged.

Run:  pytest deploy/gateway/test_self_teaching.py -q
"""
import asyncio
import copy
import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from participant_bridge import (attach_self_teaching, PAYMENTS_MCP,  # noqa: E402
                                DISPUTE_FEE_BPS, DISPUTE_FEE_MIN_MINOR)
from payment_gate import (PaymentGate, PRICE_MINOR,                  # noqa: E402
                          DEFAULT_PRICE_MINOR)
from state_store import StateStore                                   # noqa: E402


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


def run(coro_or_result):
    if asyncio.iscoroutine(coro_or_result):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro_or_result)
        finally:
            loop.close()
    return coro_or_result


def make_escrow(payee="riverside-robotics", amount=1000):
    core = ESCROW.EscrowAgentCore()
    opened = core.process_sync({"action": "open", "payer": "acme-corp",
                                "payee": payee, "amount_minor": amount})
    assert opened["status"] == "ok"
    eid = opened["data"]["escrow_id"]
    assert core.process_sync({"action": "fund", "escrow_id": eid,
                              "payment_ref": "t"})["status"] == "ok"
    return core, eid


# ---------------------------------------------------------------- PB9 --- #

def test_pb9_release_to_stranger_teaches_claim_and_balance():
    core, eid = make_escrow(payee="riverside-robotics")
    attach_self_teaching(core)
    out = core.process_sync({"action": "release", "escrow_id": eid})
    assert out["status"] == "ok"
    steps = out["payee_next_steps"]
    assert "claim_payee('riverside-robotics')" in steps["claim"]
    assert PAYMENTS_MCP in steps["claim"]
    assert steps["balance_tool"] == "payee_balance"
    assert steps["spend_tool"] == "spend_payee_earnings"


def test_pb9_additive_only_existing_keys_byte_identical():
    """The enriched response minus the new keys equals the pure response."""
    pure_core, pure_eid = make_escrow()
    pure = pure_core.process_sync({"action": "release",
                                   "escrow_id": pure_eid})

    taught_core, taught_eid = make_escrow()
    attach_self_teaching(taught_core)
    taught = taught_core.process_sync({"action": "release",
                                       "escrow_id": taught_eid})

    stripped = {k: v for k, v in taught.items() if k != "payee_next_steps"}
    # ids/timestamps are generated per-core; compare structure + values
    # that must match, then the full key sets.
    assert set(stripped) == set(pure)
    assert stripped["status"] == pure["status"]
    assert stripped["data"]["state"] == pure["data"]["state"] == "RELEASED"
    assert set(stripped["data"]) == set(pure["data"])


def test_pb9_viridis_payee_never_taught():
    """Fleet-revenue / bond-collateral escrows are not participants."""
    core, eid = make_escrow(payee="viridis:smartscale")
    attach_self_teaching(core)
    out = core.process_sync({"action": "release", "escrow_id": eid})
    assert out["status"] == "ok"
    assert "payee_next_steps" not in out


def test_pb9_async_process_taught_exactly_once():
    """The async dispatch path is enriched too, and only once even though
    process() may delegate to the (also wrapped) process_sync()."""
    core, eid = make_escrow()
    attach_self_teaching(core)
    out = run(core.process({"action": "release", "escrow_id": eid}))
    assert out["status"] == "ok"
    assert "payee_next_steps" in out
    # idempotence: re-teaching the same dict does not duplicate or alter
    before = copy.deepcopy(out)
    from participant_bridge import _teach
    assert _teach(out) == before


def test_pb9_attach_twice_is_noop():
    core, eid = make_escrow()
    attach_self_teaching(core)
    once = core.process_sync
    attach_self_teaching(core)
    assert core.process_sync is once          # no double wrap
    out = core.process_sync({"action": "status", "escrow_id": eid})
    assert out["status"] == "ok"              # still functional


def test_pb9_list_and_error_shapes_untouched():
    core, eid = make_escrow()
    attach_self_teaching(core)
    listing = core.process_sync({"action": "list"})
    assert listing["status"] == "ok"
    assert "payee_next_steps" not in listing
    assert "dispute_next_steps" not in listing
    bad = core.process_sync({"action": "release", "escrow_id": "esc_nope"})
    assert bad["status"] == "error"
    assert "payee_next_steps" not in bad


# --------------------------------------------------------------- PB10 --- #

def test_pb10_dispute_teaches_filing_and_evidence_flow():
    core, eid = make_escrow()
    attach_self_teaching(core)
    out = core.process_sync({"action": "dispute", "escrow_id": eid,
                             "reason": "non-delivery"})
    assert out["status"] == "ok"
    steps = out["dispute_next_steps"]
    assert f"file_escrow_dispute('{eid}')" in steps["file"]
    assert PAYMENTS_MCP in steps["file"]
    assert "submit_evidence" in steps["evidence_flow"]
    assert "execute_arbitration_ruling" in steps["evidence_flow"]
    assert steps["fee_schedule"] == {
        "bps": DISPUTE_FEE_BPS, "min_minor": DISPUTE_FEE_MIN_MINOR,
        "collected_on": "custody-cash escrows only (PB6)"}


def test_pb10_status_query_of_disputed_escrow_also_teaches():
    """The teaching moment includes LOOKING at a disputed escrow."""
    core, eid = make_escrow()
    attach_self_teaching(core)
    core.process_sync({"action": "dispute", "escrow_id": eid})
    out = core.process_sync({"action": "status", "escrow_id": eid})
    assert out["status"] == "ok"
    assert out["data"]["state"] == "DISPUTED"
    assert "dispute_next_steps" in out


def test_pb10_additive_only_existing_keys_preserved():
    pure_core, pure_eid = make_escrow()
    pure = pure_core.process_sync({"action": "dispute",
                                   "escrow_id": pure_eid})
    taught_core, taught_eid = make_escrow()
    attach_self_teaching(taught_core)
    taught = taught_core.process_sync({"action": "dispute",
                                       "escrow_id": taught_eid})
    stripped = {k: v for k, v in taught.items()
                if k != "dispute_next_steps"}
    assert set(stripped) == set(pure)
    assert set(stripped["data"]) == set(pure["data"])
    assert stripped["data"]["state"] == "DISPUTED"


# --------------------------------------------------------------- PG19 --- #

def build_gate(db, free=1):
    store = StateStore(db)
    scale = SMARTSCALE.SmartScaleCore()
    meter = METERING.build()
    store.attach("smartscale", scale)
    store.attach("metering", meter)
    gate = PaymentGate(store, meter, free_calls_per_day=free)
    gate.attach("smartscale", scale)
    return scale


def exhaust_to_402(scale, free=1):
    for _ in range(free):
        assert run(scale.process(dict(CALL)))["status"] == "ok"
    refusal = run(scale.process(dict(CALL)))
    assert refusal["error_type"] == "payment_required"
    return refusal


def test_pg19_402_envelope_carries_batch_hint(tmp_path):
    scale = build_gate(str(tmp_path / "s.db"))
    refusal = exhaust_to_402(scale)
    hint = refusal["payment"]["a2a"]["batch_hint"]
    price = PRICE_MINOR.get("smartscale", DEFAULT_PRICE_MINOR)
    assert hint["price_minor"] == price
    assert f"floor(amount_minor / {price})" in hint["how"]
    assert "payment_ref" in hint["how"]
    assert hint["example"] == {"escrow_amount_minor": price * 10,
                               "calls_prepaid": 10}


def test_pg19_batch_hint_states_stripe_minimum_and_ec9_floor(tmp_path):
    scale = build_gate(str(tmp_path / "s.db"))
    refusal = exhaust_to_402(scale)
    note = refusal["payment"]["a2a"]["batch_hint"]["cash_note"]
    assert "50-minor" in note and "$0.50" in note      # EC1 Stripe minimum
    assert "EC9" in note                               # third-party floor


def test_pg19_additive_pre_existing_402_keys_unchanged(tmp_path):
    """Every pre-PG19 envelope key survives with its meaning intact."""
    scale = build_gate(str(tmp_path / "s.db"))
    refusal = exhaust_to_402(scale)
    assert refusal["http_equivalent"] == 402
    assert refusal["billing_path"] == "per_call_freemium"
    a2a = refusal["payment"]["a2a"]
    assert a2a["method"] == "x402"
    assert "payable to viridis:smartscale" in a2a["note"]
    human = refusal["payment"]["human"]
    assert human["method"] == "stripe_checkout"
    assert refusal["free_tier_resets"] == "00:00 UTC"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
