#!/usr/bin/env python3
"""
PaymentGate — freemium x402-style gating for the fleet's sellable services.

Published listings promise "free to call today"; this keeps that promise while
wiring the revenue rail: every day each gated agent serves FREE_CALLS_PER_DAY
calls free, then returns a structured payment_required envelope (never a
crash) with both payment paths — the gateway's Stripe create_payment tool
(human) and the x402 idiom (A2A). Every call, allowed or refused, is metered
through the fleet's OWN agent-metering core, and each day's usage is frozen
into a real invoice at rollover: the fleet dogfoods its own rails on real
traffic.

--- INVARIANTS (spec-invariance contract) ---
PG1  The first N state-changing calls per UTC day succeed free
     (N = FREE_CALLS_PER_DAY env, default 10).
PG2  Beyond N, process() returns {status:"error",
     error_type:"payment_required", ...} including amount_minor, currency,
     and both payment instructions — never raises, never silently drops.
PG3  Read-only actions (ungateable vocabulary: describe/health handled
     upstream; per-payload actions in READ_ACTIONS) are never gated and
     never counted.
PG4  Every gated-agent call (allowed AND refused) is recorded on the
     fleet's own metering core, idempotent on event_id.
PG5  Gate counters live on the gated core (attribute) so the StateStore
     persists them: quotas survive restarts; refusals persist too.
PG6  Only the agents explicitly attached are gated — trust and settlement
     rails are never wired through the gate.
PG7  Day rollover closes the previous day's meter period into an
     immutable invoice (exactly-once via metering's own guarantees).
PG8  Metering failures degrade gracefully: a metering error never blocks
     or fails the service call (logged; surfaced via status()).
PG9  Prepaid credits are consumed AFTER the free tier, one per
     state-changing call; a call served on credit is never refused and
     never produces a payment_required envelope.
PG10 redeem_payment is pull-verified against Stripe (payment_status must
     be 'paid') and idempotent on session_id: a replay returns the
     original grant and never double-credits. credits =
     floor(amount_paid / per-call price); a payment below one call's
     price is rejected, never rounded up to a free call.
PG11 Credits persist (StateStore) and survive day rollover — a paid
     balance never expires at midnight.
PG12 Every metered event carries server-derived caller classification
     (consumer_class/channel/caller/is_test from request_context, G6) and
     every gate-created meter is origin="gateway" (write-protected in the
     metering core). Classification is transport-derived only — never read
     from tool payloads — and its absence degrades to "unknown", never to
     an error (metering stays PG8-graceful).
PG13 A2A rail: a state-changing call past the free tier that carries
     payment_ref=<escrow_id> naming an escrow that is FUNDED, payable to
     "viridis:<name>", in USD, and amount_minor >= the per-call price, has
     that escrow consumed (released through the escrow core's OWN
     exactly-once state machine, E6 — never bypassed) for
     credits = floor(amount_minor / price) >= 1, exactly once per escrow.
     The call is then served through the ordinary prepaid-credit path (PG9)
     and metered "ok". Consumption never reads classification from the
     payload (PG12 stays inviolate); the billing origin is visible in
     status()["a2a_escrow"] and in reconciliation, not in channel.
PG14 A payment_ref that is unknown, unfunded, underfunded, refunded,
     payable to a different agent, in a non-USD currency, or already
     consumed/released is refused with the standard payment_required
     envelope carrying an explicit a2a.refusal_reason — never a free pass,
     never a crash, never a partial grant.
PG15 Escrow-verification failures (escrow rail not wired, escrow core
     raising, malformed reference, persistence failure mid-consume) degrade
     to refusal — fail-closed. The mirror image of PG8: a metering failure
     never blocks a legitimate call, and an escrow failure never grants one.
     Errors are surfaced via status()["a2a_escrow"]["errors"].
PG16 Escrow consumption is idempotent on escrow id (persisted
     consumed_escrows, mirroring PG10's redeemed_sessions): a replayed
     payment_ref never grants a second batch of credits; the original grant
     record is retained and reported. payment_ref is always stripped from
     the payload before it reaches the wrapped core.
PG17 Real-cash settlement over this rail exists ONLY through the custody
     bridge (escrow_custody.py, EC1-EC8): an escrow counts as cash iff it
     was funded through a pull-verified PAID Stripe Checkout session
     recorded in the persisted custody registry. Escrows funded any other
     way remain a closed-loop internal ledger and are reported as such
     (RV6 split). Cash out (third-party payouts, refunds) is never
     executed by software — only certified for the account owner (EC5).
PG18 Free-tier accounting is PER CALLER IDENTITY (PG12 transport-derived:
     "internal:<name>", or the "ext:<hash>" ip+ua fingerprint; never from
     payloads): each identity gets its own N free calls per UTC day, so one
     caller exhausting its allowance never starves a different evaluator.
     Identity-less requests share the single "unknown" pool of N (exactly
     the pre-PG18 behavior — all existing PG1/PG2 semantics preserved for
     context-less calls). Anti-rotation bound: the AGGREGATE free grant
     across all ext:*/unknown identities is capped at
     FREE_ANON_POOL_MULTIPLIER x N per agent-day (default 5N), and the
     per-caller table is size-bounded — rotating fingerprints cannot mint
     unlimited free calls. Credits, subscriptions, and the a2a rail are
     unaffected; rollover resets all counters (PG7).
PG19 SELF-TEACHING 402: every payment_required envelope's payment.a2a
     carries a batch_hint teaching escrow batching — one larger FUNDED
     escrow prepays floor(amount_minor / price_minor) calls (exactly the
     PG13 credit grant), stating the agent's price, the 50-minor Stripe
     Checkout cash-funding minimum (EC1) and the 50-minor EC9 fee floor
     for third-party settlement. Additive only: no pre-PG19 envelope key
     changes shape or meaning.
PG20 CONVERSION TELEMETRY: every 402 refusal is countable at the gate —
     per agent per UTC day, status() reports refusals_today and the number
     of DISTINCT refused caller identities (PG12 transport-derived; bounded
     by the PG18 table bound with an explicit overflow bucket, so rotating
     fingerprints cannot grow state), alongside the cumulative conversion
     denominators that already exist (escrows consumed, sessions redeemed).
     Counters live in the same persisted gate dict (PG5) and reset at
     rollover (PG7). Additive only — no existing status() key changes.
PG21 SEAT UPSELL: a freemium payment_required envelope for a caller who
     has been refused SEAT_HINT_REFUSALS (3) or more times today gains
     payment.subscription_hint pointing at the /seats B2B plans — repeat
     paywall hits are the subscription funnel's warmest leads. Never on
     the subscription_overage path (they already have a seat). Additive
     only; below the threshold the envelope is byte-identical to PG19.
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import os
import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("viridis.payment_gate")

# actions that are never gated/counted (introspection & read surface)
READ_ACTIONS = frozenset({
    "status", "list", "verify_audit", "describe", "health",
    "list_capabilities", "get", "usage_summary", "sla_report",
    "get_report", "list_reports", "get_stats",          # smartscale reads
    "get_plan", "list_plans", "get_design", "list_designs",  # protogen reads
    "list_rule_packs", "get_rule_pack", "verify_result",      # audit-engine reads
    "list_factor_packs", "get_factor_pack", "classify_activity",  # GHG reads
    "list_assemblies", "get_assembly",                         # takeoff reads
    "list_material_pack", "get_material_pack", "describe_agent",
    "list_frameworks", "get_framework",                        # disclosure reads
    "get_receipt", "verify_receipts", "list_services",
    "service_stats",                                           # verified-relay reads
})

# Network-effect pricing 2026-07-12 (Energy AI /PRICING-NETWORK-EFFECT-2026-07-12.md):
# per-call prices sized to fit inside an agent's default budget covenant --
# adoption first, margin on team/custom tiers. Raise via the pre-committed
# volume/dependency triggers in that doc, never ad hoc.
PRICE_MINOR = {          # per-call list price once the free tier is exhausted
    "smartscale": 50,    # $0.50 / measurement (was $5.00 pre-network)
    "protogen": 100,     # $1.00 / CAD job     (was $3.00 pre-network)
    "taxcredit-engine": 200,  # $2.00 / auditable tax-credit scenario
    "ghg-ledger": 100,        # $1.00 / auditable GHG inventory
    "quantity-takeoff": 50,   # $0.50 / auditable material takeoff
    "disclosure-compiler": 200,  # $2.00 / auditable disclosure draft
    "narrative-engine": 50,   # $0.50 / narrative draft (agent-market micro)
    "regulatory-radar": 25,   # $0.25 / applicability check (cheap high-volume)
    "verified": 2,            # $0.02 / verified relay call (bps-style volume play)
}
DEFAULT_PRICE_MINOR = 100
GATE_ATTR = "_payment_gate_state"   # lives on the core -> StateStore persists
# PG18: anonymous/fingerprint identities share a bounded aggregate free pool
# (multiplier x free_calls per agent-day) and a bounded identity table.
ANON_POOL_MULTIPLIER = int(os.environ.get("FREE_ANON_POOL_MULTIPLIER", "5"))
CALLER_TABLE_MAX = 500
# PG21: a caller refused this many times in one day gets the seat upsell.
SEAT_HINT_REFUSALS = 3
SEATS_URL = "https://mcp.viridisconservation.com/seats"


def _is_anon_key(key: str) -> bool:
    return key == "unknown" or key.startswith("ext:")


def _utc_day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


class PaymentGate:
    """Freemium gate + metering dogfood for sellable agents."""

    def __init__(self, store, metering_core, free_calls_per_day: Optional[int] = None,
                 subscription_core=None,
                 account_key_getter: Optional[Callable[[], Optional[str]]] = None,
                 request_id_factory: Optional[Callable[[], str]] = None,
                 escrow_core=None, escrow_persist_key: str = "escrow"):
        self.store = store
        self.metering = metering_core
        self.subscriptions = subscription_core
        self.account_key_getter = account_key_getter or (lambda: None)
        self.request_id_factory = request_id_factory or (lambda: uuid.uuid4().hex)
        self.free_calls = (free_calls_per_day if free_calls_per_day is not None
                           else int(os.environ.get("FREE_CALLS_PER_DAY", "10")))
        self._errors: Dict[str, str] = {}
        self._subscription_errors: Dict[str, str] = {}
        self.attached = []
        self._cores: Dict[str, Any] = {}   # PG9/PG10: redeem needs the gated core
        # PG13-PG16: the a2a settlement rail. Optional — absent, every
        # payment_ref is refused fail-closed (PG15), never crashes.
        self.escrow = escrow_core
        self.escrow_persist_key = escrow_persist_key
        self._a2a_errors: Dict[str, str] = {}

    # ------------------------------------------------------------------ #
    def _payment_required(self, name: str, day: str, used: int,
                          subscription_overage: bool = False,
                          a2a_refusal: Optional[dict] = None,
                          caller_refusals: int = 0) -> dict:
        price = PRICE_MINOR.get(name, DEFAULT_PRICE_MINOR)
        if subscription_overage:
            message = (f"The active subscription's included monthly quota for "
                       f"{name} is exhausted. Overage is {price} minor units "
                       "per call; redeem prepaid credits, then retry.")
        else:
            message = (f"Free tier exhausted for {name} today "
                       f"({used}/{self.free_calls} free calls used, UTC day {day}). "
                       "Pay per call to continue.")
        envelope = {
            "status": "error",
            "error_type": "payment_required",           # PG2
            "http_equivalent": 402,
            "message": message,
            "amount_minor": price,
            "currency": "USD",
            "billing_path": ("subscription_overage" if subscription_overage
                             else "per_call_freemium"),
            "payment": {
                "human": {
                    "method": "stripe_checkout",
                    "mcp_endpoint": "https://mcp.viridisconservation.com/payments/mcp",
                    "tool": "create_payment",
                    "args_hint": {"amount_cents": price,
                                  "product_name": f"viridis {name} call"},
                    "then": ("after paying, call redeem_payment(session_id, "
                             f"agent='{name}') on the same endpoint — credits "
                             "apply instantly, 1 credit per call"),
                },
                "a2a": {
                    "method": "x402",
                    "note": ("Open+fund an escrow via "
                             "https://mcp.viridisconservation.com/escrow/mcp "
                             "payable to viridis:" + name +
                             ", then retry with payment_ref=<escrow_id>."),
                    "batch_hint": {                                # PG19
                        "how": (f"one LARGER funded escrow prepays "
                                f"floor(amount_minor / {price}) {name} "
                                "calls in a single settlement — open it "
                                "once, then reuse the same "
                                "payment_ref=<escrow_id> until the "
                                "credits are spent"),
                        "price_minor": price,
                        "example": {"escrow_amount_minor": price * 10,
                                    "calls_prepaid": 10},
                        "cash_note": ("cash funding via escrow_checkout "
                                      "has a 50-minor ($0.50) Stripe "
                                      "Checkout minimum (EC1), and "
                                      "third-party settlement carries the "
                                      "50-minor EC9 fee floor — one batch "
                                      "escrow pays each once instead of "
                                      "per call"),
                    },
                },
            },
            "free_tier_resets": "00:00 UTC",
            **({"a2a": a2a_refusal} if a2a_refusal else {}),   # PG14
        }
        if (not subscription_overage
                and caller_refusals >= SEAT_HINT_REFUSALS):     # PG21
            envelope["payment"]["subscription_hint"] = {
                "note": (f"you have hit this paywall {caller_refusals} "
                         f"times today — a B2B seat includes a monthly "
                         f"{name} quota at a lower effective per-call "
                         "price than pay-as-you-go"),
                "seats_url": SEATS_URL,
                "plans": "5 checkout-ready plans; subscribe once, every "
                         "caller on your account key is covered",
            }
        return envelope

    def _subscription_decision(self, name: str) -> Optional[dict]:
        """Resolve and durably finalize one seat decision, if authenticated.

        A subscription reservation can hold the core's transaction lock even
        when its decision is a per-call fallback (for example, a pull-refresh
        changed lifecycle state). Every non-null reservation token therefore
        follows the strict save-then-commit / rollback protocol before this
        method returns. Any ambiguity or failure returns ``None`` and the
        existing freemium gate runs exactly once.
        """
        if self.subscriptions is None:
            return None
        try:
            account_key = self.account_key_getter()
        except Exception as exc:
            self._subscription_errors[name] = (
                f"account_context: {type(exc).__name__}")
            return None
        if not isinstance(account_key, str) or not account_key:
            return None
        try:
            account_id = self.subscriptions.resolve_account_key(account_key)
        except Exception as exc:
            self._subscription_errors[name] = (
                f"account_resolution: {type(exc).__name__}")
            return None
        if not account_id:
            return None

        token = None
        try:
            request_id = self.request_id_factory()
            decision = self.subscriptions.reserve_entitlement(
                account_id, name, request_id,
                PRICE_MINOR.get(name, DEFAULT_PRICE_MINOR))
            if not isinstance(decision, dict):
                raise TypeError("subscription decision is not an object")
            token = decision.get("reservation_token")
            # Do not finalize here. The branch must remain one transaction:
            # included/fallback persists only subscription state, while a
            # credit-funded overage atomically persists BOTH subscription
            # usage and the gated core's decremented credit balance.
            return decision
        except Exception as exc:
            if token:
                try:
                    self.subscriptions.rollback_reservation(token)
                except Exception:
                    logger.critical(
                        "payment_gate[%s]: subscription reservation rollback failed",
                        name)
            self._subscription_errors[name] = (
                f"entitlement: {type(exc).__name__}")
            logger.warning(
                "payment_gate[%s]: subscription lookup failed (%s); "
                "falling through to per-call freemium", name, type(exc).__name__)
            return None

    def _rollback_subscription(self, name: str, decision: Optional[dict],
                               reason: Optional[str]) -> bool:
        token = (decision or {}).get("reservation_token") \
            if isinstance(decision, dict) else None
        if not token:
            return True
        try:
            ok = self.subscriptions.rollback_reservation(token)
        except Exception as exc:
            self._subscription_errors[name] = (
                f"rollback: {type(exc).__name__}")
            logger.critical("payment_gate[%s]: subscription rollback failed",
                            name)
            return False
        if not ok:
            self._subscription_errors[name] = "rollback: rejected"
            return False
        if reason:
            self._subscription_errors[name] = reason
        else:
            self._subscription_errors.pop(name, None)
        return True

    def _persist_subscription(self, name: str, decision: Optional[dict]) -> bool:
        """Durably finalize an included or lifecycle-fallback reservation."""
        token = (decision or {}).get("reservation_token") \
            if isinstance(decision, dict) else None
        if not token:  # already-durable idempotent replay / no state change
            self._subscription_errors.pop(name, None)
            return True
        saved = self.store.save("subscriptions", self.subscriptions)
        if not saved:
            self._rollback_subscription(name, decision,
                                        "durability: save_failed")
            return False
        try:
            committed = self.subscriptions.commit_reservation(token)
        except Exception as exc:
            committed = False
            self._subscription_errors[name] = (
                f"durability: commit_{type(exc).__name__}")
        if committed:
            self._subscription_errors.pop(name, None)
            return True

        # A post-save commit rejection is defensive-impossible for the core's
        # protocol. Attempt an in-memory rollback and persist compensation so
        # the caller is never granted against ambiguous state.
        self._rollback_subscription(name, decision,
                                    "durability: commit_failed")
        self.store.save("subscriptions", self.subscriptions)
        return False

    def _lock(self, name: str) -> "asyncio.Lock":
        """Per-agent lock so fire-and-forget metering tasks (sync-core path)
        can't race two create_meter calls for the same day."""
        if not hasattr(self, "_locks"):
            self._locks = {}
        if name not in self._locks:
            self._locks[name] = asyncio.Lock()
        return self._locks[name]

    def _billing_lock(self, name: str) -> "threading.RLock":
        """Serialize prepaid-credit mutation across sync/async tool paths."""
        if not hasattr(self, "_billing_locks"):
            self._billing_locks = {}
        if name not in self._billing_locks:
            self._billing_locks[name] = threading.RLock()
        return self._billing_locks[name]

    # ---------------- PG18: per-caller free tier ----------------------- #
    def _try_grant_free_call(self, gate: dict) -> bool:
        """Grant one free call to the current transport-derived caller
        identity (PG12/PG18). True = counted and allowed; False = this
        caller's allowance (or the bounded anonymous pool) is exhausted and
        the call falls through to credits / payment_required. Context-less
        calls land in the shared "unknown" pool — pre-PG18 behavior."""
        ctx = self._caller_context()
        key = ctx.get("caller") or "unknown"
        by_caller = gate.setdefault("used_by_caller", {})
        used = by_caller.get(key, 0)
        if used >= self.free_calls:                       # own allowance spent
            return False
        if _is_anon_key(key):
            anon_total = sum(v for k, v in by_caller.items()
                             if _is_anon_key(k))
            if anon_total >= self.free_calls * ANON_POOL_MULTIPLIER:
                return False                              # rotation bound
            if key not in by_caller and len(by_caller) >= CALLER_TABLE_MAX:
                return False                              # table bound
        by_caller[key] = used + 1
        return True

    # ---------------- PG20: conversion telemetry ----------------------- #
    def _record_refused_caller(self, gate: dict) -> int:
        """PG20: remember WHICH caller identity was refused today, so
        status() can report distinct refused callers (the funnel top).
        Bounded like PG18's table: once the map is full, new identities
        aggregate into an explicit overflow bucket — rotation cannot grow
        state. Returns THIS caller's refusal count today (PG21 reads it);
        0 on any failure. Never raises; telemetry must not break a
        refusal."""
        try:
            key = self._caller_context().get("caller") or "unknown"
            refused_by = gate.setdefault("refused_by_caller", {})
            if key not in refused_by and len(refused_by) >= CALLER_TABLE_MAX:
                key = "overflow:anon-rotation"
            refused_by[key] = refused_by.get(key, 0) + 1
            return refused_by[key]
        except Exception:                                   # PG8 family
            logger.warning("payment_gate: refused-caller telemetry failed",
                           exc_info=True)
            return 0

    # ---------------- PG13-PG16: a2a escrow settlement ----------------- #
    def _try_consume_escrow(self, name: str, core: Any, gate: dict,
                            payment_ref: Any) -> Optional[dict]:
        """Verify and consume a funded escrow for prepaid credits.

        Returns None on success or replay-of-known-grant (the ordinary PG9
        credit path then serves the call), or a PG14 refusal-detail dict
        {"payment_ref", "refusal_reason"} — the caller folds it into the
        payment_required envelope. Fail-closed everywhere (PG15): any
        ambiguity, exception, or persistence failure refuses; nothing here
        can crash the service call or grant a free pass.

        Consumption releases the escrow through the escrow core's own state
        machine (E4/E6 — never bypassed). Two windows are accepted and
        documented: (a) an external release of the same escrow between our
        FUNDED check and our release lands funds with the same payee
        (viridis:<name>) either way, so a grant remains economically
        correct; (b) an external refund in that window makes our release
        return an error envelope -> refusal. Both are safe outcomes.
        """
        with self._billing_lock(name):
            try:
                if not isinstance(payment_ref, str) or not payment_ref.strip():
                    return {"payment_ref": str(payment_ref)[:64],
                            "refusal_reason": "bad_payment_ref"}          # PG14
                ref = payment_ref.strip()
                consumed = gate.setdefault("consumed_escrows", {})
                prior = consumed.get(ref)
                if prior is not None:                                      # PG16
                    logger.info("payment_gate[%s]: escrow %s replayed — "
                                "original grant of %s credits stands, no "
                                "double-credit", name, ref, prior["credits"])
                    return None
                if self.escrow is None:                                    # PG15
                    self._a2a_errors[name] = "a2a_rail_unavailable"
                    return {"payment_ref": ref,
                            "refusal_reason": "a2a_rail_unavailable"}
                status = self.escrow.process_sync(
                    {"action": "status", "escrow_id": ref})
                if status.get("status") != "ok":                          # PG14
                    return {"payment_ref": ref,
                            "refusal_reason": "unknown_escrow"}
                esc = status.get("data") or {}
                price = PRICE_MINOR.get(name, DEFAULT_PRICE_MINOR)
                if esc.get("payee") != f"viridis:{name}":                 # PG14
                    return {"payment_ref": ref,
                            "refusal_reason": "wrong_payee"}
                if esc.get("currency") != "USD":                          # PG14
                    return {"payment_ref": ref,
                            "refusal_reason": "currency_mismatch"}
                state = esc.get("state")
                if state != "FUNDED":                                     # PG14
                    reason = {"OPEN": "unfunded",
                              "REFUNDED": "refunded",
                              "RELEASED": "already_consumed_or_released",
                              "DISPUTED": "disputed"}.get(
                                  state, "not_consumable")
                    return {"payment_ref": ref, "refusal_reason": reason}
                amount = esc.get("amount_minor")
                if not isinstance(amount, int) or amount < price:         # PG14
                    return {"payment_ref": ref,
                            "refusal_reason": "underfunded",
                            "amount_minor_required": price}
                released = self.escrow.process_sync({
                    "action": "release", "escrow_id": ref,
                    "delivery_proof": {
                        "consumed_by": "payment_gate",
                        "agent": name, "day": gate.get("day"),
                        "credits": amount // price}})
                if (released.get("status") != "ok"
                        or (released.get("data") or {}).get("state")
                        != "RELEASED"):                                    # PG15
                    self._a2a_errors[name] = (
                        f"release_refused: {released.get('error_type')}")
                    return {"payment_ref": ref,
                            "refusal_reason": "escrow_release_failed"}
                credits = amount // price                                  # PG13
                gate["credits"] = gate.get("credits", 0) + credits
                consumed[ref] = {
                    "credits": credits, "amount_minor": amount,
                    "consumed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                 time.gmtime())}
                if len(consumed) > 1000:                       # bounded (PG16)
                    oldest = sorted(consumed.items(),
                                    key=lambda kv: kv[1].get(
                                        "consumed_at", ""))[0][0]
                    consumed.pop(oldest, None)
                saved = self.store.save_many({
                    name: core, self.escrow_persist_key: self.escrow})
                if not saved:                                              # PG15
                    # Fail-closed: revert the grant. The in-memory escrow
                    # stays RELEASED but un-persisted; a restart restores
                    # FUNDED and the retry succeeds cleanly.
                    gate["credits"] -= credits
                    consumed.pop(ref, None)
                    self._a2a_errors[name] = "durability: group_save_failed"
                    return {"payment_ref": ref,
                            "refusal_reason": "settlement_not_durable"}
                self._a2a_errors.pop(name, None)
                logger.info("payment_gate[%s]: escrow %s consumed for %s "
                            "credits (%s minor, internal ledger — not cash)",
                            name, ref, credits, amount)
                return None                                                # PG13
            except Exception as exc:                                       # PG15
                self._a2a_errors[name] = (
                    f"consume: {type(exc).__name__}: {exc}")
                logger.warning("payment_gate[%s]: escrow consume failed "
                               "(%s) — refused, never granted", name, exc)
                return {"payment_ref": str(payment_ref)[:64],
                        "refusal_reason": "escrow_verify_failed"}

    def _commit_credit_overage(self, name: str, core: Any, gate: dict,
                               decision: dict) -> bool:
        """Atomically debit one credit and persist exact overage usage.

        The subscription reservation arrives with its transaction lock held.
        ``save_many`` is the sole durable commit point for the two affected
        aggregates. Failure restores the credit, rolls back quota/overage, and
        refuses the call; it never falls into a free path.
        """
        token = decision.get("reservation_token")
        if not token:
            # A replayed durable overage must not debit a second credit or
            # serve twice. Production request IDs are unique, so refusing is
            # the only safe outcome for this defensive branch.
            self._subscription_errors[name] = "overage: replay_refused"
            return False
        with self._billing_lock(name):
            if gate.get("credits", 0) <= 0:
                self._rollback_subscription(name, decision, None)
                return False
            gate["credits"] -= 1
            gate["subscription_overage"] += 1
            saved = self.store.save_many({
                "subscriptions": self.subscriptions, name: core})
            if not saved:
                gate["credits"] += 1
                gate["subscription_overage"] -= 1
                self._rollback_subscription(
                    name, decision, "durability: group_save_failed")
                return False
            try:
                committed = self.subscriptions.commit_reservation(token)
            except Exception as exc:
                committed = False
                self._subscription_errors[name] = (
                    f"durability: group_commit_{type(exc).__name__}")
            if committed:
                self._subscription_errors.pop(name, None)
                return True

            # Compensate both persisted aggregates if the in-memory commit
            # protocol ever rejects after the SQLite group transaction.
            gate["credits"] += 1
            gate["subscription_overage"] -= 1
            self._rollback_subscription(
                name, decision, "durability: group_commit_failed")
            self.store.save_many({
                "subscriptions": self.subscriptions, name: core})
            return False

    @staticmethod
    def _is_included_waiver(decision: Optional[dict]) -> bool:
        """Accept only the core's complete, unambiguous included path."""
        return bool(
            isinstance(decision, dict)
            and decision.get("path") == "included_quota_waiver"
            and decision.get("entitled") is True
            and decision.get("waive_per_call_charge") is True
            and decision.get("should_run_per_call_gate") is False
            and decision.get("bypass_anonymous_freemium") is False
            and decision.get("requires_direct_overage_charge") is False)

    @staticmethod
    def _is_direct_overage(decision: Optional[dict], price_minor: int) -> bool:
        """Accept only one exact, list-price overage path (never ambiguous)."""
        return bool(
            isinstance(decision, dict)
            and decision.get("path") == "overage_meter"
            and decision.get("entitled") is True
            and decision.get("waive_per_call_charge") is False
            and decision.get("should_run_per_call_gate") is True
            and decision.get("bypass_anonymous_freemium") is True
            and decision.get("requires_direct_overage_charge") is True
            and decision.get("overage_minor") == price_minor)

    @staticmethod
    def _caller_context() -> dict:
        """PG12/G6: server-derived caller classification for the current
        request. ContextVars propagate through both metering paths (await in
        the async wrapper; loop.create_task copies the context on the
        fire-and-forget sync path), mirroring how account_auth's bearer
        already reaches _subscription_decision. Absent context (tests,
        in-process) degrades to unknown — never an error."""
        try:
            from request_context import current_request_context
            return current_request_context()
        except Exception:
            return {"consumer_class": "unknown", "channel": "unknown",
                    "caller": None, "is_test": False}

    async def _meter(self, name: str, gate: dict, event_suffix: str,
                     outcome: str, core: Any = None) -> None:
        """PG4/PG7/PG8: record on the fleet's own metering core. `core` is
        passed on the fire-and-forget path so the meter_id mutation gets
        persisted even though the caller's save already ran."""
        try:
            ctx = self._caller_context()  # PG12: read before awaiting
            async with self._lock(name):
                day = gate["day"]
                if not gate.get("meter_id"):
                    m = await self.metering.process({
                        "action": "create_meter", "_origin": "gateway",
                        "provider": f"viridis:{name}", "consumer": "public-free-tier",
                        "unit": "call",
                        "price_minor_per_unit": PRICE_MINOR.get(name, DEFAULT_PRICE_MINOR)})
                    if m.get("status") == "ok":
                        gate["meter_id"] = m["data"]["meter_id"]
                if gate.get("meter_id"):
                    await self.metering.process({
                        "action": "record_usage", "meter_id": gate["meter_id"],
                        "event_id": f"{name}-{day}-{event_suffix}",
                        "quantity": 1, "outcome": outcome,
                        "_origin": "gateway",
                        "consumer_class": ctx.get("consumer_class", "unknown"),
                        "channel": ctx.get("channel", "unknown"),
                        "caller": ctx.get("caller"),
                        "is_test": bool(ctx.get("is_test", False))})
                self._errors.pop(name, None)
            if core is not None:
                self.store.save(name, core)
        except Exception as e:  # PG8
            self._errors[name] = f"metering: {type(e).__name__}: {e}"
            logger.warning("payment_gate[%s]: metering failed (%s) — "
                           "service call unaffected", name, e)

    async def _meter_subscription_waiver(self, name: str, gate: dict,
                                         decision: dict, outcome: str,
                                         core: Any = None) -> None:
        """Meter included-seat usage on a zero-price audit meter.

        Quota accounting remains authoritative in subscriptions-agent. This
        parallel fleet-meter record makes the waiver visible without accruing
        a second per-call invoice (ST3: never double charge).
        """
        try:
            ctx = self._caller_context()  # PG12
            async with self._lock(name):
                day = gate["day"]
                if not gate.get("subscription_meter_id"):
                    created = await self.metering.process({
                        "action": "create_meter", "_origin": "gateway",
                        "provider": f"viridis:{name}",
                        "consumer": "active-subscription-included-quota",
                        "unit": "call", "price_minor_per_unit": 0})
                    if created.get("status") == "ok":
                        gate["subscription_meter_id"] = created["data"]["meter_id"]
                if gate.get("subscription_meter_id"):
                    request_id = str(decision.get("request_id", "unknown"))
                    await self.metering.process({
                        "action": "record_usage",
                        "meter_id": gate["subscription_meter_id"],
                        "event_id": f"{name}-{day}-seat-{request_id}",
                        "quantity": 1, "outcome": outcome,
                        "_origin": "gateway",
                        "consumer_class": ctx.get("consumer_class", "unknown"),
                        "channel": ctx.get("channel", "unknown"),
                        "caller": ctx.get("caller"),
                        "is_test": bool(ctx.get("is_test", False))})
                self._errors.pop(name, None)
            if core is not None:
                self.store.save(name, core)
        except Exception as exc:  # PG8
            self._errors[name] = (
                f"subscription-metering: {type(exc).__name__}: {exc}")
            logger.warning("payment_gate[%s]: subscription metering failed "
                           "(%s) — service call unaffected", name, exc)

    async def _rollover(self, name: str, gate: dict, today: str) -> None:
        """PG7: freeze yesterday's usage into an invoice, start fresh."""
        for meter_key, billing_path in (
                ("meter_id", "per_call"),
                ("subscription_meter_id", "subscription_included")):
            old_meter = gate.get(meter_key)
            if not old_meter:
                continue
            try:
                inv = await self.metering.process({"action": "close_period",
                                                   "meter_id": old_meter,
                                                   "_origin": "gateway"})
                if inv.get("status") == "ok":
                    gate.setdefault("invoices", []).append(
                        {"day": gate["day"], "meter_id": old_meter,
                         "billing_path": billing_path,
                         "amount_minor": inv["data"].get("amount_minor", 0),
                         "invoice": inv["data"]})
                    gate["invoices"] = gate["invoices"][-90:]  # bounded
            except Exception as e:  # PG8
                self._errors[name] = f"rollover: {type(e).__name__}: {e}"
        gate["day"] = today
        gate["used"] = 0
        gate["used_by_caller"] = {}                    # PG18
        gate["refused"] = 0
        gate["refused_by_caller"] = {}                 # PG20
        gate["meter_id"] = None
        gate["subscription_meter_id"] = None
        gate["subscription_waived"] = 0
        gate["subscription_overage"] = 0

    # ------------------------------------------------------------------ #
    def _run_coro_from_sync(self, name: str, coro) -> None:
        """Drive an async metering call from a sync core's wrapper.

        Two production realities (both observed):
        - Some MCP SDK builds run sync tools in worker threads (no loop) —
          asyncio.run works.
        - Others run sync tools ON the event-loop thread — asyncio.run
          raises; the loop is merely blocked, so we SCHEDULE the metering
          coroutine as a task and it runs as soon as our sync frame returns
          (fire-and-forget; PG4 becomes eventually-consistent, never lost —
          this was gate-errors 'metering(sync-ctx)' in prod before the fix).
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            try:
                asyncio.run(coro)
            except Exception as e:                       # PG8
                self._errors[name] = f"metering(sync): {e}"
                logger.warning("payment_gate[%s]: metering failed (%s) — "
                               "service call unaffected", name, e)
        else:
            loop.create_task(coro)                       # runs after we return

    def attach(self, name: str, core: Any) -> None:
        """Wrap core.process with the freemium gate (outermost wrapper —
        refusals never touch the core; StateStore's wrapper stays inner so
        allowed calls persist their own state). The wrapper matches the
        core's calling convention (sync cores like smartscale keep a sync
        process — their adapters call it without await)."""
        if not hasattr(core, GATE_ATTR):                       # PG5
            setattr(core, GATE_ATTR, {"day": _utc_day(), "used": 0,
                                      "refused": 0, "meter_id": None,
                                      "subscription_meter_id": None,
                                      "subscription_waived": 0,
                                      "subscription_overage": 0,
                                      "invoices": [], "credits": 0,
                                      "redeemed_sessions": {},
                                      "consumed_escrows": {},
                                      "used_by_caller": {},
                                      "refused_by_caller": {}})
        else:
            # Backward-compatible restore of snapshots written before seats.
            persisted = getattr(core, GATE_ATTR)
            persisted.setdefault("subscription_meter_id", None)
            persisted.setdefault("subscription_waived", 0)
            persisted.setdefault("subscription_overage", 0)
            persisted.setdefault("consumed_escrows", {})   # pre-PG13 snapshots
            persisted.setdefault("used_by_caller", {})     # pre-PG18 snapshots
            persisted.setdefault("refused_by_caller", {})  # pre-PG20 snapshots
        self._cores[name] = core
        inner = core.process

        def _is_read(input_data) -> bool:
            action = (input_data or {}).get("action") \
                if isinstance(input_data, dict) else None
            return action in READ_ACTIONS                       # PG3

        def _try_spend_credit(gate: dict) -> bool:
            """PG9: past the free tier, prepaid credits are consumed 1/call."""
            with self._billing_lock(name):
                if gate.get("credits", 0) > 0:
                    gate["credits"] -= 1
                    return True
            return False

        if inspect.iscoroutinefunction(inner):
            @functools.wraps(inner)
            async def process(input_data):
                if _is_read(input_data):
                    return await inner(input_data)
                gate = getattr(core, GATE_ATTR)
                # PG16: payment_ref is billing metadata for THIS gate — it
                # never reaches the wrapped core, whatever path serves the call.
                payment_ref = (input_data.pop("payment_ref", None)
                               if isinstance(input_data, dict) else None)
                today = _utc_day()
                if gate["day"] != today:
                    await self._rollover(name, gate, today)     # PG7 (credits survive: PG11)
                subscription = self._subscription_decision(name)
                if self._is_included_waiver(subscription):
                    if self._persist_subscription(name, subscription):
                        gate["subscription_waived"] += 1
                        await self._meter_subscription_waiver(
                            name, gate, subscription, "ok")
                        result = await inner(input_data)
                        self.store.save(name, core)
                        return result
                    subscription = None
                if self._is_direct_overage(
                        subscription, PRICE_MINOR.get(name, DEFAULT_PRICE_MINOR)):
                    # Active seats never receive a second anonymous daily free
                    # allowance after exhausting their monthly quota.
                    if not self._commit_credit_overage(
                            name, core, gate, subscription):
                        gate["refused"] += 1
                        self._record_refused_caller(gate)       # PG20
                        await self._meter(
                            name, gate,
                            f"overage-refused-{gate['refused']}",
                            "error")
                        self.store.save(name, core)
                        return self._payment_required(
                            name, today, gate["used"], subscription_overage=True)
                    await self._meter(
                        name, gate, f"overage-ok-{gate['subscription_overage']}",
                        "ok")
                    result = await inner(input_data)
                    self.store.save(name, core)
                    return result
                if isinstance(subscription, dict):
                    if subscription.get("path") == "per_call_fallback":
                        # A pull-refresh may have mutated lifecycle state and
                        # returned fallback with its lock held.
                        self._persist_subscription(name, subscription)
                    elif subscription.get("reservation_token"):
                        # Any malformed/ambiguous grant is rolled back and
                        # interpreted pessimistically as ordinary freemium.
                        self._rollback_subscription(
                            name, subscription, "entitlement: invalid_decision")
                if not self._try_grant_free_call(gate):         # PG1/PG2/PG18
                    a2a_refusal = None
                    if payment_ref is not None:                 # PG13-PG16
                        a2a_refusal = self._try_consume_escrow(
                            name, core, gate, payment_ref)
                    if not _try_spend_credit(gate):             # PG9
                        gate["refused"] += 1
                        n_ref = self._record_refused_caller(gate)  # PG20
                        await self._meter(name, gate,
                                          f"refused-{gate['refused']}", "error")
                        self.store.save(name, core)             # PG5
                        return self._payment_required(
                            name, today, gate["used"],
                            a2a_refusal=a2a_refusal,
                            caller_refusals=n_ref)              # PG21
                gate["used"] += 1
                await self._meter(name, gate, f"ok-{gate['used']}", "ok")  # PG4
                result = await inner(input_data)
                self.store.save(name, core)                     # PG5
                return result
        else:
            @functools.wraps(inner)
            def process(input_data):
                if _is_read(input_data):
                    return inner(input_data)
                gate = getattr(core, GATE_ATTR)
                # PG16: payment_ref never reaches the wrapped core.
                payment_ref = (input_data.pop("payment_ref", None)
                               if isinstance(input_data, dict) else None)
                today = _utc_day()
                if gate["day"] != today:
                    self._run_coro_from_sync(
                        name, self._rollover(name, gate, today))  # PG7 (credits survive: PG11)
                subscription = self._subscription_decision(name)
                if self._is_included_waiver(subscription):
                    if self._persist_subscription(name, subscription):
                        gate["subscription_waived"] += 1
                        self._run_coro_from_sync(
                            name, self._meter_subscription_waiver(
                                name, gate, subscription, "ok", core=core))
                        result = inner(input_data)
                        self.store.save(name, core)
                        return result
                    subscription = None
                if self._is_direct_overage(
                        subscription, PRICE_MINOR.get(name, DEFAULT_PRICE_MINOR)):
                    if not self._commit_credit_overage(
                            name, core, gate, subscription):
                        gate["refused"] += 1
                        self._record_refused_caller(gate)       # PG20
                        self._run_coro_from_sync(
                            name, self._meter(
                                name, gate,
                                f"overage-refused-{gate['refused']}",
                                "error", core=core))
                        self.store.save(name, core)
                        return self._payment_required(
                            name, today, gate["used"], subscription_overage=True)
                    self._run_coro_from_sync(
                        name, self._meter(
                            name, gate,
                            f"overage-ok-{gate['subscription_overage']}",
                            "ok", core=core))
                    result = inner(input_data)
                    self.store.save(name, core)
                    return result
                if isinstance(subscription, dict):
                    if subscription.get("path") == "per_call_fallback":
                        self._persist_subscription(name, subscription)
                    elif subscription.get("reservation_token"):
                        self._rollback_subscription(
                            name, subscription, "entitlement: invalid_decision")
                if not self._try_grant_free_call(gate):         # PG1/PG2/PG18
                    a2a_refusal = None
                    if payment_ref is not None:                 # PG13-PG16
                        a2a_refusal = self._try_consume_escrow(
                            name, core, gate, payment_ref)
                    if not _try_spend_credit(gate):             # PG9
                        gate["refused"] += 1
                        n_ref = self._record_refused_caller(gate)  # PG20
                        self._run_coro_from_sync(
                            name, self._meter(name, gate,
                                              f"refused-{gate['refused']}", "error",
                                              core=core))
                        self.store.save(name, core)             # PG5
                        return self._payment_required(
                            name, today, gate["used"],
                            a2a_refusal=a2a_refusal,
                            caller_refusals=n_ref)              # PG21
                gate["used"] += 1
                self._run_coro_from_sync(
                    name, self._meter(name, gate, f"ok-{gate['used']}", "ok",
                                      core=core))
                result = inner(input_data)
                self.store.save(name, core)                     # PG5
                return result

        core.process = process
        self.attached.append(name)

    # ------------------------------------------------------------------ #
    def redeem(self, session_id: str, agent: str, _verify=None) -> dict:
        """PG10: redeem a PAID Stripe Checkout session for prepaid call
        credits on a gated agent. Pull-based (no webhook): the session is
        verified against Stripe's API at redemption time. Idempotent on
        session_id — a replay returns the original grant, never double
        credits. credits = floor(amount_paid / per-call price), >= 1.
        `_verify` is injectable for tests only."""
        if not isinstance(session_id, str) or not session_id.strip():
            return {"status": "error", "error_type": "bad_session",
                    "message": "session_id is required"}
        core = self._cores.get(agent)
        if core is None:
            return {"status": "error", "error_type": "unknown_agent",
                    "message": f"'{agent}' is not a gated agent",
                    "gated_agents": list(self.attached)}
        gate = getattr(core, GATE_ATTR)
        prior = gate.setdefault("redeemed_sessions", {}).get(session_id)
        if prior is not None:                                   # PG10 idempotent
            return {"status": "ok", "duplicate": True, "agent": agent,
                    "credits_granted": prior["credits"],
                    "credits_balance": gate.get("credits", 0)}
        try:
            if _verify is None:
                import stripe_payments
                _verify = stripe_payments.verify_session
            v = _verify(session_id)
        except Exception as e:
            return {"status": "error", "error_type": "verify_failed",
                    "message": str(e)[:200]}
        if v.get("status") != "ok":
            return v
        if v.get("payment_status") != "paid":
            return {"status": "error", "error_type": "not_paid",
                    "message": f"checkout session is '{v.get('payment_status')}', not paid",
                    "session_id": session_id}
        price = PRICE_MINOR.get(agent, DEFAULT_PRICE_MINOR)
        credits = int(v.get("amount_total", 0)) // price
        if credits < 1:
            return {"status": "error", "error_type": "insufficient_amount",
                    "message": (f"paid {v.get('amount_total')} minor units; one "
                                f"{agent} call costs {price}"),
                    "amount_minor_required": price}
        gate["credits"] = gate.get("credits", 0) + credits
        gate["redeemed_sessions"][session_id] = {
            "credits": credits, "amount_minor": v.get("amount_total"),
            "redeemed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if len(gate["redeemed_sessions"]) > 1000:  # bounded
            oldest = sorted(gate["redeemed_sessions"].items(),
                            key=lambda kv: kv[1].get("redeemed_at", ""))[0][0]
            gate["redeemed_sessions"].pop(oldest, None)
        self.store.save(agent, core)                            # PG5/PG11
        return {"status": "ok", "duplicate": False, "agent": agent,
                "credits_granted": credits,
                "credits_balance": gate["credits"],
                "livemode": v.get("livemode")}

    def status(self) -> Dict[str, Any]:
        return {"gated_agents": list(self.attached),
                "free_calls_per_day": self.free_calls,
                "free_tier_policy": {                          # PG18
                    "per_caller": True,
                    "anon_pool_multiplier": ANON_POOL_MULTIPLIER,
                    "callers_seen_today": {
                        n: len(getattr(c, GATE_ATTR).get("used_by_caller", {}))
                        for n, c in self._cores.items()},
                },
                "prices_minor": {
                    name: PRICE_MINOR.get(name, DEFAULT_PRICE_MINOR)
                    for name in self.attached
                },
                "credits": {n: getattr(c, GATE_ATTR).get("credits", 0)
                            for n, c in self._cores.items()},
                "subscription_entitlements": {
                    "enabled": self.subscriptions is not None,
                    "errors": dict(self._subscription_errors),
                },
                "a2a_escrow": {                                # PG13-PG17
                    "enabled": self.escrow is not None,
                    "note": "cash iff custody-verified (PG17/EC3 — see "
                            "escrow_custody + reconcile_revenue); "
                            "otherwise internal ledger, not cash",
                    "consumed": {
                        n: {"escrows": len(g.get("consumed_escrows", {})),
                            "credits_granted": sum(
                                v["credits"]
                                for v in g.get("consumed_escrows",
                                               {}).values()),
                            "amount_minor": sum(
                                v["amount_minor"]
                                for v in g.get("consumed_escrows",
                                               {}).values())}
                        for n, c in self._cores.items()
                        for g in [getattr(c, GATE_ATTR)]},
                    "errors": dict(self._a2a_errors),
                },
                "conversion": {                                # PG20
                    "note": ("the 402 funnel, honestly split: refusals_today "
                             "and distinct refused callers reset at 00:00 UTC "
                             "(PG7) and persist across restarts (PG5); "
                             "escrows_consumed / sessions_redeemed are "
                             "cumulative. conversion = strangers who came "
                             "back with money after a 402."),
                    "per_agent": {
                        n: {"refusals_today": g.get("refused", 0),
                            "refused_callers_today":
                                len(g.get("refused_by_caller", {})),
                            "escrows_consumed_total":
                                len(g.get("consumed_escrows", {})),
                            "sessions_redeemed_total":
                                len(g.get("redeemed_sessions", {}))}
                        for n, c in self._cores.items()
                        for g in [getattr(c, GATE_ATTR)]},
                },
                "errors": dict(self._errors)}
