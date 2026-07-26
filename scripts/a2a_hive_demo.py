#!/usr/bin/env python3
"""
A2A Hive Composition Demo - the rails' first native customer.

One hive job, driven end to end through the REAL rails:

    trust      vets the solver pool          (who is worth hiring?)
    covenant   bounds the hive's authority   (deny-by-default hires)
    escrow     funds every hire              (pay only reviewed work)
    metering   counts every attempt          (idempotent usage events)
    trust      re-rates every outcome        (the flywheel)
    compute-ledger prices the physics        (bits per joule, honestly)

Run:
    python3 scripts/a2a_hive_demo.py           # narrative + assertions
    python3 scripts/a2a_hive_demo.py --quiet   # assertions only (CI)

Exits non-zero if any cross-agent invariant fails - an integration test.
"""
import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = {
    "trust":    ROOT / "agent-trust-oracle-agent" / "src" / "core.py",
    "covenant": ROOT / "agent-covenant-agent" / "src" / "core.py",
    "escrow":   ROOT / "agent-escrow-agent" / "src" / "core.py",
    "metering": ROOT / "agent-metering-agent" / "src" / "core.py",
    "ledger":   ROOT / "agent-compute-ledger-agent" / "src" / "core.py",
    "hive":     ROOT / "agent-hive-orchestrator-agent" / "src" / "core.py",
}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(f"hive_{name}_core", path)
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


class DemoSolver:
    """Deterministic stand-in solver (production uses LLMSolverAdapter)."""

    def __init__(self, tag: str, quality: float):
        self.tag, self.quality = tag, quality

    async def solve(self, task):
        return {"content": f"[{self.tag}] resolves: {task['subtask']}",
                "power_w": 200.0, "duration_s": 90.0, "bit_ops": 1e16,
                "grid_g_per_kwh": 400.0}

    async def review(self, req):
        return {"score": self.quality}


class FlakySolver(DemoSolver):
    async def solve(self, task):
        raise RuntimeError("simulated solver outage")


