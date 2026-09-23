#!/usr/bin/env python3
"""
Tests for escrow_custody.py (PG17 / EC1-EC8) — real escrow core (E9 sync
surface), real StateStore, injected Stripe fakes. Third-party cash out is
asserted to be CERTIFIED ONLY; same-party refunds auto-execute (EC5,
2026-07-19). Nothing in this file (or the module) moves money.

Run:  pytest deploy/gateway/test_escrow_custody.py -q
"""
import importlib.util
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from escrow_custody import EscrowCustody, CustodyState   # noqa: E402
from state_store import StateStore                       # noqa: E402


def _load_escrow():
    for m in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
        del sys.modules[m]
    ps = importlib.util.spec_from_file_location(
        "src", ROOT / "agent-escrow-agent" / "src" / "__init__.py",
        submodule_search_locations=[str(ROOT / "agent-escrow-agent" / "src")])
    pkg = importlib.util.module_from_spec(ps)
    sys.modules["src"] = pkg
    ps.loader.exec_module(pkg)
    cs = importlib.util.spec_from_file_location(
        "src.core", ROOT / "agent-escrow-agent" / "src" / "core.py")
    mod = importlib.util.module_from_spec(cs)
    sys.modules["src.core"] = mod
    cs.loader.exec_module(mod)
    modules = {m: sys.modules[m] for m in list(sys.modules)
               if m == "src" or m.startswith("src.")}
    return mod, modules


ESCROW, ESCROW_MODULES = _load_escrow()


class FakeStripe:
    """Injectable checkout/verify/refund trio with controllable state."""

    def __init__(self):
        self.paid: dict = {}          # session_id -> amount_total
        self.n = 0
        self.fail_verify = False
        self.fail_refund = False
        self.refunds: dict = {}       # idempotency_key -> refund response
        self.refund_calls = 0

    def create_refund(self, session_id, *, idempotency_key,
                      amount_minor=None):
        """Mirrors stripe_payments.create_refund semantics (P8/P9)."""
        self.refund_calls += 1
        if self.fail_refund:
            return {"status": "error", "error_type": "stripe_error",
                    "message": "stripe down"}
        prior = self.refunds.get(idempotency_key)   # Stripe Idempotency-Key
        if prior is not None:
            return prior
        resp = {"status": "ok",
                "refund_id": f"re_test_{len(self.refunds) + 1:06d}",
                "payment_intent": f"pi_for_{session_id}",
                "amount_minor": amount_minor, "refund_status": "succeeded",
                "livemode": False}
        self.refunds[idempotency_key] = resp
        return resp

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
        if self.fail_verify:
            raise RuntimeError("stripe down")
        if session_id in self.paid:
            return {"status": "ok", "session_id": session_id,
                    "payment_status": "paid",
                    "amount_total": self.paid[session_id],
                    "currency": "usd", "livemode": False}
        return {"status": "ok", "session_id": session_id,
                "payment_status": "unpaid", "amount_total": 0,
                "currency": "usd", "livemode": False}


def build(db, connect=None):
    store = StateStore(db)
    escrow = ESCROW.build()
    store.register_modules("escrow", ESCROW_MODULES)
    store.restore("escrow", escrow)
    stripe = FakeStripe()
    custody = EscrowCustody(store, escrow,
                            create_checkout=stripe.create_checkout,
                            verify_session=stripe.verify_session,
                            execute_refund=stripe.create_refund,
                            connect=connect)
    return store, escrow, stripe, custody


def open_escrow(escrow, amount=1000, payee="agent:supplier-9",
                currency="USD", fee_bps=1000):
    # fee_bps=1000 keeps third-party fixtures at/above the EC10 esc-fee-v1
    # floor (79 minor for a 1000-minor escrow at the 'new' tier: 29
    # processing + 30 fixed + 20 margin); viridis:* payees are exempt.
    r = escrow.process_sync({"action": "open", "payer": "agent:buyer-1",
                             "payee": payee, "amount_minor": amount,
                             "currency": currency, "terms": "1 job",
                             "fee_bps": fee_bps})
    return r["data"]["escrow_id"]


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "state.db")


