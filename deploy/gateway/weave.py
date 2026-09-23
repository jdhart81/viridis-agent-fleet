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
verified supply, certificate attached) -> the share is allocated from
EnergyAI revenue to Viridis Conservation AUTONOMOUSLY, no human step.

Money-movement doctrine (revised 2026-07-19, Justin — see
docs/legal/THIRD_PARTY_PAYOUT_LICENSING_QUESTION_2026-07-19.md and memory
feedback_autonomous_money_movement): the fleet's job is to handle money
end-to-end without a human bottleneck. That splits into two cases with
different risk profiles, not one blanket rule:
  - SAME-ACCOUNT allocations (this module): EnergyAI and Viridis
    Conservation both settle under one Stripe account
    (acct_1BLyFZDTpwaqE8Ss / ViridisNorth — confirmed via
    get_stripe_account_info on 2026-07-19). There is no wire, no
    counterparty, no money-transmission exposure — it's Viridis
    reallocating its own balance. Software executes this itself.
  - CROSS-ACCOUNT / THIRD-PARTY restoration payees use the existing
    Connect rail. A pull-verified, payouts-enabled connected account is
    paid autonomously by Stripe; a non-onboarded payee receives the CR7
    certified manual fallback and onboarding guidance. No other movement
    rail exists here.

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
WV4  Cash movement for this same-account allocation executes
     autonomously at weave time: every woven event carries a cash
     instruction (payer EnergyAI -> payee Viridis Conservation,
     share_minor) recorded with executed=True, executed_at set, no human
     step. `mark_transfer_executed` is retained only as an idempotent
     confirmation endpoint for callers that still poll it — it is a
     no-op against an already-executed record. This does NOT apply to
     cross-account/third-party payouts (see doctrine note above).
WV5  Failures degrade to structured refusals and the event is NOT
     recorded as woven — a clearinghouse error never creates a phantom
     obligation, and a persistence failure reverts in-memory state.
