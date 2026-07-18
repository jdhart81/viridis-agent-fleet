"""
neurogenesis-agent — Core business logic.

DEVELOPMENTAL AGENTS for the agent economy: create an agent from a digital
genome (initial cognitive nodes + fitness metrics + growth rules + safety
axioms), then EVOLVE it with evaluation results as selective pressure —
edges strengthen on success, weaken on failure, nodes grow when tasks
repeat and prune when weights decay, and every developmental event lands
in an append-only ledger. The verdigraph-brain mount certifies what an
agent IS; this mount grows what an agent BECOMES.

Vendored engine: src/vg/* (verdigraph-neurogenesis, stdlib-only,
DOI 10.5281/zenodo.20400274). Canonical in its own repo.

Fleet-standard interface: async process(), async health(), sync describe().
process() dispatches on "action" and NEVER raises on bad input.

--- INVARIANTS (spec-invariance contract) ---
NG1 Every mutation goes through DevelopmentalAgent.process_evaluation —
    the engine's safety axioms (protected nodes, no hidden nodes,
    logged growth/pruning) are never bypassed by this wrapper.
NG2 create requires a VALID genome (agent_name, purpose, >=1 unique
    initial node, >=1 fitness metric); invalid genomes return a
    structured error naming the failed constraint.
NG3 The developmental ledger is append-only and returned verbatim —
    never edited, filtered, or summarized destructively by this wrapper.
NG4 Agent state is held on this core and persists via the fleet
    StateStore (survives restarts); save/load are also exposed as
    explicit state documents for portability.
NG5 process() never raises on bad input — structured error envelopes
    always (fleet C1 contract). Evaluation scores outside [0,1] are a
    ValidationError, not a crash.
NG6 Evaluations are bounded and deterministic: the same agent state +
    the same evaluation sequence always produce the same graph and
    ledger (no randomness in the serving path).
NG7 WU WEI COMPUTE ROUTING (added 2026-07-18): route_task chooses the
    cheapest RELIABLE execution profile for a task — and the quality
    floor is a HARD contract inherited from the engine: a profile below
    the task's min_quality is ineligible regardless of cost; compute
    savings never silently regress quality. Routing is deterministic
    given the registered profiles + task; profiles are caller-registered
    (never invented); every decision is logged with its reason and
    surfaced by compute_efficiency_report together with the
    Landauer-grounded energy context (thermo.py) — honest physics, the
    dI/dt <= P*D/(kB*T*ln2) thesis as a routable service.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from dataclasses import fields as dataclass_fields

from src.vg.agent import DevelopmentalAgent
from src.vg.compute import ComputeOptimizer, ComputeProfile, TaskProfile
from src.vg.evaluation import EvaluationResult
from src.vg.genome import AgentGenome
from src.vg.thermo import landauer_energy_per_bit

logger = logging.getLogger(__name__)

MAX_AGENTS = 200          # bounded state (PG18 table-bound idiom)


# --------------------------------------------------------------------------- #
# Fleet-standard base
# --------------------------------------------------------------------------- #
@dataclass
class AgentConfig:
    name: str
    version: str = "0.1.0"
    debug: bool = False


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentCore:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.logger = logging.getLogger(config.name)

    async def health(self) -> dict:
        return {"status": "ok", "agent": self.config.name,
                "version": self.config.version, "timestamp": _utcnow(),
                "checks": {}}

    def _err(self, message: str, *, error_type: str = "Error",
             field: str = "", value: Any = None, constraint: str = "") -> dict:
        return {"status": "error", "error_type": error_type, "field": field,
                "value": value, "constraint": constraint, "message": message,
                "timestamp": _utcnow()}

    def _ok(self, data: Any = None) -> dict:
        return {"status": "ok", "data": data, "error": None,
                "timestamp": _utcnow()}


class ValidationError(ValueError):
    def __init__(self, message, field="", value=None, constraint=""):
        super().__init__(message)
        self.field, self.value, self.constraint = field, value, constraint


# --------------------------------------------------------------------------- #
class NeurogenesisCore(AgentCore):
    """Genome -> developmental agent -> evaluation-driven evolution."""

    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config or AgentConfig(name="neurogenesis-agent"))
        # NG4: plain dict of agent_id -> state dict (StateStore-friendly:
        # pure-python, pickles cleanly). Live DevelopmentalAgent objects are
        # rebuilt lazily from state so restores are always consistent.
        self._states: Dict[str, dict] = {}
        self._seq = 0
        self._evaluations = 0
        # NG7: caller-registered compute profiles (plain dicts — StateStore/
        # PS8-safe) + append-only routing decision log.
        self._profiles: Dict[str, dict] = {}
        self._route_decisions: list = []

    # -- live-object cache (never persisted; NG4 truth is _states) --------- #
    def _live(self, agent_id: str) -> DevelopmentalAgent:
        state = self._states.get(agent_id)
        if state is None:
            raise ValidationError("unknown agent_id", field="agent_id",
                                  value=agent_id, constraint="must exist "
                                  "(create_agent first; list_agents shows all)")
        return DevelopmentalAgent.from_state_dict(state)

    def _commit(self, agent_id: str, agent: DevelopmentalAgent) -> None:
        self._states[agent_id] = agent.to_dict()

    # ---------------------------------------------------------------------- #
    async def process(self, input_data: Any) -> dict:
        try:
            if not isinstance(input_data, dict):                    # NG5/C1
                return self._err("input_data must be a dict",
                                 error_type="ValidationError",
                                 field="input_data",
                                 value=type(input_data).__name__,
                                 constraint="input_data must be a dict")
            action = input_data.get("action", "describe")
            handler = {"create_agent": self._create,
                       "list_agents": self._list,
                       "get_agent": self._get,
                       "submit_evaluation": self._evaluate,
                       "best_next_steps": self._best_next,
                       "get_ledger": self._ledger,
                       "export_state": self._export,
                       "import_state": self._import,
                       "delete_agent": self._delete,
                       "register_compute_profile": self._register_profile,
                       "route_task": self._route_task,
                       "compute_efficiency_report": self._efficiency_report,
                       "describe": lambda _d: self._ok(self.describe()),
                       }.get(action)
            if handler is None:
                return self._err(
                    f"unknown action '{action}'",
                    error_type="ValidationError", field="action", value=action,
                    constraint="one of: create_agent, list_agents, get_agent, "
                               "submit_evaluation, best_next_steps, "
                               "get_ledger, export_state, import_state, "
                               "delete_agent, register_compute_profile, "
                               "route_task, compute_efficiency_report, "
                               "describe")
            return handler(input_data)
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError",
                             field=e.field, value=e.value,
                             constraint=e.constraint)
        except ValueError as e:            # engine validation (genome/score)
            return self._err(str(e), error_type="ValidationError")
        except Exception as e:  # noqa: BLE001  (NG5)
            self.logger.exception("neurogenesis process failed")
            return self._err(f"internal error: {e}", error_type="RuntimeError")

    # ---------------------------------------------------------------------- #
    def _summary(self, agent_id: str, agent: DevelopmentalAgent) -> dict:
        return {"agent_id": agent_id,
                "agent_name": agent.genome.agent_name,
                "purpose": agent.genome.purpose,
                "nodes": len(agent.graph.nodes),
                "edges": len(agent.graph.edges),
                "ledger_events": len(agent.ledger.to_list())}

    def _create(self, data: dict) -> dict:
        genome_doc = data.get("genome")
        if not isinstance(genome_doc, dict):                        # NG2
            raise ValidationError(
                "genome is required: an object with agent_name, purpose, "
                "initial_nodes (unique, >=1), fitness_metrics (>=1), and "
                "optional growth_rules / safety_axioms",
                field="genome", constraint="object")
        if len(self._states) >= MAX_AGENTS:
            return self._err("agent table is full",
                             error_type="capacity",
                             field="agents", value=len(self._states),
                             constraint=f"max {MAX_AGENTS}; delete_agent "
                                        "frees a slot")
        genome = AgentGenome.from_dict(genome_doc)
        genome.validate()                                            # NG2
        agent = DevelopmentalAgent(genome)
        self._seq += 1
        agent_id = f"ng_{self._seq:06d}"
        self._commit(agent_id, agent)
        return self._ok({**self._summary(agent_id, agent),
                         "next_steps": {
                             "evolve": ("call submit_evaluation with task "
                                        "outcomes (scores in [0,1]) — "
                                        "success strengthens used edges, "
                                        "failure weakens them"),
                             "certify": ("compile the genome via "
                                         "/verdigraph/mcp build for a "
                                         "content-addressed brain_id")}})

    def _list(self, _data: dict) -> dict:
        return self._ok({"count": len(self._states),
                         "agents": [
                             self._summary(aid, self._live(aid))
                             for aid in sorted(self._states)]})

    def _get(self, data: dict) -> dict:
        agent_id = str(data.get("agent_id") or "")
        agent = self._live(agent_id)
        doc = agent.to_dict()
        return self._ok({**self._summary(agent_id, agent),
                         "graph": doc.get("graph"),
                         "genome": doc.get("genome")})

    def _evaluate(self, data: dict) -> dict:
        agent_id = str(data.get("agent_id") or "")
        agent = self._live(agent_id)
        ev = data.get("evaluation")
        if not isinstance(ev, dict):
            raise ValidationError(
                "evaluation is required: {task_id, task_type, "
                "success_score in [0,1], optional accuracy/"
                "user_satisfaction/cost_efficiency/safety_score/notes/"
                "used_nodes/used_edges}",
                field="evaluation", constraint="object")
        allowed = {"task_id", "task_type", "success_score", "accuracy",
                   "user_satisfaction", "cost_efficiency", "safety_score",
                   "notes", "used_nodes", "used_edges"}
        kwargs = {k: v for k, v in ev.items() if k in allowed}
        if "used_edges" in kwargs and isinstance(kwargs["used_edges"], list):
            kwargs["used_edges"] = [tuple(e) for e in kwargs["used_edges"]
                                    if isinstance(e, (list, tuple))
                                    and len(e) == 2]
        result = EvaluationResult(**kwargs)     # engine validates [0,1] (NG5)
        before = len(agent.ledger.to_list())
        agent.process_evaluation(result)                             # NG1
        self._commit(agent_id, agent)
        self._evaluations += 1
        events = agent.ledger.to_list()
        return self._ok({**self._summary(agent_id, agent),
                         "evaluation_accepted": True,
                         "is_success": result.is_success,
                         "is_failure": result.is_failure,
                         "new_ledger_events": events[before:],       # NG3
                         })

    def _best_next(self, data: dict) -> dict:
        agent_id = str(data.get("agent_id") or "")
        agent = self._live(agent_id)
        from_node = str(data.get("from_node") or "")
        if not from_node:
            raise ValidationError(
                "from_node is required (a node id from get_agent's graph)",
                field="from_node", constraint="non-empty str")
        limit = max(1, min(10, int(data.get("limit") or 3)))
        steps = agent.best_next_steps(from_node, limit=limit)
        return self._ok({"agent_id": agent_id, "from_node": from_node,
                         "best_next_steps": steps})

    def _ledger(self, data: dict) -> dict:
        agent_id = str(data.get("agent_id") or "")
        agent = self._live(agent_id)
        events = agent.ledger.to_list()                              # NG3
        limit = max(1, min(500, int(data.get("limit") or 100)))
        return self._ok({"agent_id": agent_id,
                         "total_events": len(events),
                         "events": events[-limit:]})

    def _export(self, data: dict) -> dict:
        agent_id = str(data.get("agent_id") or "")
        self._live(agent_id)                       # existence check
        return self._ok({"agent_id": agent_id,
                         "state": self._states[agent_id],
                         "note": "portable state document; import_state "
                                 "recreates the agent elsewhere (NG4)"})

    def _import(self, data: dict) -> dict:
        state = data.get("state")
        if not isinstance(state, dict):
            raise ValidationError("state is required (an export_state "
                                  "document)", field="state",
                                  constraint="object")
        agent = DevelopmentalAgent.from_state_dict(state)   # validates shape
        if len(self._states) >= MAX_AGENTS:
            return self._err("agent table is full", error_type="capacity",
                             field="agents", value=len(self._states),
                             constraint=f"max {MAX_AGENTS}")
        self._seq += 1
        agent_id = f"ng_{self._seq:06d}"
        self._commit(agent_id, agent)
        return self._ok(self._summary(agent_id, agent))

    def _delete(self, data: dict) -> dict:
        agent_id = str(data.get("agent_id") or "")
        if agent_id not in self._states:
            raise ValidationError("unknown agent_id", field="agent_id",
                                  value=agent_id, constraint="must exist")
        self._states.pop(agent_id)
        return self._ok({"agent_id": agent_id, "deleted": True})

    # ---------------- Wu Wei compute routing (NG7) --------------------- #
    @staticmethod
    def _filter_fields(cls, doc: dict) -> dict:
        allowed = {f.name for f in dataclass_fields(cls)}
        return {k: v for k, v in doc.items() if k in allowed}

    def _register_profile(self, data: dict) -> dict:
        doc = data.get("profile")
        if not isinstance(doc, dict) or not str(doc.get("id") or "").strip():
            raise ValidationError(
                "profile is required: {id, kind?, quality_score [0,1], "
                "cost_per_1k_input_tokens?, cost_per_1k_output_tokens?, "
                "latency_ms?, gpu_memory_gb?, max_context_tokens?, local?}",
                field="profile", constraint="object with non-empty id")
        profile = ComputeProfile(**self._filter_fields(ComputeProfile, doc))
        if len(self._profiles) >= 200 and profile.id not in self._profiles:
            return self._err("profile table is full", error_type="capacity",
                             field="profiles", value=len(self._profiles),
                             constraint="max 200")
        self._profiles[profile.id] = doc                     # caller-supplied
        return self._ok({"profile_id": profile.id,
                         "registered_profiles": len(self._profiles),
                         "next_steps": {"route": (
                             "call route_task with {task: {id, task_type, "
                             "expected_input_tokens, expected_output_tokens, "
                             "min_quality, risk?, difficulty?, "
                             "requires_local?}} — the cheapest profile "
                             "meeting your quality floor wins (NG7)")}})

    def _route_task(self, data: dict) -> dict:
        doc = data.get("task")
        if not isinstance(doc, dict) or not str(doc.get("id") or "").strip():
            raise ValidationError(
                "task is required: {id, task_type, expected_input_tokens, "
                "expected_output_tokens, min_quality [0,1], risk?, "
                "difficulty?, requires_local?}",
                field="task", constraint="object with non-empty id")
        if not self._profiles:
            raise ValidationError(
                "no compute profiles registered — call "
                "register_compute_profile first (profiles are yours, "
                "never invented: NG7)",
                field="profiles", constraint=">= 1 registered")
        task = TaskProfile(**self._filter_fields(TaskProfile, doc))
        optimizer = ComputeOptimizer(
            ComputeProfile(**self._filter_fields(ComputeProfile, p))
            for p in self._profiles.values())
        try:
            decision = optimizer.choose_profile(task)        # NG7 hard floor
        except ValueError as exc:
            return self._err(str(exc), error_type="no_eligible_profile",
                             field="task", value=task.id,
                             constraint="register a profile meeting the "
                                        "task's min_quality/context/local "
                                        "constraints, or relax them")
        record = {"task_id": task.id, "task_type": task.task_type,
                  "profile_id": decision.profile_id,
                  "score": decision.score,
                  "estimated_cost": decision.estimated_cost,
                  "estimated_latency_ms": decision.estimated_latency_ms,
                  "reason": decision.reason, "at": _utcnow()}
        self._route_decisions.append(record)                 # NG7 log
        if len(self._route_decisions) > 1000:
            self._route_decisions = self._route_decisions[-1000:]
        return self._ok({**record,
                         "quality_floor_honored": True,
                         "note": ("cheapest RELIABLE path: profiles below "
                                  "min_quality were ineligible regardless "
                                  "of cost (NG7)")})

    def _efficiency_report(self, data: dict) -> dict:
        limit = max(1, min(200, int(data.get("limit") or 50)))
        decisions = self._route_decisions[-limit:]
        total_cost = sum(d["estimated_cost"] for d in decisions)
        return self._ok({
            "decisions_total": len(self._route_decisions),
            "window": len(decisions),
            "total_estimated_cost": round(total_cost, 6),
            "by_profile": {
                pid: sum(1 for d in decisions if d["profile_id"] == pid)
                for pid in {d["profile_id"] for d in decisions}},
            "decisions": decisions,
            "physics": {
                "landauer_energy_per_bit_joules_at_300K":
                    landauer_energy_per_bit(300.0),
                "note": ("Landauer's floor is the physical yardstick for "
                         "compute efficiency (dI/dt <= P*D/(kB*T*ln2)); "
                         "all practical routing sits far above it — the "
                         "point is choosing the path that wastes least")},
        })

    # ---------------------------------------------------------------------- #
    async def health(self) -> dict:
        h = await super().health()
        h["checks"] = {"agents": len(self._states),
                       "evaluations": self._evaluations,
                       "compute_profiles": len(self._profiles),
                       "route_decisions": len(self._route_decisions)}
        return h

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": ("Developmental agents from digital genomes: "
                            "evaluation-driven growth/pruning over a "
                            "cognitive graph with safety axioms and an "
                            "append-only developmental ledger."),
            "capabilities": ["create_agent", "list_agents", "get_agent",
                             "submit_evaluation", "best_next_steps",
                             "get_ledger", "export_state", "import_state",
                             "delete_agent", "register_compute_profile",
                             "route_task", "compute_efficiency_report",
                             "describe"],
            "inputs": {"action": "str", "genome": "dict?", "agent_id": "str?",
                       "evaluation": "dict?", "from_node": "str?",
                       "state": "dict?", "limit": "int?"},
            "outputs": {"agent_id": "str", "nodes": "int", "edges": "int",
                        "ledger_events": "int"},
        }


def build(config: Optional[AgentConfig] = None) -> NeurogenesisCore:
    return NeurogenesisCore(config)
