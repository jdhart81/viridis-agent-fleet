"""Reference paid-access policy for gated fleet agents (pure, side-effect free).

This module makes the fleet's monetization contract explicit, auditable and
testable in the open. The hosted gateway composes it; it performs no counting,
I/O, payment verification or clock reads of its own — every input is passed in,
so the decision is deterministic and unit-testable.

WHY THIS EXISTS
---------------
The gated agents advertise a price "after N free calls/day", but the only thing
that distinguishes a *paid* call from a free one is the evidence the caller
brings. An escrow funded via the free agent-to-agent `fund` path carries no
verified value (funding_kind == "self_asserted"); only verified value
(CASH/STRIPE/X402, see agent-escrow-agent) should satisfy the paywall. And the
free tier must key on a stable caller identity (a wallet address or API key),
or it can be farmed indefinitely by rotating anonymous callers.

CONFIGURABLE, NOT POLICY
------------------------
Limits and prices live in ``PolicyConfig`` set to the fleet's CURRENT numbers
(10 free calls/day; per-agent prices passed in by the caller). Changing a free
tier or a price is a one-value edit and a SEPARATE decision — this module does
not change any number, and wiring it into the live gate is a separate deploy.

INVARIANTS (pinned by tests)
----------------------------
P1 No free call without an identified caller: anonymous callers get
   ``anon_free_calls_per_day`` (0 by default), so the free path cannot be
   farmed by rotating identities.
P2 An identified caller is allowed free up to ``free_calls_per_day`` (strictly
   less than the limit have been used today), independent of payment evidence.
P3 Past the free tier, a call is allowed ONLY with verified value: a redeemed
   Stripe credit, a settled x402 payment, OR a cash-equivalent escrow that
   names the right payee for at least the price. A self-asserted escrow alone
   is NOT sufficient.
P4 A denial returns a structured ``payment_required`` envelope (never raises),
   carrying the price and the available payment paths — the caller is told
   exactly what to do next.
P5 Pure: identical inputs always yield an identical decision; no I/O, no global
   state, no wall-clock read inside the decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Funding kinds that represent verified value actually moved. Must agree with
# agent-escrow-agent/src/core.py CASH_EQUIVALENT; kept as a local literal set so
# this module stays dependency-free and independently publishable.
CASH_EQUIVALENT_FUNDING = frozenset({"cash", "stripe", "x402"})


@dataclass(frozen=True)
class PolicyConfig:
    """Fleet monetization parameters, at their CURRENT live values.

    Editing these is a deliberate, separate decision — not part of wiring the
    policy in.
    """
    free_calls_per_day: int = 10
    anon_free_calls_per_day: int = 0  # free tier requires an identified caller
    require_cash_for_paid: bool = True  # self-asserted escrow never satisfies paid


DEFAULT_CONFIG = PolicyConfig()


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str
    # Present only when allowed is False; a ready-to-return payment_required body.
    payment_required: Optional[Dict[str, Any]] = None


def _caller_is_identified(caller_identity: Optional[str]) -> bool:
    return bool(caller_identity and str(caller_identity).strip())


def _escrow_satisfies(
    escrow_public: Optional[Dict[str, Any]],
    *,
    expected_payee: str,
    price_minor: int,
    require_cash: bool,
) -> bool:
    """A FUNDED escrow to the right payee for >= price.

    When ``require_cash`` is True (the default policy), the escrow must also be
    cash-equivalent — a self-asserted escrow never satisfies the paywall.
    """
    if not escrow_public:
        return False
    if escrow_public.get("state") != "FUNDED":
        return False
    if require_cash and escrow_public.get("funding_kind") not in CASH_EQUIVALENT_FUNDING:
        return False
    if escrow_public.get("payee") != expected_payee:
        return False
    return int(escrow_public.get("amount_minor", 0)) >= int(price_minor)


def _payment_required_envelope(
    *, agent: str, tool: str, price_minor: int, currency: str
) -> Dict[str, Any]:
    """Structured 402-idiom body: both payment paths, inline (P4)."""
    return {
        "status": "payment_required",
        "agent": agent,
        "tool": tool,
        "price_minor": int(price_minor),
        "currency": currency,
        "reason": "free tier exhausted; verified payment required",
        "pay_options": [
            {
                "kind": "stripe_checkout",
                "flow": "create_payment -> pay -> redeem_payment",
                "note": "instant prepaid credits once the session verifies as paid",
            },
            {
                "kind": "cash_escrow",
                "flow": "open_escrow -> escrow_checkout -> pay URL -> confirm_escrow_funding -> retry with payment_ref",
                "note": "only a cash-confirmed escrow satisfies the gate; a self-asserted fund does not",
            },
            {
                "kind": "x402",
                "flow": "settle the x402 route in Base USDC",
            },
        ],
    }


def authorize_call(
    *,
    agent: str,
    tool: str,
    price_minor: int,
    currency: str = "USD",
    caller_identity: Optional[str] = None,
    calls_today: int = 0,
    expected_payee: str = "",
    escrow_public: Optional[Dict[str, Any]] = None,
    stripe_credit_available: bool = False,
    x402_paid: bool = False,
    config: PolicyConfig = DEFAULT_CONFIG,
) -> AccessDecision:
    """Decide whether one gated call may proceed. Pure (P5), never raises (P4).

    Args:
        agent, tool: identifiers echoed into the payment_required envelope.
        price_minor: this call's price in minor units.
        caller_identity: wallet address or API key; None/empty = anonymous.
        calls_today: calls already served to this identity today (gate-counted).
        expected_payee: the escrow payee the gate requires for this agent.
        escrow_public: an escrow's public() record supplied as payment proof.
        stripe_credit_available: a redeemed Stripe credit covers this call.
        x402_paid: a settled x402 payment covers this call.
        config: limits/prices (defaults to current live values).
    """
    # Free tier (P1/P2) — identity-bound.
    free_limit = (
        config.free_calls_per_day
        if _caller_is_identified(caller_identity)
        else config.anon_free_calls_per_day
    )
    if calls_today < free_limit:
        return AccessDecision(True, "within free tier")

    # Paid tier (P3) — verified value only.
    if stripe_credit_available:
        return AccessDecision(True, "redeemed stripe credit")
    if x402_paid:
        return AccessDecision(True, "settled x402 payment")
    if _escrow_satisfies(
        escrow_public, expected_payee=expected_payee, price_minor=price_minor,
        require_cash=config.require_cash_for_paid,
    ):
        reason = (
            "cash-equivalent escrow verified"
            if config.require_cash_for_paid
            else "escrow accepted (cash requirement relaxed)"
        )
        return AccessDecision(True, reason)

    # Denied (P4).
    return AccessDecision(
        False,
        "free tier exhausted and no verified payment",
        payment_required=_payment_required_envelope(
            agent=agent, tool=tool, price_minor=price_minor, currency=currency
        ),
    )
