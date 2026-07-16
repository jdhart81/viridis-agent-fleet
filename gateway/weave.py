"""
weave.py — The Weave: EnergyAI revenue routes restoration through the
fleet's OWN rails. Viridis becomes its own first arm's-length customer.

Rate schedule (RATIFIED 2026-07-16, Justin, option B of
docs/deployment/WEAVE_RATE_OPTIONS_2026-07-16.md):

    weave-B-v1:  10.00% of subscription revenue (1000 bps)
                  5.00% of lead-fee revenue      (500 bps)
    escalator (pre-committed, per the fleet's pricing doctrine — never
    ad hoc): +500 bps on the subscription rate per $10,000 cumulative
    EnergyAI MRR, capped at 2500 bps (25%). The escalator changes the
    VERSION (weave-B-v2, ...), never silently mutates v1 records.

Flow per revenue event: deterministic share computation -> the share is
executed against the offset-clearinghouse as a money-denominated
purchase+retirement (`buy_offset_budget`, retired cheapest-first from
verified supply, certificate attached) -> a CERTIFIED cash instruction for
Justin (move the share from EnergyAI's Stripe to Viridis Conservation).
Software never moves the money (fleet doctrine; same as EC5).

--- INVARIANTS (spec-invariance contract) ---
WV1  The rate schedule is pre-committed, versioned, and embedded in every
     record. A share is computed from the schedule version current at
     record time; later escalations never rewrite history.
WV2  share_minor = floor(amount_minor * bps / 10000), integer math only.
     Idempotent on event_id: a replayed event returns the original record
     and never double-retires or double-obligates.
WV3  The share is settled through the fleet's own clearinghouse:
     buy_offset_budget(budget_minor=share, purchase_id=weave:<event_id>)
     — retirement certificate (and its Verra provenance, when present)
     rides into the weave record. The clearinghouse's own idempotency (O2)
     backs WV2 at the settlement layer.
WV4  Cash movement is never executed by software: every woven event
     carries a certified instruction (payer EnergyAI -> payee Viridis
     Conservation, share_minor) with executed=False until the admin marks
     it done. Mirrors escrow_custody EC5 exactly.
WV5  Failures degrade to structured refusals and the event is NOT
     recorded as woven — a clearinghouse error never creates a phantom
     obligation, and a persistence failure reverts in-memory state.
WV6  The weave ledger is a CONSERVATION OBLIGATION ledger, reported
     distinctly — its totals are never presented as fleet service revenue
     (they are EnergyAI's restoration share in flight to conservation).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("viridis.weave")

RATE_SCHEDULE = {                                             # WV1
    "version": "weave-B-v1",
    "ratified": "2026-07-16",
    "ratified_by": "Justin Hart (option B)",
    "rates_bps": {"subscription": 1000, "lead": 500},
    "escalator": ("+500 bps subscription rate per $10,000 cumulative "
                  "EnergyAI MRR, cap 2500 bps; each step is a new "
                  "schedule version, never a rewrite"),
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _err(error_type: str, message: str, **extra) -> dict:
    return {"status": "error", "error_type": error_type,
            "message": message, "timestamp": _now(), **extra}


class WeaveState:
    """Plain persisted holder (same pattern as CustodyState)."""

    def __init__(self):
        self.events: Dict[str, dict] = {}     # event_id -> woven record


class Weave:
    """Composes revenue events into retired offsets + certified cash."""

    def __init__(self, store, offsets_core, persist_key: str = "weave"):
        self.store = store
        self.offsets = offsets_core
        self.persist_key = persist_key
        self.state = WeaveState()
        self._errors: Dict[str, str] = {}
        try:                                                   # WV5 posture
            self.store.restore(persist_key, self.state)
        except Exception as exc:
            self._errors["restore"] = f"{type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------ #
    @staticmethod
    def compute_share(revenue_type: str, amount_minor: int) -> Optional[int]:
        """WV1/WV2: pure, deterministic, integer-only."""
        bps = RATE_SCHEDULE["rates_bps"].get(revenue_type)
        if bps is None:
            return None
        return (amount_minor * bps) // 10000

    async def weave_event(self, event_id: Any, revenue_type: Any,
                          amount_minor: Any, source: Any = "",
                          dry_run: bool = False) -> dict:
        if not isinstance(event_id, str) or not event_id.strip():
            return _err("bad_event_id", "event_id is required")
        event_id = event_id.strip()
        prior = self.state.events.get(event_id)
        if prior is not None:                                  # WV2 idempotent
            return {"status": "ok", "duplicate": True, **prior}
        if revenue_type not in RATE_SCHEDULE["rates_bps"]:     # WV1
            return _err("bad_revenue_type",
                        "revenue_type must be one of "
                        f"{sorted(RATE_SCHEDULE['rates_bps'])}")
        if (not isinstance(amount_minor, int) or isinstance(amount_minor, bool)
                or amount_minor <= 0):
            return _err("bad_amount", "amount_minor must be a positive int")
        share = self.compute_share(revenue_type, amount_minor)  # WV2
        if share <= 0:
            return _err("share_rounds_to_zero",
                        f"{amount_minor} minor at "
                        f"{RATE_SCHEDULE['rates_bps'][revenue_type]} bps "
                        "yields no whole minor unit; batch smaller events")
        try:                                                    # WV3
            purchase = await self.offsets.process({
                "action": "buy_offset_budget",
                "buyer": "viridis:weave/energyai",
                "purchase_id": f"weave:{event_id}",
                "budget_minor": share,
                "dry_run": bool(dry_run)})
        except Exception as exc:                                # WV5
            self._errors[event_id] = f"offsets: {type(exc).__name__}"
            return _err("clearinghouse_error",
                        "offset purchase failed; event NOT woven — retry")
        if purchase.get("status") != "ok":                      # WV5
            return _err("clearinghouse_refused",
                        f"offsets refused: {purchase.get('message')}",
                        detail={k: purchase.get(k)
                                for k in ("error_type", "field", "constraint")})
        pdata = purchase.get("data") or {}
        record = {
            "event_id": event_id,
            "revenue_type": revenue_type,
            "amount_minor": amount_minor,
            "share_minor": share,
            "rate_schedule": dict(RATE_SCHEDULE),               # WV1
            "source": str(source)[:200],
            "retirement": {
                "purchase_id": pdata.get("purchase_id"),
                "retired_g": pdata.get("mass_g"),
                "spent_minor": pdata.get("total_cost_minor"),
                "certificate_hash": pdata.get("certificate_hash"),  # O4
                "retired_at": pdata.get("retired_at"),
                "fills": pdata.get("fills"),
            },
            "cash_instruction": {                               # WV4
                "type": "restoration_share_transfer",
                "action_for_justin": (
                    f"move {share} minor units from EnergyAI Stripe to "
                    "Viridis Conservation (restoration share, "
                    f"{RATE_SCHEDULE['version']})"),
                "executed": False, "executed_at": None,
            },
            "dry_run": bool(dry_run),
            "woven_at": _now(),
        }
        if dry_run:                    # preview: nothing recorded (WV2 intact)
            return {"status": "ok", "duplicate": False, "preview": True,
                    **record}
        self.state.events[event_id] = record
        try:
            saved = bool(self.store.save(self.persist_key, self.state))
        except Exception:
            saved = False
        if not saved:                                           # WV5 revert
            self.state.events.pop(event_id, None)
            return _err("persist_failed",
                        "retirement executed but weave record not durable; "
                        "RETRY THE SAME event_id — the clearinghouse "
                        "purchase is idempotent (O2), nothing double-retires")
        self._errors.pop(event_id, None)
        logger.info("weave: %s -> share %s minor -> retired %sg (%s)",
                    event_id, share, record["retirement"]["retired_g"],
                    RATE_SCHEDULE["version"])
        return {"status": "ok", "duplicate": False, **record}

    def mark_transfer_executed(self, event_id: Any) -> dict:
        """WV4: the admin records the manual Stripe transfer. Idempotent."""
        record = self.state.events.get(
            event_id.strip() if isinstance(event_id, str) else "")
        if record is None:
            return _err("unknown_event", "no woven event with that id")
        instr = record["cash_instruction"]
        if instr["executed"]:
            return {"status": "ok", "duplicate": True, **record}
        instr["executed"] = True
        instr["executed_at"] = _now()
        try:
            saved = bool(self.store.save(self.persist_key, self.state))
        except Exception:
            saved = False
        if not saved:                                           # WV5
            instr["executed"] = False
            instr["executed_at"] = None
            return _err("persist_failed", "not durable; retry")
        return {"status": "ok", "duplicate": False, **record}

    def status(self) -> dict:                                   # WV6
        events = list(self.state.events.values())
        pending = [e for e in events
                   if not e["cash_instruction"]["executed"]]
        return {
            "rate_schedule": dict(RATE_SCHEDULE),
            "events_woven": len(events),
            "share_total_minor": sum(e["share_minor"] for e in events),
            "retired_total_g": sum(int(e["retirement"].get("retired_g") or 0)
                                   for e in events),
            "cash_transfers_pending": len(pending),
            "cash_pending_minor": sum(e["share_minor"] for e in pending),
            "meaning": ("CONSERVATION OBLIGATION ledger (WV6) — EnergyAI's "
                        "restoration share, retired through the fleet's own "
                        "clearinghouse; never fleet service revenue"),
            "errors": dict(self._errors),
        }
