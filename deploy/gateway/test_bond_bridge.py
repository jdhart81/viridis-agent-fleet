#!/usr/bin/env python3
"""
Tests for bond_bridge.py (CB1-CB6) — real escrow, surety, verified-relay
cores; real StateStore; fake custody registry. Zero Viridis capital is
asserted structurally: every payout source is the provider's collateral.

Run:  pytest deploy/gateway/test_bond_bridge.py -q
"""
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from bond_bridge import BondBridge, COLLATERAL_PAYEE   # noqa: E402
from state_store import StateStore                     # noqa: E402


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
    mods = {m: sys.modules[m] for m in list(sys.modules)
            if m == "src" or m.startswith("src.")}
    return mod, mods


ESCROW, ESCROW_M = _load("agent-escrow-agent")
SURETY, SURETY_M = _load("agent-surety-agent")
VERIFIED, VERIFIED_M = _load("agent-verified-relay-agent")


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeCustody:
    class _S:
        def __init__(self):
            self.funded = {}
    def __init__(self):
        self.state = self._S()
        self.refunds = {}
        self.refund_calls = 0
        self.fail_refund = False
        self._execute_refund = self.create_refund

    def create_refund(self, session_id, *, idempotency_key,
                      amount_minor=None):
        self.refund_calls += 1
        if self.fail_refund:
            return {"status": "error", "error_type": "stripe_error",
                    "message": "refund rail unavailable"}
        prior = self.refunds.get(idempotency_key)
        if prior is not None:
            return prior
        result = {
            "status": "ok",
            "refund_id": f"re_test_{len(self.refunds) + 1:06d}",
            "payment_intent": f"pi_for_{session_id}",
            "amount_minor": amount_minor,
            "refund_status": "succeeded",
            "livemode": False,
            "timestamp": "2026-07-20T00:00:00Z",
        }
        self.refunds[idempotency_key] = result
        return result


def build(db):
    store = StateStore(db)
    escrow = ESCROW.build()
    surety = SURETY.build() if hasattr(SURETY, "build") else None
    if surety is None:
        for n in dir(SURETY):
            if n.endswith("Core") and n != "AgentCore":
                surety = getattr(SURETY, n)()
    verified = VERIFIED.build() if hasattr(VERIFIED, "build") else None
    if verified is None:
        for n in dir(VERIFIED):
            if n.endswith("Core") and n != "AgentCore":
                verified = getattr(VERIFIED, n)()
    custody = FakeCustody()
    bridge = BondBridge(store, escrow, surety, verified, custody,
                        execute_refund=custody.create_refund)
    return store, escrow, surety, verified, custody, bridge


def register_service(verified):
    r = run(verified.process({
        "action": "register_service",
        "url": "https://api.provider.example/mcp",
        "provider": "riverside-robotics",
        "description": "robotics jobs"}))
    assert r["status"] == "ok", r
    return r["data"]["service_id"]


def post_collateral(escrow, custody, amount=10000, cash=True):
    eid = escrow.process_sync({
        "action": "open", "payer": "riverside-robotics",
        "payee": COLLATERAL_PAYEE, "amount_minor": amount,
        "currency": "USD", "terms": "bond collateral",
        "fee_bps": 0})["data"]["escrow_id"]
    escrow.process_sync({"action": "fund", "escrow_id": eid,
                         "payment_ref": "stripe:cs_test_collateral"})
    if cash:
        custody.state.funded[eid] = {"session_id": "cs_test_collateral",
                                     "amount_total": amount}
    return eid


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "state.db")


# ---------------------------- CB1 --------------------------------------- #
def test_cb1_binds_only_against_cash_collateral(db):
    _, escrow, _, verified, custody, bridge = build(db)
    sid = register_service(verified)
    internal = post_collateral(escrow, custody, cash=False)   # not custody-cash
    r = run(bridge.bind(sid, internal, "2026-08-16T00:00:00Z"))
    assert r["error_type"] == "not_cash"
    wrong_payee = escrow.process_sync({
        "action": "open", "payer": "p", "payee": "someone-else",
        "amount_minor": 10000, "currency": "USD", "fee_bps": 0})["data"]["escrow_id"]
    escrow.process_sync({"action": "fund", "escrow_id": wrong_payee})
    custody.state.funded[wrong_payee] = {"session_id": "cs_2",
                                         "amount_total": 10000}
    r2 = run(bridge.bind(sid, wrong_payee, "2026-08-16T00:00:00Z"))
    assert r2["error_type"] == "wrong_payee"