WV6  The weave ledger is a CONSERVATION OBLIGATION ledger, reported
     distinctly — its totals are never presented as fleet service revenue
     (they are EnergyAI's restoration share in flight to conservation).
WV7  An external restoration payee uses ConnectRail exactly once with
     purpose_key `weave-restoration:<event_id>`. Not-onboarded or incomplete
     payees fall back to a certified manual instruction; transient rail
     failures fail closed and record no woven event. Dry-runs never transfer.
WV8  Legacy persisted records are durably closed at restore time only if
     their instruction is explicitly scoped `same_account_allocation` OR it
     matches the pre-WV4 fixed-beneficiary schema (restoration-share type, no
     payee/rail/scope, exact EnergyAI-to-Viridis action text). The migration
     never touches an external/manual instruction and reverts its in-memory
     change if persistence fails.
"""
from __future__ import annotations

import copy
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

DEFAULT_RESTORATION_PAYEE = "viridis:conservation"


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

    def __init__(self, store, offsets_core, persist_key: str = "weave",
                 connect=None):
        self.store = store
        self.offsets = offsets_core
        self.persist_key = persist_key
        self.connect = connect
        self.state = WeaveState()
        self._errors: Dict[str, str] = {}
        try:                                                   # WV5 posture
            self.store.restore(persist_key, self.state)
        except Exception as exc:
            self._errors["restore"] = f"{type(exc).__name__}: {exc}"
        else:
            self._close_legacy_same_account()

    def _close_legacy_same_account(self) -> None:
        """WV8: reconcile pre-WV4 same-account records without a human step."""
        changed = []
        for event_id, record in self.state.events.items():
            instruction = record.get("cash_instruction")
            if not isinstance(instruction, dict) \
                    or instruction.get("executed") is True:
                continue
            legacy_action = str(instruction.get("action_for_justin", ""))
            pre_wv4_fixed_beneficiary = (
                instruction.get("type") == "restoration_share_transfer"
                and not any(key in instruction
                            for key in ("scope", "rail", "payee"))
                and legacy_action.startswith("move ")
                and "from EnergyAI Stripe to Viridis Conservation "
                    "(restoration share," in legacy_action)
            if (instruction.get("scope") != "same_account_allocation"
                    and not pre_wv4_fixed_beneficiary):
                continue
            changed.append((event_id, copy.deepcopy(record)))
            instruction["scope"] = "same_account_allocation"
            instruction["payee"] = DEFAULT_RESTORATION_PAYEE
            instruction["executed"] = True
            instruction["executed_at"] = _now()
            instruction["autonomy_migration"] = "FA-I1-2026-07-20"
            if legacy_action:
                instruction["note"] = (
                    f"{legacy_action} — legacy same-account allocation "
                    "closed autonomously; no wire")
                instruction.pop("action_for_justin", None)
            record.setdefault("restoration_payee",
                              DEFAULT_RESTORATION_PAYEE)
        if not changed:
            return
        try:
            saved = bool(self.store.save(self.persist_key, self.state))
        except Exception:
            saved = False
        if saved:
            return
        for event_id, original in changed:
            self.state.events[event_id] = original
        self._errors["legacy_same_account_migration"] = (
            "persist_failed: legacy same-account records remain pending")

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
                          dry_run: bool = False,
                          payee_id: Any = DEFAULT_RESTORATION_PAYEE) -> dict:
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
        if not isinstance(payee_id, str) or not payee_id.strip():
            return _err("bad_payee", "payee_id must be a non-empty string")
        payee = payee_id.strip()
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
        if payee.startswith("viridis:"):
            payee_label = ("Viridis Conservation"
                           if payee == DEFAULT_RESTORATION_PAYEE else payee)
            cash_instruction = {                                # WV4
                "type": "restoration_share_transfer",
                "payee": payee,
                "scope": "same_account_allocation",
                "note": (
                    f"{share} minor units allocated from EnergyAI revenue "
                    f"to {payee_label} (restoration share, "
                    f"{RATE_SCHEDULE['version']}) — both under Stripe "
                    "acct_1BLyFZDTpwaqE8Ss, executed autonomously, no wire"),
                "executed": not bool(dry_run),
                "executed_at": None if dry_run else _now(),
            }
        else:
            base = {                                             # WV7
                "type": "restoration_share_transfer",
                "payee": payee,
                "amount_minor": share,
            }
            can_connect = (self.connect is not None
                           and self.connect.can_pay(payee))
            if dry_run:
                if can_connect:
                    cash_instruction = {
                        **base, "rail": "connect",
                        "scope": "third_party_licensed_rail",
                        "would_execute": True,
                        "note": (f"preview only: {share} minor units would "
                                 f"transfer to {payee} through Stripe Connect"),
                        "executed": False, "executed_at": None,
                    }
                else:
                    cash_instruction = {
                        **base, "rail": "manual", "would_execute": False,
                        "action_for_justin": (
                            f"pay {share} minor units to restoration payee "
                            f"{payee}"),
                        "onboarding_hint": (
                            "payee can make the live transfer autonomous by "
                            "completing Stripe Connect onboarding: call "
                            f"begin_payout_onboarding(payee_id='{payee}')"),
                        "executed": False, "executed_at": None,
                    }
            elif can_connect:
                xfer = self.connect.execute_transfer(
                    payee, share,
                    purpose_key=f"weave-restoration:{event_id}"[:255],
                    transfer_group=event_id,
                    metadata={"event_id": event_id,
                              "rail": "weave-restoration"})
                if xfer.get("status") == "ok":
                    cash_instruction = {
                        **base, "rail": "connect",
                        "scope": "third_party_licensed_rail",
                        "transfer_id": xfer["transfer_id"],
                        "note": (f"paid {share} minor units to restoration "
                                 f"payee {payee} through Stripe Connect "
                                 f"transfer {xfer['transfer_id']} — autonomous, "
                                 "no human step"),
                        "executed": True,
                        "executed_at": xfer.get("executed_at") or _now(),
                    }
                elif xfer.get("error_type") == "payouts_not_enabled":
                    cash_instruction = {
                        **base, "rail": "manual",
                        "action_for_justin": (
                            f"pay {share} minor units to restoration payee "
                            f"{payee}"),
                        "onboarding_requirements_due": xfer.get(
                            "requirements_currently_due", []),
                        "executed": False, "executed_at": None,
                    }
                else:
                    return xfer
            else:
                cash_instruction = {
                    **base, "rail": "manual",
                    "action_for_justin": (
                        f"pay {share} minor units to restoration payee {payee}"),
                    "onboarding_hint": (
                        "payee can make future restoration transfers autonomous "
                        "by completing Stripe Connect onboarding: call "
                        f"begin_payout_onboarding(payee_id='{payee}')"),
                    "executed": False, "executed_at": None,
                }

        record = {
            "event_id": event_id,
            "revenue_type": revenue_type,
            "amount_minor": amount_minor,
            "share_minor": share,
            "restoration_payee": payee,
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
            "cash_instruction": cash_instruction,
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
        """WV4/WV7: idempotent confirmation/admin close-out.

        Same-account and Connect instructions are already executed and return
        duplicate=True. A CR7 manual external-payee instruction can be marked
        executed only after the certified fallback was completed."""
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