# --------------------------- EC1 --------------------------------------- #
def test_ec1_checkout_exact_amount_and_metadata(db):
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow, amount=1234)
    r = custody.create_funding_checkout(eid)
    assert r["status"] == "ok"
    assert r["amount_minor"] == 1234
    assert r["session_id"].startswith("cs_test_")


@pytest.mark.parametrize("setup,reason", [
    ("unknown", "unknown_escrow"),
    ("funded_state", "not_open"),
    ("currency", "currency_mismatch"),
])
def test_ec1_only_open_usd_escrows(db, setup, reason):
    _, escrow, stripe, custody = build(db)
    if setup == "unknown":
        target = "esc_nope"
    elif setup == "funded_state":
        target = open_escrow(escrow)
        escrow.process_sync({"action": "fund", "escrow_id": target})
    else:
        target = open_escrow(escrow, currency="EUR")
    r = custody.create_funding_checkout(target)
    assert r["status"] == "error"
    assert r["error_type"] == reason


# --------------------------- EC2 --------------------------------------- #
def test_ec2_unpaid_session_never_funds(db):
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow)
    custody.create_funding_checkout(eid)
    r = custody.confirm_funding(eid)                 # nothing was paid
    assert r["error_type"] == "not_paid"
    assert escrow.process_sync(
        {"action": "status", "escrow_id": eid})["data"]["state"] == "OPEN"


def test_ec2_underpaid_session_never_funds(db):
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow, amount=1000)
    co = custody.create_funding_checkout(eid)
    stripe.pay(co["session_id"], 999)
    r = custody.confirm_funding(eid)
    assert r["error_type"] == "underpaid"


def test_ec2_paid_session_funds_through_core_state_machine(db):
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow, amount=1000)
    co = custody.create_funding_checkout(eid)
    stripe.pay(co["session_id"], 1000)
    r = custody.confirm_funding(eid)
    assert r["status"] == "ok" and r["cash"] is True
    esc = escrow.process_sync({"action": "status", "escrow_id": eid})["data"]
    assert esc["state"] == "FUNDED"
    audit = escrow.process_sync({"action": "verify_audit", "escrow_id": eid})
    assert audit["data"]["valid"] is True             # E7 chain intact


# --------------------------- EC3 / PG17 -------------------------------- #
def test_ec3_only_verified_fundings_count_as_cash(db):
    _, escrow, stripe, custody = build(db)
    cash = open_escrow(escrow, amount=500, fee_bps=1200)  # >= EC10 floor 55
    internal = open_escrow(escrow, amount=700)
    co = custody.create_funding_checkout(cash)
    stripe.pay(co["session_id"], 500)
    custody.confirm_funding(cash)
    escrow.process_sync({"action": "fund", "escrow_id": internal})  # old rail
    s = custody.status()
    assert s["cash_funded_escrows"] == 1
    assert s["cash_funded_minor"] == 500              # internal one excluded


# --------------------------- EC4 --------------------------------------- #
def test_ec4_replay_and_cross_escrow_session_reuse(db):
    _, escrow, stripe, custody = build(db)
    e1 = open_escrow(escrow, amount=1000)
    e2 = open_escrow(escrow, amount=1000)
    co = custody.create_funding_checkout(e1)
    stripe.pay(co["session_id"], 1000)
    first = custody.confirm_funding(e1)
    replay = custody.confirm_funding(e1)              # idempotent
    assert first["duplicate"] is False and replay["duplicate"] is True
    assert replay["session_id"] == first["session_id"]
    stolen = custody.confirm_funding(e2, session_id=co["session_id"])
    assert stolen["error_type"] == "session_already_used"


# --------------------------- EC5 --------------------------------------- #
def test_ec5_third_party_release_certifies_net_of_frozen_fee(db):
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow, amount=1000, payee="agent:supplier-9")
    co = custody.create_funding_checkout(eid)
    stripe.pay(co["session_id"], 1000)
    custody.confirm_funding(eid)
    escrow.process_sync({"action": "release", "escrow_id": eid})
    inst = custody.settlement_instruction(eid)
    assert inst["type"] == "payout"
    assert inst["gross_minor"] == 1000
    assert inst["fee_minor"] == 100                   # frozen at open (E3), >= EC10 floor
    assert inst["net_minor"] == 900
    assert inst["executed"] is False                  # certified, NOT executed
    again = custody.settlement_instruction(eid)
    assert again["duplicate"] is True                 # idempotent


