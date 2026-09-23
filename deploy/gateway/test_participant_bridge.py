#!/usr/bin/env python3
"""
Tests for participant_bridge.py (PB1-PB8) — real escrow, identity,
arbitration, smartscale + metering cores; real StateStore; real PaymentGate.

Run:  pytest deploy/gateway/test_participant_bridge.py -q
"""
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from participant_bridge import ParticipantBridge          # noqa: E402
from payment_gate import PaymentGate, GATE_ATTR, PRICE_MINOR  # noqa: E402
from state_store import StateStore                        # noqa: E402
from escrow_custody import EscrowCustody                  # noqa: E402
from connect_rail import ConnectRail                       # noqa: E402


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
IDENTITY, IDENTITY_M = _load("agent-identity-registry-agent")
ARBITRATION, ARBITRATION_M = _load("agent-arbitration-agent")
SMARTSCALE, SMARTSCALE_M = _load("smartscale-agent")
METERING, METERING_M = _load("agent-metering-agent")


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeCustody:
    """PB2 cash registry plus a controllable PB13 settlement surface."""
    class _S:
        def __init__(self):
            self.funded = {}
    def __init__(self):
        self.state = self._S()
        self.settlement_calls = []
        self.settlement_results = []

    def settlement_instruction(self, escrow_id):
        self.settlement_calls.append(escrow_id)
        if self.settlement_results:
            return dict(self.settlement_results.pop(0))
        return {"status": "ok", "type": "payout", "rail": "manual",
                "escrow_id": escrow_id, "executed": False,
                "action_for_justin": "certified fallback"}


def build(db):
    store = StateStore(db)
    escrow = ESCROW.build()
    identity = IDENTITY.build() if hasattr(IDENTITY, "build") else None
    if identity is None:
        for n in dir(IDENTITY):
            if n.endswith("Core") and n != "AgentCore":
                identity = getattr(IDENTITY, n)()
    arbitration = ARBITRATION.build() if hasattr(ARBITRATION, "build") else None
    if arbitration is None:
        for n in dir(ARBITRATION):
            if n.endswith("Core") and n != "AgentCore":
                arbitration = getattr(ARBITRATION, n)()
    scale = SMARTSCALE.SmartScaleCore()
    meter = METERING.build()
    for name, mods in (("escrow", ESCROW_M), ("smartscale", SMARTSCALE_M)):
        store.register_modules(name, mods)
    store.attach("smartscale", scale)
    gate = PaymentGate(store, meter, free_calls_per_day=0)
    gate.attach("smartscale", scale)
    custody = FakeCustody()
    bridge = ParticipantBridge(store, escrow, identity, arbitration,
                               gate, custody)
    return store, escrow, identity, arbitration, gate, scale, custody, bridge


def earn(escrow, payee="riverside-robotics", amount=5000, fee_bps=100):
    eid = escrow.process_sync({"action": "open", "payer": "agent:research-lab",
                               "payee": payee, "amount_minor": amount,
                               "currency": "USD", "terms": "job",
                               "fee_bps": fee_bps})["data"]["escrow_id"]
    escrow.process_sync({"action": "fund", "escrow_id": eid})
    escrow.process_sync({"action": "release", "escrow_id": eid})
    return eid


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "state.db")


# ---------------------------- PB1 --------------------------------------- #
def test_pb1_claim_registers_identity_and_is_exclusive(db):
    _, escrow, identity, _, _, _, _, bridge = build(db)
    earn(escrow)
    r = run(bridge.claim_payee("riverside-robotics", contact="ops@rr.example"))
    assert r["status"] == "ok"
    assert r["claim_secret"]
    assert r["review"] == "pending-human-review"       # PB1 honesty
    resolved = run(identity.process({"action": "resolve",
                                     "agent_id": "riverside-robotics"}))
    assert resolved["status"] == "ok"
    rival = run(bridge.claim_payee("riverside-robotics"))
    assert rival["error_type"] == "already_claimed"
    assert "arbitration" in rival["message"]


def test_pb1_no_earnings_no_claim_and_viridis_reserved(db):
    _, _, _, _, _, _, _, bridge = build(db)
    assert run(bridge.claim_payee("nobody"))["error_type"] == "no_earnings"
    assert run(bridge.claim_payee("viridis:protogen"))["error_type"] == "reserved"