async def main() -> int:
    mods = {k: _load(k, p) for k, p in AGENTS.items()}
    trust = mods["trust"].build()
    cov = mods["covenant"].build()
    escrow = mods["escrow"].build()
    meter = mods["metering"].build()
    ledger = mods["ledger"].build()

    say("\n[1] WIRING - the hive boots on the real rails")
    solvers = {
        "solver-apollo": {"adapter": DemoSolver("apollo", 0.85),
                          "price_minor": 120,
                          "capabilities": ["analysis"]},
        "solver-hermes": {"adapter": DemoSolver("hermes", 0.90),
                          "price_minor": 100,
                          "capabilities": ["analysis"]},
        "solver-flaky":  {"adapter": FlakySolver("flaky", 0.9),
                          "price_minor": 80,
                          "capabilities": ["analysis"]},
    }
    hive = mods["hive"].build(
        solvers=solvers,
        rails={"trust": trust, "covenant": cov, "escrow": escrow,
               "metering": meter, "ledger": ledger})
    check("hive boots in wired mode", hive.rails_mode == "wired")

    say("\n[2] COVENANT - the principal grants bounded hiring authority")
    grant = await cov.process({"action": "grant", "principal": "justin",
                               "agent_id": "hive-orchestrator",
                               "scopes": ["hive.*"],
                               "budget_minor": 100_000,
                               "expires_at": "2099-01-01T00:00:00+00:00"})
    check("covenant granted", grant["status"] == "ok")
    covenant_id = grant["data"]["covenant_id"]

    say("\n[3] SOLVE - one hard problem, three subtasks, redundancy 2")
    res = await hive.process({
        "action": "solve",
        "problem": "Design a wildfire early-warning sensor mesh for HDFM "
                   "forests: sensing, comms, and power subsystems.",
        "subtasks": ["sensing subsystem", "comms subsystem",
                     "power subsystem"],
        "budget_minor": 2000, "redundancy": 2, "seed": 42,
        "fee_bps": 100, "covenant_id": covenant_id,
    })
    check("job completes", res["status"] == "ok"
          and res["data"]["state"] == "COMPLETE")
    data = res["data"]
    syn = data["synthesis"]

    say("\n[4] H1 - budget conservation on real escrows")
    b = data["budget"]
    check("spent + refunded == committed",
          b["spent_minor"] + b["refunded_minor"] == b["committed_minor"])
    check("committed within budget",
          b["committed_minor"] <= b["total_minor"])

    say("\n[5] H4/H8 - review gate and fail-safe on the flaky solver")
    audit = (await hive.process({"action": "audit_job",
                                 "job_id": data["job_id"]}))["data"]
    failed = [c for c in audit["lineage"]["contributions"] if c["failed"]]
    check("flaky solver failed without crashing the job",
          all(c["solver_id"] == "solver-flaky" for c in failed)
          and len(failed) >= 1)
    check("every review has reviewer != author",
          all(r["reviewer"] != r["author"]
              for r in audit["lineage"]["reviews"]))
    check("synthesis contains only accepted work",
          all(s["review_score"] >= 0.6 for s in syn["sections"]))

    say("\n[6] H5 - every escrow terminal on the REAL escrow rail")
    terminal = 0
    for s in audit["lineage"]["settlements"]:
        st = await escrow.process({"action": "status",
                                   "escrow_id": s["escrow_id"]})
        if st["data"]["state"] in ("RELEASED", "REFUNDED"):
            terminal += 1
    check(f"all {len(audit['lineage']['settlements'])} escrows terminal",
          terminal == len(audit["lineage"]["settlements"]) and terminal > 0)
    aud0 = await escrow.process({
        "action": "verify_audit",
        "escrow_id": audit["lineage"]["settlements"][0]["escrow_id"]})
    check("escrow audit chain verifies", aud0["data"]["valid"] is True)

    say("\n[7] TRUST FLYWHEEL - outcomes re-rated the pool")
    t_good = await trust.process({"action": "score",
                                  "agent_id": "solver-hermes"})
    t_bad = await trust.process({"action": "score",
                                 "agent_id": "solver-flaky"})
    check("delivering solver has live (non-prior) score",
          t_good["data"]["prior"] is False)
    check("delivering solver outranks the flaky one",
          t_good["data"]["score"] > t_bad["data"]["score"])

    say("\n[8] H7 - physics on the REAL compute ledger")
    check("physics accounted with energy > 0",
          syn["physics_accounted"] is True and syn["energy_j"] > 0)
    check("bits-per-joule reported",
          syn["bits_per_joule"] is not None and syn["bits_per_joule"] > 0)
    fp = await ledger.process({"action": "footprint",
                               "agent_id": "solver-hermes"})
    check("ledger footprint recorded for accepted work",
          fp["status"] == "ok" and fp["data"]["total_energy_j"] > 0)

    say("\n[9] H6 - emergence honesty")
    check("collective covers all 3 subtasks", syn["coverage"] == 1.0)
    check("emergent only with >= 2 contributors",
          syn["emergent"] is (len(syn["contributing_solvers"]) >= 2
                              and len(syn["sections"]) > max(
              sum(1 for s in syn["sections"] if s["solver_id"] == sid)
              for sid in syn["contributing_solvers"])))

    say("\n[10] H9 - recompute-in-verify audit")
    ok = await hive.process({"action": "verify_audit", "audit": audit})
    check("authentic audit verifies + matches known job",
          ok["data"]["valid"] is True
          and ok["data"]["matches_known_job"] is True)
    import copy as _copy
    tampered = _copy.deepcopy(audit)
    tampered["lineage"]["synthesis"]["collective_score"] = 1.0
    bad = await hive.process({"action": "verify_audit", "audit": tampered})
    check("tampered audit rejected", bad["data"]["valid"] is False)

    say("\n[11] H2 - a nested hive is just another solver, depth-gated")
    child = mods["hive"].build(solvers={
        k: v for k, v in solvers.items() if k != "solver-flaky"})

    class ChildHiveAdapter:
        """Wrap a hive as a SolverAdapter - nesting via the registry."""

        async def solve(self, task):
            depth = task.get("depth")
            r = await child.process({
                "action": "solve", "problem": task["subtask"],
                "budget_minor": 300, "seed": task.get("seed", 0),
                "depth": depth if depth is not None else 0})
            sections = r["data"]["synthesis"]["sections"] \
                if r["status"] == "ok" else []
            return {"content": " | ".join(s["content"] for s in sections)
                               or "child hive produced nothing",
                    "power_w": 100.0, "duration_s": 30.0, "bit_ops": 1e15}

        async def review(self, req):
            return {"score": 0.8}

    nested_solvers = dict(solvers)
    nested_solvers["child-hive"] = {"adapter": ChildHiveAdapter(),
                                    "kind": "hive", "price_minor": 150}
    hive2 = mods["hive"].build(solvers=nested_solvers,
                               rails={"trust": trust, "covenant": cov,
                                      "escrow": escrow, "metering": meter,
                                      "ledger": ledger})
    shallow = await hive2.process({
        "action": "solve", "problem": "nested test", "budget_minor": 1000,
        "seed": 5, "depth": 0, "redundancy": 4,
        "covenant_id": covenant_id})
    a_sh = (await hive2.process({"action": "audit_job",
                                 "job_id": shallow["data"]["job_id"]}))
    refused = [h for h in a_sh["data"]["lineage"]["hires"]
               if h["solver_id"] == "child-hive" and not h["hired"]]
    check("depth 0: child hive refused (deny-by-default)",
          len(refused) >= 1 and all("H2" in h["reason"] for h in refused))
    deep = await hive2.process({
        "action": "solve", "problem": "nested test", "budget_minor": 1000,
        "seed": 6, "depth": 1, "redundancy": 4,
        "covenant_id": covenant_id})
    a_dp = (await hive2.process({"action": "audit_job",
                                 "job_id": deep["data"]["job_id"]}))
    hired = [h for h in a_dp["data"]["lineage"]["hires"]
             if h["solver_id"] == "child-hive" and h["hired"]]
    check("depth 1: child hive hired with decremented depth",
          len(hired) >= 1 and all(h["child_depth"] == 0 for h in hired))

    failures = [l for l, ok_ in CHECKS if not ok_]
    say("\n" + "=" * 68)
    if failures:
        say(f"  RESULT: {len(failures)} INVARIANT(S) FAILED: {failures}")
        return 1
    say(f"  RESULT: ALL {len(CHECKS)} CROSS-AGENT INVARIANTS PASSED.")
    say("  The hive hired, reviewed, synthesized, settled, re-rated, and")
    say("  carbon-accounted a burst of real A2A transactions - and a hive")
    say("  hired a hive, bounded by depth. The rails' first native customer.")
    say("=" * 68)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    QUIET = ap.parse_args().quiet
    sys.exit(asyncio.run(main()))