def test_ec5_viridis_payee_release_is_pure_revenue(db):
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow, amount=400, payee="viridis:protogen")
    co = custody.create_funding_checkout(eid)
    stripe.pay(co["session_id"], 400)
    custody.confirm_funding(eid)
    escrow.process_sync({"action": "release", "escrow_id": eid})
    inst = custody.settlement_instruction(eid)
    assert inst["type"] == "revenue_recognized"
    assert inst["revenue_minor"] == 400
    assert inst["executed"] is True                   # nothing to move


def test_ec5_refund_certifies_original_session(db):
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow, amount=800, fee_bps=1000)
    co = custody.create_funding_checkout(eid)
    stripe.pay(co["session_id"], 800)
    custody.confirm_funding(eid)
    escrow.process_sync({"action": "refund", "escrow_id": eid})
    inst = custody.settlement_instruction(eid)
    assert inst["type"] == "refund"
    assert inst["session_id"] == co["session_id"]
    assert inst["refund_minor"] == 800
    # refund-to-originator executes autonomously (EC5, 2026-07-19):
    # a REAL Stripe refund is issued, not just bookkeeping
    assert inst["executed"] is True
    assert inst["scope"] == "same_party_refund"
    assert inst["executed_at"] is not None
    assert inst["refund_id"].startswith("re_")
    assert stripe.refund_calls == 1                   # money actually moved
    # idempotent: replay returns the record, never a second Stripe refund
    again = custody.settlement_instruction(eid)
    assert again["duplicate"] is True
    assert stripe.refund_calls == 1
    # mark_executed is now a no-op idempotent confirmation for refunds
    confirm = custody.mark_executed(eid)
    assert confirm["duplicate"] is True
    assert confirm["executed_at"] == inst["executed_at"]


def test_ec5_refund_rail_failure_fails_closed_then_retries(db):
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow, amount=800, fee_bps=1000)
    co = custody.create_funding_checkout(eid)
    stripe.pay(co["session_id"], 800)
    custody.confirm_funding(eid)
    escrow.process_sync({"action": "refund", "escrow_id": eid})
    stripe.fail_refund = True
    r = custody.settlement_instruction(eid)
    assert r["status"] == "error"                     # fail-closed
    assert eid not in custody.state.instructions      # nothing recorded
    stripe.fail_refund = False
    ok = custody.settlement_instruction(eid)          # retry succeeds
    assert ok["status"] == "ok" and ok["executed"] is True
    assert stripe.refund_calls == 2                   # 1 failed + 1 real


def test_ec5_internal_ledger_escrows_have_no_cash_instructions(db):
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow)
    escrow.process_sync({"action": "fund", "escrow_id": eid})   # old rail
    escrow.process_sync({"action": "release", "escrow_id": eid})
    inst = custody.settlement_instruction(eid)
    assert inst["error_type"] == "not_custody_funded"


def test_ec5_mark_executed_idempotent(db):
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow, amount=1000)
    co = custody.create_funding_checkout(eid)
    stripe.pay(co["session_id"], 1000)
    custody.confirm_funding(eid)
    escrow.process_sync({"action": "release", "escrow_id": eid})
    custody.settlement_instruction(eid)
    a = custody.mark_executed(eid)
    b = custody.mark_executed(eid)
    assert a["duplicate"] is False and a["executed"] is True
    assert b["duplicate"] is True
    assert b["executed_at"] == a["executed_at"]


# ----------------- EC5 x CR: Connect-rail payouts ----------------------- #
from connect_rail import ConnectRail                     # noqa: E402


class FakeConnectStripe:
    """Injectable Connect rail functions (stripe_payments P8-P12 shape)."""

    def __init__(self, payouts_enabled=True):
        self.payouts_enabled = payouts_enabled
        self.accounts: dict = {}      # idempotency_key -> account resp
        self.transfers: dict = {}     # idempotency_key -> transfer resp
        self.transfer_calls = 0
        self.fail_transfer = False

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
        if self.fail_transfer:
            return {"status": "error", "error_type": "stripe_error",
                    "message": "stripe down"}
        prior = self.transfers.get(idempotency_key)    # Stripe Idempotency-Key
        if prior is not None:
            return prior
        resp = {"status": "ok",
                "transfer_id": f"tr_test_{len(self.transfers) + 1:06d}",
                "destination": destination, "amount_minor": amount_minor,
                "transfer_group": transfer_group, "livemode": False}
        self.transfers[idempotency_key] = resp
        return resp


