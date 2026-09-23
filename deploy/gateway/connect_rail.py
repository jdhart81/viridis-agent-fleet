"""
connect_rail.py — CR: the STRUCTURAL gate that makes third-party payouts
autonomous AND legal.

THE SYSTEM LOOP (closes the last human gate in the escrow economy):

    payer -> Stripe Checkout (PG17 custody, pull-verified paid)
      -> escrow core state machine (E-invariants)
        -> RELEASED + payee ONBOARDED here -> Transfer API, executed by
           software, paid out by STRIPE (the licensed money transmitter)
        -> RELEASED + payee not onboarded -> certified manual instruction
           (today's human-gated path — the fallback, never broken)
        -> REFUNDED -> Refund API to the original session (same-party,
           cleared 2026-07-19)
      -> transfer/refund ids -> reconciliation -> verified receipts
         -> underwriting -> premiums (revenue) -> more escrow volume

Why this is the legal fix, not a workaround: with Connect, the payee
onboards with Stripe (Express account — Stripe runs KYC/AML and holds the
regulatory coverage). Viridis never "transmits money to another person"
(the 18 U.S.C. §1960 exposure in docs/legal/
THIRD_PARTY_PAYOUT_LICENSING_QUESTION_2026-07-19.md); it instructs a
licensed processor to pay its onboarded recipient — the standard
marketplace structure. The human gate is replaced by a structural gate:
no onboarded, payouts-enabled connected account -> no autonomous payout,
ever. This module owns that structural gate.

--- INVARIANTS (spec-invariance contract) ---
CR1  One payee ID maps to at most one connected account, forever.
     begin_onboarding is idempotent: re-begin returns the existing
     account with a fresh onboarding link, never a second account.
CR2  Payout eligibility is pull-verified at TRANSFER TIME via a live
     GET /v1/accounts (payouts_enabled) — never a cached status, never
     a caller claim (verify_session/PG10 posture). Not eligible ->
     structured refusal carrying Stripe's requirements_currently_due.
CR3  execute_transfer is exactly-once per purpose_key: a replay returns
     the original transfer record and never calls Stripe again. The
     same purpose_key rides to Stripe as the Idempotency-Key (P8), so
     even a crash between call and persist cannot double-pay.
CR4  Fail-closed everywhere: verify errors, transfer errors, and
     persistence failures refuse with structured envelopes and record
     nothing (save-or-revert, EC7/PB5 family). A failed transfer is
     retryable with the SAME purpose_key.
CR5  The Stripe key is never accepted, stored, or echoed (rides on
     stripe_payments P6/P12).
CR6  Transfers go ONLY to accounts in this registry, created by this
     module's own onboarding — never to a raw acct_... supplied by a
     caller. The registry is the trust boundary.
CR7  Legal posture is structural, not procedural: if this rail is
     unavailable for a payee, callers MUST fall back to the certified
     manual instruction (human-gated) — never to any other movement
     mechanism. There is no third path.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

logger = logging.getLogger("viridis.connect_rail")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _err(error_type: str, message: str, **extra) -> dict:
    return {"status": "error", "error_type": error_type,
            "message": message, "timestamp": _now(), **extra}


class ConnectState:
    """Plain persisted holder (CustodyState pattern)."""

    def __init__(self):
        self.payees: Dict[str, dict] = {}     # payee_id -> account record (CR1)
        self.transfers: Dict[str, dict] = {}  # purpose_key -> transfer (CR3)


class ConnectRail:
    """Payee onboarding registry + exactly-once transfer execution."""

    def __init__(self, store, persist_key: str = "connect_rail",
                 create_connect_account=None, create_account_link=None,
                 get_connect_account=None, create_transfer=None):
        self.store = store
        self.persist_key = persist_key
        # injectable rail functions (tests); None -> stripe_payments.<name>
        self._create_connect_account = create_connect_account
        self._create_account_link = create_account_link
        self._get_connect_account = get_connect_account
        self._create_transfer = create_transfer
        self.state = ConnectState()
        self._errors: Dict[str, str] = {}
        try:                                                    # CR4
            self.store.restore(persist_key, self.state)
        except Exception as exc:
            self._errors["restore"] = f"{type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------ #
    def _persist(self) -> bool:
        try:
            return bool(self.store.save(self.persist_key, self.state))
        except Exception as exc:                                # CR4
            self._errors["persist"] = f"{type(exc).__name__}: {exc}"
            return False

    def _rail(self, name):
        """Resolve an injected rail function, defaulting to stripe_payments."""
        fn = getattr(self, f"_{name}")
        if fn is not None:
            return fn
        import stripe_payments
        return getattr(stripe_payments, name)

    # ------------------------------------------------------------------ #
    def begin_onboarding(self, payee_id: Any) -> dict:
        """CR1: create (once) the payee's Express account + a fresh
        Stripe-hosted onboarding link. Idempotent on payee_id."""
        if not isinstance(payee_id, str) or not payee_id.strip():
            return _err("bad_payee_id", "payee_id is required")
        payee_id = payee_id.strip()
        record = self.state.payees.get(payee_id)
        if record is None:
            try:
                # deterministic Idempotency-Key: a crash/persist failure
                # retried gets the SAME Stripe account back, never a
                # duplicate/orphan (CR1 across process boundaries).
                created = self._rail("create_connect_account")(
                    payee_id, idempotency_key=f"connect-acct:{payee_id}"[:255])
            except Exception as exc:                            # CR4
                self._errors[payee_id] = f"account: {type(exc).__name__}"
                return _err("stripe_error", "account creation failed")
            if created.get("status") != "ok":
                return created
            record = {"payee_id": payee_id,
                      "account_id": created["account_id"],
                      "livemode": created.get("livemode"),
                      "created_at": _now()}
            self.state.payees[payee_id] = record
            if not self._persist():                             # CR4 revert
                self.state.payees.pop(payee_id, None)
                return _err("persist_failed",
                            "account created but registry not durable; "
                            "retry begin_onboarding — the deterministic "
                            "Idempotency-Key returns the same account, "
                            "nothing orphans")
        try:
            link = self._rail("create_account_link")(record["account_id"])
        except Exception as exc:                                # CR4
            return _err("stripe_error", f"link: {type(exc).__name__}")
        if link.get("status") != "ok":
            return link
        return {"status": "ok", "payee_id": payee_id,
                "account_id": record["account_id"],
                "onboarding_url": link["url"],
                "expires_at": link.get("expires_at"),
                "then": ("payee completes Stripe-hosted onboarding (Stripe "
                         "runs KYC); call payout_onboarding_status to "
                         "pull-verify payouts_enabled — payouts to this "
                         "payee turn autonomous the moment it's true")}

    def onboarding_status(self, payee_id: Any) -> dict:
        """CR2 surface: pull-verify the payee's account live from Stripe."""
        if not isinstance(payee_id, str) or not payee_id.strip():
            return _err("bad_payee_id", "payee_id is required")
        record = self.state.payees.get(payee_id.strip())
        if record is None:
            return _err("not_onboarded",
                        "no connected account for this payee; call "
                        "begin_payout_onboarding first")
        try:
            acct = self._rail("get_connect_account")(record["account_id"])
        except Exception as exc:                                # CR4
            return _err("stripe_error", f"verify: {type(exc).__name__}")
        if acct.get("status") != "ok":
            return acct
        return {"status": "ok", "payee_id": payee_id.strip(), **{
            k: acct[k] for k in ("account_id", "payouts_enabled",
                                 "charges_enabled", "details_submitted",
                                 "requirements_currently_due", "livemode")}}

    # ------------------------------------------------------------------ #
    def can_pay(self, payee_id: Any) -> bool:
        """Cheap registry check (NOT eligibility — that's pull-verified at
        transfer time, CR2). Used by callers to pick a rail."""
        return isinstance(payee_id, str) \
            and payee_id.strip() in self.state.payees

    def execute_transfer(self, payee_id: Any, amount_minor: Any,
                         purpose_key: Any, transfer_group: str = "",
                         metadata: dict | None = None) -> dict:
        """CR2/CR3/CR4: exactly-once, pull-verified, fail-closed transfer.

        purpose_key is the caller's deterministic identity for this payment
        (e.g. 'escrow-payout-<escrow_id>') — it is the replay key here AND
        the Stripe Idempotency-Key, so no failure mode double-pays.
        """
        if not isinstance(purpose_key, str) or not purpose_key.strip():
            return _err("bad_purpose_key", "purpose_key is required")
        purpose_key = purpose_key.strip()
        prior = self.state.transfers.get(purpose_key)
        if prior is not None:                                   # CR3
            return {"status": "ok", "duplicate": True, **prior}
        if not isinstance(payee_id, str) \
                or payee_id.strip() not in self.state.payees:   # CR6
            return _err("not_onboarded",
                        "payee has no connected account in the registry; "
                        "fall back to the certified manual instruction (CR7)")
        record = self.state.payees[payee_id.strip()]
        if not isinstance(amount_minor, int) or isinstance(amount_minor, bool) \
                or amount_minor <= 0:
            return _err("bad_amount", "amount_minor must be a positive int")
        try:                                                    # CR2 fresh
            acct = self._rail("get_connect_account")(record["account_id"])
        except Exception as exc:                                # CR4
            return _err("stripe_error", f"verify: {type(exc).__name__}")
        if acct.get("status") != "ok":
            return acct
        if not acct.get("payouts_enabled"):                     # CR2
            return _err("payouts_not_enabled",
                        "Stripe reports payouts_enabled=false for this "
                        "payee; onboarding incomplete — surface "
                        "requirements to the payee and retry after",
                        requirements_currently_due=acct.get(
                            "requirements_currently_due", []))
        try:
            xfer = self._rail("create_transfer")(
                record["account_id"], amount_minor,
                idempotency_key=purpose_key,                    # CR3/P8
                transfer_group=transfer_group,
                metadata={"payee_id": payee_id.strip(),
                          "purpose_key": purpose_key, **(metadata or {})})
        except Exception as exc:                                # CR4
            self._errors[purpose_key] = f"transfer: {type(exc).__name__}"
            return _err("stripe_error",
                        "transfer failed; nothing recorded — retry with the "
                        "SAME purpose_key (Stripe idempotency guards the "
                        "crash-after-send case)")
        if xfer.get("status") != "ok":
            return xfer
        entry = {"purpose_key": purpose_key, "payee_id": payee_id.strip(),
                 "account_id": record["account_id"],
                 "transfer_id": xfer["transfer_id"],
                 "amount_minor": amount_minor,
                 "transfer_group": transfer_group,
                 "livemode": xfer.get("livemode"),
                 "executed_at": _now()}
        self.state.transfers[purpose_key] = entry
        if not self._persist():                                 # CR4 revert
            self.state.transfers.pop(purpose_key, None)
            return _err("persist_failed",
                        "transfer sent but record not durable; RETRY with "
                        "the SAME purpose_key — Stripe's Idempotency-Key "
                        "returns the same transfer, nothing double-pays")
        self._errors.pop(purpose_key, None)
        logger.info("connect_rail: %s -> %s minor to %s (%s)", purpose_key,
                    amount_minor, payee_id.strip(), xfer["transfer_id"])
        return {"status": "ok", "duplicate": False, **entry}

    # ------------------------------------------------------------------ #
    def status(self) -> dict:
        return {"payees_onboarded": len(self.state.payees),
                "transfers_executed": len(self.state.transfers),
                "transfers_minor": sum(t["amount_minor"]
                                       for t in self.state.transfers.values()),
                "note": ("structural gate: payouts execute only to "
                         "registry accounts Stripe has onboarded+KYC'd, "
                         "pull-verified payouts_enabled at transfer time "
                         "(CR2/CR6); no rail -> certified manual fallback, "
                         "never any other path (CR7)"),
                "errors": dict(self._errors)}