# ---------------------------- PB2 --------------------------------------- #
def test_pb2_balance_derived_and_split_cash_vs_internal(db):
    _, escrow, _, _, _, _, custody, bridge = build(db)
    e1 = earn(escrow, amount=5000, fee_bps=100)        # net 4950 internal
    e2 = earn(escrow, amount=1000, fee_bps=1000)       # net 900, cash-backed
    custody.state.funded[e2] = {"session_id": "cs_x", "amount_total": 1000}
    b = bridge.payee_balance("riverside-robotics")
    assert b["earned_internal_minor"] == 4950
    assert b["cash_backed_minor"] == 900
    assert b["spendable_internal_minor"] == 4950       # cash not spendable here


# ---------------------------- PB3 --------------------------------------- #
def test_pb3_spend_converts_earnings_to_gate_credits(db):
    _, escrow, _, _, gate, scale, _, bridge = build(db)
    earn(escrow, amount=5000, fee_bps=100)             # net 4950
    secret = run(bridge.claim_payee("riverside-robotics"))["claim_secret"]
    r = bridge.spend_earnings("riverside-robotics", secret, "smartscale",
                              1000, spend_id="s-1")
    assert r["status"] == "ok"
    assert r["credits"] == 1000 // PRICE_MINOR["smartscale"]   # 20
    assert getattr(scale, GATE_ATTR)["credits"] == 20
    b = bridge.payee_balance("riverside-robotics")
    assert b["spendable_internal_minor"] == 3950
    replay = bridge.spend_earnings("riverside-robotics", secret, "smartscale",
                                   1000, spend_id="s-1")
    assert replay["duplicate"] is True                 # idempotent
    assert getattr(scale, GATE_ATTR)["credits"] == 20  # no double credit


def test_pb3_overspend_and_wrong_secret_refused(db):
    _, escrow, _, _, _, scale, _, bridge = build(db)
    earn(escrow, amount=1000, fee_bps=100)             # net 990
    secret = run(bridge.claim_payee("riverside-robotics"))["claim_secret"]
    over = bridge.spend_earnings("riverside-robotics", secret, "smartscale",
                                 99999, spend_id="s-over")
    assert over["error_type"] == "insufficient_balance"
    bad = bridge.spend_earnings("riverside-robotics", "wrong", "smartscale",
                                100, spend_id="s-bad")
    assert bad["error_type"] == "unauthorized"
    assert getattr(scale, GATE_ATTR)["credits"] == 0   # nothing granted


def test_pb3_persist_failure_reverts_everything(db):
    _, escrow, _, _, gate, scale, _, bridge = build(db)
    earn(escrow, amount=5000, fee_bps=100)
    secret = run(bridge.claim_payee("riverside-robotics"))["claim_secret"]
    bridge.store.save_many = lambda cores: False
    r = bridge.spend_earnings("riverside-robotics", secret, "smartscale",
                              1000, spend_id="s-1")
    assert r["error_type"] == "persist_failed"
    assert getattr(scale, GATE_ATTR)["credits"] == 0   # reverted
    assert bridge.payee_balance(
        "riverside-robotics")["spendable_internal_minor"] == 4950


# ---------------------------- PB6 --------------------------------------- #
def dispute(escrow, amount=2500, payee="observatory-vendor"):
    eid = escrow.process_sync({"action": "open", "payer": "astronomy-club",
                               "payee": payee, "amount_minor": amount,
                               "currency": "USD", "terms": "footage",
                               "fee_bps": 100})["data"]["escrow_id"]
    escrow.process_sync({"action": "fund", "escrow_id": eid})
    escrow.process_sync({"action": "dispute", "escrow_id": eid,
                         "reason": "footage not delivered"})
    return eid