def test_cb1_cb2_cb3_full_bind_with_uw_v1_premium(db):
    _, escrow, surety, verified, custody, bridge = build(db)
    sid = register_service(verified)
    eid = post_collateral(escrow, custody, amount=10000)
    r = run(bridge.bind(sid, eid, "2026-08-16T00:00:00Z"))
    assert r["status"] == "ok", r
    assert r["premium_minor"] > 0                              # CB2
    assert r["coverage_minor"] == 10000 - r["premium_minor"]
    assert r["quote_hash"]                                     # CB2/BW4
    bond = run(surety.process({"action": "status",
                               "bond_id": r["bond_id"]}))
    assert bond["data"]["state"] == "ACTIVE"                   # CB3
    audit = run(surety.process({"action": "verify_audit",
                                "bond_id": r["bond_id"]}))
    assert audit["data"]["valid"] is True          # funding_ref in audit chain


def test_cb3_cb5_one_collateral_one_bond_idempotent(db):
    _, escrow, _, verified, custody, bridge = build(db)
    sid = register_service(verified)
    eid = post_collateral(escrow, custody)
    first = run(bridge.bind(sid, eid, "2026-08-16T00:00:00Z"))
    replay = run(bridge.bind(sid, eid, "2026-08-16T00:00:00Z"))
    assert first["duplicate"] is False and replay["duplicate"] is True
    assert replay["bond_id"] == first["bond_id"]
    assert bridge.status()["collateralized_bonds"] == 1


# ---------------------------- CB4 (legs) --------------------------------- #
from connect_rail import ConnectRail                    # noqa: E402


class FakeConnectStripe:
    """Injectable Connect rail (same shape as test_escrow_custody's)."""

    def __init__(self, payouts_enabled=True):
        self.payouts_enabled = payouts_enabled
        self.accounts: dict = {}
        self.transfers: dict = {}
        self.transfer_calls = 0
        self.fail_transfer = False

    def create_connect_account(self, payee_ref, *, idempotency_key):
        prior = self.accounts.get(idempotency_key)
        if prior is None:
            prior = {"status": "ok",
                     "account_id": f"acct_t{len(self.accounts) + 1:06d}",
                     "livemode": False}
            self.accounts[idempotency_key] = prior
        return prior

    def create_account_link(self, account_id):
        return {"status": "ok",
                "url": f"https://connect.stripe.com/setup/{account_id}"}

    def get_connect_account(self, account_id):
        return {"status": "ok", "account_id": account_id,
                "payouts_enabled": self.payouts_enabled,
                "charges_enabled": False, "details_submitted": True,
                "requirements_currently_due": [], "livemode": False}

    def create_transfer(self, destination, amount_minor, *,
                        idempotency_key, transfer_group="", metadata=None):
        self.transfer_calls += 1
        if self.fail_transfer:
            return {"status": "error", "error_type": "stripe_error",
                    "message": "stripe down"}
        prior = self.transfers.get(idempotency_key)
        if prior is None:
            prior = {"status": "ok",
                     "transfer_id": f"tr_t{len(self.transfers) + 1:06d}",
                     "destination": destination,
                     "amount_minor": amount_minor,
                     "transfer_group": transfer_group, "livemode": False}
            self.transfers[idempotency_key] = prior
        return prior


def build_with_connect(db):
    store, escrow, surety, verified, custody, _ = build(db)
    fc = FakeConnectStripe()
    rail = ConnectRail(store,
                       create_connect_account=fc.create_connect_account,
                       create_account_link=fc.create_account_link,
                       get_connect_account=fc.get_connect_account,
                       create_transfer=fc.create_transfer)
    bridge = BondBridge(store, escrow, surety, verified, custody,
                        connect=rail)
    return escrow, surety, verified, custody, fc, rail, bridge


