"""
underwriting_bridge.py — price a surety bond from a Verified track record.

The composition that turns evidence into an insurable number: a provider that
has racked up successful, tamper-evident Viridis Verified deliveries has, by
construction, a track record — and the surety underwriter (model uw-v1) can
price a bond behind it. This is the "trust-with-consequences" seat made
concrete: attestation without skin-in-the-game is a phone book; here the
receipts a provider earned relaying real calls become the actuarial input to
what it costs to bond them.

Lives in the gateway (like reconciliation.py) so the two agent cores stay
decoupled — the metering/billing-critical cores never import each other. This
is a pure read-side composition of two in-scope cores at build_app time; it
adds no new mount and no new agent (growth gate intact).

Mapping (conservative, honest — the premium reflects DELIVERY history only):
  successful_deliveries <- service.calls_ok      (proven good relays lower the rate)
  slashes / slashed_minor <- 0                    (Verified has no slash authority;
                                                   only agent-arbitration can slash,
                                                   so we never fabricate one here)
  attestations / bonds_completed <- 0             (out of scope for this bridge;
                                                   a future trust-oracle bridge can
                                                   raise the evidence weight)
A provider with zero successful deliveries prices at the unknown-counterparty
rate (or is declined by surety's own ceiling) — no free lunch.

--- INVARIANTS ---
BW1  Read-only: never mutates Verified or surety state (both calls are pure
     reads / pure computations).
BW2  Unknown service_id -> structured error envelope, never a crash.
BW3  Monotonicity: for fixed coverage and duration, a service with more
     successful deliveries never receives a HIGHER premium than one with
     fewer (delegated to surety's uw-v1 monotonicity; asserted in tests).
BW4  Traceability: the returned quote carries surety's recomputable
     quote_hash and the exact history inputs used, so any party can re-derive
     the premium from the disclosed Verified stats.
BW5  Honest evidence: only calls_ok feeds successful_deliveries; error and
     total counts are reported for transparency but never invented into
     attestations or negative into slashes.
BW6  Validation is delegated: coverage_minor / duration_days bounds and
     integer-only arithmetic are enforced by surety.price_bond, so the bridge
     and the core cannot disagree on what is a valid quote.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def quote_bond_for_service(verified_core: Any, surety_core: Any,
                                 service_id: str, coverage_minor: int,
                                 duration_days: int) -> dict:
    """Compose Verified delivery stats -> surety bond quote (BW1-BW6)."""
    if not isinstance(service_id, str) or not service_id:
        return {"status": "error", "error_type": "ValidationError",
                "field": "service_id", "message": "service_id is required",
                "timestamp": _now()}

    stats = await verified_core.process(
        {"action": "service_stats", "service_id": service_id})   # BW1 read
    if stats.get("status") != "ok":                              # BW2
        return stats
    s = stats["data"]

    calls_ok = int(s.get("calls_ok", 0))
    history = {                                                  # BW5 honest map
        "successful_deliveries": calls_ok,
        "attestations": 0,
        "bonds_completed": 0,
        "slashes": 0,
        "slashed_minor": 0,
    }
    quote = await surety_core.process({                         # BW1 read/pure
        "action": "price_bond",
        "coverage_minor": coverage_minor,
        "duration_days": duration_days,
        "history": history,
    })
    if quote.get("status") != "ok":                             # BW6 delegated
        return quote

    return {
        "status": "ok",
        "generated_at": _now(),
        "service": {
            "service_id": s.get("service_id"),
            "provider": s.get("provider"),
            "url": s.get("url"),
            "calls_total": s.get("calls_total"),
            "calls_ok": calls_ok,
            "calls_error": s.get("calls_error"),
        },
        "underwriting_inputs": history,                         # BW4 disclosure
        "quote": quote["data"],                                 # carries quote_hash
        "note": ("Premium reflects Viridis Verified delivery history only "
                 "(successful relays). It is a quote, not a bound policy; "
                 "post + activate a bond on agent-surety to make it real."),
    }
