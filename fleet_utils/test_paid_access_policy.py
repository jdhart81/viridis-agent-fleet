"""Invariants P1-P5 for the reference paid-access policy."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fleet_utils.paid_access_policy import (
    authorize_call, AccessDecision, PolicyConfig, DEFAULT_CONFIG,
)

AGENT, TOOL, PAYEE, PRICE = "regulatory-radar", "scan_regulations", "viridis:regulatory-radar", 25


def _cash_escrow(amount=PRICE, payee=PAYEE, state="FUNDED", kind="cash"):
    return {"state": state, "funding_kind": kind, "payee": payee, "amount_minor": amount}


# P2 — identified caller is free under the limit.
def test_identified_caller_free_under_limit():
    d = authorize_call(agent=AGENT, tool=TOOL, price_minor=PRICE,
                       caller_identity="wallet:0xabc", calls_today=9)
    assert d.allowed and d.payment_required is None


# P1 — anonymous caller gets zero free calls by default; farming is blocked.
def test_anonymous_caller_no_free_calls():
    d = authorize_call(agent=AGENT, tool=TOOL, price_minor=PRICE,
                       caller_identity=None, calls_today=0)
    assert not d.allowed
    assert d.payment_required["status"] == "payment_required"


def test_blank_identity_is_anonymous():
    d = authorize_call(agent=AGENT, tool=TOOL, price_minor=PRICE,
                       caller_identity="   ", calls_today=0)
    assert not d.allowed


# P3 — past the free tier, a self-asserted escrow does NOT satisfy the paywall.
def test_self_asserted_escrow_rejected_past_free_tier():
    esc = _cash_escrow(kind="self_asserted")
    d = authorize_call(agent=AGENT, tool=TOOL, price_minor=PRICE, expected_payee=PAYEE,
                       caller_identity="wallet:0xabc", calls_today=10, escrow_public=esc)
    assert not d.allowed


# P3 — a cash-equivalent escrow to the right payee for >= price satisfies it.
def test_cash_escrow_satisfies_paid_tier():
    d = authorize_call(agent=AGENT, tool=TOOL, price_minor=PRICE, expected_payee=PAYEE,
                       caller_identity="wallet:0xabc", calls_today=10,
                       escrow_public=_cash_escrow())
    assert d.allowed and "cash-equivalent" in d.reason


def test_x402_and_stripe_kinds_are_cash_equivalent():
    for kind in ("x402", "stripe"):
        d = authorize_call(agent=AGENT, tool=TOOL, price_minor=PRICE, expected_payee=PAYEE,
                           caller_identity="w", calls_today=10,
                           escrow_public=_cash_escrow(kind=kind))
        assert d.allowed, kind


def test_cash_escrow_wrong_payee_rejected():
    d = authorize_call(agent=AGENT, tool=TOOL, price_minor=PRICE, expected_payee=PAYEE,
                       caller_identity="w", calls_today=10,
                       escrow_public=_cash_escrow(payee="viridis:someone-else"))
    assert not d.allowed


def test_cash_escrow_underfunded_rejected():
    d = authorize_call(agent=AGENT, tool=TOOL, price_minor=PRICE, expected_payee=PAYEE,
                       caller_identity="w", calls_today=10,
                       escrow_public=_cash_escrow(amount=PRICE - 1))
    assert not d.allowed


def test_unfunded_cash_escrow_rejected():
    d = authorize_call(agent=AGENT, tool=TOOL, price_minor=PRICE, expected_payee=PAYEE,
                       caller_identity="w", calls_today=10,
                       escrow_public=_cash_escrow(state="OPEN"))
    assert not d.allowed


def test_stripe_credit_and_x402_flags_satisfy():
    d1 = authorize_call(agent=AGENT, tool=TOOL, price_minor=PRICE,
                        caller_identity="w", calls_today=10, stripe_credit_available=True)
    d2 = authorize_call(agent=AGENT, tool=TOOL, price_minor=PRICE,
                        caller_identity="w", calls_today=10, x402_paid=True)
    assert d1.allowed and d2.allowed


# P4 — denial carries a usable envelope naming both paths.
def test_payment_required_envelope_shape():
    d = authorize_call(agent=AGENT, tool=TOOL, price_minor=PRICE,
                       caller_identity="w", calls_today=10)
    env = d.payment_required
    assert env["agent"] == AGENT and env["tool"] == TOOL and env["price_minor"] == PRICE
    kinds = {o["kind"] for o in env["pay_options"]}
    assert {"stripe_checkout", "cash_escrow", "x402"} <= kinds


# P5 — pure/deterministic: same inputs, same decision.
def test_deterministic():
    kw = dict(agent=AGENT, tool=TOOL, price_minor=PRICE, caller_identity="w", calls_today=10)
    assert authorize_call(**kw) == authorize_call(**kw)


# Config holds current numbers and is the only place to change them.
def test_current_config_values():
    assert DEFAULT_CONFIG.free_calls_per_day == 10
    assert DEFAULT_CONFIG.anon_free_calls_per_day == 0
    assert DEFAULT_CONFIG.require_cash_for_paid is True


def test_relaxed_cash_requirement_is_opt_in():
    # With cash requirement relaxed, any FUNDED escrow to the payee is accepted.
    cfg = PolicyConfig(require_cash_for_paid=False)
    esc = {"state": "FUNDED", "funding_kind": "self_asserted", "payee": PAYEE, "amount_minor": PRICE}
    d = authorize_call(agent=AGENT, tool=TOOL, price_minor=PRICE, expected_payee=PAYEE,
                       caller_identity="w", calls_today=10, escrow_public=esc, config=cfg)
    assert d.allowed