def build_connect(db, payouts_enabled=True):
    store = StateStore(db)
    escrow = ESCROW.build()
    store.register_modules("escrow", ESCROW_MODULES)
    store.restore("escrow", escrow)
    stripe = FakeStripe()
    fc = FakeConnectStripe(payouts_enabled=payouts_enabled)
    rail = ConnectRail(store,
                       create_connect_account=fc.create_connect_account,
                       create_account_link=fc.create_account_link,
                       get_connect_account=fc.get_connect_account,
                       create_transfer=fc.create_transfer)
    custody = EscrowCustody(store, escrow,
                            create_checkout=stripe.create_checkout,
                            verify_session=stripe.verify_session,
                            execute_refund=stripe.create_refund,
                            connect=rail)
    return store, escrow, stripe, fc, rail, custody


def _fund_and_release(escrow, stripe, custody, payee="agent:supplier-9"):
    eid = open_escrow(escrow, amount=1000, payee=payee)
    co = custody.create_funding_checkout(eid)
    stripe.pay(co["session_id"], 1000)
    custody.confirm_funding(eid)
    escrow.process_sync({"action": "release", "escrow_id": eid})
    return eid


def test_ec5_cr_onboarded_payee_payout_auto_executes(db):
    _, escrow, stripe, fc, rail, custody = build_connect(db)
    ob = rail.begin_onboarding("agent:supplier-9")
    assert ob["status"] == "ok" and ob["onboarding_url"]
    eid = _fund_and_release(escrow, stripe, custody)
    inst = custody.settlement_instruction(eid)
    assert inst["type"] == "payout"
    assert inst["rail"] == "connect"
    assert inst["scope"] == "third_party_licensed_rail"
    assert inst["executed"] is True                   # autonomous
    assert inst["transfer_id"].startswith("tr_")
    assert inst["net_minor"] == 900                   # fee still frozen (E3)
    assert fc.transfer_calls == 1
    again = custody.settlement_instruction(eid)       # idempotent
    assert again["duplicate"] is True
    assert fc.transfer_calls == 1                     # never re-pays
    confirm = custody.mark_executed(eid)              # no-op confirmation
    assert confirm["duplicate"] is True


def test_ec5_cr_not_onboarded_falls_back_to_certified_manual(db):
    _, escrow, stripe, fc, rail, custody = build_connect(db)
    # no begin_onboarding for this payee
    eid = _fund_and_release(escrow, stripe, custody)
    inst = custody.settlement_instruction(eid)
    assert inst["rail"] == "manual"
    assert inst["executed"] is False                  # still human-gated
    assert "action_for_justin" in inst
    assert "begin_payout_onboarding" in inst["onboarding_hint"]
    assert fc.transfer_calls == 0                     # rail never touched


def test_ec5_cr_incomplete_onboarding_falls_back_with_requirements(db):
    _, escrow, stripe, fc, rail, custody = build_connect(
        db, payouts_enabled=False)
    rail.begin_onboarding("agent:supplier-9")         # started, not finished
    eid = _fund_and_release(escrow, stripe, custody)
    inst = custody.settlement_instruction(eid)
    assert inst["rail"] == "manual"
    assert inst["executed"] is False
    assert inst["onboarding_requirements_due"] == ["external_account"]
    assert fc.transfer_calls == 0                     # CR2 blocked pre-send


def test_ec5_cr_transient_rail_failure_fails_closed_then_retries(db):
    _, escrow, stripe, fc, rail, custody = build_connect(db)
    rail.begin_onboarding("agent:supplier-9")
    eid = _fund_and_release(escrow, stripe, custody)
    fc.fail_transfer = True
    r = custody.settlement_instruction(eid)
    assert r["status"] == "error"                     # fail-closed
    assert eid not in custody.state.instructions      # NOT locked to manual
    fc.fail_transfer = False
    ok = custody.settlement_instruction(eid)          # retry -> autonomous
    assert ok["status"] == "ok" and ok["executed"] is True
    assert ok["rail"] == "connect"


