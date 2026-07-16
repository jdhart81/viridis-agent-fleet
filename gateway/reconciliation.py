"""Revenue reconciliation — ledger accrual vs Stripe settled cash (G10).

Lives in the gateway (next to stripe_payments.py), NOT in the metering agent:
the billing-critical metering core must never hold or receive payment
credentials. This module is a pure read-side composition of three sources:

  1. The metering core's gateway-origin meters (gross usage value + frozen
     daily invoices) — what the ledger says usage is worth.
  2. The payment gate's redemption records — which Stripe sessions were
     converted into prepaid credits, per agent.
  3. Stripe's Checkout Sessions API — what cash actually settled.

Money-flow reality this report is honest about: the fleet does NOT invoice
externally. Humans prepay via Stripe Checkout, redeem the session for call
credits, then consume credits. Meter "accrued" therefore measures GROSS USAGE
VALUE (every call at list price, including the free tier) and will exceed
settled cash by design. The report separates the two instead of pretending
they should be equal.

--- INVARIANTS ---
RV1  Read-only: never mutates the metering core, the gate state, or Stripe.
RV2  Honest accounting: gross usage value, frozen invoice totals, redeemed
     value, and Stripe settled cash are reported as distinct numbers with
     explicit definitions — never silently netted against each other.
RV3  Discrepancy candor: paid-but-unredeemed sessions, redeemed-but-missing
     sessions, and test-mode sessions are enumerated, never dropped.
RV4  Degrades structurally: a Stripe failure (no key, API error) yields a
     report with stripe.status="error" and the ledger side intact — never an
     exception into a tool call.
RV5  Test traffic is visible but separate: gateway meters flagged is_test
     and internal/self-test events never inflate the headline numbers
     (they ride on the metering core's G7 exclusion).
RV6  A2A escrow settlement (PG13-PG16) is a CLOSED-LOOP INTERNAL LEDGER
     quantity — the escrow core custodies no funds (PG17 deferred). It is
     reported in its own a2a_escrow bucket with an explicit non-cash label
     and is never summed into settled_minor, redeemed_minor, or any number
     presented as cash.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def build_report(metering_core: Any, gate: Any, *, days: int = 30,
                       list_sessions: Optional[Callable[..., dict]] = None,
                       now_epoch: Optional[int] = None) -> dict:
    """Compose the reconciliation report. `gate` is the PaymentGate (for
    redemption records); `list_sessions` is injectable for tests and defaults
    to stripe_payments.list_checkout_sessions (RV1: all reads)."""
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 365:
        return {"status": "error", "error_type": "ValidationError",
                "field": "days", "message": "days must be an int in [1, 365]",
                "timestamp": _now()}
    now_epoch = int(now_epoch if now_epoch is not None else time.time())
    since_epoch = now_epoch - days * 86400

    # ---- 1. Ledger side: gateway-origin meters only (RV5 excludes test) --
    ledger_providers: dict = {}
    ledger_totals = {"gross_usage_value_minor": 0, "invoiced_minor": 0,
                     "events": 0, "meters": 0}
    listed = await metering_core.process({"action": "list_meters"})
    for m in (listed.get("data") or {}).get("meters", []):
        # Meter origin: "gateway" = fleet billing; "legacy" = pre-v0.2.0
        # gateway/public mixed (kept for continuity); "public" = sandbox.
        if m.get("origin", "legacy") == "public" or m.get("is_test"):
            continue
        summary = await metering_core.process(
            {"action": "usage_summary", "meter_id": m["meter_id"]})
        if summary.get("status") != "ok":
            continue
        s = summary["data"]
        prov = ledger_providers.setdefault(m["provider"], {
            "gross_usage_value_minor": 0, "invoiced_minor": 0,
            "events": 0, "meters": 0, "origin_mix": set()})
        prov["gross_usage_value_minor"] += int(s.get("accrued_minor", 0))
        prov["events"] += int(s.get("event_count", 0))
        prov["meters"] += 1
        prov["origin_mix"].add(m.get("origin", "legacy"))
    # Frozen daily invoices live on each gated core's gate state (PG7).
    for name, core in getattr(gate, "_cores", {}).items():
        state = getattr(core, "_payment_gate_state", None) or {}
        for inv in state.get("invoices", []):
            prov = ledger_providers.setdefault(f"viridis:{name}", {
                "gross_usage_value_minor": 0, "invoiced_minor": 0,
                "events": 0, "meters": 0, "origin_mix": set()})
            prov["invoiced_minor"] += int(inv.get("amount_minor", 0))
    for prov in ledger_providers.values():
        prov["origin_mix"] = sorted(prov["origin_mix"])
        for k in ("gross_usage_value_minor", "invoiced_minor",
                  "events", "meters"):
            ledger_totals[k] += prov[k]

    # ---- 2. Redemption side: sessions converted to credits ---------------
    redemptions: dict = {"by_agent": {}, "total_redeemed_minor": 0,
                         "credits_outstanding": 0}
    redeemed_ids: dict = {}
    for name, core in getattr(gate, "_cores", {}).items():
        state = getattr(core, "_payment_gate_state", None) or {}
        sessions = state.get("redeemed_sessions", {}) or {}
        agent_total = sum(int(v.get("amount_minor") or 0)
                          for v in sessions.values())
        redemptions["by_agent"][name] = {
            "sessions_redeemed": len(sessions),
            "redeemed_minor": agent_total,
            "credits_outstanding": int(state.get("credits", 0)),
        }
        redemptions["total_redeemed_minor"] += agent_total
        redemptions["credits_outstanding"] += int(state.get("credits", 0))
        for sid in sessions:
            redeemed_ids[sid] = name

    # ---- 2b. A2A escrow settlement: internal ledger, NOT cash (RV6) -------
    a2a_escrow: dict = {"by_agent": {}, "total_escrow_settled_minor": 0,
                        "escrows_consumed": 0,
                        "is_cash": False,
                        "meaning": "escrows consumed for call credits via "
                                   "the gate's a2a rail (PG13-PG16). The "
                                   "escrow core custodies no funds — this is "
                                   "a closed-loop internal ledger quantity, "
                                   "never cash (PG17 deferred)."}
    for name, core in getattr(gate, "_cores", {}).items():
        state = getattr(core, "_payment_gate_state", None) or {}
        consumed = state.get("consumed_escrows", {}) or {}
        agent_minor = sum(int(v.get("amount_minor") or 0)
                          for v in consumed.values())
        if consumed:
            a2a_escrow["by_agent"][name] = {
                "escrows_consumed": len(consumed),
                "escrow_settled_minor": agent_minor,
                "credits_granted": sum(int(v.get("credits") or 0)
                                       for v in consumed.values()),
            }
        a2a_escrow["total_escrow_settled_minor"] += agent_minor
        a2a_escrow["escrows_consumed"] += len(consumed)

    # ---- 3. Stripe side: settled cash in the window (RV4) ----------------
    if list_sessions is None:
        import stripe_payments
        list_sessions = stripe_payments.list_checkout_sessions
    stripe_side: dict
    try:
        raw = list_sessions(created_after_epoch=since_epoch, limit=100)
    except Exception as e:  # RV4
        raw = {"status": "error", "error_type": "stripe_error",
               "message": str(e)[:200]}
    if raw.get("status") != "ok":
        stripe_side = {"status": "error", "detail": raw,
                       "settled_minor": None, "paid_sessions": None}
        paid_sessions = []
    else:
        paid_sessions = [s for s in raw["sessions"]
                         if s.get("payment_status") == "paid"
                         and s.get("livemode")]
        stripe_side = {
            "status": "ok",
            "settled_minor": sum(int(s.get("amount_total") or 0)
                                 for s in paid_sessions),
            "paid_sessions": len(paid_sessions),
            "testmode_sessions": [s["session_id"] for s in raw["sessions"]
                                  if not s.get("livemode")],
            "window_truncated": bool(raw.get("has_more")),
        }

    # ---- 4. Discrepancies (RV3) ------------------------------------------
    discrepancies = []
    for s in paid_sessions:
        sid = s.get("session_id")
        if sid and sid not in redeemed_ids:
            discrepancies.append({
                "type": "paid_not_redeemed", "session_id": sid,
                "amount_minor": s.get("amount_total"),
                "meaning": "cash settled but credits never claimed"})
    stripe_ids = {s.get("session_id") for s in paid_sessions}
    for sid, agent in redeemed_ids.items():
        if stripe_side["status"] == "ok" and sid not in stripe_ids:
            discrepancies.append({
                "type": "redeemed_outside_window", "session_id": sid,
                "agent": agent,
                "meaning": f"redeemed >{days}d ago or missing from Stripe "
                           "listing — widen the window before treating as "
                           "an anomaly"})

    return {
        "status": "ok",
        "generated_at": _now(),
        "window": {"days": days, "since_epoch": since_epoch},
        "ledger": {"providers": ledger_providers, "totals": ledger_totals},
        "redemptions": redemptions,
        "a2a_escrow": a2a_escrow,
        "stripe": stripe_side,
        "discrepancies": discrepancies,
        "definitions": {
            "gross_usage_value_minor": "every metered call at list price, "
                                       "INCLUDING the daily free tier — an "
                                       "activity measure, not receivables",
            "invoiced_minor": "daily periods frozen by the gate's rollover "
                              "(PG7); the fleet's internal ledger of record",
            "settled_minor": "Stripe live-mode paid Checkout Sessions in the "
                             "window — the only number that is actual cash",
            "redeemed_minor": "settled sessions converted into call credits",
            "escrow_settled_minor": "escrows consumed for credits over the "
                                    "a2a rail — internal ledger only, NOT "
                                    "cash (RV6); excluded from settled_minor",
        },
    }