def _slash_and_release(surety, bond_id, amount=500,
                       claimant="agent:harmed-party"):
    claim = run(surety.process({
        "action": "file_claim", "bond_id": bond_id, "claimant": claimant,
        "amount_minor": amount, "reason": "missed delivery"}))
    assert claim["status"] == "ok", claim
    slashed = run(surety.process({
        "action": "slash", "bond_id": bond_id,
        "claim_id": claim["data"]["claim_id"],
        "ruling_case_id": "case-t-001", "ruling_hash": "deadbeef",
        "upheld": True}))
    assert slashed["status"] == "ok", slashed
    released = run(surety.process({"action": "release", "bond_id": bond_id,
                                   "_now": "2026-08-01T00:00:00+00:00"}))
    assert released["status"] == "ok", released
    return claim["data"]["claim_id"]


def _assert_executed_legs_have_money_evidence(instruction):
    for leg in instruction["legs"]:
        if leg["executed"]:
            assert any(leg.get(field) for field in (
                "refund_id", "transfer_id", "money_primitive_id")), leg


def test_cb4_clean_expiry_auto_executes_provider_return(db):
    _, escrow, surety, verified, custody, bridge = build(db)
    sid = register_service(verified)
    eid = post_collateral(escrow, custody, amount=10000)
    bound = run(bridge.bind(sid, eid, "2026-07-17T00:00:00Z"))
    released = run(surety.process({"action": "release",
                                   "bond_id": bound["bond_id"],
                                   "_now": "2026-08-01T00:00:00+00:00"}))
    assert released["status"] == "ok", released
    inst = run(bridge.certify_settlement(bound["bond_id"]))
    assert inst["status"] == "ok"
    assert inst["slashed_minor"] == 0
    assert inst["executed"] is True                   # all legs autonomous
    assert len(inst["legs"]) == 1
    leg = inst["legs"][0]
    assert leg["leg"] == "provider_return"
    assert leg["scope"] == "same_party_refund"
    assert leg["rail"] == "stripe_refund"
    assert leg["refund_id"].startswith("re_")
    assert leg["payment_intent"].startswith("pi_")
    assert leg["executed"] is True and leg["executed_at"] is not None
    assert leg["amount_minor"] == 10000 - bound["premium_minor"]
    assert inst["return_to_provider_minor"] == 10000 - bound["premium_minor"]
    replay = run(bridge.certify_settlement(bound["bond_id"]))
    assert replay["duplicate"] is True                         # CB5
    assert custody.refund_calls == 1
    _assert_executed_legs_have_money_evidence(inst)


def test_cb4_slashed_bond_provider_leg_autonomous_claimant_leg_gated(db):
    """The legs win: even on a SLASHED bond the provider's own collateral
    comes back autonomously; only the claimant leg (true third party,
    not onboarded here) stays certified-manual."""
    _, escrow, surety, verified, custody, bridge = build(db)
    sid = register_service(verified)
    eid = post_collateral(escrow, custody, amount=10000)
    bound = run(bridge.bind(sid, eid, "2026-07-17T00:00:00Z"))
    claim_id = _slash_and_release(surety, bound["bond_id"], amount=500)
    inst = run(bridge.certify_settlement(bound["bond_id"]))
    assert inst["status"] == "ok"
    assert inst["slashed_minor"] == 500
    assert inst["executed"] is False                  # one leg still manual
    legs = {l["leg"]: l for l in inst["legs"]}
    assert legs["provider_return"]["executed"] is True
    assert legs["provider_return"]["refund_id"].startswith("re_")
    assert legs["provider_return"]["amount_minor"] == \
        10000 - bound["premium_minor"] - 500
    cl = legs["claimant_payout"]
    assert cl["executed"] is False and cl["rail"] == "manual"
    assert cl["claim_id"] == claim_id and cl["amount_minor"] == 500
    assert "begin_payout_onboarding" in cl["onboarding_hint"]
    assert "action_for_justin" in inst                # manual rollup
    _assert_executed_legs_have_money_evidence(inst)


