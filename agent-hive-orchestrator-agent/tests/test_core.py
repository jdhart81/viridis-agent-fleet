"""Invariant tests H1-H10 for the hive orchestrator core.

Rails are exercised through recording mocks that implement the exact
call shapes of the real rails (mirrored from scripts/a2a_*_demo.py).
"""

import asyncio
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core import (  # noqa: E402
    HiveOrchestratorCore, ValidationError, build, shannon_bits,
)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- fixtures

class GoodSolver:
    """Deterministic solver: content derived from the subtask."""

    def __init__(self, tag, quality=0.9):
        self.tag, self.quality = tag, quality

    async def solve(self, task):
        return {"content": f"[{self.tag}] answer to: {task['subtask']}",
                "power_w": 100.0, "duration_s": 60.0, "bit_ops": 1e15}

    async def review(self, req):
        return {"score": self.quality}


class CrashingSolver:
    async def solve(self, task):
        raise RuntimeError("adapter exploded")

    async def review(self, req):
        return {"score": 0.9}


class GarbageSolver:
    async def solve(self, task):
        return {"content": "junk", "power_w": float("inf"),
                "duration_s": -1, "bit_ops": float("nan")}

    async def review(self, req):
        return {"score": float("nan")}


class MockEscrow:
    """Real-shaped escrow state machine, recording every transition."""

    def __init__(self):
        self.store, self.n, self.calls = {}, 0, []

    async def process(self, req):
        self.calls.append(copy.deepcopy(req))
        a = req["action"]
        if a == "open":
            self.n += 1
            eid = f"esc-{self.n}"
            fee = req["amount_minor"] * req.get("fee_bps", 0) // 10_000
            self.store[eid] = {"state": "OPEN",
                               "amount_minor": req["amount_minor"],
                               "fee_minor": fee}
            return {"status": "ok",
                    "data": {"escrow_id": eid, "fee_minor": fee,
                             "net_to_payee_minor":
                                 req["amount_minor"] - fee}}
        rec = self.store.get(req.get("escrow_id"))
        if rec is None:
            return {"status": "error", "error_type": "NotFound",
                    "message": "unknown escrow"}
        if a == "fund":
            rec["state"] = "FUNDED"
        elif a == "dispute":
            rec["state"] = "DISPUTED"
        elif a == "release":
            if rec["state"] == "REFUNDED":
                return {"status": "error", "error_type": "StateError",
                        "message": "released after refund"}
            rec["state"] = "RELEASED"
        elif a == "refund":
            if rec["state"] == "RELEASED":
                return {"status": "error", "error_type": "StateError",
                        "message": "refund after release"}
            rec["state"] = "REFUNDED"
        return {"status": "ok", "data": dict(rec)}


class MockCovenant:
    def __init__(self, deny_over_minor=None, deny_all=False):
        self.deny_over, self.deny_all, self.calls = deny_over_minor, \
            deny_all, []

    async def process(self, req):
        self.calls.append(copy.deepcopy(req))
        if req["action"] != "check_act":
            return {"status": "ok", "data": {}}
        allowed = not self.deny_all and not (
            self.deny_over is not None
            and req.get("amount_minor", 0) > self.deny_over)
        return {"status": "ok", "data": {"allowed": allowed}}


class MockSimpleRail:
    def __init__(self, name):
        self.name, self.calls = name, []

    async def process(self, req):
        self.calls.append(copy.deepcopy(req))
        a = req.get("action")
        if self.name == "trust" and a == "score":
            return {"status": "ok", "data": {"score": 0.5,
                                             "tier": "NEUTRAL",
                                             "prior": True}}
        if self.name == "metering" and a == "create_meter":
            return {"status": "ok", "data": {"meter_id":
                                             f"m-{len(self.calls)}"}}
        if self.name == "ledger" and a == "record_work":
            energy = float(req["power_w"]) * float(req["duration_s"])
            return {"status": "ok", "data": {"energy_j": energy,
                                             "carbon_g": 1.0,
                                             "landauer_efficiency": 0.5}}
        return {"status": "ok", "data": {}}


