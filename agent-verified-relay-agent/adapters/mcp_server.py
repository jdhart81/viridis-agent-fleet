"""
MCP adapter for agent-verified-relay-agent (Viridis Verified). One MCP tool
per core action. Thin wrapper — all logic lives in src/core.py.
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
    try:
        return FastMCP(name, instructions=description)
    except TypeError:
        try:
            return FastMCP(name, description=description)
        except TypeError:
            return FastMCP(name)

mcp = _mk_mcp("agent-verified-relay-agent",
              description="Viridis Verified — wrap any MCP server with "
                          "tamper-evident delivery receipts, metered fees, "
                          "and dispute-ready evidence.")
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


@mcp.tool()
async def register_service(url: str, provider: str, description: str = "",
                           fee_minor: int = 2,
                           payment_ref: Optional[str] = None,
                           request_id: Optional[str] = None) -> str:
    """Register a third-party MCP server (https, public FQDN only) under
    Viridis Verified. Returns a content-addressed service_id; idempotent on
    (url, provider). fee_minor is the per-verified-call fee in cents."""
    return await _run({"action": "register_service", "url": url,
                       "provider": provider, "description": description,
                       "fee_minor": fee_minor,
                       **({"payment_ref": payment_ref} if payment_ref else {}),
                       **({"request_id": request_id}
                          if request_id is not None else {})})


@mcp.tool()
async def call_verified(service_id: str, tool: str, call_id: str,
                        arguments: Optional[Dict[str, Any]] = None,
                        timeout_s: int = 20,
                        payment_ref: Optional[str] = None,
                        request_id: Optional[str] = None) -> str:
    """Relay a tools/call to a registered MCP service and notarize the
    exchange: request hash + response hash + outcome land in a tamper-evident
    receipt chain. Idempotent on call_id (a replay returns the original
    receipt and cached result — the downstream is never double-called).
    Failures are receipted evidence, not silence."""
    return await _run({"action": "call_verified", "service_id": service_id,
                       "tool": tool, "call_id": call_id,
                       "arguments": arguments or {}, "timeout_s": timeout_s,
                       **({"payment_ref": payment_ref} if payment_ref else {}),
                       **({"request_id": request_id}
                          if request_id is not None else {})})


@mcp.tool()
async def get_receipt(receipt_id: str) -> str:
    """Fetch a single delivery receipt by id."""
    return await _run({"action": "get_receipt", "receipt_id": receipt_id})


@mcp.tool()
async def verify_receipts(service_id: str) -> str:
    """Recompute a service's full receipt hash chain and fee ledger.
    Any party can audit Viridis Verified from receipts alone."""
    return await _run({"action": "verify_receipts", "service_id": service_id})


@mcp.tool()
async def list_services() -> str:
    """List registered services with call/fee counters."""
    return await _run({"action": "list_services"})


@mcp.tool()
async def service_stats(service_id: str) -> str:
    """Call counts, error counts, and accrued fees for one service."""
    return await _run({"action": "service_stats", "service_id": service_id})


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