def test_cb4_onboarded_claimant_leg_pays_via_connect_exactly_once(db):
    escrow, surety, verified, custody, fc, rail, bridge = \
        build_with_connect(db)
    rail.begin_onboarding("agent:harmed-party")
    sid = register_service(verified)
    eid = post_collateral(escrow, custody, amount=10000)
    bound = run(bridge.bind(sid, eid, "2026-07-17T00:00:00Z"))
    _slash_and_release(surety, bound["bond_id"], amount=500)
    inst = run(bridge.certify_settlement(bound["bond_id"]))
    assert inst["status"] == "ok"
    assert inst["executed"] is True                   # ALL legs autonomous
    legs = {l["leg"]: l for l in inst["legs"]}
    assert legs["claimant_payout"]["rail"] == "connect"
    assert legs["claimant_payout"]["transfer_id"].startswith("tr_")
    assert legs["claimant_payout"]["scope"] == "third_party_licensed_rail"
    assert fc.transfer_calls == 1
    replay = run(bridge.certify_settlement(bound["bond_id"]))
    assert replay["duplicate"] is True
    assert fc.transfer_calls == 1                     # never re-pays (CB5)
    assert custody.refund_calls == 1                  # never double-refunds
    _assert_executed_legs_have_money_evidence(inst)


def test_fa15_provider_refund_failure_fails_closed_then_retries(db):
    _, escrow, surety, verified, custody, bridge = build(db)
    sid = register_service(verified)
    eid = post_collateral(escrow, custody, amount=10000)
    bound = run(bridge.bind(sid, eid, "2026-07-17T00:00:00Z"))
    run(surety.process({"action": "release", "bond_id": bound["bond_id"],
                        "_now": "2026-08-01T00:00:00+00:00"}))
    custody.fail_refund = True
    failed = run(bridge.certify_settlement(bound["bond_id"]))
    assert failed["status"] == "error"
    assert bound["bond_id"] not in bridge.state.instructions
    custody.fail_refund = False
    settled = run(bridge.certify_settlement(bound["bond_id"]))
    assert settled["status"] == "ok"
    assert settled["legs"][0]["refund_id"].startswith("re_")
    _assert_executed_legs_have_money_evidence(settled)


def test_fa15_missing_original_checkout_evidence_never_executes(db):
    _, escrow, surety, verified, custody, bridge = build(db)
    sid = register_service(verified)
    eid = post_collateral(escrow, custody, amount=10000)
    bound = run(bridge.bind(sid, eid, "2026-07-17T00:00:00Z"))
    run(surety.process({"action": "release", "bond_id": bound["bond_id"],
                        "_now": "2026-08-01T00:00:00+00:00"}))
    custody.state.funded[eid].pop("session_id")
    refused = run(bridge.certify_settlement(bound["bond_id"]))
    assert refused["error_type"] == "missing_collateral_evidence"
    assert bound["bond_id"] not in bridge.state.instructions


def test_cb4_transient_rail_failure_fails_closed_then_retries(db):
    escrow, surety, verified, custody, fc, rail, bridge = \
        build_with_connect(db)
    rail.begin_onboarding("agent:harmed-party")
    sid = register_service(verified)
    eid = post_collateral(escrow, custody, amount=10000)
    bound = run(bridge.bind(sid, eid, "2026-07-17T00:00:00Z"))
    _slash_and_release(surety, bound["bond_id"], amount=500)
    fc.fail_transfer = True
    r = run(bridge.certify_settlement(bound["bond_id"]))
    assert r["status"] == "error"                     # fail-closed
    assert bound["bond_id"] not in bridge.state.instructions
    fc.fail_transfer = False
    ok = run(bridge.certify_settlement(bound["bond_id"]))
    assert ok["status"] == "ok" and ok["executed"] is True


def test_cb4_active_bond_has_no_settlement_paperwork(db):
    _, escrow, _, verified, custody, bridge = build(db)
    sid = register_service(verified)
    eid = post_collateral(escrow, custody)
    bound = run(bridge.bind(sid, eid, "2026-12-31T00:00:00Z"))
    r = run(bridge.certify_settlement(bound["bond_id"]))
    assert r["error_type"] == "not_terminal"


# ---------------------------- CB6 --------------------------------------- #
def test_cb6_persist_failure_reverts_bind_record(db):
    _, escrow, _, verified, custody, bridge = build(db)
    sid = register_service(verified)
    eid = post_collateral(escrow, custody)
    bridge.store.save = lambda *a, **k: False
    r = run(bridge.bind(sid, eid, "2026-08-16T00:00:00Z"))
    assert r["error_type"] == "persist_failed"
    assert eid not in bridge.state.collateral_used             # retryable


