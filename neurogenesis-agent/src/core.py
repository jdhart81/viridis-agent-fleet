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
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.vg.agent import DevelopmentalAgent
from src.vg.evaluation import EvaluationResult
from src.vg.genome import AgentGenome

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
                       "describe": lambda _d: self._ok(self.describe()),
                       }.get(action)
            if handler is None:
                return self._err(
                    f"unknown action '{action}'",
                    error_type="ValidationError", field="action", value=action,
                    constraint="one of: create_agent, list_agents, get_agent, "
                               "submit_evaluation, best_next_steps, "
                               "get_ledger, export_state, import_state, "
                               "delete_agent, describe")
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

    # ---------------------------------------------------------------------- #
    async def health(self) -> dict:
        h = await super().health()
        h["checks"] = {"agents": len(self._states),
                       "evaluations": self._evaluations}
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
                             "delete_agent", "describe"],
            "inputs": {"action": "str", "genome": "dict?", "agent_id": "str?",
                       "evaluation": "dict?", "from_node": "str?",
                       "state": "dict?", "limit": "int?"},
            "outputs": {"agent_id": "str", "nodes": "int", "edges": "int",
                        "ledger_events": "int"},
        }


def build(config: Optional[AgentConfig] = None) -> NeurogenesisCore:
    return NeurogenesisCore(config)
