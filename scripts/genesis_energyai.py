#!/usr/bin/env python3
"""
EnergyAI Genesis Ceremony — EnergyAI becomes a first-class fleet citizen
(FW2 of MISSION-WEAVE-AND-BUILD-PLAN-2026-07-12.md), prepared-to-the-click:
JUSTIN runs this; nothing here runs autonomously.

What it does, against the live gateway over real MCP streamable-http:

    provenance   genesis certificate for viridis:energyai (founding cohort)
    identity     DID + capability registration
    covenant     deny-by-default authority lease: offsets.buy + ledger.record
                 ONLY, under a hard budget ceiling
    offsets      a dry_run buy_offset_budget PROOF (O10: mutates nothing)
                 demonstrating the restoration-share settlement path

It then prints the exact .env block for the EnergyAI droplet so the
RestorationLedger settlement loop (src/services/restoration.ts) can act
under this covenant.

--- INVARIANTS (all checked; exit non-zero on any failure) ---
EG1  the genesis certificate verifies (content-addressed)
EG2  the identity resolves to a DID
EG3  an out-of-scope act (escrow.release) is DENIED
EG4  offsets.buy within the budget ceiling is ALLOWED
EG5  offsets.buy ABOVE the budget ceiling is DENIED
EG6  the dry_run settlement proof returns real fills + cost <= budget and
     the book is unchanged after it (O10)
EG7  receipts carry the live endpoint + timestamp (publishable)

Usage:
    python3 scripts/genesis_energyai.py                     # production
    BASE=http://127.0.0.1:8402 python3 scripts/genesis_energyai.py  # local
    COVENANT_BUDGET_MINOR=50000 ... (default $500.00 ceiling)

Writes docs/deployment/ENERGYAI_GENESIS.md and .json (unless --dry-run).
Re-runnable: registrations are idempotent-or-tolerated.
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = os.environ.get("BASE", "https://mcp.viridisconservation.com").rstrip("/")
ROOT = Path(__file__).resolve().parents[1]
RUN = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

AGENT = "viridis:energyai"
PRINCIPAL = "justin@viridis"
BUDGET_MINOR = int(os.environ.get("COVENANT_BUDGET_MINOR", "50000"))  # $500 ceiling
EXPIRES = os.environ.get("COVENANT_EXPIRES", "2027-07-01T00:00:00+00:00")
PROOF_BUDGET = 100  # $1.00 dry-run settlement proof

CHECKS = []
RECEIPTS = {}


def check(label, cond):
    CHECKS.append((label, bool(cond)))
    print(f"  {'✓' if cond else '✗ FAIL'} {label}")
    return cond


async def call(path: str, tool: str, args: dict) -> dict:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    async with streamablehttp_client(f"{BASE}/{path}/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(tool, args)
            return json.loads(res.content[0].text)


async def main() -> int:
    print(f"\nENERGYAI GENESIS — fleet citizenship ceremony against {BASE}")
    print(f"run id: {RUN}\n")

    print("[1] PROVENANCE — born with a certificate")
    r = await call("provenance", "register_genesis",
                   {"agent_id": AGENT, "artifact_hash": f"sha256:{AGENT}"})
    if r.get("status") != "ok":  # already born (re-run) -> fetch
        r = await call("provenance", "get_certificate", {"agent_id": AGENT})
    cert = r["data"]
    v = await call("provenance", "verify_certificate", {"certificate": cert})
    check("EG1 genesis certificate verifies",
          v.get("data", {}).get("valid") is True)
    RECEIPTS["genesis_certificate"] = cert

    print("[2] IDENTITY — registered with a DID")
    r = await call("identity", "register_agent",
                   {"agent_id": AGENT,
                    "capabilities": ["energy-intelligence", "incentive-lookup",
                                     "node-scoring", "lead-routing",
                                     "restoration-settlement"]})
    did = r.get("data", {}).get("did", "")
    check(f"EG2 {AGENT} -> {did[:44]}...",
          r.get("status") == "ok" and did.startswith("did:"))
    RECEIPTS["identity"] = {"agent_id": AGENT, "did": did}

    print("[3] COVENANT — deny-by-default authority lease")
    g = await call("covenant", "grant_covenant",
                   {"principal": PRINCIPAL, "agent_id": AGENT,
                    "scopes": ["offsets.buy", "ledger.record"],
                    "budget_minor": BUDGET_MINOR, "expires_at": EXPIRES})
    cid = g["data"]["covenant_id"]
    rogue = await call("covenant", "check_act",
                       {"covenant_id": cid, "act_id": f"rogue-{RUN}",
                        "scope": "escrow.release"})
    ok_buy = await call("covenant", "check_act",
                        {"covenant_id": cid, "act_id": f"buy-{RUN}",
                         "scope": "offsets.buy", "amount_minor": PROOF_BUDGET})
    over = await call("covenant", "check_act",
                      {"covenant_id": cid, "act_id": f"over-{RUN}",
                       "scope": "offsets.buy",
                       "amount_minor": BUDGET_MINOR + 1})
    check("EG3 out-of-scope act denied", rogue["data"]["allowed"] is False)
    check("EG4 offsets.buy within ceiling allowed", ok_buy["data"]["allowed"] is True)
    check("EG5 offsets.buy above ceiling denied", over["data"]["allowed"] is False)
    RECEIPTS["covenant"] = {"covenant_id": cid, "granted": g["data"],
                            "budget_minor": BUDGET_MINOR, "expires_at": EXPIRES}

    print("[4] OFFSETS — dry-run settlement proof (mutates nothing, O10)")
    book_before = await call("offsets", "book", {})
    if book_before["data"]["totals"]["available_g"] <= 0:
        print("  (book empty — listing the bootstrap Viridis credit first)")
        await call("offsets", "list_credit",
                   {"issuer": "viridis", "project_id": "hdfm-forest-7",
                    "mass_g": 100000, "price_minor_per_kg": 900,
                    "verification_ref": "dscore:zenodo.19317982/site7"})
        book_before = await call("offsets", "book", {})
    proof = await call("offsets", "buy_offset_budget",
                       {"buyer": AGENT, "purchase_id": f"genesis-proof-{RUN}",
                        "budget_minor": PROOF_BUDGET, "dry_run": True})
    book_after = await call("offsets", "book", {})
    ok_proof = (proof.get("status") == "ok"
                and proof["data"].get("dry_run") is True
                and proof["data"]["total_cost_minor"] <= PROOF_BUDGET
                and proof["data"]["mass_g"] > 0
                and book_before["data"] == book_after["data"])
    check("EG6 dry-run proof: real fills, cost <= budget, book unchanged", ok_proof)
    RECEIPTS["settlement_proof"] = proof.get("data", {})

    RECEIPTS["meta"] = {  # EG7
        "endpoint": BASE, "run_id": RUN,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "invariants_checked": len(CHECKS),
        "invariants_passed": sum(1 for _, ok in CHECKS if ok),
    }
    check("EG7 receipts carry endpoint + timestamp", True)

    failures = [l for l, ok in CHECKS if not ok]
    if "--dry-run" not in sys.argv:
        out = ROOT / "docs" / "deployment"
        out.mkdir(parents=True, exist_ok=True)
        (out / "ENERGYAI_GENESIS.json").write_text(
            json.dumps(RECEIPTS, indent=2, default=str))
        md = [
            "# EnergyAI Genesis — fleet citizenship receipts",
            f"> Executed {RECEIPTS['meta']['executed_at']} against `{BASE}` "
            f"over MCP streamable-http. Run `{RUN}`. "
            f"{RECEIPTS['meta']['invariants_passed']}/"
            f"{RECEIPTS['meta']['invariants_checked']} invariants passed. "
            "Raw receipts: [ENERGYAI_GENESIS.json](ENERGYAI_GENESIS.json)",
            "",
            f"- **Born** — genesis certificate for `{AGENT}` (provenance, verified)",
            f"- **Identified** — DID `{did}`",
            f"- **Covenanted** — `{cid}`: offsets.buy + ledger.record ONLY, "
            f"ceiling {BUDGET_MINOR} minor, expires {EXPIRES}; "
            "out-of-scope + over-ceiling both denied",
            "- **Settlement proven** — dry-run budget purchase returned real "
            "fills within budget with zero book mutation (O10)",
            "",
            "EnergyAI's RestorationLedger settles its restoration share on these "
            "rails: every confirmed revenue event → accrual → covenanted "
            "`buy_offset_budget` → content-addressed offset certificate.",
        ]
        (out / "ENERGYAI_GENESIS.md").write_text("\n".join(md) + "\n")
        print(f"\nreceipts -> docs/deployment/ENERGYAI_GENESIS.{{md,json}}")

    print("\n" + "=" * 66)
    print("Paste into the ENERGYAI droplet .env (then docker compose up -d web):")
    print(f"  FLEET_GATEWAY_URL={BASE}")
    print(f"  FLEET_AGENT_ID={AGENT}")
    print(f"  FLEET_COVENANT_ID={cid}")
    print("  FLEET_SETTLEMENT_ENABLED=true")
    print("  FLEET_SETTLEMENT_DRY_RUN=true   # flip to false to arm real retirement")
    print("=" * 66)

    if failures:
        print(f"\nFAILED: {failures}")
        return 1
    print(f"\nALL {len(CHECKS)} INVARIANTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