# --------------------------- EC6 --------------------------------------- #
def test_ec6_stripe_failure_refuses_never_crashes_never_funds(db):
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow)
    co = custody.create_funding_checkout(eid)
    stripe.pay(co["session_id"], 1000)
    stripe.fail_verify = True
    r = custody.confirm_funding(eid)
    assert r["status"] == "error"
    assert r["error_type"] == "verify_failed"
    assert escrow.process_sync(
        {"action": "status", "escrow_id": eid})["data"]["state"] == "OPEN"


# --------------------------- EC7 --------------------------------------- #
def test_ec7_funding_survives_restart(db):
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow, amount=1000)
    co = custody.create_funding_checkout(eid)
    stripe.pay(co["session_id"], 1000)
    custody.confirm_funding(eid)

    # ---- restart: fresh escrow core + custody, same db ----
    store2 = StateStore(db)
    escrow2 = ESCROW.build()
    store2.register_modules("escrow", ESCROW_MODULES)
    store2.restore("escrow", escrow2)
    custody2 = EscrowCustody(store2, escrow2,
                             create_checkout=stripe.create_checkout,
                             verify_session=stripe.verify_session)
    assert escrow2.process_sync(
        {"action": "status", "escrow_id": eid})["data"]["state"] == "FUNDED"
    replay = custody2.confirm_funding(eid)            # EC4 across restart
    assert replay["duplicate"] is True
    assert custody2.status()["cash_funded_minor"] == 1000


def test_ec7_persist_failure_reverts_funding_record(db):
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow, amount=1000)
    co = custody.create_funding_checkout(eid)
    stripe.pay(co["session_id"], 1000)
    custody.store.save_many = lambda cores: False
    r = custody.confirm_funding(eid)
    assert r["error_type"] == "persist_failed"
    assert eid not in custody.state.funded            # reverted, retryable


# --------------------------- EC8 --------------------------------------- #
def test_ec8_no_key_material_in_any_envelope(db):
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow)
    blob = str(custody.create_funding_checkout(eid)) \
        + str(custody.confirm_funding(eid)) + str(custody.status())
    assert "sk_live" not in blob and "sk_test" not in blob
    assert "api_key" not in blob.lower()


# --------------------------- EC11 -------------------------------------- #
def test_ec11_stale_terminal_checkout_is_visible_without_secrets(db):
    _, escrow, _, custody = build(db)
    eid = open_escrow(escrow, amount=1000)
    custody.state.checkouts[eid] = {
        "session_id": "cs_live_NEVER_EXPOSE",
        "url": "https://checkout.stripe.com/private",
        "amount_minor": 1000,
        "payee": "test:payee-1",
        "livemode": True,
        "created_at": "2026-07-19T18:34:22Z",
    }
    escrow.process_sync({"action": "fund", "escrow_id": eid})
    escrow.process_sync({"action": "refund", "escrow_id": eid})

    before = copy.deepcopy(custody.state.__dict__)
    report = custody.checkout_lifecycle_report(
        now=datetime(2026, 7, 30, 20, 0, tzinfo=timezone.utc))
    record = report["records"][0]
    assert record["escrow_id"] == eid
    assert record["local_escrow_state"] == "REFUNDED"
    assert record["payee_class"] == "internal_test"
    assert record["lifecycle"] == "stale_terminal_escrow"
    assert record["age_hours"] > 26
    assert record["recommended_action"] == \
        "pull_verify_then_archive_local_record"
    assert report["boundaries"]["stripe_mutated"] is False
    assert report["boundaries"]["custody_state_mutated"] is False
    assert custody.state.__dict__ == before
    encoded = json.dumps(report)
    assert "cs_live_NEVER_EXPOSE" not in encoded
    assert "checkout.stripe.com" not in encoded
    assert "test:payee-1" not in encoded