def solvers(n=3, quality=0.9, price=100):
    return {f"solver-{i}": {"adapter": GoodSolver(f"s{i}", quality),
                            "price_minor": price,
                            "capabilities": ["reasoning"]}
            for i in range(n)}


def wired_rails():
    return {"escrow": MockEscrow(), "covenant": MockCovenant(),
            "trust": MockSimpleRail("trust"),
            "metering": MockSimpleRail("metering"),
            "ledger": MockSimpleRail("ledger"),
            "identity": MockSimpleRail("identity")}


def solve(core, **overrides):
    req = {"action": "solve", "problem": "design a sensor network",
           "budget_minor": 1000, "seed": 7}
    req.update(overrides)
    return run(core.process(req))


# ---------------------------------------------------------------- H1

def test_h1_budget_conservation_books_balance():
    rails = wired_rails()
    core = build(solvers=solvers(3), rails=rails)
    res = solve(core)
    assert res["status"] == "ok"
    b = res["data"]["budget"]
    assert b["spent_minor"] + b["refunded_minor"] == b["committed_minor"]
    assert b["committed_minor"] <= b["total_minor"]
    assert res["data"]["unspent_minor"] == b["total_minor"] - b["spent_minor"]


def test_h1_hire_refused_when_budget_exhausted():
    core = build(solvers=solvers(3, price=400), rails=wired_rails())
    res = solve(core, budget_minor=500, redundancy=3)  # only 1 hire fits
    assert res["status"] == "ok"
    hires = res["data"]["hires"]
    assert hires == 1
    audit = run(core.process({"action": "audit_job",
                              "job_id": res["data"]["job_id"]}))
    refused = [h for h in audit["data"]["lineage"]["hires"]
               if not h["hired"] and "H1" in h.get("reason", "")]
    assert refused, "budget-exhausted refusals must be recorded"


def test_h1_budget_bounds_validated():
    core = build(solvers=solvers())
    for bad in (0, -5, float("nan"), float("inf"), True, "lots"):
        res = solve(core, budget_minor=bad)
        assert res["status"] == "error"
        assert res["error_type"] == "ValidationError"


# ---------------------------------------------------------------- H2

def test_h2_hive_solver_needs_depth():
    s = solvers(2)
    s["child-hive"] = {"adapter": GoodSolver("hive", 0.95), "kind": "hive",
                       "price_minor": 100}
    core = build(solvers=s, rails=wired_rails())
    res = solve(core, depth=0, redundancy=3)
    audit = run(core.process({"action": "audit_job",
                              "job_id": res["data"]["job_id"]}))
    hires = audit["data"]["lineage"]["hires"]
    hive_hires = [h for h in hires if h["solver_id"] == "child-hive"]
    assert hive_hires and all(not h["hired"] for h in hive_hires)
    assert all("H2" in h["reason"] for h in hive_hires)


def test_h2_hive_solver_hired_with_depth_and_decremented():
    s = solvers(2)
    s["child-hive"] = {"adapter": GoodSolver("hive", 0.95), "kind": "hive",
                       "price_minor": 100}
    core = build(solvers=s, rails=wired_rails())
    res = solve(core, depth=2, redundancy=3)
    audit = run(core.process({"action": "audit_job",
                              "job_id": res["data"]["job_id"]}))
    hired = [h for h in audit["data"]["lineage"]["hires"]
             if h["solver_id"] == "child-hive" and h["hired"]]
    assert hired and all(h["child_depth"] == 1 for h in hired)


def test_h2_covenant_denial_blocks_hire_and_escrow():
    rails = wired_rails()
    rails["covenant"] = MockCovenant(deny_all=True)
    core = build(solvers=solvers(3), rails=rails)
    res = solve(core)
    assert res["status"] == "ok"
    assert res["data"]["hires"] == 0
    assert rails["escrow"].calls == [], "no escrow may open without covenant"