def test_pb6_disputed_escrow_files_case_with_fee_recorded_not_collected(db):
    _, escrow, _, arbitration, _, _, _, bridge = build(db)
    eid = dispute(escrow, amount=2500)
    r = run(bridge.file_dispute(eid))
    assert r["status"] == "ok"
    assert r["case_id"].startswith("case-")
    assert r["fee_minor"] == max(2500 * 250 // 10000, 50)      # 62
    assert r["fee_collected"] is False                          # internal ledger
    replay = run(bridge.file_dispute(eid))
    assert replay["duplicate"] is True                          # idempotent
    case = run(arbitration.process({"action": "get_case",
                                    "case_id": r["case_id"]}))
    assert case["data"]["claimant"] == "astronomy-club"


def test_pb6_only_disputed_escrows_file(db):
    _, escrow, _, _, _, _, _, bridge = build(db)
    eid = earn(escrow)                                          # RELEASED
    r = run(bridge.file_dispute(eid))
    assert r["error_type"] == "not_disputed"
    assert run(bridge.file_dispute("esc_nope"))["error_type"] == "unknown_escrow"


# ---------------------------- PB7 --------------------------------------- #
def rule_case(arbitration, case_id, claimant_wins: bool):
    case = run(arbitration.process({"action": "get_case",
                                    "case_id": case_id}))["data"]
    evidence = run(arbitration.process({
        "action": "submit_evidence", "case_id": case_id,
        "party": case["claimant"] if claimant_wins else case["respondent"],
        "kind": "statement", "content": "evidence"}))
    assert evidence["status"] == "ok", evidence
    return run(arbitration.process({"action": "rule", "case_id": case_id}))


def test_pb7_ruling_executes_onto_escrow_exactly_once(db):
    _, escrow, _, arbitration, _, _, _, bridge = build(db)
    eid = dispute(escrow)
    case_id = run(bridge.file_dispute(eid))["case_id"]
    ruled = rule_case(arbitration, case_id, claimant_wins=True)
    assert ruled["status"] == "ok", ruled
    instruction = ruled["data"]["escrow_instruction"]   # rule returns the ruling body
    r = run(bridge.execute_ruling(case_id))
    assert r["status"] == "ok"
    assert r["instruction"] == instruction
    esc = escrow.process_sync({"action": "status", "escrow_id": eid})["data"]
    assert esc["state"] == ("REFUNDED" if instruction == "refund"
                            else "RELEASED")
    replay = run(bridge.execute_ruling(case_id))
    assert replay["duplicate"] is True                          # exactly once
    audit = escrow.process_sync({"action": "verify_audit", "escrow_id": eid})
    assert audit["data"]["valid"] is True                       # E7 intact


def test_pb13_cash_ruling_invokes_custody_once_and_replay_is_safe(db):
    _, escrow, _, arbitration, _, _, custody, bridge = build(db)
    eid = dispute(escrow)
    custody.state.funded[eid] = {"session_id": "cs_cash_1",
                                 "amount_total": 2500}
    custody.settlement_results = [{
        "status": "ok", "type": "refund", "scope": "same_party_refund",
        "refund_id": "re_cash_1", "escrow_id": eid, "executed": True}]
    case_id = run(bridge.file_dispute(eid))["case_id"]
    ruled = rule_case(arbitration, case_id, claimant_wins=True)
    assert ruled["data"]["escrow_instruction"] == "refund"
    result = run(bridge.execute_ruling(case_id))
    assert result["status"] == "ok"
    assert result["cash_settlement"]["refund_id"] == "re_cash_1"
    assert custody.settlement_calls == [eid]
    replay = run(bridge.execute_ruling(case_id))
    assert replay["duplicate"] is True
    assert replay["cash_settlement"]["refund_id"] == "re_cash_1"
    assert custody.settlement_calls == [eid]


def test_pb13_connect_or_manual_receipt_is_orchestrated_not_reimplemented(db):
    _, escrow, _, arbitration, _, _, custody, bridge = build(db)
    eid = dispute(escrow)
    custody.state.funded[eid] = {"session_id": "cs_cash_2",
                                 "amount_total": 2500}
    custody.settlement_results = [{
        "status": "ok", "type": "payout", "rail": "connect",
        "scope": "third_party_licensed_rail", "transfer_id": "tr_cash_2",
        "escrow_id": eid, "executed": True}]
    case_id = run(bridge.file_dispute(eid))["case_id"]
    ruled = rule_case(arbitration, case_id, claimant_wins=False)
    assert ruled["data"]["escrow_instruction"] == "release"
    result = run(bridge.execute_ruling(case_id))
    assert result["cash_settlement"]["rail"] == "connect"
    assert result["cash_settlement"]["transfer_id"] == "tr_cash_2"
    assert custody.settlement_calls == [eid]


def test_pb13_transient_cash_failure_retries_same_case(db):
    _, escrow, _, arbitration, _, _, custody, bridge = build(db)
    eid = dispute(escrow)
    custody.state.funded[eid] = {"session_id": "cs_cash_3",
                                 "amount_total": 2500}
    custody.settlement_results = [
        {"status": "error", "error_type": "stripe_error",
         "message": "temporary"},
        {"status": "ok", "type": "refund", "refund_id": "re_cash_3",
         "escrow_id": eid, "executed": True},
    ]
    case_id = run(bridge.file_dispute(eid))["case_id"]
    rule_case(arbitration, case_id, claimant_wins=True)
    failed = run(bridge.execute_ruling(case_id))
    assert failed["error_type"] == "cash_settlement_failed"
    assert case_id in bridge.state.executions   # ruling stays durable
    retried = run(bridge.execute_ruling(case_id))
    assert retried["status"] == "ok" and retried["duplicate"] is True
    assert retried["cash_settlement"]["refund_id"] == "re_cash_3"
    assert custody.settlement_calls == [eid, eid]


def test_pb7_unruled_case_refused(db):
    _, escrow, _, _, _, _, _, bridge = build(db)
    eid = dispute(escrow)
    case_id = run(bridge.file_dispute(eid))["case_id"]
    r = run(bridge.execute_ruling(case_id))
    assert r["error_type"] == "not_ruled"
    assert run(bridge.execute_ruling("case-nope"))["error_type"] == "unknown_case"


# ---------------------------- PB8 --------------------------------------- #
def test_pb8_state_survives_restart(db):
    store, escrow, _, _, _, _, _, bridge = build(db)
    earn(escrow, amount=5000, fee_bps=100)
    # in prod the escrow mount persists its own mutations (store.attach);
    # earn() bypassed the wrapper, so snapshot explicitly here
    store.save("escrow", escrow)
    secret = run(bridge.claim_payee("riverside-robotics"))["claim_secret"]
    bridge.spend_earnings("riverside-robotics", secret, "smartscale",
                          1000, spend_id="s-1")

    store2 = StateStore(db)
    escrow2 = ESCROW.build()
    store2.register_modules("escrow", ESCROW_M)
    store2.restore("escrow", escrow2)
    scale2 = SMARTSCALE.SmartScaleCore()
    store2.register_modules("smartscale", SMARTSCALE_M)
    store2.restore("smartscale", scale2)
    meter2 = METERING.build()
    gate2 = PaymentGate(store2, meter2, free_calls_per_day=0)
    gate2.attach("smartscale", scale2)
    bridge2 = ParticipantBridge(store2, escrow2, None, None, gate2,
                                FakeCustody())
    assert "riverside-robotics" in bridge2.state.claims
    b = bridge2.payee_balance("riverside-robotics")
    assert b["spendable_internal_minor"] == 3950                # spend survived
    assert getattr(scale2, GATE_ATTR)["credits"] == 20          # credits too
    s = bridge2.status()
    assert s["spends"] == 1 and "claim_secret" not in str(s["claims"])


# ---- Integration: participant cash-out via REAL custody + Connect rail ---- #
# Coverage-only (2026-07-19): participant cash-out flows exclusively through
# escrow_custody's EC5 settlement_instruction — already unit-tested in
# test_escrow_custody.py. This proves that composition holds when the
# escrow is one the participant bridge's own core produced, using the SAME
# escrow core instance the bridge is built on. No production code changes
# for this test; fixtures copied in (not imported) per test-file isolation.
class FakeStripe:
    """Injectable checkout/verify trio — copied from test_escrow_custody.py."""

    def __init__(self):
        self.paid: dict = {}
        self.n = 0

    def create_checkout(self, amount_cents, product_name, *, currency="usd",
                        metadata=None, **_):
        self.n += 1
        sid = f"cs_test_{self.n:06d}"
        return {"status": "ok", "url": f"https://checkout.stripe.com/c/{sid}",
                "session_id": sid, "amount_cents": amount_cents,
                "currency": currency, "livemode": False}

    def pay(self, session_id, amount):
        self.paid[session_id] = amount

    def verify_session(self, session_id):
        if session_id in self.paid:
            return {"status": "ok", "session_id": session_id,
                    "payment_status": "paid",
                    "amount_total": self.paid[session_id],
                    "currency": "usd", "livemode": False}
        return {"status": "ok", "session_id": session_id,
                "payment_status": "unpaid", "amount_total": 0,
                "currency": "usd", "livemode": False}


class FakeConnectStripe:
    """Injectable Connect rail functions — copied from
    test_escrow_custody.py / test_bond_bridge.py."""

    def __init__(self, payouts_enabled=True):
        self.payouts_enabled = payouts_enabled
        self.accounts: dict = {}
        self.transfers: dict = {}
        self.transfer_calls = 0

    def create_connect_account(self, payee_ref, *, idempotency_key):
        prior = self.accounts.get(idempotency_key)
        if prior is not None:
            return prior
        resp = {"status": "ok",
                "account_id": f"acct_test{len(self.accounts) + 1:06d}",
                "livemode": False}
        self.accounts[idempotency_key] = resp
        return resp

    def create_account_link(self, account_id):
        return {"status": "ok",
                "url": f"https://connect.stripe.com/setup/{account_id}",
                "expires_at": 9999999999}

    def get_connect_account(self, account_id):
        return {"status": "ok", "account_id": account_id,
                "payouts_enabled": self.payouts_enabled,
                "charges_enabled": False,
                "details_submitted": self.payouts_enabled,
                "requirements_currently_due":
                    [] if self.payouts_enabled else ["external_account"],
                "livemode": False}

    def create_transfer(self, destination, amount_minor, *,
                        idempotency_key, transfer_group="", metadata=None):
        self.transfer_calls += 1
        prior = self.transfers.get(idempotency_key)
        if prior is not None:
            return prior
        resp = {"status": "ok",
                "transfer_id": f"tr_test_{len(self.transfers) + 1:06d}",
                "destination": destination, "amount_minor": amount_minor,
                "transfer_group": transfer_group, "livemode": False}
        self.transfers[idempotency_key] = resp
        return resp


def test_participant_payee_connect_onboarded_payout_auto_executes(db):
    store, escrow, identity, arbitration, gate, scale, _fake_custody, bridge = \
        build(db)
    stripe = FakeStripe()
    fc = FakeConnectStripe()
    rail = ConnectRail(store,
                       create_connect_account=fc.create_connect_account,
                       create_account_link=fc.create_account_link,
                       get_connect_account=fc.get_connect_account,
                       create_transfer=fc.create_transfer)
    # Real custody, wired onto the SAME escrow core + store the bridge uses.
    custody = EscrowCustody(store, escrow, create_checkout=stripe.create_checkout,
                            verify_session=stripe.verify_session, connect=rail)
    ob = rail.begin_onboarding("riverside-robotics")
    assert ob["status"] == "ok"
    eid = escrow.process_sync({
        "action": "open", "payer": "agent:research-lab",
        "payee": "riverside-robotics", "amount_minor": 5000,
        "currency": "USD", "terms": "job",
        "fee_bps": 1000})["data"]["escrow_id"]           # >= EC10 floor
    co = custody.create_funding_checkout(eid)
    assert co["status"] == "ok"
    stripe.pay(co["session_id"], 5000)
    funded = custody.confirm_funding(eid)
    assert funded["status"] == "ok"
    released = escrow.process_sync({"action": "release", "escrow_id": eid})
    assert released["status"] == "ok"
    inst = custody.settlement_instruction(eid)
    assert inst["status"] == "ok"
    assert inst["type"] == "payout"
    assert inst["rail"] == "connect"
    assert inst["scope"] == "third_party_licensed_rail"
    assert inst["executed"] is True                      # no human step
    assert inst["transfer_id"].startswith("tr_")
    assert inst["net_minor"] == 5000 - 500                # fee_bps=1000 frozen (E3)
    assert fc.transfer_calls == 1
    # The bridge's own view of this payee (claim + balance) still works
    # unchanged alongside custody's cash view — composition, not collision.
    claim = run(bridge.claim_payee("riverside-robotics",
                                   contact="ops@rr.example"))
    assert claim["status"] == "ok"
