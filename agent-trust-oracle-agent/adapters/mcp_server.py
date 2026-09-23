"""
MCP adapter for agent-trust-oracle-agent. One MCP tool per core action.
Thin wrapper — all logic lives in src/core.py.
Run: python adapters/mcp_server.py            (smoke: describe + health)
     python adapters/mcp_server.py --serve    (stdio MCP server; needs `mcp`)
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from mcp.server.fastmcp import FastMCP
    HAS_MCP = True
except ImportError:  # pragma: no cover
    HAS_MCP = False

    class FastMCP:  # stdlib shim so smoke tests run anywhere
        def __init__(self, name, **kw): self.name, self.tools = name, {}
        def tool(self, *a, **k):
            def deco(fn): self.tools[fn.__name__] = fn; return fn
            return deco
        def run(self): raise RuntimeError("`mcp` SDK not installed - pip install mcp")

from src.core import build

def _mk_mcp(name, description=""):
    """FastMCP compat across SDK versions (description -> instructions -> bare)."""
    try:
        return FastMCP(name, instructions=description)
    except TypeError:
        try:
            return FastMCP(name, description=description)
        except TypeError:
            return FastMCP(name)

mcp = _mk_mcp("agent-trust-oracle-agent",
              description="Decay-weighted agent reputation + tamper-evident trust "
                          "attestations — should you delegate authority or money "
                          "to this agent?")
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


@mcp.tool()
async def record_outcome(agent_id: str, kind: str, weight: float = 1.0,
                   counterparty: str = "", note: str = "") -> str:
    """Record an interaction outcome for an agent. kind: success | delivered |
    dispute_won | failure | undelivered | dispute_lost | timeout |
    security_incident (security incidents carry a 3x penalty)."""
    return await _run({"action": "record_outcome", "agent_id": agent_id, "kind": kind,
                 "weight": weight, "counterparty": counterparty, "note": note})


@mcp.tool()
async def score_agent(agent_id: str) -> str:
    """Get an agent's decay-weighted trust score in [0,1] and tier. Unknown
    agents get a neutral 0.5 prior — no blind trust, no unfair zero."""
    return await _run({"action": "score", "agent_id": agent_id})


@mcp.tool()
async def attest(agent_id: str, claim: str = "reputation-snapshot") -> str:
    """Issue a tamper-evident (hash-chained) trust attestation for an agent."""
    return await _run({"action": "attest", "agent_id": agent_id, "claim": claim})


@mcp.tool()
async def verify_attestation(agent_id: str, attestation_id: str) -> str:
    """Verify a previously issued attestation by recomputing its hash."""
    return await _run({"action": "verify_attestation", "agent_id": agent_id,
                 "attestation_id": attestation_id})


@mcp.tool()
async def history(agent_id: str) -> str:
    """Full outcome history + attestation count + current score for an agent."""
    return await _run({"action": "history", "agent_id": agent_id})


@mcp.tool()
async def describe_agent() -> str:
    """Fleet-standard self-description."""
    return json.dumps(agent.describe(), default=str, indent=2)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), default=str, indent=2))
        print(json.dumps(asyncio.run(agent.health()), default=str, indent=2))