def test_h2_depth_bounds():
    core = build(solvers=solvers())
    assert solve(core, depth=99)["status"] == "error"
    assert solve(core, depth=-1)["status"] == "error"
    assert solve(core, depth=True)["status"] == "error"


# ---------------------------------------------------------------- H3

def test_h3_determinism_across_fresh_engines():
    r1 = solve(build(solvers=solvers(3), rails=wired_rails()))
    r2 = solve(build(solvers=solvers(3), rails=wired_rails()))
    assert r1["data"]["plan_hash"] == r2["data"]["plan_hash"]
    assert r1["data"]["audit_sha256"] == r2["data"]["audit_sha256"]
    assert r1["data"]["synthesis"] == r2["data"]["synthesis"]


def test_h3_seed_changes_plan_hash():
    r1 = solve(build(solvers=solvers(3)), seed=1)
    r2 = solve(build(solvers=solvers(3)), seed=2)
    assert r1["data"]["plan_hash"] != r2["data"]["plan_hash"]


def test_h3_reopen_same_plan_is_idempotent():
    core = build(solvers=solvers(3))
    req = {"action": "open_job", "problem": "p", "budget_minor": 500,
           "seed": 3}
    first = run(core.process(req))
    second = run(core.process(dict(req)))
    assert second["data"]["duplicate"] is True
    assert first["data"]["job_id"] == second["data"]["job_id"]


# ---------------------------------------------------------------- H4

def test_h4_reviewer_never_author():
    core = build(solvers=solvers(3), rails=wired_rails())
    res = solve(core)
    audit = run(core.process({"action": "audit_job",
                              "job_id": res["data"]["job_id"]}))
    for review in audit["data"]["lineage"]["reviews"]:
        assert review["reviewer"] != review["author"]


def test_h4_unreviewed_contribution_never_accepted():
    core = build(solvers=solvers(1), rails=wired_rails())  # nobody to review
    res = solve(core, redundancy=1)
    assert res["status"] == "ok"
    assert res["data"]["synthesis"]["sections"] == []
    assert res["data"]["synthesis"]["collective_score"] == 0.0


def test_h4_rejected_contribution_excluded_and_refunded():
    core = build(solvers=solvers(3, quality=0.2), rails=wired_rails())
    res = solve(core)  # all reviews score 0.2 < 0.6 threshold
    assert res["data"]["synthesis"]["sections"] == []
    b = res["data"]["budget"]
    assert b["spent_minor"] == 0 and b["refunded_minor"] == \
        b["committed_minor"]


# ---------------------------------------------------------------- H5

def test_h5_every_escrow_terminal_at_completion():
    rails = wired_rails()
    core = build(solvers=solvers(3), rails=rails)
    res = solve(core)
    assert res["status"] == "ok"
    states = [r["state"] for r in rails["escrow"].store.values()]
    assert states and all(s in ("RELEASED", "REFUNDED") for s in states)
    audit = run(core.process({"action": "audit_job",
                              "job_id": res["data"]["job_id"]}))
    for s in audit["data"]["lineage"]["settlements"]:
        assert s["terminal_state"] in ("RELEASED", "REFUNDED")


# ---------------------------------------------------------------- H6

def test_h6_emergent_requires_two_contributors_and_wider_coverage():
    core = build(solvers=solvers(3), rails=wired_rails())
    res = solve(core, subtasks=["a", "b", "c"], redundancy=2)
    syn = res["data"]["synthesis"]
    if syn["emergent"]:
        assert len(syn["contributing_solvers"]) >= 2
        assert len(syn["sections"]) > max(
            [sum(1 for s in syn["sections"] if s["solver_id"] == sid)
             for sid in syn["contributing_solvers"]])


