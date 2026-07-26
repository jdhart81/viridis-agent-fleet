"""Deterministic nested hive-mind orchestration over the Viridis A2A rails.

The hive does not think; it structures thinking. It hires N solver agents,
forces independent cross-review, synthesizes only what survives review, and
settles every hire through the real rails (covenant -> escrow -> meter ->
trust -> compute-ledger). "Collective intelligence with a balance sheet."

H1   BUDGET CONSERVATION - committed + fees never exceed budget_minor; a hire
     that would overdraw is refused; spent + refunded + unspent == budget.
H2   DENY-BY-DEFAULT NESTED AUTHORITY - each job carries depth in [0, MAX];
     hiring a "hive"-kind solver requires depth >= 1 and passes depth-1;
     with a covenant wired, every hire needs an allowed check_act first.
H3   DETERMINISM - identical (problem, subtasks, registry, seed, params)
     produce identical plan_hash and audit_sha256 (no wall clock in hashes).
H4   REVIEWER != AUTHOR - a contribution is accepted only after >= 1 review
     by a different solver scoring >= accept_threshold; unreviewed or
     rejected contributions never enter synthesis.
H5   SETTLEMENT CLOSURE - a job completes only when every escrow it opened
     is terminal (RELEASED for accepted work, REFUNDED otherwise).
H6   EMERGENCE HONESTY - collective_score is exactly what cross-review
     measured; emergent=True only when >= 2 distinct solvers contributed
     accepted work AND the collective covers more than any single solver.
H7   THERMODYNAMIC ACCOUNTING - accepted work posts energy/carbon to the
     compute-ledger when wired; bits_per_joule = accepted Shannon bits /
     total energy_j; physics fields are null when unwired, never fabricated.
H8   FAIL-SAFE DEGRADATION - a crashing or garbage solver never crashes the
     job: contribution rejected, escrow refunded, trust outcome recorded,
     job continues; all numerics reject bool/NaN/Inf and enforce bounds.
H9   CONTENT-ADDRESSED AUDIT - audit exposes the full lineage; verify_audit
     RECOMPUTES the digest from lineage (never trusts the stored hash).
H10  STANDALONE HONESTY - without rails the same code path runs with
     simulated in-core rails and every rail record is marked simulated=True.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("agent-hive-orchestrator")

VERSION = "0.1.0"
MAX_DEPTH = 3
MAX_BUDGET_MINOR = 10_000_000  # $100k ceiling per job
MAX_SUBTASKS = 64
MAX_CONTENT_BYTES = 262_144
DEFAULT_ACCEPT_THRESHOLD = 0.6
DEFAULT_REDUNDANCY = 2
RAIL_NAMES = ("identity", "trust", "covenant", "escrow", "metering", "ledger")
KNOWN_ACTIONS = frozenset({
    "open_job", "run_job", "solve", "job_status", "audit_job",
    "verify_audit", "list_solvers",
})
READ_ACTIONS = frozenset({
    "job_status", "audit_job", "verify_audit", "list_solvers",
})


@dataclass
class AgentConfig:
    name: str = "agent-hive-orchestrator-agent"
    version: str = VERSION
    debug: bool = False


class ValidationError(ValueError):
    def __init__(self, message: str, field: str = "", value: Any = None,
                 constraint: str = ""):
        super().__init__(message)
        self.field = field
        self.value = value
        self.constraint = constraint


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _error(error_type: str, message: str, *, field_: str = "",
           value: Any = None, constraint: str = "") -> Dict[str, Any]:
    """Fleet-canonical error envelope (schema-identical to fleet_utils)."""
    return {
        "status": "error",
        "error_type": error_type,
        "field": field_ or None,
        "value": value,
        "constraint": constraint or None,
        "message": message,
        "timestamp": _now(),
    }


def _require_number(container: Dict[str, Any], field_: str, *,
                    positive: bool = False, allow_zero: bool = False,
                    min_value: Optional[float] = None,
                    max_value: Optional[float] = None) -> float:
    """NaN/Inf/bool-safe float coercion (fleet_utils.require_number shape)."""
    if field_ not in container:
        raise ValidationError(f"'{field_}' is required", field_, None,
                              "field is required")
    raw = container[field_]
    if isinstance(raw, bool):
        raise ValidationError(f"'{field_}' must be numeric, not bool",
                              field_, raw, "must be numeric, not bool")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"'{field_}' must be numeric", field_, raw,
                              "must be numeric")
    if not math.isfinite(value):
        raise ValidationError(f"'{field_}' must be finite", field_, raw,
                              "must be finite (no NaN/Inf)")
    if positive and value <= 0 and not allow_zero:
        raise ValidationError(f"'{field_}' must be > 0", field_, raw, "> 0")
    if positive and value < 0 and allow_zero:
        raise ValidationError(f"'{field_}' must be >= 0", field_, raw, ">= 0")
    if min_value is not None and value < min_value:
        raise ValidationError(f"'{field_}' must be >= {min_value}", field_,
                              raw, f">= {min_value}")
    if max_value is not None and value > max_value:
        raise ValidationError(f"'{field_}' must be <= {max_value}", field_,
                              raw, f"<= {max_value}")
    return value


def _int_minor(container: Dict[str, Any], field_: str, *, minimum: int = 1,
               maximum: int = MAX_BUDGET_MINOR) -> int:
    value = _require_number(container, field_, min_value=float(minimum),
                            max_value=float(maximum))
    if value != int(value):
        raise ValidationError(f"'{field_}' must be an integer minor amount",
                              field_, container[field_], "integer minor units")
    return int(value)


def shannon_bits(content: str) -> float:
    """Deterministic information proxy: Shannon entropy (bits/byte) x bytes.

    An honest *proxy*, not a claim of semantic information. Used only for the
    bits_per_joule telemetry (H7) - never for pricing or settlement.
    """
    data = content.encode("utf-8")
    if not data:
        return 0.0
    counts: Dict[int, int] = {}
    for b in data:
        counts[b] = counts.get(b, 0) + 1
    n = len(data)
    entropy = -sum((c / n) * math.log2(c / n) for c in counts.values())
    return round(entropy * n, 3)


# --------------------------------------------------------------------------
# Simulated rails (H10). Same call shapes as the real rails so the engine
# runs one code path; every record they touch is marked simulated=True.
# --------------------------------------------------------------------------

class _SimEscrow:
    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}
        self._n = 0

    async def process(self, req: Dict[str, Any]) -> Dict[str, Any]:
        action = req.get("action")
        if action == "open":
            self._n += 1
            eid = f"sim-esc-{self._n}"
            fee = req.get("amount_minor", 0) * req.get("fee_bps", 0) // 10_000
            self._store[eid] = {"state": "OPEN",
                                "amount_minor": req["amount_minor"],
                                "fee_minor": fee}
            return {"status": "ok", "data": {"escrow_id": eid,
                                             "fee_minor": fee,
                                             "net_to_payee_minor":
                                                 req["amount_minor"] - fee}}
        rec = self._store.get(req.get("escrow_id", ""))
        if rec is None:
            return _error("NotFound", "unknown escrow")
        if action == "fund":
            rec["state"] = "FUNDED"
        elif action == "dispute":
            rec["state"] = "DISPUTED"
        elif action == "release":
            if rec["state"] == "REFUNDED":
                return _error("StateError", "cannot release a refunded escrow")
            rec["state"] = "RELEASED"
        elif action == "refund":
            if rec["state"] == "RELEASED":
                return _error("StateError", "cannot refund a released escrow")
            rec["state"] = "REFUNDED"
        elif action != "status":
            return _error("UnknownOperation", f"unknown action {action}")
        return {"status": "ok", "data": dict(rec)}


class _SimSimple:
    """Catch-all simulated rail: acknowledges every action deterministically."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: List[Dict[str, Any]] = []

    async def process(self, req: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append(req)
        action = req.get("action", "")
        data: Dict[str, Any] = {"simulated": True}
        if self.name == "covenant" and action == "check_act":
            data["allowed"] = True
        if self.name == "trust" and action == "score":
            data.update({"score": 0.5, "tier": "NEUTRAL", "prior": True})
        if self.name == "metering":
            if action == "create_meter":
                data["meter_id"] = f"sim-meter-{_digest(req)[:8]}"
            if action == "record_usage":
                data["duplicate"] = False
        if self.name == "ledger" and action == "record_work":
            power = float(req.get("power_w", 0.0))
            dur = float(req.get("duration_s", 0.0))
            energy = power * dur
            data.update({"energy_j": energy,
                         "carbon_g": round(energy / 3_600_000.0
                                           * float(req.get(
                                               "grid_intensity_g_per_kwh",
                                               400.0)), 6)})
        return {"status": "ok", "data": data}


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------

class HiveOrchestratorCore:
    """Nested hive-mind orchestration engine (see module invariants)."""

    KNOWN_ACTIONS = KNOWN_ACTIONS
    READ_ACTIONS = READ_ACTIONS

    def __init__(self, config: Optional[AgentConfig] = None,
                 solvers: Optional[Dict[str, Dict[str, Any]]] = None,
                 rails: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or AgentConfig()
        self.solvers: Dict[str, Dict[str, Any]] = {}
        for solver_id, profile in (solvers or {}).items():
            self.register_solver(solver_id, profile)
        rails = rails or {}
        unknown = sorted(set(rails) - set(RAIL_NAMES))
        if unknown:
            raise ValidationError(f"unknown rails: {unknown}", "rails",
                                  unknown, f"subset of {RAIL_NAMES}")
        self.rails_mode = "wired" if rails else "standalone"
        self._sim = {"escrow": _SimEscrow(),
                     **{n: _SimSimple(n) for n in RAIL_NAMES if n != "escrow"}}
        self._rails = {name: rails.get(name) for name in RAIL_NAMES}
        self.jobs: Dict[str, Dict[str, Any]] = {}

    # -- registry ----------------------------------------------------------

    def register_solver(self, solver_id: str, profile: Dict[str, Any]) -> None:
        if not isinstance(solver_id, str) or not solver_id.strip():
            raise ValidationError("solver_id must be a non-empty string",
                                  "solver_id", solver_id, "non-empty str")
        if not isinstance(profile, dict):
            raise ValidationError("solver profile must be a dict", "profile",
                                  type(profile).__name__, "dict")
        adapter = profile.get("adapter")
        if not (hasattr(adapter, "solve") and hasattr(adapter, "review")):
            raise ValidationError(
                "solver adapter must expose async solve() and review()",
                "adapter", type(adapter).__name__, "SolverAdapter protocol")
        kind = profile.get("kind", "worker")
        if kind not in ("worker", "hive"):
            raise ValidationError("solver kind must be worker|hive", "kind",
                                  kind, "worker|hive")
        price = _int_minor(profile, "price_minor", minimum=1)
        self.solvers[solver_id] = {
            "adapter": adapter, "kind": kind, "price_minor": price,
            "capabilities": list(profile.get("capabilities", [])),
        }

    async def _rail(self, name: str, req: Dict[str, Any],
                    job: Dict[str, Any]) -> Dict[str, Any]:
        """Route to a wired rail or its simulated stand-in; log to lineage."""
        rail = self._rails.get(name)
        simulated = rail is None
        target = self._sim[name] if simulated else rail
        try:
            resp = await target.process(req)
        except Exception as exc:  # a broken rail must not brick the job (H8)
            resp = _error("RailError", f"{name} rail raised: {exc}")
        job["lineage"]["rail_calls"].append({
            "rail": name, "action": req.get("action"),
            "simulated": simulated, "status": resp.get("status"),
        })
        return resp

    # -- public contract ----------------------------------------------------

    async def process(self, input_data: Any) -> Dict[str, Any]:
        if not isinstance(input_data, dict):
            return _error("ValidationError", "input_data must be a dict",
                          field_="input_data",
                          value=type(input_data).__name__,
                          constraint="input_data must be a dict")
        action = input_data.get("action")
        handlers: Dict[str, Callable[[Dict[str, Any]],
                                     Awaitable[Dict[str, Any]]]] = {
            "open_job": self._open_job,
            "run_job": self._run_job,
            "solve": self._solve,
            "job_status": self._job_status,
            "audit_job": self._audit_job,
            "verify_audit": self._verify_audit,
            "list_solvers": self._list_solvers,
        }
        handler = handlers.get(action)
        if handler is None:
            return _error("UnknownOperation", f"Unknown action: {action}",
                          field_="action", value=action,
                          constraint=f"one of {sorted(handlers)}")
        try:
            return await handler(input_data)
        except ValidationError as exc:
            return _error("ValidationError", str(exc), field_=exc.field,
                          value=exc.value, constraint=exc.constraint)

    # -- open ---------------------------------------------------------------

    async def _open_job(self, req: Dict[str, Any]) -> Dict[str, Any]:
        problem = req.get("problem")
        if not isinstance(problem, str) or not problem.strip():
            raise ValidationError("problem must be a non-empty string",
                                  "problem", problem, "non-empty str")
        if len(problem.encode()) > MAX_CONTENT_BYTES:
            raise ValidationError("problem too large", "problem",
                                  len(problem.encode()),
                                  f"<= {MAX_CONTENT_BYTES} bytes")
        budget = _int_minor(req, "budget_minor")
        depth_raw = req.get("depth", 0)
        if isinstance(depth_raw, bool) or not isinstance(depth_raw, int):
            raise ValidationError("depth must be an integer", "depth",
                                  depth_raw, f"int in [0,{MAX_DEPTH}]")
        if not 0 <= depth_raw <= MAX_DEPTH:
            raise ValidationError("depth out of range", "depth", depth_raw,
                                  f"int in [0,{MAX_DEPTH}]")
        subtasks = req.get("subtasks") or [problem]
        if (not isinstance(subtasks, list) or not subtasks
                or len(subtasks) > MAX_SUBTASKS
                or not all(isinstance(s, str) and s.strip()
                           for s in subtasks)):
            raise ValidationError("subtasks must be 1..%d non-empty strings"
                                  % MAX_SUBTASKS, "subtasks", subtasks,
                                  f"list[str] length 1..{MAX_SUBTASKS}")
        redundancy = req.get("redundancy", DEFAULT_REDUNDANCY)
        if isinstance(redundancy, bool) or not isinstance(redundancy, int) \
                or not 1 <= redundancy <= 8:
            raise ValidationError("redundancy must be int in [1,8]",
                                  "redundancy", redundancy, "int in [1,8]")
        threshold = float(req.get("accept_threshold",
                                  DEFAULT_ACCEPT_THRESHOLD))
        if not (isinstance(threshold, (int, float))
                and not isinstance(threshold, bool)
                and math.isfinite(threshold) and 0.0 < threshold <= 1.0):
            raise ValidationError("accept_threshold must be in (0,1]",
                                  "accept_threshold", threshold, "(0,1]")
        seed = req.get("seed", 0)
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValidationError("seed must be an integer", "seed", seed,
                                  "int")

        plan = {
            "problem": problem, "subtasks": list(subtasks),
            "budget_minor": budget, "depth": depth_raw,
            "redundancy": redundancy, "accept_threshold": threshold,
            "seed": seed, "fee_bps": int(req.get("fee_bps", 0) or 0),
            "covenant_id": req.get("covenant_id"),
            "principal": req.get("principal", "unspecified"),
            "solver_registry_hash": _digest(sorted(
                (sid, p["kind"], p["price_minor"])
                for sid, p in self.solvers.items())),
            "engine_version": VERSION,
        }
        job_id = "hive-" + _digest(plan)[:16]
        if job_id in self.jobs:  # idempotent re-open (same plan -> same job)
            return {"status": "ok",
                    "data": {"job_id": job_id, "duplicate": True,
                             "plan_hash": self.jobs[job_id]["plan_hash"]}}
        job = {
            "job_id": job_id, "plan": plan, "plan_hash": _digest(plan),
            "state": "OPEN", "opened_at": _now(),
            "budget": {"total_minor": budget, "committed_minor": 0,
                       "spent_minor": 0, "refunded_minor": 0,
                       "fees_minor": 0},
            "lineage": {"plan": plan, "hires": [], "contributions": [],
                        "reviews": [], "settlements": [], "rail_calls": [],
                        "synthesis": None, "rails_mode": self.rails_mode},
            "result": None,
        }
        self.jobs[job_id] = job
        return {"status": "ok", "data": {"job_id": job_id, "duplicate": False,
                                         "plan_hash": job["plan_hash"],
                                         "rails_mode": self.rails_mode}}

    # -- run ----------------------------------------------------------------

    def _ranked_solvers(self, trust_scores: Dict[str, float],
                        seed: int) -> List[str]:
        """Deterministic ranking: trust desc, price asc, seeded stable tiebreak."""
        def key(sid: str):
            profile = self.solvers[sid]
            tiebreak = _digest({"sid": sid, "seed": seed})
            return (-trust_scores.get(sid, 0.5), profile["price_minor"],
                    tiebreak)
        return sorted(self.solvers, key=key)

    async def _run_job(self, req: Dict[str, Any]) -> Dict[str, Any]:
        job = self.jobs.get(req.get("job_id", ""))
        if job is None:
            return _error("NotFound", "unknown job_id", field_="job_id",
                          value=req.get("job_id"), constraint="opened job")
        if job["state"] == "COMPLETE":  # idempotent
            return {"status": "ok", "data": {**job["result"],
                                             "duplicate": True}}
        if job["state"] == "RUNNING":
            return _error("StateError", "job already running")
        job["state"] = "RUNNING"
        plan, budget = job["plan"], job["budget"]
        seed, threshold = plan["seed"], plan["accept_threshold"]

        # 1. vet: pull trust scores for ranking (H2 vet-before-hire)
        trust_scores: Dict[str, float] = {}
        for sid in sorted(self.solvers):
            resp = await self._rail("trust", {"action": "score",
                                              "agent_id": sid}, job)
            if resp.get("status") == "ok":
                trust_scores[sid] = float(resp["data"].get("score", 0.5))
        ranked = self._ranked_solvers(trust_scores, seed)

        # 2. hire + solve, per subtask x redundancy
        contributions: List[Dict[str, Any]] = []
        for t_idx, subtask in enumerate(plan["subtasks"]):
            assigned: List[str] = []
            for r in range(plan["redundancy"]):
                if not ranked:
                    break
                candidates = [s for s in ranked if s not in assigned]
                if not candidates:
                    break
                sid = candidates[(t_idx + r) % len(candidates)]
                profile = self.solvers[sid]
                price = profile["price_minor"]
                fee = price * plan["fee_bps"] // 10_000

                # H2: nesting gate
                if profile["kind"] == "hive" and plan["depth"] < 1:
                    job["lineage"]["hires"].append(
                        {"solver_id": sid, "subtask_index": t_idx,
                         "hired": False, "reason": "depth-exhausted (H2)"})
                    continue
                # H1: budget gate
                if budget["committed_minor"] + price + fee \
                        > budget["total_minor"]:
                    job["lineage"]["hires"].append(
                        {"solver_id": sid, "subtask_index": t_idx,
                         "hired": False, "reason": "budget-exhausted (H1)"})
                    continue
                # H2: covenant gate (deny-by-default when wired)
                act_id = f"{job['job_id']}-t{t_idx}-r{r}-{sid}"
                cov = await self._rail("covenant", {
                    "action": "check_act",
                    "covenant_id": plan.get("covenant_id"),
                    "act_id": act_id, "scope": "hive.hire",
                    "amount_minor": price}, job)
                if not (cov.get("status") == "ok"
                        and cov.get("data", {}).get("allowed") is True):
                    job["lineage"]["hires"].append(
                        {"solver_id": sid, "subtask_index": t_idx,
                         "hired": False, "reason": "covenant-denied (H2)"})
                    continue

                esc = await self._rail("escrow", {
                    "action": "open", "payer": f"hive:{job['job_id']}",
                    "payee": sid, "amount_minor": price,
                    "fee_bps": plan["fee_bps"],
                    "terms": _digest({"subtask": subtask,
                                      "act_id": act_id})}, job)
                if esc.get("status") != "ok":
                    job["lineage"]["hires"].append(
                        {"solver_id": sid, "subtask_index": t_idx,
                         "hired": False, "reason": "escrow-open-failed"})
                    continue
                eid = esc["data"]["escrow_id"]
                await self._rail("escrow", {"action": "fund",
                                            "escrow_id": eid}, job)
                budget["committed_minor"] += price + fee
                budget["fees_minor"] += fee
                assigned.append(sid)
                hire = {"solver_id": sid, "subtask_index": t_idx,
                        "hired": True, "escrow_id": eid, "act_id": act_id,
                        "price_minor": price, "fee_minor": fee,
                        "child_depth": (plan["depth"] - 1
                                        if profile["kind"] == "hive"
                                        else None)}
                job["lineage"]["hires"].append(hire)

                meter = await self._rail("metering", {
                    "action": "create_meter", "provider": sid,
                    "consumer": f"hive:{job['job_id']}", "unit": "attempt",
                    "price_minor_per_unit": price}, job)
                meter_id = meter.get("data", {}).get("meter_id")

                # solve (H8: exceptions degrade, never crash)
                task_payload = {"subtask": subtask, "problem": plan["problem"],
                                "seed": seed, "depth": hire["child_depth"]}
                try:
                    solved = await profile["adapter"].solve(task_payload)
                    if not isinstance(solved, dict) or \
                            not isinstance(solved.get("content"), str) or \
                            not solved["content"].strip():
                        raise ValueError("solver returned no usable content")
                    if len(solved["content"].encode()) > MAX_CONTENT_BYTES:
                        raise ValueError("solver content exceeds size bound")
                    contribution = {
                        "solver_id": sid, "subtask_index": t_idx,
                        "escrow_id": eid, "act_id": act_id,
                        "content": solved["content"],
                        "content_sha256": _digest(solved["content"]),
                        "bits": shannon_bits(solved["content"]),
                        "physics": self._safe_physics(solved),
                        "failed": False,
                    }
                except Exception as exc:
                    contribution = {
                        "solver_id": sid, "subtask_index": t_idx,
                        "escrow_id": eid, "act_id": act_id, "content": None,
                        "content_sha256": None, "bits": 0.0, "physics": None,
                        "failed": True, "failure": str(exc)[:500],
                    }
                if meter_id:
                    await self._rail("metering", {
                        "action": "record_usage", "meter_id": meter_id,
                        "event_id": act_id, "quantity": 1,
                        "outcome": ("error" if contribution["failed"]
                                    else "ok")}, job)
                contributions.append(contribution)
        job["lineage"]["contributions"] = contributions

        # 3. cross-review (H4: reviewer != author; unreviewed never accepted)
        for c_idx, contrib in enumerate(contributions):
            if contrib["failed"]:
                contrib["accepted"] = False
                continue
            reviewers = [s for s in ranked if s != contrib["solver_id"]
                         and hasattr(self.solvers[s]["adapter"], "review")]
            if not reviewers:
                contrib["accepted"] = False
                contrib["review"] = None  # unreviewed -> not accepted (H4)
                continue
            reviewer = reviewers[c_idx % len(reviewers)]
            try:
                review = await self.solvers[reviewer]["adapter"].review(
                    {"content": contrib["content"],
                     "subtask": plan["subtasks"][contrib["subtask_index"]],
                     "seed": seed})
                score = float(review.get("score"))
                if not math.isfinite(score) or not 0.0 <= score <= 1.0:
                    raise ValueError("review score out of [0,1]")
            except Exception as exc:
                review, score = {"error": str(exc)[:200]}, 0.0
            contrib["review"] = {"reviewer_id": reviewer,
                                 "score": round(score, 6)}
            contrib["accepted"] = score >= threshold
            job["lineage"]["reviews"].append({
                "contribution_sha256": contrib["content_sha256"],
                "author": contrib["solver_id"], "reviewer": reviewer,
                "score": round(score, 6), "accepted": contrib["accepted"]})

        # 4. settle every escrow (H5) + trust feedback
        for contrib in contributions:
            accepted = contrib.get("accepted", False)
            if accepted:
                await self._rail("escrow", {
                    "action": "release", "escrow_id": contrib["escrow_id"],
                    "delivery_proof": contrib["content_sha256"]}, job)
                budget["spent_minor"] += self._hire_total(job,
                                                          contrib["escrow_id"])
                outcome = "delivered"
            else:
                await self._rail("escrow", {
                    "action": "dispute", "escrow_id": contrib["escrow_id"],
                    "reason": "rejected by hive cross-review"}, job)
                await self._rail("escrow", {
                    "action": "refund", "escrow_id": contrib["escrow_id"],
                    "reason": "hive review gate (H4)"}, job)
                budget["refunded_minor"] += self._hire_total(
                    job, contrib["escrow_id"])
                outcome = "dispute_lost"
            status = await self._rail("escrow", {
                "action": "status", "escrow_id": contrib["escrow_id"]}, job)
            job["lineage"]["settlements"].append({
                "escrow_id": contrib["escrow_id"],
                "solver_id": contrib["solver_id"],
                "terminal_state": status.get("data", {}).get("state"),
                "accepted": accepted})
            await self._rail("trust", {"action": "record_outcome",
                                       "agent_id": contrib["solver_id"],
                                       "kind": outcome,
                                       "counterparty":
                                           f"hive:{job['job_id']}"}, job)

        # 5. physics (H7) - accepted work only, ledger-idempotent entry ids
        total_energy_j = 0.0
        physics_accounted = self._rails.get("ledger") is not None
        for contrib in contributions:
            if not contrib.get("accepted") or not contrib.get("physics"):
                continue
            phys = contrib["physics"]
            resp = await self._rail("ledger", {
                "action": "record_work", "agent_id": contrib["solver_id"],
                "entry_id": contrib["content_sha256"],
                "power_w": phys["power_w"], "duration_s": phys["duration_s"],
                "bit_ops": phys["bit_ops"],
                "grid_intensity_g_per_kwh": phys["grid_g_per_kwh"],
                "task": f"hive subtask {contrib['subtask_index']}"}, job)
            if resp.get("status") == "ok":
                total_energy_j += float(resp["data"].get("energy_j", 0.0))

        # 6. synthesis (H4/H6): best accepted contribution per subtask
        picked: List[Dict[str, Any]] = []
        for t_idx in range(len(plan["subtasks"])):
            pool = [c for c in contributions
                    if c["subtask_index"] == t_idx and c.get("accepted")]
            if pool:
                pool.sort(key=lambda c: (-c["review"]["score"],
                                         c["content_sha256"]))
                picked.append(pool[0])
        accepted_solvers = sorted({c["solver_id"] for c in picked})
        coverage = len(picked) / len(plan["subtasks"])
        collective_score = (round(
            sum(c["review"]["score"] for c in picked) / len(picked), 6)
            if picked else 0.0)
        per_solver_cover: Dict[str, int] = {}
        for c in picked:
            per_solver_cover[c["solver_id"]] = \
                per_solver_cover.get(c["solver_id"], 0) + 1
        best_single_cover = max(per_solver_cover.values(), default=0)
        emergent = (len(accepted_solvers) >= 2
                    and len(picked) > best_single_cover)
        accepted_bits = round(sum(c["bits"] for c in picked), 3)
        synthesis = {
            "sections": [{"subtask": plan["subtasks"][c["subtask_index"]],
                          "solver_id": c["solver_id"],
                          "content_sha256": c["content_sha256"],
                          "content": c["content"],
                          "review_score": c["review"]["score"]}
                         for c in picked],
            "coverage": round(coverage, 6),
            "collective_score": collective_score,
            "contributing_solvers": accepted_solvers,
            "emergent": emergent,
            "accepted_information_bits": accepted_bits,
            "energy_j": total_energy_j if physics_accounted else None,
            "bits_per_joule": (round(accepted_bits / total_energy_j, 6)
                               if physics_accounted and total_energy_j > 0
                               else None),
            "physics_accounted": physics_accounted,
        }
        job["lineage"]["synthesis"] = synthesis

        # close the books (H1 conservation check - fail loud)
        b = job["budget"]
        unspent = b["total_minor"] - b["spent_minor"]
        if b["spent_minor"] + b["refunded_minor"] != b["committed_minor"] \
                or b["committed_minor"] > b["total_minor"] or unspent < 0:
            job["state"] = "FAILED"
            return _error("ConservationError",
                          "budget conservation violated (H1)",
                          value=dict(b), constraint="spent+refunded<=total")
        dangling = [s for s in job["lineage"]["settlements"]
                    if s["terminal_state"] not in ("RELEASED", "REFUNDED")]
        if dangling:
            job["state"] = "FAILED"
            return _error("SettlementError",
                          "dangling escrows at completion (H5)",
                          value=dangling, constraint="all escrows terminal")

        job["state"] = "COMPLETE"
        job["completed_at"] = _now()
        audit_sha = self._lineage_digest(job)
        job["audit_sha256"] = audit_sha
        job["result"] = {
            "job_id": job["job_id"], "state": "COMPLETE",
            "plan_hash": job["plan_hash"], "audit_sha256": audit_sha,
            "synthesis": synthesis, "budget": dict(b),
            "unspent_minor": unspent,
            "hires": len([h for h in job["lineage"]["hires"] if h["hired"]]),
            "rails_mode": self.rails_mode, "duplicate": False,
        }
        return {"status": "ok", "data": job["result"]}

    def _hire_total(self, job: Dict[str, Any], escrow_id: str) -> int:
        for h in job["lineage"]["hires"]:
            if h.get("escrow_id") == escrow_id:
                return h["price_minor"] + h["fee_minor"]
        return 0

    @staticmethod
    def _safe_physics(solved: Dict[str, Any]) -> Optional[Dict[str, float]]:
        """Validate solver-declared physics; reject non-finite claims (H8)."""
        try:
            return {
                "power_w": _require_number(solved, "power_w", positive=True,
                                           max_value=1e6),
                "duration_s": _require_number(solved, "duration_s",
                                              positive=True, max_value=1e7),
                "bit_ops": _require_number(solved, "bit_ops", positive=True,
                                           max_value=1e30),
                "grid_g_per_kwh": _require_number(
                    solved, "grid_g_per_kwh", positive=True, allow_zero=True,
                    max_value=2000.0) if "grid_g_per_kwh" in solved
                else 400.0,
            }
        except ValidationError:
            return None

    # -- convenience: open + run in one call --------------------------------

    async def _solve(self, req: Dict[str, Any]) -> Dict[str, Any]:
        opened = await self._open_job(req)
        if opened.get("status") != "ok":
            return opened
        return await self._run_job({"action": "run_job",
                                    "job_id": opened["data"]["job_id"]})

    # -- status / audit ------------------------------------------------------

    async def _job_status(self, req: Dict[str, Any]) -> Dict[str, Any]:
        job = self.jobs.get(req.get("job_id", ""))
        if job is None:
            return _error("NotFound", "unknown job_id")
        return {"status": "ok", "data": {
            "job_id": job["job_id"], "state": job["state"],
            "plan_hash": job["plan_hash"], "budget": dict(job["budget"]),
            "rails_mode": self.rails_mode}}

    def _lineage_digest(self, job: Dict[str, Any]) -> str:
        """Content-address the lineage (H3/H9).

        Rail-assigned identifiers (escrow/meter ids) are excluded so the
        digest covers the hive's *decisions and content*, which are
        deterministic, rather than counters assigned by external rails.
        Timestamps are excluded by construction (never stored in lineage).
        """
        return _digest(self._normalized_lineage(job["lineage"]))

    @staticmethod
    def _normalized_lineage(lineage: Dict[str, Any]) -> Dict[str, Any]:
        drop = {"escrow_id", "meter_id"}

        def scrub(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: scrub(v) for k, v in sorted(obj.items())
                        if k not in drop}
            if isinstance(obj, list):
                return [scrub(v) for v in obj]
            return obj

        return scrub(lineage)

    async def _audit_job(self, req: Dict[str, Any]) -> Dict[str, Any]:
        job = self.jobs.get(req.get("job_id", ""))
        if job is None:
            return _error("NotFound", "unknown job_id")
        if job["state"] != "COMPLETE":
            return _error("StateError", "audit available after completion",
                          value=job["state"], constraint="state == COMPLETE")
        return {"status": "ok", "data": {
            "job_id": job["job_id"], "lineage": job["lineage"],
            "audit_sha256": job["audit_sha256"]}}

    async def _verify_audit(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """H9: recompute the digest from the presented lineage - never trust
        the embedded hash (recompute-in-verify; taxcredit-engine lesson)."""
        audit = req.get("audit")
        if not isinstance(audit, dict) or "lineage" not in audit \
                or "audit_sha256" not in audit:
            raise ValidationError("audit must contain lineage + audit_sha256",
                                  "audit", type(audit).__name__,
                                  "{lineage, audit_sha256}")
        recomputed = _digest(self._normalized_lineage(audit["lineage"]))
        valid = recomputed == audit["audit_sha256"]
        job = self.jobs.get(audit.get("job_id", ""))
        known = job is not None and job.get("audit_sha256") == recomputed
        return {"status": "ok", "data": {
            "valid": valid, "recomputed_sha256": recomputed,
            "matches_known_job": known}}

    async def _list_solvers(self, req: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok", "data": {"solvers": [
            {"solver_id": sid, "kind": p["kind"],
             "price_minor": p["price_minor"],
             "capabilities": p["capabilities"]}
            for sid, p in sorted(self.solvers.items())]}}

    # -- fleet-standard surface ----------------------------------------------

    async def health(self) -> Dict[str, Any]:
        provider_probe = getattr(self, "_solver_provider_ready", None)
        provider_ready = (
            bool(provider_probe()) if callable(provider_probe) else True)
        wired_ready = (
            self.rails_mode == "standalone"
            or (len(self.solvers) >= 2
                and all(self._rails.get(name) is not None for name in (
                    "trust", "covenant", "escrow", "metering", "ledger"))))
        return {"status": ("ok" if provider_ready and wired_ready
                           else "degraded"),
                "agent": self.config.name,
                "version": self.config.version,
                "checks": {"rails_mode": self.rails_mode,
                           "solvers_registered": len(self.solvers),
                           "solver_provider_ready": provider_ready,
                           "wired_dependencies_ready": wired_ready,
                           "jobs": len(self.jobs)}}

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.config.name, "version": self.config.version,
            "description": ("Deterministic nested hive-mind orchestration: "
                            "hire N solvers through covenant/escrow/meter, "
                            "adversarial cross-review, honest synthesis, "
                            "carbon-accounted, content-addressed audit."),
            "capabilities": ["hive-orchestration", "nested-composition",
                             "adversarial-review", "a2a-settlement",
                             "bits-per-joule-telemetry"],
            "actions": ["open_job", "run_job", "solve", "job_status",
                        "audit_job", "verify_audit", "list_solvers"],
            "invariants": ["H1-budget-conservation", "H2-deny-by-default",
                           "H3-determinism", "H4-reviewer-not-author",
                           "H5-settlement-closure", "H6-emergence-honesty",
                           "H7-thermodynamic-accounting", "H8-fail-safe",
                           "H9-recompute-in-verify", "H10-standalone-honesty"],
            "rails_mode": self.rails_mode,
            "pricing": {"model": "premium per solve; sub-hires settle "
                                 "through escrow at solver list price",
                        "free_per_day": 3, "usd_per_solve": 5.00,
                        "free_scope": "per caller, UTC day"},
            "outputs": {"status": "str (ok|error)", "data": "dict"},
        }


def build(config: Optional[AgentConfig] = None,
          solvers: Optional[Dict[str, Dict[str, Any]]] = None,
          rails: Optional[Dict[str, Any]] = None) -> HiveOrchestratorCore:
    return HiveOrchestratorCore(config=config, solvers=solvers, rails=rails)
