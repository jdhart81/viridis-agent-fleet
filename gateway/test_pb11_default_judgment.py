#!/usr/bin/env python3
"""
Tests for PB11 — autonomous default judgment (policy DJ-14) — with the
real escrow + arbitration cores through the participant bridge. One test
per claim.

Run:  pytest deploy/gateway/test_pb11_default_judgment.py -q
"""
import asyncio
import importlib.util
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from participant_bridge import (ParticipantBridge,          # noqa: E402
                                DEFAULT_JUDGMENT_DAYS,
                                DEFAULT_JUDGMENT_POLICY)
from payment_gate import PaymentGate                        # noqa: E402
from state_store import StateStore                         # noqa: E402


def _load(agent_dir):
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


ESCROW = _load("agent-escrow-agent")
IDENTITY = _load("agent-identity-registry-agent")
ARBITRATION = _load("agent-arbitration-agent")
METERING = _load("agent-metering-agent")


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FakeCustody:
    class _S:
        def __init__(self):
            self.funded = {}
    def __init__(self):
        self.state = self._S()


def build(db):
    store = StateStore(db)
    escrow = ESCROW.build()
    identity = IDENTITY.build() if hasattr(IDENTITY, "build") else None
    arbitration = ARBITRATION.build() if hasattr(ARBITRATION, "build") else None
    meter = METERING.build()
    gate = PaymentGate(store, meter, free_calls_per_day=0)
    bridge = ParticipantBridge(store, escrow, identity, arbitration,
                               gate, FakeCustody())
    return escrow, arbitration, bridge


def disputed_escrow(escrow, payer="astronomy-club", payee="observatory-vendor",
                    amount=7500):
    eid = escrow.process_sync({"action": "open", "payer": payer,
                               "payee": payee,
                               "amount_minor": amount})["data"]["escrow_id"]
    escrow.process_sync({"action": "fund", "escrow_id": eid,
                         "payment_ref": "t"})
    escrow.process_sync({"action": "dispute", "escrow_id": eid,
                         "reason": "non-delivery"})
    return eid


def backdate(bridge, escrow_id, days=DEFAULT_JUDGMENT_DAYS + 1):
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                        time.gmtime(time.time() - days * 86400))
    bridge.state.disputes[escrow_id]["filed_at"] = old


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "state.db")


def test_pb11_ripe_silent_claim_default_judged_and_executed(db):
    """14d of claimant silence -> ruled for respondent -> escrow RELEASED."""
    escrow, arbitration, bridge = build(db)
    eid = disputed_escrow(escrow)
    filing = run(bridge.file_dispute(eid))
    assert filing["status"] == "ok"
    backdate(bridge, eid)
    swept = run(bridge.sweep_stale_disputes())
    assert swept["status"] == "ok"
    assert swept["policy"] == DEFAULT_JUDGMENT_POLICY
    [r] = swept["results"]
    assert r["outcome"] == "default_judgment_executed"
    esc = escrow.process_sync({"action": "status", "escrow_id": eid})
    assert esc["data"]["state"] == "RELEASED"
    case = run(arbitration.process({"action": "get_case",
                                    "case_id": filing["case_id"]}))
    assert case["data"]["ruling"]["default_judgment"] is True
    assert case["data"]["ruling"]["respondent_pct"] == 100


def test_pb11_unripe_case_untouched(db):
    escrow, arbitration, bridge = build(db)
    eid = disputed_escrow(escrow)
    filing = run(bridge.file_dispute(eid))
    swept = run(bridge.sweep_stale_disputes())
    [r] = swept["results"]
    assert r["outcome"] == "not_ripe"
    esc = escrow.process_sync({"action": "status", "escrow_id": eid})
    assert esc["data"]["state"] == "DISPUTED"
    case = run(arbitration.process({"action": "get_case",
                                    "case_id": filing["case_id"]}))
    assert case["data"]["ruling"] is None


def test_pb11_evidenced_claim_never_auto_ruled(db):
    """Claimant evidence forces the merits path — surfaced, not ruled."""
    escrow, arbitration, bridge = build(db)
    eid = disputed_escrow(escrow)
    filing = run(bridge.file_dispute(eid))
    run(arbitration.process({"action": "submit_evidence",
                             "case_id": filing["case_id"],
                             "party": "astronomy-club",
                             "kind": "statement", "content": "not delivered"}))
    backdate(bridge, eid)
    swept = run(bridge.sweep_stale_disputes())
    [r] = swept["results"]
    assert r["outcome"] == "needs_merits_ruling"
    esc = escrow.process_sync({"action": "status", "escrow_id": eid})
    assert esc["data"]["state"] == "DISPUTED"           # untouched


def test_pb11_sweep_idempotent(db):
    """A second sweep converges: nothing double-executes (A7/PB7/E6)."""
    escrow, arbitration, bridge = build(db)
    eid = disputed_escrow(escrow)
    run(bridge.file_dispute(eid))
    backdate(bridge, eid)
    first = run(bridge.sweep_stale_disputes())
    assert first["results"][0]["outcome"] == "default_judgment_executed"
    second = run(bridge.sweep_stale_disputes())
    assert second["results"][0]["outcome"] == "already_executed"
    assert bridge.status()["rulings_executed"] == 1


def test_pb11_executes_preexisting_merits_ruling(db):
    """A case someone already ruled on the merits just gets executed."""
    escrow, arbitration, bridge = build(db)
    eid = disputed_escrow(escrow)
    filing = run(bridge.file_dispute(eid))
    run(arbitration.process({"action": "submit_evidence",
                             "case_id": filing["case_id"],
                             "party": "observatory-vendor",
                             "kind": "delivery_proof", "content": "receipt"}))
    run(arbitration.process({"action": "rule",
                             "case_id": filing["case_id"]}))
    swept = run(bridge.sweep_stale_disputes())          # not even ripe
    [r] = swept["results"]
    assert r["outcome"] == "executed_existing_ruling"
    esc = escrow.process_sync({"action": "status", "escrow_id": eid})
    assert esc["data"]["state"] in ("RELEASED", "REFUNDED")


def test_pb11_unparseable_filed_at_is_never_ripe(db):
    escrow, arbitration, bridge = build(db)
    eid = disputed_escrow(escrow)
    run(bridge.file_dispute(eid))
    bridge.state.disputes[eid]["filed_at"] = "garbage"
    swept = run(bridge.sweep_stale_disputes())
    assert swept["results"][0]["outcome"] == "not_ripe"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
