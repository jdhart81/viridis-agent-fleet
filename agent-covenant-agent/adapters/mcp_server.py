"""
MCP adapter for agent-covenant-agent. One MCP tool per core action.
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

mcp = _mk_mcp("agent-covenant-agent",
              description="Machine-checkable authority leases for agents: scoped, "
                          "budgeted, expiring, revocable, audited. Deny-by-default.")
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


try:  # MCP tool annotations: let hosts and registries see which tools are safe reads
    from mcp.types import ToolAnnotations as _ToolAnnotations
except ImportError:  # pragma: no cover - stdlib shim keeps smoke tests runnable
    def _ToolAnnotations(**kw):
        return kw
_READ = _ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                         idempotentHint=True, openWorldHint=False)
_WRITE = _ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                          idempotentHint=False, openWorldHint=False)
_DESTRUCTIVE = _ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                idempotentHint=False, openWorldHint=False)


@mcp.tool(annotations=_WRITE)
async def grant_covenant(principal: str, agent_id: str, scopes: List[str],
                   budget_minor: int, expires_at: str) -> str:
    """Grant an agent a covenant: an explicit lease of authority. scopes support
    wildcards ('payments.*', '*'); budget_minor is the total spend ceiling in
    minor units; expires_at is ISO-8601. Returns the covenant_id."""
    return await _run({"action": "grant", "principal": principal, "agent_id": agent_id,
                 "scopes": scopes, "budget_minor": budget_minor,
                 "expires_at": expires_at})


@mcp.tool(annotations=_WRITE)
async def check_act(covenant_id: str, act_id: str, scope: str, amount_minor: int = 0) -> str:
    """Check (and if allowed, record) a proposed act against a covenant.
    Deny-by-default. Idempotent on act_id — retries never double-consume
    budget. Every check lands on the audit chain."""
    return await _run({"action": "check_act", "covenant_id": covenant_id,
                 "act_id": act_id, "scope": scope, "amount_minor": amount_minor})


@mcp.tool(annotations=_DESTRUCTIVE)
async def revoke_covenant(covenant_id: str, reason: str = "") -> str:
    """Revoke a covenant immediately and terminally. All subsequent checks deny."""
    return await _run({"action": "revoke", "covenant_id": covenant_id, "reason": reason})


@mcp.tool(annotations=_READ)
async def covenant_status(covenant_id: str) -> str:
    """Current state, consumed/remaining budget, and check count."""
    return await _run({"action": "status", "covenant_id": covenant_id})


@mcp.tool(annotations=_READ)
async def verify_audit(covenant_id: str) -> str:
    """Verify the tamper-evident audit chain of allowed/denied acts."""
    return await _run({"action": "verify_audit", "covenant_id": covenant_id})


@mcp.tool(annotations=_READ)
async def list_covenants(state: Optional[str] = None, agent_id: Optional[str] = None) -> str:
    """List covenants, optionally filtered by state (ACTIVE|REVOKED|EXPIRED)
    and/or the bound agent."""
    return await _run({"action": "list", "state": state, "agent_id": agent_id})


@mcp.tool(annotations=_READ)
async def describe_agent() -> str:
    """Describe this agent: name, version, purpose, every action it supports
    and the inputs each one takes. Read-only and free; call it first to learn
    how to use this server."""
    return json.dumps(agent.describe(), default=str, indent=2)


try:  # report {"status": "error"} results to MCP clients as tool errors (isError)
    from fleet_utils.mcp_errors import flag_error_results
except ImportError:  # loaded without the fleet root on sys.path, as the gateway does
    import sys as _sys
    from pathlib import Path as _Path
    _fleet_root = _Path(__file__).resolve().parents[2]
    if (_fleet_root / "fleet_utils").is_dir() and str(_fleet_root) not in _sys.path:
        _sys.path.append(str(_fleet_root))
    try:
        from fleet_utils.mcp_errors import flag_error_results
    except ImportError:  # pragma: no cover - adapter copied without fleet_utils
        def flag_error_results(server):
            return 0
flag_error_results(mcp)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), default=str, indent=2))
        print(json.dumps(asyncio.run(agent.health()), default=str, indent=2))