def test_ec11_provider_expired_and_paid_states_are_unambiguous(db):
    _, escrow, _, custody = build(db)
    eid = open_escrow(escrow, amount=1000)
    custody.state.checkouts[eid] = {
        "session_id": "cs_live_PRIVATE",
        "url": "https://checkout.stripe.com/private",
        "amount_minor": 1000,
        "payee": "agent:supplier",
        "livemode": True,
        "created_at": "2026-07-19T18:34:22Z",
    }
    observed = datetime(2026, 7, 30, 20, 0, tzinfo=timezone.utc)
    custody._verify_session = lambda _sid: {
        "status": "ok",
        "checkout_status": "expired",
        "payment_status": "unpaid",
        "expires_at": 1785000000,
    }
    expired = custody.checkout_lifecycle_report(
        verify_provider=True, now=observed)["records"][0]
    assert expired["lifecycle"] == "provider_expired_unpaid"
    assert expired["recommended_action"] == \
        "review_then_archive_local_record"
    assert expired["provider_expiration_authorized"] is False
    assert expired["local_archive_authorized"] is False

    custody._verify_session = lambda _sid: {
        "status": "ok",
        "checkout_status": "complete",
        "payment_status": "paid",
    }
    paid = custody.checkout_lifecycle_report(
        verify_provider=True, now=observed)["records"][0]
    assert paid["lifecycle"] == "paid_unconfirmed"
    assert paid["recommended_action"] == \
        "confirm_funding_do_not_expire"


def test_ec11_provider_failure_blocks_cleanup_recommendation(db):
    _, escrow, _, custody = build(db)
    eid = open_escrow(escrow, amount=1000)
    custody.state.checkouts[eid] = {
        "session_id": "cs_live_PRIVATE",
        "amount_minor": 1000,
        "payee": "agent:supplier",
        "livemode": True,
        "created_at": "2026-07-19T18:34:22Z",
    }
    custody._verify_session = lambda _sid: {
        "status": "error",
        "error_type": "stripe_error",
    }
    report = custody.checkout_lifecycle_report(
        verify_provider=True,
        now=datetime(2026, 7, 30, 20, 0, tzinfo=timezone.utc),
    )
    record = report["records"][0]
    assert record["lifecycle"] == "provider_check_error"
    assert record["recommended_action"] == \
        "restore_provider_read_before_action"


def test_ec1_below_stripe_minimum_refused_with_guidance(db):
    """A 25-minor escrow cannot be charged by Stripe (min ~$0.50): refuse
    with an actionable batch-prepay message, never an opaque 400 (EC1/EC6)."""
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow, amount=25)
    r = custody.create_funding_checkout(eid)
    assert r["status"] == "error"
    assert r["error_type"] == "below_stripe_minimum"
    assert r["minimum_minor"] == 50
    assert "larger escrow" in r["message"]


# ----------------------- EC10 (esc-fee-v1) ------------------------------ #
from escrow_custody import FEE_SCHEDULE                  # noqa: E402


def test_ec10_below_floor_refused_with_actionable_tiered_guidance(db):
    """A 1%-fee escrow to a new third party is below cost+margin — refused
    BEFORE cash enters, naming the tier, the required fee_bps, and the
    discount path (EC10). The old flat-50 floor would have passed a
    negative-margin settlement here."""
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow, amount=10000, fee_bps=100)  # fee 100 < floor
    r = custody.create_funding_checkout(eid)
    assert r["status"] == "error"
    assert r["error_type"] == "fee_below_floor"
    # floor = ceil(10000*290/10000)+30+ceil(10000*200/10000) = 290+30+200
    assert r["fee_floor_minor"] == 520
    assert r["required_fee_bps"] == 520
    assert r["payee_tier"] == "new" and r["margin_bps"] == 200
    assert r["fee_schedule_version"] == "esc-fee-v1"
    assert "begin_payout_onboarding" in r["message"]      # discount path


def test_ec10_connect_onboarded_payee_earns_lower_floor(db):
    _, escrow, stripe, fc, rail, custody = build_connect(db)
    rail.begin_onboarding("agent:supplier-9")
    # floor drops to 290+30+150 = 470: fee 500 now clears it...
    eid = open_escrow(escrow, amount=10000, fee_bps=500)
    r = custody.create_funding_checkout(eid)
    assert r["status"] == "ok"
    assert r["payee_tier"] == "connect_onboarded"         # EC10 stamp
    assert r["fee_schedule_version"] == "esc-fee-v1"
    # ...but the same fee is refused for a payee who has NOT onboarded
    eid2 = open_escrow(escrow, amount=10000, fee_bps=500,
                       payee="agent:never-onboarded")
    r2 = custody.create_funding_checkout(eid2)
    assert r2["error_type"] == "fee_below_floor"
    assert r2["payee_tier"] == "new"