def test_h6_no_emergence_claim_for_single_solver_output():
    s = {"solver-0": {"adapter": GoodSolver("s0"), "price_minor": 100},
         "reviewer": {"adapter": GoodSolver("rev"), "price_minor": 900}}
    core = build(solvers=s, rails=wired_rails())
    # budget lets only solver-0 be hired per subtask; reviewer reviews only
    res = solve(core, budget_minor=250, subtasks=["a", "b"], redundancy=1)
    syn = res["data"]["synthesis"]
    assert len(syn["contributing_solvers"]) <= 1
    assert syn["emergent"] is False


def test_h6_collective_score_is_measured_not_inflated():
    core = build(solvers=solvers(3, quality=0.7), rails=wired_rails())
    res = solve(core)
    syn = res["data"]["synthesis"]
    for section in syn["sections"]:
        assert section["review_score"] == 0.7
    assert syn["collective_score"] == 0.7


# ---------------------------------------------------------------- H7

def test_h7_physics_posted_and_bits_per_joule_reported():
    rails = wired_rails()
    core = build(solvers=solvers(3), rails=rails)
    res = solve(core)
    syn = res["data"]["synthesis"]
    assert syn["physics_accounted"] is True
    assert syn["energy_j"] > 0
    assert syn["bits_per_joule"] is not None
    # energy is posted for EVERY accepted (paid) contribution, including
    # redundant attempts - redundancy costs joules; that cost is never hidden
    audit = run(core.process({"action": "audit_job",
                              "job_id": res["data"]["job_id"]}))
    accepted = [c for c in audit["data"]["lineage"]["contributions"]
                if c.get("accepted")]
    ledger_entries = [c for c in rails["ledger"].calls
                      if c["action"] == "record_work"]
    assert len(ledger_entries) == len(accepted) >= len(syn["sections"])
    expected = round(syn["accepted_information_bits"] / syn["energy_j"], 6)
    assert syn["bits_per_joule"] == expected


def test_h7_no_fabricated_physics_when_ledger_unwired():
    rails = wired_rails()
    del rails["ledger"]
    core = build(solvers=solvers(3), rails=rails)
    res = solve(core)
    syn = res["data"]["synthesis"]
    assert syn["physics_accounted"] is False
    assert syn["energy_j"] is None and syn["bits_per_joule"] is None


def test_h7_shannon_bits_deterministic_and_sane():
    assert shannon_bits("") == 0.0
    assert shannon_bits("aaaa") == 0.0  # zero entropy
    b = shannon_bits("hello world")
    assert b > 0 and b == shannon_bits("hello world")


# ---------------------------------------------------------------- H8

def test_h8_crashing_solver_degrades_not_crashes():
    s = solvers(2)
    s["boom"] = {"adapter": CrashingSolver(), "price_minor": 50}
    rails = wired_rails()
    core = build(solvers=s, rails=rails)
    res = solve(core, redundancy=3)
    assert res["status"] == "ok"
    audit = run(core.process({"action": "audit_job",
                              "job_id": res["data"]["job_id"]}))
    failed = [c for c in audit["data"]["lineage"]["contributions"]
              if c["failed"]]
    assert failed and all(c["solver_id"] == "boom" for c in failed)
    for c in failed:  # crashed work is refunded, never released
        settle = [s_ for s_ in audit["data"]["lineage"]["settlements"]
                  if s_["solver_id"] == "boom"]
        assert all(x["terminal_state"] == "REFUNDED" for x in settle)


def test_h8_garbage_physics_rejected_not_posted():
    s = solvers(2)
    s["garbage"] = {"adapter": GarbageSolver(), "price_minor": 50}
    rails = wired_rails()
    core = build(solvers=s, rails=rails)
    res = solve(core, redundancy=3)
    assert res["status"] == "ok"
    for call in rails["ledger"].calls:
        if call["action"] == "record_work":
            assert call["power_w"] != float("inf")
            assert call["duration_s"] > 0


