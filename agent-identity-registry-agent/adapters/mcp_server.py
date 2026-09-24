"""
MCP adapter for agent-identity-registry-agent. One MCP tool per core action.
Thin wrapper — all logic lives in src/core.py.
Run: python adapters/mcp_server.py            (smoke: describe + health)
     python adapters/mcp_server.py --serve    (stdio MCP server; needs `mcp`)
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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

mcp = _mk_mcp("agent-identity-registry-agent",
              description="Verifiable agent identity (content-addressed DIDs), "
                          "capability advertising, and capability-based discovery — "
                          "the passport + directory of the A2A economy.")
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


@mcp.tool()
async def register_agent(agent_id: str, capabilities: List[str], name: str = "",
                   endpoint: str = "", pubkey: str = "",
                   pricing: Optional[Dict[str, Any]] = None,
                   reputation_hint: float = 0.5) -> str:
    """Register (or idempotently update) an agent identity. Returns a
    deterministic content-addressed DID. capabilities is a non-empty list of
    lowercase capability tags other agents can discover you by."""
    return await _run({"action": "register", "agent_id": agent_id, "capabilities": capabilities,
                 "name": name or agent_id, "endpoint": endpoint, "pubkey": pubkey,
                 "pricing": pricing or {}, "reputation_hint": reputation_hint})


@mcp.tool()
async def resolve_agent(agent_id: str = "", did: str = "") -> str:
    """Resolve an identity by agent_id or DID to its full public registration."""
    return await _run({"action": "resolve", "agent_id": agent_id or None, "did": did or None})


@mcp.tool()
async def discover_agents(capabilities: List[str], limit: int = 25) -> str:
    """Find ACTIVE agents matching ALL requested capabilities (AND semantics),
    deterministically ordered by match count then reputation."""
    return await _run({"action": "discover", "capabilities": capabilities, "limit": limit})


@mcp.tool()
async def revoke_agent(agent_id: str = "", did: str = "") -> str:
    """Revoke an identity: it disappears from discovery (terminal) but its
    record is retained for auditability."""
    return await _run({"action": "revoke", "agent_id": agent_id or None, "did": did or None})


@mcp.tool()
async def list_registrations(status: Optional[str] = None) -> str:
    """List registrations, optionally filtered by status (ACTIVE|REVOKED)."""
    return await _run({"action": "list", "status": status})


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