def test_ec10_verified_track_record_earns_lowest_floor(db):
    store, escrow, stripe, fc, rail, _ = build_connect(db)
    deliveries = {"agent:supplier-9": 12}                 # >= threshold
    custody = EscrowCustody(store, escrow,
                            create_checkout=stripe.create_checkout,
                            verify_session=stripe.verify_session,
                            execute_refund=stripe.create_refund,
                            connect=rail,
                            verified_stats=lambda p: deliveries.get(p, 0))
    rail.begin_onboarding("agent:supplier-9")
    # floor 290+30+100 = 420: fee 450 clears only at the verified tier
    eid = open_escrow(escrow, amount=10000, fee_bps=450)
    r = custody.create_funding_checkout(eid)
    assert r["status"] == "ok"
    assert r["payee_tier"] == "connect_verified"
    # a payee below the delivery threshold stays at connect_onboarded
    deliveries["agent:supplier-9"] = 9
    eid2 = open_escrow(escrow, amount=10000, fee_bps=450)
    r2 = custody.create_funding_checkout(eid2)
    assert r2["error_type"] == "fee_below_floor"
    assert r2["payee_tier"] == "connect_onboarded"


def test_ec10_verified_stats_adapter_sync_and_fail_safe():
    """The gateway's connect_verified tier reads delivery counts sync
    from the verified core's V7 surface; unknown payees and errors
    resolve to 0 (no discount — fail-safe, never fail-open)."""
    from escrow_custody import verified_stats_from_core

    class FakeVerifiedCore:
        def _list_services(self, d):
            return {"status": "ok", "data": {"count": 3, "services": [
                {"provider": "riverside-robotics", "calls_ok": 7},
                {"provider": "riverside-robotics", "calls_ok": 5},
                {"provider": "someone-else", "calls_ok": 99}]}}

    stats = verified_stats_from_core(FakeVerifiedCore())
    assert stats("riverside-robotics") == 12          # summed across services
    assert stats("unknown-payee") == 0

    class BrokenCore:
        def _list_services(self, d):
            raise RuntimeError("boom")

    assert verified_stats_from_core(BrokenCore())("x") == 0


def test_ec10_viridis_payee_exempt_from_fee_floor(db):
    """viridis:* payees: whole amount is revenue, processing is COGS — a
    1%-fee escrow cash-funds fine (EC10 exemption, ex-EC9)."""
    _, escrow, stripe, custody = build(db)
    eid = open_escrow(escrow, amount=1000, payee="viridis:protogen",
                      fee_bps=100)
    r = custody.create_funding_checkout(eid)
    assert r["status"] == "ok"
    assert r["payee_tier"] == "viridis_exempt"


def test_ec10_proof_no_passing_settlement_is_negative_margin(db):
    """Structural proof: for any amount and any tier, the MINIMUM fee that
    passes EC10 still nets Viridis >= the tier margin after real card
    processing (2.9% + 30c of the whole amount). The old flat-50 floor
    fails this for every amount above ~$7."""
    _, escrow, stripe, custody = build(db)
    amounts = [100, 317, 1000, 5000, 10000, 99999, 1_000_000]
    for margin_name, margin in FEE_SCHEDULE["margin_bps"].items():
        for amount in amounts:
            floor = (-(-amount * 290 // 10000) + 30
                     + -(-amount * margin // 10000))
            processing = amount * 0.029 + 30              # true card cost
            net = floor - processing
            assert net >= amount * margin / 10000 - 2, (
                f"negative/thin margin at A={amount} tier={margin_name}: "
                f"floor={floor} processing={processing:.1f} net={net:.1f}")
            assert net > 0
    # and the module computes the same floor the proof uses
    got, tier, m = custody._fee_floor_minor(10000, "agent:supplier-9")
    assert (got, tier, m) == (520, "new", 200)
