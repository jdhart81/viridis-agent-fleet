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
  cash out  — NEVER executed by software. Releases to third-party payees and
              refunds produce CERTIFIED INSTRUCTIONS (net of the escrow's
              own frozen 1% fee, E3) that Justin executes manually in the
              Stripe dashboard — the fleet's standing doctrine ("agent
              computes and certifies; the CEO moves money").

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
EC5  Cash out is never executed: release of a custody-funded escrow to a
     third-party payee yields a certified payout instruction for exactly
     net_to_payee (amount - frozen fee, E3); a refund yields a certified
     refund instruction naming the original session. Instructions are
     deterministic, idempotent per escrow, and carry executed=False until
     an admin-token holder marks them executed.
EC6  Custody failures degrade to structured refusals, never crashes, and
     never fund, release, refund, or certify anything (PG8/PG15 family).
EC7  All custody state is persisted through the StateStore before success
     is reported; a restart never forgets a funding or double-issues an
     instruction (mirrors PG5/PG16 durability posture).
EC8  The Stripe key is never accepted as an argument, echoed, or stored
     (rides on stripe_payments P6).
EC9  Third-party settlement is never cash-funded at a loss: for a
     non-viridis payee, the escrow's frozen fee (E3) must be at least
     FEE_FLOOR_MINOR (Stripe's processing cut exceeds a 1% fee on small
     amounts). The refusal is actionable — reopen with a higher fee_bps or
     a larger amount. viridis:* payees are exempt (the whole amount is
     revenue; processing cost is COGS, not a loss).
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
# EC9: Viridis's take on a third-party settlement must at least cover the
# card-processing cost (~2.9% + 30c). Below this floor the 1% fee loses
# money on every transaction — refuse at funding time, before cash enters.
FEE_FLOOR_MINOR = 50


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
                 create_checkout=None, verify_session=None):
        self.store = store
        self.escrow = escrow_core
        self.persist_key = persist_key
        self.escrow_persist_key = escrow_persist_key
        self._create_checkout = create_checkout
        self._verify_session = verify_session
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
        if (not str(esc["payee"]).startswith(VIRIDIS_PAYEE_PREFIX)
                and int(esc["fee_minor"]) < FEE_FLOOR_MINOR):      # EC9
            return _err("fee_below_floor",
                        f"third-party settlement fee {esc['fee_minor']} minor "
                        f"is below the {FEE_FLOOR_MINOR}-minor floor (card "
                        "processing would exceed Viridis's take). Reopen the "
                        "escrow with a higher fee_bps or a larger amount so "
                        f"that fee_minor >= {FEE_FLOOR_MINOR}",
                        fee_floor_minor=FEE_FLOOR_MINOR,
                        frozen_fee_minor=int(esc["fee_minor"]))
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
            instruction = {
                "type": "refund", "escrow_id": escrow_id,
                "session_id": evidence["session_id"],
                "refund_minor": evidence["amount_total"],
                "action_for_justin": (
                    "Stripe dashboard -> Payments -> session "
                    f"{evidence['session_id']} -> Refund "
                    f"{evidence['amount_total']} minor units"),
                "certified_at": _now(), "executed": False,
                "executed_at": None}
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
            instruction = {
                "type": "payout", "escrow_id": escrow_id,
                "payee": esc["payee"],
                "gross_minor": int(esc["amount_minor"]),
                "fee_minor": int(esc["fee_minor"]),          # frozen at open, E3
                "net_minor": int(esc["net_to_payee_minor"]),
                "action_for_justin": (
                    f"pay {esc['net_to_payee_minor']} minor units to "
                    f"{esc['payee']}; Viridis keeps fee {esc['fee_minor']}"),
                "certified_at": _now(), "executed": False,
                "executed_at": None}
        self.state.instructions[escrow_id] = instruction
        if not self._persist():                                 # EC7
            self.state.instructions.pop(escrow_id, None)
            return _err("persist_failed", "instruction not durable; retry")
        return {"status": "ok", "duplicate": False, **instruction}

    def mark_executed(self, escrow_id: Any) -> dict:
        """EC5: Justin (admin-token gated at the tool layer) records that he
        executed a certified instruction. Idempotent."""
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
                     "settled_minor); cash out is certified for Justin, "
                     "never executed by software (EC5)"),
            "errors": dict(self._errors),
        }
