#!/usr/bin/env python3
"""
A2A Genesis Composition Demo — the constitution of the agent economy.

The founding happens once. This demo runs one agent's full life under the
three new founding-era primitives, composed with the existing rails:

    provenance   born with a certificate     (who made you?)
    covenant     acts under explicit authority (what may you do?)
    metering     its work is counted           (what did you do?)
    compute-ledger its physics are priced      (what did it cost the planet?)
    offsets      its carbon is retired         (did you pay the planet back?)
    recall       and when its maker is compromised, the whole line is contained

Run:
    python3 scripts/a2a_genesis_demo.py            # narrative + assertions
    python3 scripts/a2a_genesis_demo.py --quiet    # assertions only (CI)

Exits non-zero if any cross-agent invariant fails — an integration test.
"""
import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = {
    "provenance": ROOT / "agent-provenance-agent" / "src" / "core.py",
    "identity":   ROOT / "agent-identity-registry-agent" / "src" / "core.py",
    "covenant":   ROOT / "agent-covenant-agent" / "src" / "core.py",
    "metering":   ROOT / "agent-metering-agent" / "src" / "core.py",
    "ledger":     ROOT / "agent-compute-ledger-agent" / "src" / "core.py",
    "offsets":    ROOT / "agent-offset-clearinghouse-agent" / "src" / "core.py",
}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(f"genesis_{name}_core", path)
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
    prov = mods["provenance"].build()
    ident = mods["identity"].build()
    cov = mods["covenant"].build()
    meter = mods["metering"].build()
    ledger = mods["ledger"].build()
    offsets = mods["offsets"].build()

    say("\n[1] GENESIS — a factory and its worker are born, provably in the founding cohort")
    factory = await prov.process({"action": "register_genesis", "agent_id": "forge-01",
                                  "artifact_hash": "sha256:forge"})
    worker = await prov.process({"action": "register_genesis", "agent_id": "cad-worker-01",
                                 "parent_id": "forge-01", "artifact_hash": "sha256:worker"})
    check("founding-cohort certificates issued (epoch 0, monotone indices)",
          factory["data"]["founding_cohort"] and worker["data"]["founding_cohort"]
          and worker["data"]["genesis_index"] == factory["data"]["genesis_index"] + 1)
    v = await prov.process({"action": "verify_certificate",
                            "certificate": worker["data"]})
    check("birth certificate verifies (content-addressed)", v["data"]["valid"] is True)

    say("\n[2] IDENTITY — the worker joins the directory")
    reg = await ident.process({"action": "register", "agent_id": "cad-worker-01",
                               "capabilities": ["cad", "step-export"]})
    check("worker registered with a DID", reg["status"] == "ok"
          and reg["data"]["did"].startswith("did:"))

    say("\n[3] COVENANT — its principal grants explicit, bounded authority")
    grant = await cov.process({"action": "grant", "principal": "justin",
                               "agent_id": "cad-worker-01",
                               "scopes": ["cad.*", "offsets.buy"],
                               "budget_minor": 5000,
                               "expires_at": "2099-01-01T00:00:00+00:00"})
    cid = grant["data"]["covenant_id"]
    rogue = await cov.process({"action": "check_act", "covenant_id": cid,
                               "act_id": "rogue-1", "scope": "accounts.delete"})
    check("out-of-scope act denied (deny-by-default)",
          rogue["data"]["allowed"] is False)

    say("\n[4] WORK — the worker's jobs are metered")
    m = await meter.process({"action": "create_meter", "provider": "cad-worker-01",
                             "consumer": "buyer-9", "unit": "job",
                             "price_minor_per_unit": 300})
    mid = m["data"]["meter_id"]
    for i in range(4):
        allowed = await cov.process({"action": "check_act", "covenant_id": cid,
                                     "act_id": f"job-{i}", "scope": "cad.generate"})
        assert allowed["data"]["allowed"]
        await meter.process({"action": "record_usage", "meter_id": mid,
                             "event_id": f"job-{i}", "quantity": 1})
    inv = await meter.process({"action": "close_period", "meter_id": mid})
    check("4 covenant-authorized jobs metered and invoiced (1200 minor)",
          inv["data"]["amount_minor"] == 1200)

    say("\n[5] PHYSICS — the work is carbon-accounted")
    w = await ledger.process({"action": "record_work", "agent_id": "cad-worker-01",
                              "entry_id": f"{mid}-p0", "power_w": 200.0,
                              "duration_s": 3600.0, "bit_ops": 1e19,
                              "grid_intensity_g_per_kwh": 400.0})
    emitted = w["data"]["carbon_g"]
    check("energy + carbon recorded (0.2 kWh -> 80 gCO2e)",
          abs(emitted - 80.0) < 1e-9)

    say("\n[6] OFFSET — the worker pays the planet back through VERIFIED credits")
    unverified = await offsets.process({"action": "list_credit", "issuer": "sketchy",
                                        "project_id": "trust-me", "mass_g": 10000,
                                        "price_minor_per_kg": 1})
    check("unverified credit rejected from the book", unverified["status"] == "error")
    await offsets.process({"action": "list_credit", "issuer": "viridis",
                           "project_id": "hdfm-forest-7", "mass_g": 10000,
                           "price_minor_per_kg": 900,
                           "verification_ref": "dscore:zenodo.19317982/site7"})
    spend = await cov.process({"action": "check_act", "covenant_id": cid,
                               "act_id": "offset-1", "scope": "offsets.buy",
                               "amount_minor": 100})
    check("offset spend authorized by covenant (budget consumed)",
          spend["data"]["allowed"] is True)
    buy = await offsets.process({"action": "buy_offset", "buyer": "cad-worker-01",
                                 "purchase_id": "offset-1", "mass_g": 80})
    vc = await offsets.process({"action": "verify_certificate",
                                "certificate": buy["data"]})
    check("offset certificate verifies", vc["data"]["valid"] is True)
    np = await offsets.process({"action": "net_position", "buyer": "cad-worker-01",
                                "emitted_g": emitted})
    check("worker is carbon-accountable (net 0)",
          np["data"]["net_g"] == 0 and np["data"]["carbon_accountable"] is True)

    say("\n[7] CONTAINMENT — the factory is compromised; the whole line is contained")
    rc = await prov.process({"action": "recall", "agent_id": "forge-01",
                             "reason": "compromised build pipeline"})
    check("recall cascades to the worker",
          "cad-worker-01" in rc["data"]["descendants_quarantined"])
    late_child = await prov.process({"action": "register_genesis",
                                     "agent_id": "cad-worker-02",
                                     "parent_id": "forge-01"})
    check("new children of a recalled parent are quarantined at birth",
          late_child["data"]["quarantined"] is True)
    await cov.process({"action": "revoke", "covenant_id": cid,
                       "reason": "lineage recall: forge-01"})
    post = await cov.process({"action": "check_act", "covenant_id": cid,
                              "act_id": "post-recall", "scope": "cad.generate"})
    check("revoked covenant denies everything", post["data"]["allowed"] is False)
    audit = await cov.process({"action": "verify_audit", "covenant_id": cid})
    check("full authority audit chain verifies", audit["data"]["valid"] is True)

    failures = [l for l, ok in CHECKS if not ok]
    say("\n" + "=" * 68)
    if failures:
        say(f"  RESULT: {len(failures)} INVARIANT(S) FAILED: {failures}")
        return 1
    say(f"  RESULT: ALL {len(CHECKS)} CROSS-AGENT INVARIANTS PASSED.")
    say("  Born with a certificate. Acting under a covenant. Work metered,")
    say("  physics priced, carbon repaid, lineage containable.")
    say("  That is a constitution, not just plumbing.")
    say("=" * 68)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    QUIET = ap.parse_args().quiet
    sys.exit(asyncio.run(main()))
