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
party FROM the collateral; clean expiry returns it — both as CERTIFIED
instructions only (EC5 doctrine: software never moves cash out).

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
CB4  Cash out is certified only: a slash produces a certified payout
     instruction (claimant, amount from collateral); expiry release
     produces a certified collateral-return instruction (collateral -
     premium - total slashed). Software never executes either.
CB5  Idempotent everywhere: bind is exactly-once per collateral escrow;
     settlement certification is exactly-once per bond event; replays
     return the original record.
CB6  Failures refuse with structured envelopes and revert (save-or-revert,
     PB5/EC7 family); bridge state persists and survives restarts.
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
                 custody, persist_key: str = "bonds"):
        self.store = store
        self.escrow = escrow_core
        self.surety = surety_core
        self.verified = verified_core
        self.custody = custody
        self.persist_key = persist_key
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
        """CB4: certified cash-out paperwork for a bond's terminal events —
        slashed amounts to claimants, remaining collateral back to the
        provider on release. Never moves money; idempotent per bond."""
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
        slashed = int(b.get("slashed_minor") or 0)
        back_to_provider = record["collateral_minor"] \
            - record["premium_minor"] - slashed
        instruction = {
            "bond_id": bond_id, "type": "bond_settlement",
            "slashed_minor": slashed,
            "premium_kept_minor": record["premium_minor"],
            "return_to_provider_minor": max(back_to_provider, 0),
            "provider": record["provider"],
            "action_for_justin": (
                f"from collateral {record['collateral_minor']} minor "
                f"(escrow {record['collateral_escrow_id']}): keep premium "
                f"{record['premium_minor']}, pay slashed claims {slashed} "
                f"per surety audit, return "
                f"{max(back_to_provider, 0)} to {record['provider']}"),
            "certified_at": _now(), "executed": False}
        self.state.instructions[bond_id] = instruction
        if not self._persist():                                 # CB6
            self.state.instructions.pop(bond_id, None)
            return _err("persist_failed", "not durable; retry")
        return {"status": "ok", "duplicate": False, **instruction}

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
                         "ruling-gated in the surety core (SB); cash out "
                         "is certified only (CB4)"),
                "errors": dict(self._errors)}
