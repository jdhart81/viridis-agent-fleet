"""
MCP adapter for agent-provenance-agent. One MCP tool per core action.
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

mcp = _mk_mcp("agent-provenance-agent",
              description="Genesis certificates, lineage, and cascading recalls: "
                          "birth certificates + bloodlines for the agent economy.")
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


@mcp.tool()
async def register_genesis(agent_id: str, parent_id: Optional[str] = None,
                     artifact_hash: str = "") -> str:
    """Register an agent's birth. Issues a content-addressed genesis
    certificate with a strictly monotone index (epoch 0 = the founding
    cohort). parent_id records lineage; children of recalled/quarantined
    parents are quarantined at birth. Idempotent — an agent is born once."""
    return await _run({"action": "register_genesis", "agent_id": agent_id,
                 "parent_id": parent_id, "artifact_hash": artifact_hash})


@mcp.tool()
async def get_certificate(agent_id: str) -> str:
    """Fetch an agent's genesis certificate + recall/quarantine status."""
    return await _run({"action": "get_certificate", "agent_id": agent_id})


@mcp.tool()
async def verify_certificate(certificate: Dict[str, Any]) -> str:
    """Verify a certificate: recompute its content hash and check the ledger."""
    return await _run({"action": "verify_certificate", "certificate": certificate})


@mcp.tool()
async def lineage(agent_id: str) -> str:
    """Full ancestry and descendants of an agent, plus its generation number."""
    return await _run({"action": "lineage", "agent_id": agent_id})


@mcp.tool()
async def recall(agent_id: str, reason: str = "") -> str:
    """Recall an agent: flags it and quarantines every transitive descendant.
    Reports exactly which agents were quarantined."""
    return await _run({"action": "recall", "agent_id": agent_id, "reason": reason})


@mcp.tool()
async def list_records(epoch: Optional[int] = None) -> str:
    """List genesis records, optionally by epoch (0 = founding cohort)."""
    return await _run({"action": "list", "epoch": epoch})


@mcp.tool()
async def register_artifact(artifact_id: str, artifact_hash: str,
                            producer_agent_id: str,
                            parent_hashes: Optional[List[str]] = None,
                            relation: str = "derived_from",
                            metadata_digest: str = "") -> str:
    """Register a content-addressed artifact in a separate provenance DAG.
    Parent hashes may be registered artifacts or external content roots.
    Idempotent on artifact_id; does not consume a genesis index."""
    return await _run({"action": "register_artifact",
                       "artifact_id": artifact_id,
                       "artifact_hash": artifact_hash,
                       "producer_agent_id": producer_agent_id,
                       "parent_hashes": parent_hashes or [],
                       "relation": relation,
                       "metadata_digest": metadata_digest})


@mcp.tool()
async def get_artifact(artifact_id: str) -> str:
    """Fetch one registered artifact by artifact_id."""
    return await _run({"action": "get_artifact", "artifact_id": artifact_id})


@mcp.tool()
async def verify_artifact(artifact: Dict[str, Any]) -> str:
    """Recompute an artifact record hash and verify it against the DAG ledger."""
    return await _run({"action": "verify_artifact", "artifact": artifact})


@mcp.tool()
async def list_artifacts(producer_agent_id: Optional[str] = None) -> str:
    """List artifacts, optionally filtered by producer agent."""
    return await _run({"action": "list_artifacts",
                       "producer_agent_id": producer_agent_id})


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
