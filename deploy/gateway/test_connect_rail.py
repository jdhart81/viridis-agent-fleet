#!/usr/bin/env python3
"""
Tests for connect_rail.py (CR1-CR7) — real StateStore, injected Stripe
fakes. The structural gate is asserted directly: transfers happen ONLY to
registry accounts, ONLY when Stripe pull-verifies payouts_enabled, and
exactly once per purpose_key.

Run:  pytest deploy/gateway/test_connect_rail.py -q
"""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from connect_rail import ConnectRail            # noqa: E402
from state_store import StateStore              # noqa: E402


class FakeStripe:
    def __init__(self, payouts_enabled=True):
        self.payouts_enabled = payouts_enabled
        self.accounts: dict = {}     # idempotency_key -> resp (Stripe idem.)
        self.account_calls = 0
        self.transfers: dict = {}
        self.transfer_calls = 0
        self.verify_calls = 0
        self.fail_verify = False
        self.fail_transfer = False

    def create_connect_account(self, payee_ref, *, idempotency_key):
        self.account_calls += 1
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
        self.verify_calls += 1
        if self.fail_verify:
            raise RuntimeError("stripe down")
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
        prior = self.transfers.get(idempotency_key)
        if prior is not None:
            return prior
        resp = {"status": "ok",
                "transfer_id": f"tr_test_{len(self.transfers) + 1:06d}",
                "destination": destination, "amount_minor": amount_minor,
                "transfer_group": transfer_group, "livemode": False}
        self.transfers[idempotency_key] = resp
        return resp


def build(db, payouts_enabled=True):
    store = StateStore(db)
    fs = FakeStripe(payouts_enabled=payouts_enabled)
    rail = ConnectRail(store,
                       create_connect_account=fs.create_connect_account,
                       create_account_link=fs.create_account_link,
                       get_connect_account=fs.get_connect_account,
                       create_transfer=fs.create_transfer)
    return store, fs, rail


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "state.db")


# ---------------------------- CR1 --------------------------------------- #
def test_cr1_onboarding_idempotent_one_account_per_payee(db):
    _, fs, rail = build(db)
    a = rail.begin_onboarding("agent:supplier-9")
    b = rail.begin_onboarding("agent:supplier-9")     # re-begin
    assert a["status"] == b["status"] == "ok"
    assert a["account_id"] == b["account_id"]         # same account, forever
    assert len(fs.accounts) == 1                      # one Stripe account
    assert b["onboarding_url"]                        # fresh link each time


def test_cr1_persist_failure_reverts_and_retry_does_not_orphan(db):
    store, fs, rail = build(db)
    real_save = store.save
    store.save = lambda *a, **k: False
    r = rail.begin_onboarding("agent:supplier-9")
    assert r["error_type"] == "persist_failed"
    assert "agent:supplier-9" not in rail.state.payees   # reverted
    store.save = real_save
    ok = rail.begin_onboarding("agent:supplier-9")       # retry
    assert ok["status"] == "ok"
    # deterministic Idempotency-Key -> Stripe returned the SAME account
    assert len(fs.accounts) == 1
    assert fs.account_calls == 2


# ---------------------------- CR2 --------------------------------------- #
def test_cr2_transfer_pull_verifies_eligibility_every_time(db):
    _, fs, rail = build(db)
    rail.begin_onboarding("agent:supplier-9")
    fs.payouts_enabled = False                        # onboarding stalled
    r = rail.execute_transfer("agent:supplier-9", 950, "escrow-payout:e1")
    assert r["error_type"] == "payouts_not_enabled"
    assert r["requirements_currently_due"] == ["external_account"]
    assert fs.transfer_calls == 0                     # blocked BEFORE send
    fs.payouts_enabled = True                         # payee finishes
    ok = rail.execute_transfer("agent:supplier-9", 950, "escrow-payout:e1")
    assert ok["status"] == "ok"
    assert fs.verify_calls == 2                       # verified fresh both times


# ---------------------------- CR3 --------------------------------------- #
def test_cr3_exactly_once_per_purpose_key(db):
    _, fs, rail = build(db)
    rail.begin_onboarding("agent:supplier-9")
    first = rail.execute_transfer("agent:supplier-9", 950, "escrow-payout:e1")
    replay = rail.execute_transfer("agent:supplier-9", 950, "escrow-payout:e1")
    assert first["duplicate"] is False and replay["duplicate"] is True
    assert replay["transfer_id"] == first["transfer_id"]
    assert fs.transfer_calls == 1                     # Stripe hit once
    other = rail.execute_transfer("agent:supplier-9", 500, "escrow-payout:e2")
    assert other["transfer_id"] != first["transfer_id"]


def test_cr3_crash_between_send_and_persist_cannot_double_pay(db):
    store, fs, rail = build(db)
    rail.begin_onboarding("agent:supplier-9")
    real_save = store.save
    store.save = lambda *a, **k: False                # "crash" after send
    r = rail.execute_transfer("agent:supplier-9", 950, "escrow-payout:e1")
    assert r["error_type"] == "persist_failed"
    assert "escrow-payout:e1" not in rail.state.transfers   # reverted
    store.save = real_save
    ok = rail.execute_transfer("agent:supplier-9", 950, "escrow-payout:e1")
    assert ok["status"] == "ok"
    # Stripe's Idempotency-Key returned the SAME transfer — one payment
    assert len(fs.transfers) == 1
    assert ok["transfer_id"] == fs.transfers["escrow-payout:e1"]["transfer_id"]


# ---------------------------- CR4 --------------------------------------- #
def test_cr4_verify_failure_refuses_never_crashes_never_pays(db):
    _, fs, rail = build(db)
    rail.begin_onboarding("agent:supplier-9")
    fs.fail_verify = True
    r = rail.execute_transfer("agent:supplier-9", 950, "escrow-payout:e1")
    assert r["status"] == "error"
    assert fs.transfer_calls == 0


