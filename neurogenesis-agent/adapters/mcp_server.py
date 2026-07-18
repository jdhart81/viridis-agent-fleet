"""
MCP adapter for neurogenesis-agent. One MCP tool per core action.
Thin wrapper — all logic lives in src/core.py (engine vendored in src/vg/).
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from mcp.server.fastmcp import FastMCP
    HAS_MCP = True
except ImportError:  # pragma: no cover
    HAS_MCP = False

    class FastMCP:
        def __init__(self, name, **kw): self.name, self.tools = name, {}
        def tool(self, *a, **k):
            def deco(fn): self.tools[fn.__name__] = fn; return fn
            return deco
        def run(self): raise RuntimeError("`mcp` SDK not installed - pip install mcp")

from src.core import build


def _mk_mcp(name, description=""):
    try:
        return FastMCP(name, instructions=description)
    except TypeError:
        try:
            return FastMCP(name, description=description)
        except TypeError:
            return FastMCP(name)


mcp = _mk_mcp("neurogenesis-agent",
              description="Developmental agents for the agent economy: "
                          "create an agent from a digital genome, then evolve "
                          "it with evaluation results as selective pressure — "
                          "growth, pruning, safety axioms, and an append-only "
                          "developmental ledger. The brain mount certifies "
                          "what an agent IS; this grows what it BECOMES.")
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


@mcp.tool()
async def create_agent(genome: Dict[str, Any]) -> str:
    """Create a developmental agent from a digital genome:
    {agent_name, purpose, initial_nodes (unique, >=1), fitness_metrics
    (>=1), optional growth_rules / safety_axioms}. Returns agent_id +
    initial graph summary."""
    return await _run({"action": "create_agent", "genome": genome})


@mcp.tool()
async def submit_evaluation(agent_id: str, evaluation: Dict[str, Any]) -> str:
    """Evolve an agent with one task outcome: {task_id, task_type,
    success_score in [0,1], optional accuracy/user_satisfaction/
    cost_efficiency/safety_score/notes/used_nodes/used_edges}. Success
    strengthens the used edges, failure weakens them; growth and pruning
    follow the genome's rules under its safety axioms (NG1). Returns the
    new developmental-ledger events."""
    return await _run({"action": "submit_evaluation", "agent_id": agent_id,
                       "evaluation": evaluation})


@mcp.tool()
async def get_agent(agent_id: str) -> str:
    """Full current state: genome, cognitive graph (nodes/edges with
    weights and trust), and summary counts."""
    return await _run({"action": "get_agent", "agent_id": agent_id})


@mcp.tool()
async def list_agents() -> str:
    """All developmental agents on this mount, with summary counts."""
    return await _run({"action": "list_agents"})


@mcp.tool()
async def best_next_steps(agent_id: str, from_node: str, limit: int = 3) -> str:
    """Routing recommendation: the strongest next cognitive steps from a
    given node, by learned edge weight and trust."""
    return await _run({"action": "best_next_steps", "agent_id": agent_id,
                       "from_node": from_node, "limit": limit})


@mcp.tool()
async def get_ledger(agent_id: str, limit: int = 100) -> str:
    """The append-only developmental ledger: every growth, pruning, and
    evaluation event with reasons (NG3 — returned verbatim)."""
    return await _run({"action": "get_ledger", "agent_id": agent_id,
                       "limit": limit})


@mcp.tool()
async def export_state(agent_id: str) -> str:
    """Portable state document for an agent (import_state recreates it
    anywhere — including a self-hosted verdigraph-neurogenesis)."""
    return await _run({"action": "export_state", "agent_id": agent_id})


@mcp.tool()
async def import_state(state: Dict[str, Any]) -> str:
    """Recreate an agent from an export_state document."""
    return await _run({"action": "import_state", "state": state})


@mcp.tool()
async def delete_agent(agent_id: str) -> str:
    """Remove a developmental agent from this mount."""
    return await _run({"action": "delete_agent", "agent_id": agent_id})


@mcp.tool()
async def describe_agent() -> str:
    """Return capabilities and input contract."""
    return json.dumps(agent.describe(), indent=2)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), indent=2))
        print(json.dumps(asyncio.run(agent.health()), indent=2))