def test_h8_nondict_input_guard():
    core = build(solvers=solvers())
    for bad in (None, 42, "text", [1]):
        res = run(core.process(bad))
        assert res["status"] == "error"
        assert res["error_type"] == "ValidationError"
        assert res["field"] == "input_data"


def test_h8_unknown_action_envelope():
    core = build(solvers=solvers())
    res = run(core.process({"action": "conquer_world"}))
    assert res["status"] == "error"
    assert res["error_type"] == "UnknownOperation"


# ---------------------------------------------------------------- H9

def test_h9_audit_recompute_detects_tamper():
    core = build(solvers=solvers(3), rails=wired_rails())
    res = solve(core)
    audit = run(core.process({"action": "audit_job",
                              "job_id": res["data"]["job_id"]}))["data"]
    ok = run(core.process({"action": "verify_audit", "audit": audit}))
    assert ok["data"]["valid"] is True
    assert ok["data"]["matches_known_job"] is True

    tampered = copy.deepcopy(audit)
    tampered["lineage"]["synthesis"]["collective_score"] = 1.0
    bad = run(core.process({"action": "verify_audit", "audit": tampered}))
    assert bad["data"]["valid"] is False


def test_h9_forged_self_consistent_audit_flagged_as_unknown():
    """A forged audit whose hash matches its own lineage still fails the
    known-job check (recompute-in-verify + provenance, taxcredit lesson)."""
    core = build(solvers=solvers(3), rails=wired_rails())
    res = solve(core)
    audit = run(core.process({"action": "audit_job",
                              "job_id": res["data"]["job_id"]}))["data"]
    forged = copy.deepcopy(audit)
    forged["lineage"]["synthesis"]["collective_score"] = 1.0
    forged["audit_sha256"] = core._lineage_digest(
        {"lineage": forged["lineage"]})
    res2 = run(core.process({"action": "verify_audit", "audit": forged}))
    assert res2["data"]["valid"] is True  # internally consistent...
    assert res2["data"]["matches_known_job"] is False  # ...but not ours


# ---------------------------------------------------------------- H10

def test_h10_standalone_marks_everything_simulated():
    core = build(solvers=solvers(3))  # no rails
    res = solve(core)
    assert res["status"] == "ok"
    assert res["data"]["rails_mode"] == "standalone"
    audit = run(core.process({"action": "audit_job",
                              "job_id": res["data"]["job_id"]}))
    calls = audit["data"]["lineage"]["rail_calls"]
    assert calls and all(c["simulated"] is True for c in calls)
    assert res["data"]["synthesis"]["physics_accounted"] is False


def test_h10_wired_marks_calls_real():
    core = build(solvers=solvers(3), rails=wired_rails())
    res = solve(core)
    audit = run(core.process({"action": "audit_job",
                              "job_id": res["data"]["job_id"]}))
    assert all(c["simulated"] is False
               for c in audit["data"]["lineage"]["rail_calls"])


# ---------------------------------------------------------------- surface

def test_registry_validation():
    core = build()
    try:
        core.register_solver("", {"adapter": GoodSolver("x"),
                                  "price_minor": 1})
        assert False
    except ValidationError:
        pass
    try:
        core.register_solver("s", {"adapter": object(), "price_minor": 1})
        assert False
    except ValidationError:
        pass
    try:
        core.register_solver("s", {"adapter": GoodSolver("x"),
                                   "price_minor": 0})
        assert False
    except ValidationError:
        pass


def test_unknown_rails_rejected():
    try:
        build(rails={"blockchain": object()})
        assert False
    except ValidationError:
        pass


def test_describe_and_health():
    core = build(solvers=solvers(2))
    d = core.describe()
    assert d["name"] == "agent-hive-orchestrator-agent"
    assert "H1-budget-conservation" in d["invariants"]
    h = run(core.health())
    assert h["status"] == "ok" and h["checks"]["solvers_registered"] == 2