# ---------------------------- CR6 --------------------------------------- #
def test_cr6_transfers_only_to_registry_payees(db):
    _, fs, rail = build(db)
    r = rail.execute_transfer("agent:unknown", 950, "escrow-payout:e1")
    assert r["error_type"] == "not_onboarded"
    assert fs.transfer_calls == 0
    assert rail.can_pay("agent:unknown") is False


# ------------------- stripe_payments P8-P12 primitives ------------------- #
import stripe_payments                              # noqa: E402


def test_p8_money_moves_require_idempotency_key():
    r = stripe_payments.create_transfer("acct_x1", 950, idempotency_key="",
                                        api_key="sk_test_x")
    assert r["error_type"] == "bad_idempotency_key"
    r2 = stripe_payments.create_refund("cs_test_1", idempotency_key="short",
                                       api_key="sk_test_x")
    assert r2["error_type"] == "bad_idempotency_key"
    r3 = stripe_payments.create_connect_account("p", idempotency_key="x",
                                                api_key="sk_test_x")
    assert r3["error_type"] == "bad_idempotency_key"


def test_p10_transfer_destination_must_be_connected_account():
    r = stripe_payments.create_transfer("cus_notanacct", 950,
                                        idempotency_key="escrow-payout:e1",
                                        api_key="sk_test_x")
    assert r["error_type"] == "bad_destination"


def test_p12_no_key_refuses_never_crashes():
    import os
    saved = os.environ.pop("STRIPE_API_KEY", None)
    try:
        for r in (
            stripe_payments.create_transfer(
                "acct_x1", 950, idempotency_key="escrow-payout:e1"),
            stripe_payments.create_refund(
                "cs_test_1", idempotency_key="escrow-refund:e1"),
            stripe_payments.get_connect_account("acct_x1"),
            stripe_payments.create_connect_account(
                "p", idempotency_key="connect-acct:p"),
            stripe_payments.create_account_link("acct_x1"),
        ):
            assert r["error_type"] == "no_api_key"
    finally:
        if saved is not None:
            os.environ["STRIPE_API_KEY"] = saved


def test_p8_p10_transfer_posts_idempotency_header_and_form():
    seen = {}

    def transport(url, data, headers):
        seen["url"] = url
        seen["headers"] = headers
        seen["form"] = data.decode()
        return {"id": "tr_1x", "destination": "acct_x1", "amount": 950,
                "transfer_group": "esc_1", "livemode": False}

    r = stripe_payments.create_transfer(
        "acct_x1", 950, idempotency_key="escrow-payout:esc_1",
        transfer_group="esc_1", api_key="sk_test_secret",
        _transport=transport)
    assert r["status"] == "ok" and r["transfer_id"] == "tr_1x"
    assert seen["headers"]["Idempotency-Key"] == "escrow-payout:esc_1"
    assert "destination=acct_x1" in seen["form"]
    assert "amount=950" in seen["form"]
    # P6/P12: the key never appears in the returned envelope
    assert "sk_test_secret" not in str(r)


def test_p9_refund_targets_original_payment_intent_only():
    def get_transport(url, headers):
        return {"id": "cs_test_1", "payment_intent": "pi_abc123"}

    seen = {}

    def transport(url, data, headers):
        seen["form"] = data.decode()
        return {"id": "re_1x", "amount": 800, "status": "succeeded",
                "livemode": False}

    r = stripe_payments.create_refund(
        "cs_test_1", idempotency_key="escrow-refund:e1", amount_minor=800,
        api_key="sk_test_x", _transport=transport,
        _get_transport=get_transport)
    assert r["status"] == "ok" and r["refund_id"] == "re_1x"
    assert "payment_intent=pi_abc123" in seen["form"]
    # by construction there is no alternate-destination parameter
    assert "destination" not in seen["form"]


def test_p7_restricted_live_key_fallback_when_account_omits_livemode():
    def create_transport(url, data, headers):
        return {"id": "acct_live1"}

    created = stripe_payments.create_connect_account(
        "payee-1", idempotency_key="connect-acct:payee-1",
        api_key="rk_live_secret", _transport=create_transport)
    assert created["status"] == "ok"
    assert created["livemode"] is True

    def get_transport(url, headers):
        return {"id": "acct_live1", "payouts_enabled": True,
                "charges_enabled": True, "details_submitted": True,
                "requirements": {"currently_due": []}}

    verified = stripe_payments.get_connect_account(
        "acct_live1", api_key="rk_live_secret", _transport=get_transport)
    assert verified["status"] == "ok"
    assert verified["livemode"] is True


# ---------------------------- CR (durability) ---------------------------- #
def test_cr_registry_and_transfers_survive_restart(db):
    store, fs, rail = build(db)
    rail.begin_onboarding("agent:supplier-9")
    rail.execute_transfer("agent:supplier-9", 950, "escrow-payout:e1")

    store2 = StateStore(db)
    fs2 = FakeStripe()
    rail2 = ConnectRail(store2,
                        create_connect_account=fs2.create_connect_account,
                        create_account_link=fs2.create_account_link,
                        get_connect_account=fs2.get_connect_account,
                        create_transfer=fs2.create_transfer)
    assert rail2.can_pay("agent:supplier-9") is True
    replay = rail2.execute_transfer("agent:supplier-9", 950,
                                    "escrow-payout:e1")
    assert replay["duplicate"] is True                # CR3 across restarts
    assert fs2.transfer_calls == 0
    s = rail2.status()
    assert s["payees_onboarded"] == 1
    assert s["transfers_executed"] == 1
