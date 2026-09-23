#!/usr/bin/env python3
"""
A2A Settlement-Stack Composition Demo — meter -> escrow -> arbitration -> ledger.

Proves the three NEW Viridis A2A primitives (added 2026-07-09) compose with the
existing rails into a full settlement stack:

    metering   counts the work        (how much?)
    escrow     settles the payment    (pay on delivery)
    arbitration resolves the dispute  (recourse, machine-verifiable)
    compute-ledger prices the physics (compute is carbon)

Run:
    python3 scripts/a2a_settlement_stack_demo.py           # narrative + assertions
    python3 scripts/a2a_settlement_stack_demo.py --quiet   # assertions only (CI)

Exits non-zero if any cross-agent invariant fails — an integration test.
"""
import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = {
    "metering":    ROOT / "agent-metering-agent" / "src" / "core.py",
    "escrow":      ROOT / "agent-escrow-agent" / "src" / "core.py",
    "arbitration": ROOT / "agent-arbitration-agent" / "src" / "core.py",
    "ledger":      ROOT / "agent-compute-ledger-agent" / "src" / "core.py",
    "trust":       ROOT / "agent-trust-oracle-agent" / "src" / "core.py",
}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(f"stack_{name}_core", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


QUIET = False
CHECKS = []


def say(*a):
    if not QUIET:
        print(*a)


def check(label: str, cond: bool):
    CHECKS.append((label, cond))
    say(f"  {'✓' if cond else '✗ FAIL'} {label}")
    return cond


async def main() -> int:
    mods = {k: _load(k, p) for k, p in AGENTS.items()}
    meter = mods["metering"].build()
    escrow = mods["escrow"].build()
    arb = mods["arbitration"].build()
    ledger = mods["ledger"].build()
    trust = mods["trust"].build()

    say("\n[1] METER — provider's work is counted, tamper-evidently")
    m = await meter.process({"action": "create_meter", "provider": "cad-pro",
                             "consumer": "buyer-1", "unit": "call",
                             "price_minor_per_unit": 500, "sla_target": 0.95})
    mid = m["data"]["meter_id"]
    for i in range(9):
        await meter.process({"action": "record_usage", "meter_id": mid,
                             "event_id": f"job-{i}", "quantity": 1})
    bad = await meter.process({"action": "record_usage", "meter_id": mid,
                               "event_id": "job-9", "quantity": 1, "outcome": "error"})
    check("10 usage events recorded", bad["status"] == "ok")
    replay = await meter.process({"action": "record_usage", "meter_id": mid,
                                  "event_id": "job-3", "quantity": 50})
    check("replayed event_id not double-billed (x402 idempotency)",
          replay["data"]["duplicate"] is True)
    chain = await meter.process({"action": "verify_chain", "meter_id": mid})
    check("meter hash chain verifies", chain["data"]["valid"] is True)

    say("\n[2] INVOICE -> ESCROW — the frozen invoice becomes the escrow amount")
    inv = await meter.process({"action": "close_period", "meter_id": mid})
    amount = inv["data"]["amount_minor"]
    check("invoice frozen exactly-once at 10 * 500 = 5000 minor", amount == 5000)
    inv2 = await meter.process({"action": "close_period", "meter_id": mid})
    check("second close is an idempotent no-op", inv2["data"]["duplicate"] is True)
    e = await escrow.process({"action": "open", "payer": "buyer-1", "payee": "cad-pro",
                              "amount_minor": amount, "terms": inv["data"]["invoice_id"]})
    eid = e["data"]["escrow_id"]
    await escrow.process({"action": "fund", "escrow_id": eid})
    st = await escrow.process({"action": "status", "escrow_id": eid})
    check("escrow FUNDED with the metered amount",
          st["data"]["state"] == "FUNDED" and st["data"]["amount_minor"] == amount)

    say("\n[3] DISPUTE -> ARBITRATION — SLA breach is admissible evidence")
    await escrow.process({"action": "dispute", "escrow_id": eid,
                          "reason": "1 of 10 jobs failed"})
    sla = await meter.process({"action": "sla_report", "meter_id": mid})
    check("SLA report shows breach (0.9 < 0.95)", sla["data"]["breach"] is True)
    c = await arb.process({"action": "file_case", "escrow_id": eid,
                           "claimant": "buyer-1", "respondent": "cad-pro",
                           "amount_minor": amount})
    cid = c["data"]["case_id"]
    await arb.process({"action": "submit_evidence", "case_id": cid, "party": "buyer-1",
                       "kind": "log", "content": f"SLA breach: {sla['data']}"})
    await arb.process({"action": "submit_evidence", "case_id": cid, "party": "cad-pro",
                       "kind": "delivery_proof", "content": "9 delivered artifacts"})
    rec = await trust.process({"action": "record_outcome", "agent_id": "cad-pro",
                               "kind": "delivered", "counterparty": "buyer-1"})
    check("trust oracle records the delivery outcome", rec["status"] == "ok")
    ts = await trust.process({"action": "score", "agent_id": "cad-pro"})
    check("provider has a live (non-prior) trust score",
          ts["status"] == "ok" and ts["data"]["prior"] is False)
    provider_trust = ts["data"]["score"]
    await arb.process({"action": "set_trust_scores", "case_id": cid,
                       "scores": {"cad-pro": provider_trust}})
    ruling = await arb.process({"action": "rule", "case_id": cid})
    r = ruling["data"]
    check("ruling allocates exactly 100%", r["claimant_pct"] + r["respondent_pct"] == 100)
    check("allocated amounts sum to the escrow amount",
          r["claimant_amount_minor"] + r["respondent_amount_minor"] == amount)
    v = await arb.process({"action": "verify_ruling", "case_id": cid})
    check("ruling is machine-verifiable (recomputes from cited inputs)",
          v["data"]["valid"] is True)
    again = await arb.process({"action": "rule", "case_id": cid})
    check("re-ruling is idempotent (exactly-once justice)",
          again["data"]["duplicate"] is True
          and again["data"]["ruling_hash"] == r["ruling_hash"])

    say(f"\n[4] SETTLEMENT — arbiter instruction '{r['escrow_instruction']}' executes")
    action = "refund" if r["escrow_instruction"] == "refund" else "release"
    settled = await escrow.process({"action": action, "escrow_id": eid,
                                    "reason": f"arbitration {cid}: {r['ruling_hash'][:12]}"})
    check("DISPUTED escrow settles per the ruling",
          settled["status"] == "ok"
          and settled["data"]["state"] in ("RELEASED", "REFUNDED"))
    double = await escrow.process({"action": "release", "escrow_id": eid})
    check("no double-spend after arbitration",
          double["status"] == "ok" and double["data"]["state"] == settled["data"]["state"])

    say("\n[5] PHYSICS — the work is carbon-accounted on the compute ledger")
    w = await ledger.process({"action": "record_work", "agent_id": "cad-pro",
                              "entry_id": f"{mid}-period0", "power_w": 350.0,
                              "duration_s": 1800.0, "task": "10 CAD jobs",
                              "bit_ops": 1e20, "grid_intensity_g_per_kwh": 380.0,
                              "price_minor_per_kwh": 14000})
    check("work recorded with energy + carbon", w["status"] == "ok"
          and w["data"]["energy_j"] == 630000.0 and w["data"]["carbon_g"] > 0)
    check("Landauer efficiency in (0,1]",
          0.0 < w["data"]["landauer_efficiency"] <= 1.0)
    impossible = await ledger.process({"action": "record_work", "agent_id": "cad-pro",
                                       "entry_id": "cheat", "power_w": 1e-9,
                                       "duration_s": 1e-9, "bit_ops": 1e30})
    check("physically impossible workload claim rejected (Landauer floor)",
          impossible["status"] == "error")
    att = await ledger.process({"action": "attest", "entry_id": f"{mid}-period0"})
    ver = await ledger.process({"action": "verify_attestation",
                                "attestation": att["data"]["attestation"]})
    check("carbon attestation verifies", ver["data"]["valid"] is True)
    fp = await ledger.process({"action": "footprint", "agent_id": "cad-pro"})
    check("footprint aggregates exactly",
          fp["data"]["total_energy_j"] == w["data"]["energy_j"])

    failures = [l for l, ok in CHECKS if not ok]
    say("\n" + "=" * 68)
    if failures:
        say(f"  RESULT: {len(failures)} INVARIANT(S) FAILED: {failures}")
        return 1
    say(f"  RESULT: ALL {len(CHECKS)} CROSS-AGENT INVARIANTS PASSED.")
    say("  meter -> invoice -> escrow -> dispute -> ruling -> settlement ->")
    say("  carbon ledger: the full A2A settlement stack, composed end to end.")
    say("=" * 68)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    QUIET = ap.parse_args().quiet
    sys.exit(asyncio.run(main()))
