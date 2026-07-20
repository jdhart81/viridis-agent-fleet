"""
escrow_custody.py — PG17: real-cash custody for the a2a escrow rail.

Until this module, escrow settlement was a CLOSED-LOOP INTERNAL LEDGER: the
escrow core's `fund` action is a pure state transition, so "funded" carried
no money. This bridge makes funding real without touching the escrow core's
state machine (E1-E9 untouched, custody delegated to a rail adapter exactly
as the core's own docstring specifies):

  cash in   — a Stripe Checkout Session is created per escrow; the escrow is
              marked FUNDED only after the session is pull-verified PAID
              (same idiom as PG10). The cash sits in Viridis's Stripe
              balance, held against the escrow.
  cash out  — the autonomous-and-legal loop (2026-07-19, both waves;
              see docs/legal/
              THIRD_PARTY_PAYOUT_LICENSING_QUESTION_2026-07-19.md):
              REFUNDS execute autonomously as real Stripe refunds to the
              original session (refund-to-originator — the payer's own
              money). RELEASES to a Connect-ONBOARDED payee execute
              autonomously via Stripe's licensed Transfer rail
              (connect_rail.py — Stripe is the money transmitter,
              Viridis only instructs its licensed processor; net of the
              escrow's frozen 1% fee, E3). RELEASES to a payee who has
              NOT onboarded fall back to today's CERTIFIED INSTRUCTION
              that Justin executes manually — the only remaining
              human-gated leg, and it shrinks payee-by-payee as they
              onboard, not by policy change.

Revenue meaning (honest accounting, extends RV6):
  * custody-funded escrow released to a viridis:<agent> payee = REAL REVENUE
    (the cash is already ours; no payout exists).
  * custody-funded escrow to a third-party payee = held funds; Viridis's
    revenue is the frozen fee_minor, realized when Justin executes the
    certified payout.
  * escrows funded WITHOUT a verified paid session remain the internal
    ledger they always were, and are still reported as non-cash.
  * custody cash arrives through Checkout, so it is a SUBSET of Stripe
    settled_minor in reconciliation — labeled, never double-added.

--- INVARIANTS (spec-invariance contract) ---
EC1  create_funding_checkout only for an existing escrow in state OPEN with
     currency USD; the Checkout amount equals amount_minor exactly and the
     session carries metadata escrow_id. Recreating replaces the pending
     session (only the verified-paid one ever matters).
EC2  confirm_funding marks an escrow FUNDED only after verify_session
     reports payment_status == "paid" AND amount_total >= amount_minor.
     Anything less (unpaid, underpaid, verify error, no key) refuses
     fail-closed — an escrow is never funded on ambiguity.
EC3  A verified funding is recorded in a persisted custody registry
     (escrow_id -> session evidence). ONLY registry entries count as cash
     anywhere in reporting; everything else stays internal-ledger (PG17).
EC4  One paid session funds at most one escrow, and one escrow is funded by
     at most one session. confirm_funding is idempotent on both: replays
     return the original record, never a second funding.
EC5  Cash-out execution splits by counterparty AND rail (2026-07-19,
     both waves — this is the full autonomous-and-legal loop):
       - SAME-PARTY REFUND (REFUNDED): a REAL Stripe refund is issued
         against the original session (refund-to-originator — the
         payer's own money; no transmission to another person) and the
         instruction records executed=True, executed_at, refund_id,
         scope="same_party_refund". Idempotency-Key
         "escrow-refund:<escrow_id>" makes retries single-shot.
       - THIRD-PARTY PAYOUT, payee Connect-onboarded (connect_rail
         registry, CR1-CR7): the payout EXECUTES AUTONOMOUSLY via
         Stripe's licensed Transfer rail — Stripe, not Viridis, is the
         money transmitter; eligibility (payouts_enabled) is
         pull-verified at transfer time; exactly-once per escrow.
         Instruction records executed=True, transfer_id,
         rail="connect", scope="third_party_licensed_rail".
       - THIRD-PARTY PAYOUT, payee NOT onboarded (or onboarding
         incomplete): today's certified manual instruction, unchanged —
         executed=False, action_for_justin, rail="manual", gated behind
         the admin-token mark_executed. This is the ONLY fallback (no
         third path), pending either payee onboarding or counsel's
         answer to docs/legal/
         THIRD_PARTY_PAYOUT_LICENSING_QUESTION_2026-07-19.md.
     Transient rail failures refuse fail-closed and retryable — an
     escrow is never silently locked into the manual path by a blip.
     Instructions remain deterministic and idempotent per escrow.
EC6  Custody failures degrade to structured refusals, never crashes, and
     never fund, release, refund, or certify anything (PG8/PG15 family).
EC7  All custody state is persisted through the StateStore before success
     is reported; a restart never forgets a funding or double-issues an
     instruction (mirrors PG5/PG16 durability posture).
EC8  The Stripe key is never accepted as an argument, echoed, or stored
     (rides on stripe_payments P6).
EC9  (superseded by EC10, 2026-07-19 — kept for history) The original
     flat 50-minor fee floor. Mis-calibrated: card processing is
     ~2.9%+30c of the WHOLE escrow amount, so the flat floor only
     protected escrows below ~$7 and every larger 1%-fee third-party
     settlement funded by card was negative-margin.
EC10 Third-party settlement is never cash-funded below cost+margin
     (esc-fee-v1, docs/deployment/ESCROW_FEE_SCHEDULE_esc-fee-v1.md):
     the escrow's frozen fee (E3) must be >=
       ceil(A*290/10000) + 30 + ceil(A*margin_bps/10000)
     where margin_bps is the payee's EARNED tier — 200 new, 150
     Connect-onboarded, 100 onboarded + >=10 Viridis Verified certified
     deliveries. The schedule is pre-committed and versioned (changes
     mint esc-fee-v2, never rewrite); the version + tier are stamped on
     the funding record; an open escrow's frozen fee is NEVER mutated.
     Refusals are actionable: required_fee_bps for this amount plus the
     discount path (onboarding/track record). viridis:* payees are
     exempt (the whole amount is revenue; processing is COGS, not a
     loss). Structural consequence: any fee that passes EC10 nets
     Viridis >= ~margin_bps of the amount after card processing — a
     negative-margin settlement cannot be funded.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("viridis.escrow_custody")

VIRIDIS_PAYEE_PREFIX = "viridis:"
# Stripe refuses charges below ~$0.50 USD. Escrows smaller than this cannot
# be cash-funded individually — callers batch-prepay instead (one larger
# escrow buys floor(amount/price) credits, PG13). Encoded so the refusal is
# ours and actionable, not an opaque Stripe 400 (EC1/EC6).
STRIPE_MIN_CHECKOUT_MINOR = 50
# EC10 (esc-fee-v1, adopted 2026-07-19 under Justin's delegation — see
# docs/deployment/ESCROW_FEE_SCHEDULE_esc-fee-v1.md): Viridis's take on a
# card-funded third-party settlement must cover the card-processing cost
# of the WHOLE escrow (~2.9% + 30c — the old flat 50-minor floor lost
# money above ~$7) PLUS an earned margin. The margin tiers ARE the
# network mechanic: payees earn their way down by doing exactly what
# compounds the network (onboard to Connect -> autonomous settlement;
# build a Viridis Verified track record -> non-portable moat).
# Pre-committed and versioned (weave RATE_SCHEDULE pattern): changes
# create esc-fee-v2, never mutate v1 or any open escrow's frozen fee.
FEE_SCHEDULE = {
    "version": "esc-fee-v1",
    "adopted": "2026-07-19",
    "adopted_by": ("Fable under Justin's delegation (standing CEO veto "
                   "before deploy)"),
    "card_rail_cost_bps": 290,
    "card_rail_fixed_minor": 30,
    "margin_bps": {
        "new": 200,                 # unverified counterparty risk, priced
        "connect_onboarded": 150,   # zero-labor autonomous settlement
        "connect_verified": 100,    # >=10 certified deliveries (uw-v1 src)
    },
    "verified_deliveries_threshold": 10,
    "de_escalator": ("-25 bps all tiers per $10,000 cumulative monthly "
                     "settled third-party volume; each step is a new "
                     "schedule version; floor 50 bps over rail cost"),
    "future": ("non-card rails (x402/USDC, ACH) re-price the rail-cost "
               "term to that rail's actual cost — not yet implemented"),
}


def _ceil_bps(amount_minor: int, bps: int) -> int:
    return -(-amount_minor * bps // 10000)


def verified_stats_from_core(verified_core):
    """EC10: sync adapter payee_id -> certified 'ok' delivery count.

    The verified core's process() surface is async but its read methods
    are sync and pure (V7) — _list_services returns each service's
    public() with provider + calls_ok. Identity mapping: an escrow payee
    qualifies for the connect_verified tier when the SAME string is a
    registered Viridis Verified provider (exactly how uw-v1/bond_bridge
    key track records). Unknown payee or any error -> 0 (no discount —
    fail-safe: worst case a payee pays the connect_onboarded rate)."""
    def _stats(payee: str) -> int:
        try:
            listed = verified_core._list_services({})
            services = (listed.get("data") or {}).get("services") or []
            return sum(int(s.get("calls_ok") or 0) for s in services
                       if s.get("provider") == payee)
        except Exception:
            return 0
    return _stats


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _err(error_type: str, message: str, **extra) -> dict:
    return {"status": "error", "error_type": error_type,
            "message": message, "timestamp": _now(), **extra}


class CustodyState:
    """Plain persisted holder (pickled whole by the StateStore)."""

    def __init__(self):
        self.checkouts: Dict[str, dict] = {}       # escrow_id -> pending session
        self.funded: Dict[str, dict] = {}          # escrow_id -> paid evidence (EC3)
        self.sessions_used: Dict[str, str] = {}    # session_id -> escrow_id (EC4)
        self.instructions: Dict[str, dict] = {}    # escrow_id -> payout/refund cert (EC5)


class EscrowCustody:
    """PG17 custody bridge between the escrow core and the Stripe rail."""

    def __init__(self, store, escrow_core,
                 persist_key: str = "escrow_custody",
                 escrow_persist_key: str = "escrow",
                 create_checkout=None, verify_session=None,
                 execute_refund=None, connect=None, verified_stats=None):
        self.store = store
        self.escrow = escrow_core
        self.persist_key = persist_key
        self.escrow_persist_key = escrow_persist_key
        self._create_checkout = create_checkout
        self._verify_session = verify_session
        # 2026-07-19 autonomy rails (both optional; absent -> prior
        # behavior, so nothing regresses):
        #   execute_refund — callable issuing a real Stripe refund against
        #     the original session (defaults to stripe_payments.create_refund
        #     at call time, same idiom as create_checkout/verify_session).
        #   connect — a connect_rail.ConnectRail; when the payee is
        #     onboarded there, payouts execute autonomously via Stripe's
        #     licensed Transfer rail instead of certifying for Justin.
        self._execute_refund = execute_refund
        self.connect = connect
        # esc-fee-v1 (EC10): optional callable payee_id -> certified
        # delivery count (the same track record uw-v1 prices from).
        # None -> the connect_verified tier is simply unreachable; the
        # gateway wires this once an async-safe verified-stats adapter
        # exists (verified core is async; this method is sync).
        self._verified_stats = verified_stats
        self.state = CustodyState()
        self._errors: Dict[str, str] = {}
        # EC7: the persisted aggregate is the plain CustodyState holder —
        # never this bridge object itself (its store/escrow handles must not
        # be snapshotted or restored over live references).
        try:
            self.store.restore(persist_key, self.state)
        except Exception as exc:               # EC6
            self._errors["restore"] = f"{type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------ #
    def _persist(self) -> bool:
        try:
            return bool(self.store.save(self.persist_key, self.state))
        except Exception as exc:               # EC6
            self._errors["persist"] = f"{type(exc).__name__}: {exc}"
            return False

    def _escrow_status(self, escrow_id: str) -> dict:
        try:
            return self.escrow.process_sync(
                {"action": "status", "escrow_id": escrow_id})
        except Exception as exc:               # EC6
            return _err("escrow_error", f"escrow core failed: {type(exc).__name__}")

    def _payee_tier(self, payee: str) -> tuple[str, int]:
        """EC10: resolve the payee's earned margin tier (esc-fee-v1)."""
        tiers = FEE_SCHEDULE["margin_bps"]
        tier = "new"
        if self.connect is not None and self.connect.can_pay(payee):
            tier = "connect_onboarded"
            if self._verified_stats is not None:
                try:
                    n = int(self._verified_stats(payee) or 0)
                except Exception:              # EC6: never crash on stats
                    n = 0
                if n >= FEE_SCHEDULE["verified_deliveries_threshold"]:
                    tier = "connect_verified"
        return tier, tiers[tier]

    def _fee_floor_minor(self, amount_minor: int, payee: str
                         ) -> tuple[int, str, int]:
        """EC10: fee_min = ceil(A*290/10000) + 30 + ceil(A*margin/10000).

        Structural invariant: any fee passing this floor nets Viridis at
        least ~margin_bps of the amount AFTER card processing — no
        card-funded third-party settlement can be negative-margin.
        """
        tier, margin = self._payee_tier(payee)
        floor = (_ceil_bps(amount_minor, FEE_SCHEDULE["card_rail_cost_bps"])
                 + FEE_SCHEDULE["card_rail_fixed_minor"]
                 + _ceil_bps(amount_minor, margin))
        return floor, tier, margin

    # ------------------------------------------------------------------ #
    def create_funding_checkout(self, escrow_id: Any) -> dict:
        """EC1: one Stripe Checkout for exactly this escrow's amount."""
        if not isinstance(escrow_id, str) or not escrow_id.strip():
            return _err("bad_escrow_id", "escrow_id is required")
        escrow_id = escrow_id.strip()
        status = self._escrow_status(escrow_id)
        if status.get("status") != "ok":
            return _err("unknown_escrow", f"no such escrow '{escrow_id}'")
        esc = status["data"]
        if escrow_id in self.state.funded:                      # EC4
            return _err("already_funded",
                        "escrow already custody-funded; nothing to pay",
                        evidence=self.state.funded[escrow_id])
        if esc["state"] != "OPEN":
            return _err("not_open",
                        f"escrow is {esc['state']}; only OPEN escrows take funding")
        if esc.get("currency") != "USD":                        # EC1
            return _err("currency_mismatch", "custody rail is USD-only")
        if int(esc["amount_minor"]) < STRIPE_MIN_CHECKOUT_MINOR:  # EC1
            return _err("below_stripe_minimum",
                        f"Stripe cannot charge {esc['amount_minor']} minor "
                        f"units (minimum {STRIPE_MIN_CHECKOUT_MINOR}); open "
                        "one larger escrow instead — it prepays "
                        "floor(amount/price) calls (PG13)",
                        minimum_minor=STRIPE_MIN_CHECKOUT_MINOR)
        fee_meta = {"fee_schedule_version": FEE_SCHEDULE["version"],
                    "payee_tier": "viridis_exempt"}
        if not str(esc["payee"]).startswith(VIRIDIS_PAYEE_PREFIX):  # EC10
            amount = int(esc["amount_minor"])
            floor, tier, margin = self._fee_floor_minor(
                amount, str(esc["payee"]))
            fee_meta = {"fee_schedule_version": FEE_SCHEDULE["version"],
                        "payee_tier": tier}
            if int(esc["fee_minor"]) < floor:
                required_bps = -(-floor * 10000 // amount)
                hint = ""
                if tier == "new":
                    hint = (" Or lower the floor: the payee can onboard "
                            "via begin_payout_onboarding (tier "
                            "connect_onboarded, 150 bps margin) and build "
                            "a Viridis Verified track record (tier "
                            "connect_verified, 100 bps).")
                return _err(
                    "fee_below_floor",
                    f"third-party settlement fee {esc['fee_minor']} minor "
                    f"is below the esc-fee-v1 floor {floor} for this "
                    f"amount (card processing ~2.9%+30c of the WHOLE "
                    f"escrow + {margin} bps earned margin, tier '{tier}'). "
                    f"Reopen the escrow with fee_bps >= {required_bps}."
                    + hint,
                    fee_floor_minor=floor,
                    frozen_fee_minor=int(esc["fee_minor"]),
                    required_fee_bps=required_bps,
                    payee_tier=tier, margin_bps=margin,
                    fee_schedule_version=FEE_SCHEDULE["version"])
        create = self._create_checkout
        if create is None:
            import stripe_payments
            create = stripe_payments.create_checkout
        try:
            session = create(
                int(esc["amount_minor"]),
                f"escrow {escrow_id} -> {esc['payee']}",
                metadata={"escrow_id": escrow_id, "payee": esc["payee"],
                          "rail": "a2a-escrow-custody"})
        except Exception as exc:                                # EC6
            self._errors[escrow_id] = f"checkout: {type(exc).__name__}"
            return _err("stripe_error", "checkout creation failed")
        if session.get("status") != "ok":
            return session                       # structured Stripe error (EC6)
        record = {"session_id": session["session_id"], "url": session["url"],
                  "amount_minor": int(esc["amount_minor"]),
                  "payee": esc["payee"], "livemode": session.get("livemode"),
                  **fee_meta,                                   # EC10 stamp
                  "created_at": _now()}
        self.state.checkouts[escrow_id] = record                # EC1: replace
        if not self._persist():                                 # EC7
            return _err("persist_failed",
                        "checkout created but custody state not durable; "
                        "retry create_funding_checkout")
        self._errors.pop(escrow_id, None)
        return {"status": "ok", "escrow_id": escrow_id, **record,
                "then": ("pay the url, then call confirm_escrow_funding("
                         f"escrow_id='{escrow_id}') — the escrow turns FUNDED "
                         "only after the session verifies paid")}

    # ------------------------------------------------------------------ #
    def confirm_funding(self, escrow_id: Any,
                        session_id: Optional[str] = None) -> dict:
        """EC2/EC3/EC4: pull-verify paid, then fund through the core's E1."""
        if not isinstance(escrow_id, str) or not escrow_id.strip():
            return _err("bad_escrow_id", "escrow_id is required")
        escrow_id = escrow_id.strip()
        prior = self.state.funded.get(escrow_id)
        if prior is not None:                                   # EC4 idempotent
            return {"status": "ok", "duplicate": True,
                    "escrow_id": escrow_id, "cash": True, **prior}
        pending = self.state.checkouts.get(escrow_id)
        sid = (session_id or (pending or {}).get("session_id") or "").strip()
        if not sid:
            return _err("no_session",
                        "no checkout recorded for this escrow; call "
                        "escrow_checkout first or pass session_id")
        claimed_by = self.state.sessions_used.get(sid)
        if claimed_by is not None and claimed_by != escrow_id:  # EC4
            return _err("session_already_used",
                        f"session already funded escrow '{claimed_by}'")
        status = self._escrow_status(escrow_id)
        if status.get("status") != "ok":
            return _err("unknown_escrow", f"no such escrow '{escrow_id}'")
        esc = status["data"]
        if esc["state"] not in ("OPEN", "FUNDED"):
            return _err("not_fundable", f"escrow is {esc['state']}")
        verify = self._verify_session
        if verify is None:
            import stripe_payments
            verify = stripe_payments.verify_session
        try:
            v = verify(sid)
        except Exception as exc:                                # EC6
            self._errors[escrow_id] = f"verify: {type(exc).__name__}"
            return _err("verify_failed", "session verification failed")
        if v.get("status") != "ok":
            return v                                            # EC2 fail-closed
        if v.get("payment_status") != "paid":                   # EC2
            return _err("not_paid",
                        f"session is '{v.get('payment_status')}', not paid",
                        session_id=sid)
        if int(v.get("amount_total") or 0) < int(esc["amount_minor"]):  # EC2
            return _err("underpaid",
                        f"paid {v.get('amount_total')} < required "
                        f"{esc['amount_minor']}", session_id=sid)
        funded = self.escrow.process_sync({
            "action": "fund", "escrow_id": escrow_id,
            "payment_ref": f"stripe:{sid}"})
        if funded.get("status") != "ok" \
                or (funded.get("data") or {}).get("state") != "FUNDED":
            return _err("escrow_fund_failed",
                        f"core refused fund: {funded.get('error_type')}")  # EC6
        evidence = {"session_id": sid,
                    "amount_total": int(v.get("amount_total") or 0),
                    "livemode": bool(v.get("livemode")),
                    "funded_at": _now()}
        self.state.funded[escrow_id] = evidence                 # EC3
        self.state.sessions_used[sid] = escrow_id               # EC4
        pending_record = self.state.checkouts.pop(escrow_id, None)
        try:                                                    # EC7: one atomic
            saved = bool(self.store.save_many({                 # group commit
                self.escrow_persist_key: self.escrow,
                self.persist_key: self.state}))
        except Exception:
            saved = False
        if not saved:                                           # fail-closed
            self.state.funded.pop(escrow_id, None)
            self.state.sessions_used.pop(sid, None)
            if pending_record is not None:
                self.state.checkouts[escrow_id] = pending_record
            return _err("persist_failed",
                        "funding verified but not durable; retry — the paid "
                        "session is not lost")
        self._errors.pop(escrow_id, None)
        logger.info("escrow_custody: %s FUNDED with cash via %s (%s minor, "
                    "livemode=%s)", escrow_id, sid,
                    evidence["amount_total"], evidence["livemode"])
        return {"status": "ok", "duplicate": False, "cash": True,
                "escrow_id": escrow_id, "escrow_state": "FUNDED", **evidence}

    # ------------------------------------------------------------------ #
    def settlement_instruction(self, escrow_id: Any) -> dict:
        """EC5: certified cash-out paperwork for a terminal custody escrow.

        RELEASED + third-party payee -> payout instruction (net of frozen fee).
        RELEASED + viridis:* payee   -> revenue recognition record (no payout).
        REFUNDED                     -> refund instruction (original session).
        Never touches Stripe. Idempotent per escrow.
        """
        if not isinstance(escrow_id, str) or not escrow_id.strip():
            return _err("bad_escrow_id", "escrow_id is required")
        escrow_id = escrow_id.strip()
        existing = self.state.instructions.get(escrow_id)
        if existing is not None:                                # EC5 idempotent
            return {"status": "ok", "duplicate": True, **existing}
        evidence = self.state.funded.get(escrow_id)
        if evidence is None:                                    # PG17/EC3
            return _err("not_custody_funded",
                        "escrow was never cash-funded; internal-ledger escrows "
                        "have no cash to move")
        status = self._escrow_status(escrow_id)
        if status.get("status") != "ok":
            return _err("unknown_escrow", f"no such escrow '{escrow_id}'")
        esc = status["data"]
        if esc["state"] not in ("RELEASED", "REFUNDED"):
            return _err("not_terminal",
                        f"escrow is {esc['state']}; instructions exist only "
                        "for RELEASED/REFUNDED")
        if esc["state"] == "REFUNDED":
            # Same-party refund: EXECUTE the real Stripe refund against the
            # original session (money actually moves back to the payer —
            # not just bookkeeping). Fail-closed: any rail failure refuses
            # with nothing recorded; retry is safe because the
            # deterministic Idempotency-Key means Stripe returns the same
            # refund instead of issuing a second one.
            refund = self._execute_refund
            if refund is None:
                import stripe_payments
                refund = stripe_payments.create_refund
            try:
                issued = refund(
                    evidence["session_id"],
                    idempotency_key=f"escrow-refund:{escrow_id}"[:255],
                    amount_minor=evidence["amount_total"])
            except Exception as exc:                            # EC6
                self._errors[escrow_id] = f"refund: {type(exc).__name__}"
                return _err("refund_failed",
                            "refund rail failed; nothing recorded — retry "
                            "settlement_instruction (idempotency-guarded, "
                            "cannot double-refund)")
            if issued.get("status") != "ok":                    # fail-closed
                return issued
            instruction = {
                "type": "refund", "scope": "same_party_refund",
                "escrow_id": escrow_id,
                "session_id": evidence["session_id"],
                "refund_minor": evidence["amount_total"],
                "refund_id": issued["refund_id"],
                "note": (
                    f"refunded {evidence['amount_total']} minor units to "
                    f"the originator of session {evidence['session_id']} "
                    f"via Stripe refund {issued['refund_id']} — "
                    "refund-to-originator, executed autonomously "
                    "(EC5, 2026-07-19), no human step"),
                "certified_at": _now(), "executed": True,
                "executed_at": _now()}
        elif str(esc["payee"]).startswith(VIRIDIS_PAYEE_PREFIX):
            instruction = {
                "type": "revenue_recognized", "escrow_id": escrow_id,
                "payee": esc["payee"],
                "revenue_minor": evidence["amount_total"],
                "note": ("cash already in Viridis's Stripe balance; no "
                         "movement required — this record IS the recognition"),
                "certified_at": _now(), "executed": True,
                "executed_at": _now()}
        else:
            payee = str(esc["payee"])
            net = int(esc["net_to_payee_minor"])
            base = {
                "type": "payout", "escrow_id": escrow_id,
                "payee": payee,
                "gross_minor": int(esc["amount_minor"]),
                "fee_minor": int(esc["fee_minor"]),          # frozen at open, E3
                "net_minor": net}
            if self.connect is not None and self.connect.can_pay(payee):
                # Payee is Connect-onboarded: Stripe (the licensed
                # transmitter) executes the payout; software only
                # instructs it. Eligibility is pull-verified inside the
                # rail at transfer time (CR2); exactly-once per escrow
                # (CR3, purpose_key below doubles as the Stripe
                # Idempotency-Key).
                xfer = self.connect.execute_transfer(
                    payee, net,
                    purpose_key=f"escrow-payout:{escrow_id}"[:255],
                    transfer_group=escrow_id,
                    metadata={"escrow_id": escrow_id, "rail": "escrow-payout"})
                if xfer.get("status") == "ok":
                    instruction = {
                        **base, "rail": "connect",
                        "scope": "third_party_licensed_rail",
                        "transfer_id": xfer["transfer_id"],
                        "note": (
                            f"paid {net} minor units to {payee} via Stripe "
                            f"Connect transfer {xfer['transfer_id']} "
                            f"(licensed rail; Viridis keeps fee "
                            f"{esc['fee_minor']}) — autonomous, no human "
                            "step (EC5/CR, 2026-07-19)"),
                        "certified_at": _now(), "executed": True,
                        "executed_at": xfer.get("executed_at") or _now()}
                elif xfer.get("error_type") == "payouts_not_enabled":
                    # Onboarding started but incomplete: fall back to the
                    # certified manual instruction (CR7 — money can still
                    # move via Justin) and surface Stripe's requirements
                    # so the payee can finish.
                    instruction = {
                        **base, "rail": "manual",
                        "action_for_justin": (
                            f"pay {net} minor units to {payee}; Viridis "
                            f"keeps fee {esc['fee_minor']}"),
                        "onboarding_requirements_due": xfer.get(
                            "requirements_currently_due", []),
                        "certified_at": _now(), "executed": False,
                        "executed_at": None}
                else:
                    # Transient rail failure (stripe_error, persist, ...):
                    # fail-closed and retryable — do NOT lock this escrow
                    # into the manual path over a blip.
                    return xfer
            else:
                instruction = {
                    **base, "rail": "manual",
                    "action_for_justin": (
                        f"pay {net} minor units to {payee}; Viridis keeps "
                        f"fee {esc['fee_minor']}"),
                    "onboarding_hint": (
                        "payee can turn future payouts autonomous by "
                        "completing Stripe Connect onboarding: call "
                        f"begin_payout_onboarding(payee_id='{payee}')"),
                    "certified_at": _now(), "executed": False,
                    "executed_at": None}
        self.state.instructions[escrow_id] = instruction
        if not self._persist():                                 # EC7
            self.state.instructions.pop(escrow_id, None)
            return _err("persist_failed", "instruction not durable; retry")
        return {"status": "ok", "duplicate": False, **instruction}

    def mark_executed(self, escrow_id: Any) -> dict:
        """EC5: Justin (admin-token gated at the tool layer) records that he
        executed a certified instruction. Idempotent.

        Since 2026-07-19 this splits by instruction type (same pattern as
        weave.mark_transfer_executed): REFUND records and Connect-rail
        PAYOUT records auto-execute at settlement_instruction() time, so
        for those this is a no-op idempotent confirmation (returns
        duplicate=True against the already-executed record). For MANUAL
        payout records (payee not Connect-onboarded) it remains the real
        gate — the only way such a payout is ever marked executed."""
        instruction = self.state.instructions.get(
            escrow_id.strip() if isinstance(escrow_id, str) else "")
        if instruction is None:
            return _err("no_instruction", "no certified instruction for this escrow")
        if instruction["executed"]:
            return {"status": "ok", "duplicate": True, **instruction}
        instruction["executed"] = True
        instruction["executed_at"] = _now()
        if not self._persist():                                 # EC7
            instruction["executed"] = False
            instruction["executed_at"] = None
            return _err("persist_failed", "not durable; retry")
        return {"status": "ok", "duplicate": False, **instruction}

    # ------------------------------------------------------------------ #
    def status(self) -> dict:
        pending_payout = [i for i in self.state.instructions.values()
                          if i["type"] == "payout" and not i["executed"]]
        return {
            "cash_funded_escrows": len(self.state.funded),
            "cash_funded_minor": sum(e["amount_total"]
                                     for e in self.state.funded.values()),
            "pending_checkouts": len(self.state.checkouts),
            "instructions": {
                "total": len(self.state.instructions),
                "pending_payout_minor": sum(i["net_minor"]
                                            for i in pending_payout),
                "pending_payouts": len(pending_payout),
            },
            "note": ("cash arrives via Stripe Checkout (subset of "
                     "settled_minor); refunds + Connect-onboarded payouts "
                     "execute autonomously on Stripe's licensed rails; "
                     "only non-onboarded payees' payouts remain certified "
                     "for Justin (EC5, 2026-07-19)"),
            "errors": dict(self._errors),
        }