def test_cb6_status_asserts_zero_viridis_capital(db):
    _, escrow, _, verified, custody, bridge = build(db)
    sid = register_service(verified)
    eid = post_collateral(escrow, custody)
    run(bridge.bind(sid, eid, "2026-08-16T00:00:00Z"))
    s = bridge.status()
    assert s["viridis_capital_at_risk_minor"] == 0             # the whole point
    assert s["premiums_earned_minor"] > 0


# ---------------------- mark_leg_executed (admin close-out) -------------- #
def test_mark_leg_executed_manual_leg_flips_top_level_and_idempotent(db):
    _, escrow, surety, verified, custody, bridge = build(db)
    sid = register_service(verified)
    eid = post_collateral(escrow, custody, amount=10000)
    bound = run(bridge.bind(sid, eid, "2026-07-17T00:00:00Z"))
    claim_id = _slash_and_release(surety, bound["bond_id"], amount=500)
    inst = run(bridge.certify_settlement(bound["bond_id"]))
    assert inst["executed"] is False                  # manual leg pending
    missing = bridge.mark_leg_executed(bound["bond_id"], claim_id)
    assert missing["error_type"] == "missing_money_primitive"
    assert inst["executed"] is False
    a = bridge.mark_leg_executed(
        bound["bond_id"], claim_id, "manual:bank-receipt-001")
    assert a["status"] == "ok" and a["duplicate"] is False
    legs = {l["leg"]: l for l in a["legs"]}
    assert legs["claimant_payout"]["executed"] is True
    assert legs["claimant_payout"]["executed_at"] is not None
    assert legs["claimant_payout"]["money_primitive_id"] == \
        "manual:bank-receipt-001"
    assert a["executed"] is True                      # every leg now done
    # persisted, not just in-memory on the return value:
    assert bridge.state.instructions[bound["bond_id"]]["executed"] is True
    b = bridge.mark_leg_executed(bound["bond_id"], claim_id,
                                 "manual:different-receipt")
    assert b["status"] == "ok" and b["duplicate"] is True
    assert b["executed"] is True                      # unchanged, no re-flip
    _assert_executed_legs_have_money_evidence(b)


def test_mark_leg_executed_unknown_claim_and_bond_refused(db):
    _, escrow, surety, verified, custody, bridge = build(db)
    sid = register_service(verified)
    eid = post_collateral(escrow, custody, amount=10000)
    bound = run(bridge.bind(sid, eid, "2026-07-17T00:00:00Z"))
    _slash_and_release(surety, bound["bond_id"], amount=500)
    run(bridge.certify_settlement(bound["bond_id"]))
    bad_claim = bridge.mark_leg_executed(
        bound["bond_id"], "claim-nonexistent", "manual:receipt")
    assert bad_claim["error_type"] == "unknown_claim"
    bad_bond = bridge.mark_leg_executed(
        "bond-nonexistent", "claim-x", "manual:receipt")
    assert bad_bond["error_type"] == "unknown_bond"
    bad_bond_id = bridge.mark_leg_executed(
        "", "claim-x", "manual:receipt")
    assert bad_bond_id["error_type"] == "bad_bond_id"
    bad_claim_id = bridge.mark_leg_executed(
        bound["bond_id"], "", "manual:receipt")
    assert bad_claim_id["error_type"] == "bad_claim_id"


def test_mark_leg_executed_autonomous_connect_leg_is_noop_duplicate(db):
    """A leg that already auto-executed via the Connect rail (or a
    provider_return leg) is a no-op confirmation, not a re-execution —
    same idempotent-duplicate posture as weave/escrow_custody."""
    escrow, surety, verified, custody, fc, rail, bridge = \
        build_with_connect(db)
    rail.begin_onboarding("agent:harmed-party")
    sid = register_service(verified)
    eid = post_collateral(escrow, custody, amount=10000)
    bound = run(bridge.bind(sid, eid, "2026-07-17T00:00:00Z"))
    claim_id = _slash_and_release(surety, bound["bond_id"], amount=500)
    inst = run(bridge.certify_settlement(bound["bond_id"]))
    assert inst["executed"] is True                   # already all-autonomous
    assert fc.transfer_calls == 1
    r = bridge.mark_leg_executed(bound["bond_id"], claim_id, "ignored")
    assert r["status"] == "ok" and r["duplicate"] is True
    assert fc.transfer_calls == 1                      # never re-paid
