"""
insured_job_bridge.py — the insured-delivery product as ONE call.

Insured Delivery (scripts/insured_delivery_demo.py) proves six Viridis rails
compose into insurable agent-to-agent work. But a buyer shouldn't have to
hand-wire six rails to find out what it costs. This bridge answers, in a
single read-only call, "what does it cost to insure this job, and how do I
run it?" — turning the composition PROOF into an evaluable, executable
PRODUCT.

It composes (all reads / pure): the provider's Viridis Verified delivery
record -> a surety bond premium priced off that record (underwriting uw-v1)
-> the escrow settlement fee -> a total protection cost, plus the exact
ordered playbook of calls each party makes to run the insured job.

Lives in the gateway (like reconciliation.py / underwriting_bridge.py) so the
agent cores stay decoupled; no new mount, no new agent.

--- INVARIANTS ---
IJ1  The bond premium is priced from the provider's Verified track record via
     the SAME underwriting bridge (uw-v1) used elsewhere; the recomputable
     quote_hash is carried through for auditability.
IJ2  Itemized totals are exact integers: total_protection_cost_minor ==
     bond_premium_minor + escrow_fee_minor.
IJ3  Read-only: composes only reads/pure computations; never posts a bond,
     opens an escrow, or mutates any core.
IJ4  Unknown service_id -> structured error envelope, never a crash.
IJ5  Honest insurability: if surety DECLINES to bond the provider (SB10 risk
     ceiling), the job is reported insurable=false with the decline reason and
     no fabricated premium.
IJ6  The playbook is the exact, deterministic, ordered sequence of tool calls
     that executes the insured job end to end (post bond -> activate -> open
     escrow -> fund -> deliver+notarize -> release | dispute->rule->slash).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _playbook(service_id: str, coverage_minor: int, job_amount_minor: int) -> list:
    """IJ6: the exact ordered calls to run the insured job."""
    return [
        {"step": 1, "actor": "provider", "mount": "surety", "tool": "post_bond",
         "args": {"principal_agent": "<provider>", "principal": coverage_minor,
                  "coverage": "insured delivery", "expires_at": "<ISO deadline>"}},
        {"step": 2, "actor": "provider", "mount": "surety", "tool": "activate",
         "args": {"bond_id": "<from step 1>", "funding_ref": "<x402 premium>"}},
        {"step": 3, "actor": "buyer", "mount": "escrow", "tool": "open",
         "args": {"payer": "<buyer>", "payee": "<provider>",
                  "amount_minor": job_amount_minor, "terms": "insured job",
                  "deadline": "<ISO deadline>"}},
        {"step": 4, "actor": "buyer", "mount": "escrow", "tool": "fund",
         "args": {"escrow_id": "<from step 3>", "funding_ref": "<x402 job>"}},
        {"step": 5, "actor": "provider", "mount": "verified", "tool": "call_verified",
         "args": {"service_id": service_id, "tool": "<deliverable>",
                  "call_id": "<unique>"},
         "note": "delivery is relayed + receipted; optionally notarize via "
                 "notary.commit/reveal"},
        {"step": "6a", "actor": "buyer", "mount": "escrow", "tool": "release",
         "when": "delivery accepted", "args": {"escrow_id": "<from step 3>"}},
        {"step": "6b", "actor": "buyer", "mount": "arbitration", "tool": "file_case",
         "when": "delivery disputed",
         "args": {"escrow_id": "<from step 3>", "claimant": "<buyer>",
                  "respondent": "<provider>", "amount_minor": job_amount_minor},
         "note": "then rule -> escrow.refund -> surety.file_claim + slash "
                 "(against the ruling) makes the buyer whole"},
    ]


async def quote_insured_job(verified_core: Any, surety_core: Any,
                            service_id: str, job_amount_minor: int,
                            coverage_minor: int, duration_days: int,
                            escrow_fee_bps: int = 100) -> dict:
    """One-call insured-job quote (IJ1-IJ6). Read-only."""
    if not isinstance(service_id, str) or not service_id:
        return {"status": "error", "error_type": "ValidationError",
                "field": "service_id", "message": "service_id is required",
                "timestamp": _now()}
    for name, v in (("job_amount_minor", job_amount_minor),
                    ("coverage_minor", coverage_minor),
                    ("duration_days", duration_days)):
        if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
            return {"status": "error", "error_type": "ValidationError",
                    "field": name, "message": f"{name} must be a positive integer",
                    "timestamp": _now()}

    stats = await verified_core.process(
        {"action": "service_stats", "service_id": service_id})   # IJ3 read
    if stats.get("status") != "ok":                              # IJ4
        return stats
    s = stats["data"]

    import underwriting_bridge  # IJ1: same uw-v1 bridge
    uw = await underwriting_bridge.quote_bond_for_service(
        verified_core, surety_core, service_id, coverage_minor, duration_days)
    if uw.get("status") != "ok":
        return uw
    quote = uw["quote"]

    escrow_fee = math.ceil(job_amount_minor * escrow_fee_bps / 10_000)  # E3 mirror

    if quote.get("decision") != "quote":                         # IJ5
        return {
            "status": "ok", "generated_at": _now(),
            "insurable": False,
            "reason": quote.get("reason", "provider is not currently bondable"),
            "provider": {"service_id": s.get("service_id"),
                         "provider": s.get("provider"),
                         "verified_deliveries": s.get("calls_ok")},
            "note": "The provider has no bondable track record yet. Run "
                    "verified deliveries to build one, then re-quote.",
        }

    bond_premium = quote["premium_minor"]
    total = bond_premium + escrow_fee                            # IJ2
    return {
        "status": "ok", "generated_at": _now(),
        "insurable": True,
        "provider": {"service_id": s.get("service_id"),
                     "provider": s.get("provider"),
                     "verified_deliveries": s.get("calls_ok"),
                     "delivery_errors": s.get("calls_error")},
        "job": {"amount_minor": job_amount_minor,
                "coverage_minor": coverage_minor,
                "duration_days": duration_days},
        "quote": {
            "bond_premium_minor": bond_premium,
            "bond_effective_rate_bps_per_year": quote.get("effective_rate_bps_per_year"),
            "escrow_fee_minor": escrow_fee,
            "escrow_fee_bps": escrow_fee_bps,
            "total_protection_cost_minor": total,
            "protection_pct_of_job": round(100 * total / job_amount_minor, 3),
            "currency": "USD",
            "quote_hash": quote["quote_hash"],   # IJ1 recomputable
        },
        "playbook": _playbook(service_id, coverage_minor, job_amount_minor),
        "note": "One-call insured-job quote. Bond premium reflects the "
                "provider's tamper-evident Verified track record; escrow holds "
                "the buyer's funds until proven delivery; a breach is made "
                "whole by escrow refund + a bond slash against a "
                "machine-verifiable arbitration ruling.",
    }
