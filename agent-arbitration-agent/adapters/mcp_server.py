"""
MCP adapter for agent-arbitration-agent. One MCP tool per core action.
Thin wrapper — all logic lives in src/core.py.
Run: python adapters/mcp_server.py            (smoke: describe + health)
     python adapters/mcp_server.py --serve    (stdio MCP server; needs `mcp`)
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

mcp = _mk_mcp("agent-arbitration-agent",
              description="Deterministic, machine-verifiable dispute resolution "
                          "for A2A escrows.")
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
async def file_case(escrow_id: str, claimant: str, respondent: str, amount_minor: int) -> str:
    """File a dispute over an escrow. Opens the evidence window. Parties must
    be distinct; amount is in minor currency units (cents)."""
    return await _run({"action": "file_case", "escrow_id": escrow_id, "claimant": claimant,
                 "respondent": respondent, "amount_minor": amount_minor})


@mcp.tool(annotations=_WRITE)
async def submit_evidence(case_id: str, party: str, kind: str, content: str = "") -> str:
    """Submit evidence while the case is open. kind: delivery_proof (weight 3),
    log (2), or statement (1). Only the named parties may submit."""
    return await _run({"action": "submit_evidence", "case_id": case_id, "party": party,
                 "kind": kind, "content": content})


@mcp.tool(annotations=_WRITE)
async def set_trust_scores(case_id: str, scores: Dict[str, float]) -> str:
    """Attach trust-oracle reputation scores (party -> [0,1]) as ruling inputs."""
    return await _run({"action": "set_trust_scores", "case_id": case_id, "scores": scores})


@mcp.tool(annotations=_WRITE)
async def rule(case_id: str) -> str:
    """Issue the deterministic ruling: allocates 100% of the disputed amount
    from evidence weights + trust scores, and emits an escrow instruction
    (release/refund). Exactly-once — re-ruling returns the existing ruling."""
    return await _run({"action": "rule", "case_id": case_id})


@mcp.tool(annotations=_READ)
async def verify_ruling(case_id: str) -> str:
    """Recompute the ruling from its cited evidence + trust inputs and check
    it matches the stored allocation (machine-checkable justice)."""
    return await _run({"action": "verify_ruling", "case_id": case_id})


@mcp.tool(annotations=_READ)
async def get_case(case_id: str) -> str:
    """Fetch the full case record, including any ruling."""
    return await _run({"action": "get_case", "case_id": case_id})


@mcp.tool(annotations=_READ)
async def list_cases(state: Optional[str] = None) -> str:
    """List cases, optionally filtered by state (FILED|EVIDENCE_OPEN|RULED)."""
    return await _run({"action": "list_cases", "state": state})


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
