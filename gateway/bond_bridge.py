"""
bond_bridge.py — COLLATERALIZED surety bonds: bond-writing with ZERO
Viridis capital at risk.

An insurance book normally needs reserves before it can promise payouts.
This bridge replaces the reserve with the provider's own money: a provider
cash-funds an escrow payable to "viridis:surety-collateral" (PG17 custody —
pull-verified Stripe Checkout), and that collateral IS the bond's backing.
The premium (priced by uw-v1 from the provider's Viridis Verified delivery
record, BW1-BW6) is deducted from the collateral and recognized as Viridis
revenue at bind; the remainder is the coverage. Slashes pay the harmed
party FROM the collateral; clean expiry returns the remainder through the
original Checkout Session's Stripe refund rail.

Composition: Verified track record -> uw-v1 premium -> escrow custody
collateral -> surety bond lifecycle (SB invariants, ruling-gated slashing)
-> certified settlement. Five agents, one product, no capital.

--- INVARIANTS (spec-invariance contract) ---
CB1  A bond binds ONLY against collateral that is (a) an escrow in state
     FUNDED, (b) payable to "viridis:surety-collateral", (c) present in
     the PG17 custody cash registry (real verified money), and (d) large
     enough that coverage = collateral - premium is positive. Anything
     less refuses — a bond is never written against promises.
CB2  The premium is priced by the existing uw-v1 composition (Verified
     delivery stats -> surety price_bond) at bind time and frozen on the
     bond record with its recomputable quote_hash (BW4). Bonds are only
     written for registered Viridis Verified services.
CB3  The bond lives in the surety core's own state machine (post_bond ->
     activate with funding_ref=escrow id; SB invariants including
     ruling-gated slashing are never bypassed). One collateral escrow
     backs at most one bond, and one bond has exactly one collateral.
CB4  Settlement is certified as PER-COUNTERPARTY LEGS (2026-07-19 legs
     refactor), each on the rail its risk category allows (see
     docs/legal/THIRD_PARTY_PAYOUT_LICENSING_QUESTION_2026-07-19.md):
       - provider_return leg (collateral - premium - slashed, when > 0):
         the provider's OWN money back — refund-to-originator, executes
         autonomously through a partial Stripe refund against the original
         collateral Checkout Session, even on slashed bonds. The leg is not
         executed until Stripe returns a refund_id.
       - claimant_payout leg (one per PAID claim): a true third party.
         Claimant Connect-onboarded (connect_rail CR1-CR7) -> executes
         autonomously via Stripe's licensed Transfer rail, exactly-once
         per bond+claim (purpose_key = Stripe Idempotency-Key). Not
         onboarded -> certified manual leg (action_for_justin +
         onboarding hint), the only fallback.
     Top-level executed is true iff EVERY leg executed. Transient rail
     failures refuse fail-closed with nothing recorded — the whole
     certification is retryable. Idempotent per bond (CB5 unchanged).
CB5  Idempotent everywhere: bind is exactly-once per collateral escrow;
     settlement certification is exactly-once per bond event; replays
     return the original record.
CB6  Failures refuse with structured envelopes and revert (save-or-revert,
     PB5/EC7 family); bridge state persists and survives restarts.
CB7  Every executed settlement leg carries external money-primitive evidence:
     provider returns have refund_id, Connect payouts have transfer_id, and a
     certified-manual close-out must supply money_primitive_id. A boolean is
     never accepted as evidence that money moved.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

logger = logging.getLogger("viridis.bond_bridge")

COLLATERAL_PAYEE = "viridis:surety-collateral"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _err(error_type: str, message: str, **extra) -> dict:
    return {"status": "error", "error_type": error_type,
            "message": message, "timestamp": _now(), **extra}


class BondState:
    def __init__(self):
        self.bonds: Dict[str, dict] = {}          # bond_id -> record
        self.collateral_used: Dict[str, str] = {} # escrow_id -> bond_id (CB3)
        self.instructions: Dict[str, dict] = {}   # key -> certified cash-out


class BondBridge:
    def __init__(self, store, escrow_core, surety_core, verified_core,
                 custody, persist_key: str = "bonds", connect=None,
                 execute_refund=None):
        self.store = store
        self.escrow = escrow_core
        self.surety = surety_core
        self.verified = verified_core
        self.custody = custody
        self.persist_key = persist_key
        # 2026-07-19: optional connect_rail.ConnectRail — when a slashed
        # claimant is Connect-onboarded, their leg pays out autonomously
        # via Stripe's licensed Transfer rail (escrow_custody idiom).
        self.connect = connect
        # FA-15: use the same refund-to-originator primitive as EC5. Tests
        # inject a fake; production resolves stripe_payments.create_refund.
        self._execute_refund = execute_refund
        self.state = BondState()
        self._errors: Dict[str, str] = {}
        try:                                                    # CB6
            self.store.restore(persist_key, self.state)
        except Exception as exc:
            self._errors["restore"] = f"{type(exc).__name__}: {exc}"

    def _persist(self) -> bool:
        try:
            return bool(self.store.save(self.persist_key, self.state))
        except Exception as exc:
            self._errors["persist"] = f"{type(exc).__name__}: {exc}"
            return False

    # ------------------------------------------------------------------ #
    async def bind(self, service_id: Any, collateral_escrow_id: Any,
                   expires_at: Any, duration_days: int = 30) -> dict:
        if not isinstance(collateral_escrow_id, str) \
                or not collateral_escrow_id.strip():
            return _err("bad_escrow_id", "collateral_escrow_id is required")
        eid = collateral_escrow_id.strip()
        prior_bond = self.state.collateral_used.get(eid)
        if prior_bond is not None:                              # CB5 idempotent
            return {"status": "ok", "duplicate": True,
                    **self.state.bonds[prior_bond]}
        status = self.escrow.process_sync({"action": "status",
                                           "escrow_id": eid})
        if status.get("status") != "ok":
            return _err("unknown_escrow", f"no such escrow '{eid}'")
        esc = status["data"]
        if esc["state"] != "FUNDED":                            # CB1a
            return _err("not_funded", f"collateral escrow is {esc['state']}")
        if esc["payee"] != COLLATERAL_PAYEE:                    # CB1b
            return _err("wrong_payee",
                        f"collateral must be payable to {COLLATERAL_PAYEE}")
        custody_funded = getattr(getattr(self.custody, "state", None),
                                 "funded", {}) or {}
        if eid not in custody_funded:                           # CB1c
            return _err("not_cash",
                        "collateral must be CASH-funded via escrow_checkout "
                        "+ confirm_escrow_funding (PG17) — internal-ledger "
                        "escrows cannot back a bond")
        collateral = int(esc["amount_minor"])
        import underwriting_bridge                              # CB2 (uw-v1)
        quote = await underwriting_bridge.quote_bond_for_service(
            self.verified, self.surety, str(service_id or ""),
            collateral, int(duration_days))
        if quote.get("status") != "ok":
            return _err("underwriting_refused",
                        f"quote failed: {quote.get('message')}",
                        detail={k: quote.get(k)
                                for k in ("error_type", "field")})
        qdata = quote["quote"]
        premium = int(qdata.get("premium_minor") or 0)
        coverage = collateral - premium
        if premium <= 0 or coverage <= 0:                       # CB1d
            return _err("collateral_too_small",
                        f"collateral {collateral} cannot cover premium "
                        f"{premium} plus positive coverage",
                        premium_minor=premium)
        try:                                                    # CB3
            posted = await self.surety.process({
                "action": "post_bond",
                "principal_agent": quote["service"]["provider"] or service_id,
                "principal": coverage, "expires_at": str(expires_at)})
            if posted.get("status") != "ok":
                return _err("surety_refused",
                            f"post_bond: {posted.get('message')}")
            bond_id = posted["data"]["bond_id"]
            activated = await self.surety.process({
                "action": "activate", "bond_id": bond_id,
                "funding_ref": f"escrow:{eid}"})
            if activated.get("status") != "ok":
                return _err("surety_refused",
                            f"activate: {activated.get('message')}")
        except Exception as exc:                                # CB6
            return _err("surety_error", f"{type(exc).__name__}")
        record = {"bond_id": bond_id, "service_id": str(service_id),
                  "provider": quote["service"]["provider"],
                  "collateral_escrow_id": eid,
                  "collateral_minor": collateral,
                  "premium_minor": premium,                     # CB2 frozen
                  "coverage_minor": coverage,
                  "quote_hash": qdata.get("quote_hash"),
                  "expires_at": str(expires_at),
                  "premium_note": ("premium is Viridis revenue at bind — "
                                   "cash already in Stripe via the "
                                   "collateral checkout (PG17)"),
                  "bound_at": _now()}
        self.state.bonds[bond_id] = record
        self.state.collateral_used[eid] = bond_id               # CB3
        if not self._persist():                                 # CB6 revert
            self.state.bonds.pop(bond_id, None)
            self.state.collateral_used.pop(eid, None)
            return _err("persist_failed",
                        "bond activated in surety but bridge record not "
                        "durable; retry bind (idempotent on collateral)")
        logger.info("bond_bridge: %s bound — coverage %s, premium %s, "
                    "collateral %s (%s)", bond_id, coverage, premium, eid)
        return {"status": "ok", "duplicate": False, **record}

    async def certify_settlement(self, bond_id: Any) -> dict:
        """CB4 (legs): per-counterparty settlement for a terminal bond.
        provider_return executes through the original-session refund rail;
        claimant_payout legs execute via the Connect rail when the
        claimant is onboarded, else certify manually. Refund and Connect
        calls are idempotent; transient failures record nothing and retry
        safely."""
        if not isinstance(bond_id, str) or not bond_id.strip():
            return _err("bad_bond_id", "bond_id is required")
        bond_id = bond_id.strip()
        prior = self.state.instructions.get(bond_id)
        if prior is not None:                                   # CB5
            return {"status": "ok", "duplicate": True, **prior}
        record = self.state.bonds.get(bond_id)
        if record is None:
            return _err("unknown_bond", "not a collateralized bond")
        try:
            bond = await self.surety.process({"action": "status",
                                              "bond_id": bond_id})
        except Exception as exc:
            return _err("surety_error", f"{type(exc).__name__}")
        if bond.get("status") != "ok":
            return bond
        b = bond["data"]
        if b.get("state") not in ("RELEASED", "EXHAUSTED"):     # CB4
            return _err("not_terminal",
                        f"bond is {b.get('state')}; settlement paperwork "
                        "exists only for RELEASED/EXHAUSTED bonds")
        # The surety core's status exposes the slashed sum as
        # "slashed_total" (Bond.public()). Reading the wrong key here
        # would make slashed always 0 — which, under the 2026-07-19
        # auto-execute rule, would silently bypass the third-party gate
        # on slashed settlements. Accept both, prefer the real field.
        slashed = int(b.get("slashed_total") or b.get("slashed_minor") or 0)
        back_to_provider = max(record["collateral_minor"]
                               - record["premium_minor"] - slashed, 0)

        # CB4 (2026-07-19, legs refactor): the settlement is SPLIT into
        # per-counterparty legs so each gets the correct rail.
        legs = []
        if back_to_provider > 0:
            # FA-15: provider-return is a partial refund against the original
            # collateral Checkout Session. Stripe can only send it back to
            # the instrument that funded the collateral, so the same-party
            # classification is structural rather than caller-asserted.
            funded = getattr(getattr(self.custody, "state", None),
                             "funded", {}) or {}
            evidence = funded.get(record["collateral_escrow_id"])
            session_id = (evidence or {}).get("session_id")
            if not isinstance(session_id, str) or not session_id.strip():
                return _err(
                    "missing_collateral_evidence",
                    "cash collateral has no original Checkout Session; "
                    "provider return cannot execute without refund evidence")
            refund = self._execute_refund
            if refund is None:
                refund = getattr(self.custody, "_execute_refund", None)
            if refund is None:
                import stripe_payments
                refund = stripe_payments.create_refund
            try:
                issued = refund(
                    session_id,
                    idempotency_key=f"bond-provider-return:{bond_id}"[:255],
                    amount_minor=back_to_provider)
            except Exception as exc:
                self._errors[bond_id] = f"provider_refund: {type(exc).__name__}"
                return _err(
                    "refund_failed",
                    "provider-return refund failed; nothing recorded — retry "
                    "certify_settlement (Stripe idempotency prevents a "
                    "double refund)")
            if issued.get("status") != "ok":
                return issued
            refund_id = issued.get("refund_id")
            if not isinstance(refund_id, str) or not refund_id.strip():
                return _err("refund_failed",
                            "Stripe refund succeeded without a refund_id; "
                            "settlement was not recorded")
            legs.append({
                "leg": "provider_return", "payee": record["provider"],
                "amount_minor": back_to_provider,
                "rail": "stripe_refund",
                "scope": "same_party_refund",
                "session_id": session_id,
                "refund_id": refund_id,
                "payment_intent": issued.get("payment_intent"),
                "note": (f"return {back_to_provider} minor of remaining "
                         f"collateral (escrow "
                         f"{record['collateral_escrow_id']}) to "
                         f"{record['provider']} through Stripe refund "
                         f"{refund_id} — their own money, executed "
                         "autonomously (CB4/FA-15, 2026-07-20)"),
                "executed": True,
                "executed_at": issued.get("timestamp") or _now()})
        for claim in (b.get("claims") or []):
            if claim.get("state") != "PAID" \
                    or int(claim.get("paid_minor") or 0) <= 0:
                continue
            claimant = str(claim["claimant"])
            amount = int(claim["paid_minor"])
            purpose_key = f"bond-slash:{bond_id}:{claim['claim_id']}"[:255]
            if self.connect is not None and self.connect.can_pay(claimant):
                xfer = self.connect.execute_transfer(
                    claimant, amount, purpose_key=purpose_key,
                    transfer_group=bond_id,
                    metadata={"bond_id": bond_id,
                              "claim_id": claim["claim_id"],
                              "rail": "bond-slash"})
                if xfer.get("status") == "ok":
                    legs.append({
                        "leg": "claimant_payout", "payee": claimant,
                        "claim_id": claim["claim_id"],
                        "amount_minor": amount, "rail": "connect",
                        "scope": "third_party_licensed_rail",
                        "transfer_id": xfer["transfer_id"],
                        "executed": True,
                        "executed_at": xfer.get("executed_at") or _now()})
                    continue
                if xfer.get("error_type") != "payouts_not_enabled":
                    # Transient rail failure: fail-closed for the WHOLE
                    # certification — nothing recorded, fully retryable
                    # (exactly-once purpose_keys make the retry safe).
                    return xfer
                legs.append({
                    "leg": "claimant_payout", "payee": claimant,
                    "claim_id": claim["claim_id"],
                    "amount_minor": amount, "rail": "manual",
                    "action_for_justin": (
                        f"pay slashed claim {claim['claim_id']}: {amount} "
                        f"minor to {claimant} (per surety audit)"),
                    "onboarding_requirements_due": xfer.get(
                        "requirements_currently_due", []),
                    "executed": False, "executed_at": None})
            else:
                legs.append({
                    "leg": "claimant_payout", "payee": claimant,
                    "claim_id": claim["claim_id"],
                    "amount_minor": amount, "rail": "manual",
                    "action_for_justin": (
                        f"pay slashed claim {claim['claim_id']}: {amount} "
                        f"minor to {claimant} (per surety audit)"),
                    "onboarding_hint": (
                        "claimant can turn this and future payouts "
                        "autonomous via begin_payout_onboarding("
                        f"payee_id='{claimant}')"),
                    "executed": False, "executed_at": None})
        manual = [l for l in legs if not l["executed"]]
        instruction = {
            "bond_id": bond_id, "type": "bond_settlement",
            "slashed_minor": slashed,
            "premium_kept_minor": record["premium_minor"],
            "return_to_provider_minor": back_to_provider,
            "provider": record["provider"],
            "legs": legs,
            "executed": not manual,        # true iff every leg executed
            "certified_at": _now()}
        if manual:
            instruction["action_for_justin"] = "; ".join(
                l["action_for_justin"] for l in manual)
        self.state.instructions[bond_id] = instruction
        if not self._persist():                                 # CB6
            self.state.instructions.pop(bond_id, None)
            return _err("persist_failed", "not durable; retry")
        return {"status": "ok", "duplicate": False, **instruction}

    def mark_leg_executed(self, bond_id: Any, claim_id: Any,
                          money_primitive_id: Any = None) -> dict:
        """CB4: admin close-out for a MANUAL claimant_payout leg (payee not
        Connect-onboarded) — mirrors escrow_custody.mark_executed /
        weave.mark_transfer_executed. Idempotent per (bond_id, claim_id):
        an already-executed leg (marked before, or one that auto-executed
        via provider_return / the Connect rail) returns duplicate=True and
        changes nothing — a no-op, never a re-execution. Recomputes the
        top-level `executed` flag (true iff every leg executed). This is
        the ONLY way a manual leg is ever marked executed; it never
        touches connect_rail or any other money-movement path. CB7 requires
        the external receipt/transaction identifier from that manual action;
        the bridge never treats a bare boolean as proof of payment."""
        if not isinstance(bond_id, str) or not bond_id.strip():
            return _err("bad_bond_id", "bond_id is required")
        if not isinstance(claim_id, str) or not claim_id.strip():
            return _err("bad_claim_id", "claim_id is required")
        bond_id = bond_id.strip()
        claim_id = claim_id.strip()
        instruction = self.state.instructions.get(bond_id)
        if instruction is None:
            return _err("unknown_bond",
                        "no certified settlement for this bond")
        legs = instruction.get("legs") or []
        leg = next((l for l in legs
                   if l.get("leg") == "claimant_payout"
                   and l.get("claim_id") == claim_id), None)
        if leg is None:
            return _err("unknown_claim",
                        f"no claimant_payout leg for claim_id '{claim_id}' "
                        f"on bond '{bond_id}'")
        if leg["executed"]:                                 # idempotent
            return {"status": "ok", "duplicate": True, "bond_id": bond_id,
                    "claim_id": claim_id, **instruction}
        if not isinstance(money_primitive_id, str) \
                or not money_primitive_id.strip():
            return _err(
                "missing_money_primitive",
                "money_primitive_id is required before a manual claimant "
                "leg can be marked executed")
        primitive = money_primitive_id.strip()
        if len(primitive) > 255:
            return _err("bad_money_primitive",
                        "money_primitive_id must be at most 255 characters")
        leg["executed"] = True
        leg["executed_at"] = _now()
        leg["money_primitive_id"] = primitive
        instruction["executed"] = all(l["executed"] for l in legs)
        if not self._persist():                             # CB6 revert
            leg["executed"] = False
            leg["executed_at"] = None
            leg.pop("money_primitive_id", None)
            instruction["executed"] = all(l["executed"] for l in legs)
            return _err("persist_failed", "not durable; retry")
        return {"status": "ok", "duplicate": False, "bond_id": bond_id,
                "claim_id": claim_id, **instruction}

    def status(self) -> dict:
        bonds = list(self.state.bonds.values())
        return {"collateralized_bonds": len(bonds),
                "coverage_total_minor": sum(b["coverage_minor"]
                                            for b in bonds),
                "premiums_earned_minor": sum(b["premium_minor"]
                                             for b in bonds),
                "viridis_capital_at_risk_minor": 0,   # the whole point
                "settlements_certified": len(self.state.instructions),
                "note": ("bonds are backed by the provider's own "
                         "cash-funded collateral escrow (CB1); slashing is "
                         "ruling-gated in the surety core (SB); clean-expiry "
                         "collateral return executes as a Stripe same-party "
                         "refund with refund_id evidence; claimant Connect "
                         "transfers carry transfer_id evidence (CB4/CB7, "
                         "2026-07-20)"),
                "errors": dict(self._errors)}
