"""Phase 3b — the unified MCP tool surface.

Exposes the root/mark/toll primitives as MCP tools with a machine-readable MANIFEST and a pure
`call_tool(name, args, ...)` dispatcher (the transport-agnostic core, mirroring api/service.py::dispatch).
Phase 3c wraps this in an actual MCP server for deploy. Additive only, stdlib only.

IMPLEMENT ME — see PHASE3_SPEC.md §3b.
"""

from __future__ import annotations

from typing import Optional

from .trust_root import TrustRoot
from .mark import Envelope, verify_mark, MARK
from .toll import compute_toll
from .certifier_bridge import agent_attestation, conservation_validator

# One process-wide shared root (dev signer; Phase 3c swaps to the K3-backed TrustRoot).
_DEFAULT_ROOT = TrustRoot()

# The MCP tool manifest. Each entry: name, description, input_schema (JSON-schema-ish dict).
MANIFEST = [
    {
        "name": "viridis_bind_did",
        "description": "Derive the canonical did:viridis identity for an agent (fleet R1 formula).",
        "input_schema": {"type": "object",
                         "properties": {"agent_id": {"type": "string"}, "pubkey": {"type": "string"}},
                         "required": ["agent_id", "pubkey"]},
    },
    {
        "name": "viridis_compute_toll",
        "description": "Compute the Viridis protocol margin (take) + pass-through card cost for a settlement.",
        "input_schema": {"type": "object",
                         "properties": {"amount_minor": {"type": "integer"},
                                        "payee_tier": {"type": "string"}},
                         "required": ["amount_minor", "payee_tier"]},
    },
    {
        "name": "viridis_agent_attestation",
        "description": "Issue a mark-stamped agent-attestation envelope under the shared trust root.",
        "input_schema": {"type": "object", "properties": {"event": {"type": "object"}},
                         "required": ["event"]},
    },
    {
        "name": "viridis_verify_mark",
        "description": "Verify a 'Certified by ViridisOS' envelope against the shared root.",
        "input_schema": {"type": "object",
                         "properties": {"envelope": {"type": "object"},
                                        "profile": {"type": "string"}},
                         "required": ["envelope"]},
    },
]

_TOOL_NAMES = {t["name"] for t in MANIFEST}


def _envelope_from_dict(d: dict) -> Envelope:
    """Rebuild an Envelope from a plain dict (as it crosses the MCP boundary)."""
    return Envelope(
        payload=d["payload"], profile=d["profile"], root_id=d["root_id"],
        key_id=d["key_id"], signature=d["signature"], mark=d.get("mark", ""),
    )


def call_tool(name: str, args: dict, root: Optional[TrustRoot] = None) -> dict:
    """Dispatch an MCP tool call to the unified primitives. Pure function: (name, args) -> result dict.

    - viridis_bind_did          -> {"did": ...}
    - viridis_compute_toll      -> compute_toll(...) result dict
    - viridis_agent_attestation -> {"envelope": <envelope as dict>}
    - viridis_verify_mark       -> {"valid": bool}   (conservation profile uses conservation_validator;
                                    agent-attestation uses an accept-all structural validator)
    Unknown tool name -> {"error": "..."}. Bad args -> {"error": "..."} (never raises).
    """
    try:
        if name not in _TOOL_NAMES:
            return {"error": f"unknown tool: {name}"}

        shared_root = root or _DEFAULT_ROOT

        if name == "viridis_bind_did":
            return {"did": shared_root.bind_did(args["agent_id"], args["pubkey"])}

        if name == "viridis_compute_toll":
            return compute_toll(args["amount_minor"], args["payee_tier"])

        if name == "viridis_agent_attestation":
            from dataclasses import asdict

            envelope = agent_attestation(shared_root, args["event"])
            return {"envelope": asdict(envelope)}

        envelope = _envelope_from_dict(args["envelope"])
        validator = (
            conservation_validator
            if args.get("profile") == "conservation-claim"
            else lambda payload: isinstance(payload, dict)
        )
        return {"valid": verify_mark(shared_root, envelope, validator)}
    except Exception as exc:
        return {"error": str(exc) or type(exc).__name__}
