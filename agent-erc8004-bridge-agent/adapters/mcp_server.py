"""
MCP adapter for agent-erc8004-bridge-agent. One MCP tool per core action.
Thin wrapper — all logic lives in src/core.py.
Run: python adapters/mcp_server.py            (smoke: describe + health)
     python adapters/mcp_server.py --serve    (stdio MCP server; needs `mcp`)

Custody note: this bridge NEVER holds private keys and NEVER writes to any
chain. Exports are unsigned payloads for the caller's own signer.
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
    try:
        return FastMCP(name, instructions=description)
    except TypeError:
        try:
            return FastMCP(name, description=description)
        except TypeError:
            return FastMCP(name)


mcp = _mk_mcp("agent-erc8004-bridge-agent",
              description="The MCP-native bridge to ERC-8004 (on-chain agent "
                          "identity/reputation/validation): resolve registrations, "
                          "score their feedback with decay-weighted math, bind "
                          "on-chain identities to DIDs, export unsigned "
                          "attestations for your own signer. No keys, no chain "
                          "writes — ever.")
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


@mcp.tool()
async def import_registration(chain_id: int, token_id: int, agent_uri: str,
                              owner: str,
                              metadata: Optional[Dict[str, Any]] = None) -> str:
    """Import an ERC-8004 Identity Registry record (chain_id + ERC-721
    token_id + agentURI + owner). Idempotent: re-import updates in place.
    Returns the canonical record with its deterministic bridge DID
    (did:viridis:erc8004:<chain>:<token>)."""
    payload = {"action": "import_registration", "chain_id": chain_id,
               "token_id": token_id, "agent_uri": agent_uri, "owner": owner}
    if metadata is not None:
        payload["metadata"] = metadata
    return await _run(payload)


@mcp.tool()
async def resolve_agent(bridge_did: str = "", chain_id: Optional[int] = None,
                        token_id: Optional[int] = None) -> str:
    """Resolve an imported ERC-8004 registration by bridge DID or by
    (chain_id, token_id)."""
    payload: Dict[str, Any] = {"action": "resolve"}
    if bridge_did:
        payload["bridge_did"] = bridge_did
    if chain_id is not None:
        payload["chain_id"] = chain_id
    if token_id is not None:
        payload["token_id"] = token_id
    return await _run(payload)


@mcp.tool()
async def import_feedback(chain_id: int, token_id: int,
                          feedback: List[Dict[str, Any]]) -> str:
    """Import ERC-8004 Reputation Registry feedback records for an agent.
    Each item: {value: bool|0..1, at: ISO-8601, source?, weight?, feedback_id?}.
    Idempotent per feedback_id."""
    return await _run({"action": "import_feedback", "chain_id": chain_id,
                       "token_id": token_id, "feedback": feedback})


@mcp.tool()
async def score_agent(bridge_did: str = "", chain_id: Optional[int] = None,
                      token_id: Optional[int] = None) -> str:
    """Decay-weighted trust score in [0,1] + tier over the agent's imported
    ERC-8004 feedback — recent behavior outweighs old; no feedback scores a
    neutral 0.5 prior (no blind trust, no unfair zero)."""
    payload: Dict[str, Any] = {"action": "score"}
    if bridge_did:
        payload["bridge_did"] = bridge_did
    if chain_id is not None:
        payload["chain_id"] = chain_id
    if token_id is not None:
        payload["token_id"] = token_id
    return await _run(payload)


@mcp.tool()
async def bind_identity(fleet_did: str, chain_id: int, token_id: int,
                        proof_note: str = "") -> str:
    """Bind a fleet DID to an ERC-8004 identity. Produces an order-independent,
    content-addressed (unsigned) binding attestation."""
    return await _run({"action": "bind", "fleet_did": fleet_did,
                       "chain_id": chain_id, "token_id": token_id,
                       "proof_note": proof_note})


@mcp.tool()
async def export_attestation(chain_id: int, token_id: int) -> str:
    """Export the agent's current trust score as an UNSIGNED
    ERC-8004 Validation Registry-shaped payload, content-addressed and ready
    for YOUR OWN signer to anchor on-chain."""
    return await _run({"action": "export_attestation", "chain_id": chain_id,
                       "token_id": token_id})


@mcp.tool()
async def verify_attestation(payload: Dict[str, Any]) -> str:
    """Recompute a payload's content hash and report whether it is intact."""
    return await _run({"action": "verify", "payload": payload})


@mcp.tool()
async def list_registrations() -> str:
    """List all imported ERC-8004 registrations."""
    return await _run({"action": "list"})


@mcp.tool()
async def export_validation_response(receipt: Dict[str, Any], request_hash: str,
                                     response_uri: str, replay_ok: bool) -> str:
    """Build UNSIGNED ERC-8004 Validation Registry validationResponse args
    from an Outcome Receipt (ORC v0.1): responseHash = receipt commitment,
    tag "orc/0.1", response 100 only if the bridge re-verifies the receipt
    AND your replay succeeded. Sign and submit with your own signer; this
    bridge holds no keys and writes to no chain."""
    return await _run({"action": "export_validation_response",
                       "receipt": receipt, "request_hash": request_hash,
                       "response_uri": response_uri, "replay_ok": replay_ok})


@mcp.tool()
async def describe_agent() -> str:
    """Return the bridge's capabilities and input contract."""
    return json.dumps(agent.describe(), indent=2)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:  # smoke
        print(json.dumps(agent.describe(), indent=2))
        print(json.dumps(asyncio.run(agent.health()), indent=2))
