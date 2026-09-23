"""MCP adapter for ViridisOS — fleet-gateway convention (FastMCP + stdlib shim).

Mounts as one more agent in the existing Viridis fleet MCP gateway (viridis_mcp_gateway.py),
served at /viridisos/mcp alongside identity/trust/escrow/... — NOT a separate server.

Thin wrapper: every tool delegates to integration.mcp_server.dispatch_tool, which holds the one
shared TrustRoot + the live-canon module registry (restoration/afforestation/harmonization READY,
mutualist BLOCKED). All logic is already unit-tested (103 checks green).

Run: python adapters/mcp_server.py            (smoke: list tools + a live call)
     python adapters/mcp_server.py --serve    (stdio MCP server; needs `mcp`)
"""

from __future__ import annotations

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

    class FastMCP:  # stdlib shim so smoke tests run anywhere (matches fleet agents)
        def __init__(self, name, **kw): self.name, self.tools = name, {}
        def tool(self, *a, **k):
            def deco(fn): self.tools[fn.__name__] = fn; return fn
            return deco
        def run(self): raise RuntimeError("`mcp` SDK not installed - pip install mcp")

from integration.mcp_server import dispatch_tool, FULL_MANIFEST  # tested unified dispatch (shared root + live canon)


def _mk_mcp(name, description=""):
    """FastMCP compat across SDK versions (matches the fleet agents' _mk_mcp)."""
    try:
        return FastMCP(name, instructions=description)
    except TypeError:
        try:
            return FastMCP(name, description=description)
        except TypeError:
            return FastMCP(name)


mcp = _mk_mcp("viridisos",
              description="ViridisOS — theorem-backed conservation certification + the unified "
                          "trust root/mark/toll. Certify parcels against gate-passed canon theorems, "
                          "issue 'Certified by ViridisOS' mark envelopes, bind did:viridis identities, "
                          "and price the one protocol toll.")


def _call(name: str, args: Dict[str, Any]) -> str:
    return json.dumps(dispatch_tool(name, args), default=str, indent=2)


@mcp.tool()
def viridis_list_modules() -> str:
    """List ViridisOS modules and their LIVE/BLOCKED state (A-1 against the live canon)."""
    return _call("viridis_list_modules", {})


@mcp.tool()
def viridis_certify(module_id: str, subject: str, inputs: Dict[str, Any]) -> str:
    """Certify a subject (parcel/portfolio) with a module -> a certificate. Errors if the module's
    backing theorem is not gate-passed (BLOCKED)."""
    return _call("viridis_certify", {"module_id": module_id, "subject": subject, "inputs": inputs})


@mcp.tool()
def viridis_certify_envelope(module_id: str, subject: str, inputs: Dict[str, Any]) -> str:
    """Certify then return a 'Certified by ViridisOS' mark envelope (profile conservation-claim)."""
    return _call("viridis_certify_envelope", {"module_id": module_id, "subject": subject, "inputs": inputs})


@mcp.tool()
def viridis_verify_mark(envelope: Dict[str, Any], profile: str = "") -> str:
    """Verify a 'Certified by ViridisOS' envelope against the shared trust root."""
    return _call("viridis_verify_mark", {"envelope": envelope, "profile": profile})


@mcp.tool()
def viridis_bind_did(agent_id: str, pubkey: str) -> str:
    """Derive the canonical did:viridis identity for an agent (fleet R1 formula) under the shared root."""
    return _call("viridis_bind_did", {"agent_id": agent_id, "pubkey": pubkey})


@mcp.tool()
def viridis_agent_attestation(event: Dict[str, Any]) -> str:
    """Issue a mark-stamped agent-attestation envelope under the shared trust root."""
    return _call("viridis_agent_attestation", {"event": event})


@mcp.tool()
def viridis_compute_toll(amount_minor: int, payee_tier: str) -> str:
    """Compute the unified Viridis protocol margin (the take) + pass-through card cost for a settlement."""
    return _call("viridis_compute_toll", {"amount_minor": amount_minor, "payee_tier": payee_tier})


class _ViridisOSCore:
    """The gateway-facing core object (`agent`) the fleet gateway drives for health/describe/directory
    (viridis_mcp_gateway.py reads `mod.agent`). MCP tool serving is handled by `mcp`; this exposes the
    fleet-standard process/health/describe convention so ViridisOS mounts like any other agent."""
    name = "viridisos"
    version = "1.0.0"

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": ("ViridisOS — theorem-backed conservation certification + the unified "
                            "trust root / mark / toll."),
            "capabilities": [t["name"] for t in FULL_MANIFEST],
            "a2a_role": "certification",
        }

    def health(self) -> Dict[str, Any]:
        try:
            from viridis_platform import catalog_status
            states = {m["id"]: m["state"] for m in catalog_status()}
            ready = sum(1 for s in states.values() if s == "READY")
        except Exception as e:  # noqa: BLE001 — health must never raise
            return {"status": "error", "agent": self.name, "version": self.version, "error": str(e)}
        return {"status": "ok", "agent": self.name, "version": self.version,
                "checks": {"modules": states, "ready": ready}}

    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Fleet-core entrypoint: payload {"action": <tool>, ...args} -> dispatch_tool result."""
        payload = payload or {}
        action = payload.get("action", "")
        args = {k: v for k, v in payload.items() if k != "action"}
        return dispatch_tool(action, args)


# module-level `agent` — required by the gateway loader (cores = {path: mod.agent})
agent = _ViridisOSCore()


def _smoke() -> int:
    tools = sorted(getattr(mcp, "tools", {}).keys()) if not HAS_MCP else "[FastMCP live]"
    print("viridisos MCP adapter — tools:", tools)
    print("describe:", json.dumps(agent.describe()))
    print("health:", json.dumps(agent.health()))
    print(viridis_list_modules())
    return 0


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()          # pragma: no cover - stdio transport (needs mcp)
    else:
        raise SystemExit(_smoke())
