"""
MCP adapter for agent-notary-agent. One MCP tool per core action.
Thin wrapper — all logic lives in src/core.py.

Privacy note: the notary only ever sees SHA-256 digests — never raw content.
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


mcp = _mk_mcp("agent-notary-agent",
              description="Verifiable delivery for the agent economy: "
                          "commit-reveal content notarization. Sellers commit "
                          "to a deliverable's hash before handover; reveals "
                          "verify exactly; late reveals expire. Turns escrow "
                          "delivery proofs into cryptographic receipts. "
                          "Digests only — never raw content.")
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


@mcp.tool()
async def commit(committer: str, nonce: str, commit_hash: str, deadline: str,
                 context: str = "") -> str:
    """Commit to a deliverable BEFORE handover. commit_hash =
    sha256(salt || sha256(content)) as 64 hex chars; deadline is ISO-8601;
    context links the escrow/job. Idempotent per (committer, nonce)."""
    return await _run({"action": "commit", "committer": committer,
                       "nonce": nonce, "commit_hash": commit_hash,
                       "deadline": deadline, "context": context})


@mcp.tool()
async def reveal(commitment_id: str, salt: str, content_digest: str) -> str:
    """Reveal the committed content's digest + salt after handover. Verifies
    against the commitment (one bit of drift fails); returns a delivery_proof
    string for escrow release. Late reveals expire the commitment."""
    return await _run({"action": "reveal", "commitment_id": commitment_id,
                       "salt": salt, "content_digest": content_digest})


@mcp.tool()
async def verify(commitment_id: str, content_digest: Optional[str] = None) -> str:
    """Independently verify a revealed commitment; optionally check it against
    the digest of content you received."""
    payload: Dict[str, Any] = {"action": "verify", "commitment_id": commitment_id}
    if content_digest:
        payload["content_digest"] = content_digest
    return await _run(payload)


@mcp.tool()
async def commitment_status(commitment_id: str) -> str:
    """Current record for a commitment (pre-reveal, salt/digest stay hidden)."""
    return await _run({"action": "status", "commitment_id": commitment_id})


@mcp.tool()
async def list_commitments(state: Optional[str] = None) -> str:
    """List commitments, optionally filtered by state
    (PENDING|REVEALED|EXPIRED)."""
    return await _run({"action": "list", "state": state})


@mcp.tool()
async def seal_outcome_receipt(output: Dict[str, Any],
                               subject: Optional[Dict[str, Any]] = None,
                               profile: str = "generic",
                               excludes: Optional[List[str]] = None,
                               bindings: Optional[Dict[str, Any]] = None) -> str:
    """Seal an agent output as an Outcome Receipt (ORC v0.1) and register its
    commitment. Returns a portable receipt anyone can verify offline (L1) and
    against this notary's registry (L2). The notary attests integrity and
    time ("notarized"), not correctness. No floats in output; stores only
    digests. Spec: docs/standards/OUTCOME_RECEIPT_v0.1.md"""
    return await _run({"action": "seal_orc", "output": output,
                       "subject": subject or {}, "profile": profile,
                       "excludes": excludes or [], "bindings": bindings or {}})


@mcp.tool()
async def get_orc_commitment(commitment: str) -> str:
    """Registry lookup: is this ORC commitment sealed by this notary? Returns
    digest, issuer, profile, attestation and registered_at, or NotFound."""
    return await _run({"action": "get_commitment", "commitment": commitment})


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
