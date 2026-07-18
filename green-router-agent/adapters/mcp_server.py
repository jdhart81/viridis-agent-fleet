"""
MCP adapter for green-router-agent. One MCP tool per core action.
Thin wrapper — all logic lives in src/core.py (thermo engine vendored in
src/vg/). Real retirement is composed at the gateway (GR3).
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


mcp = _mk_mcp("green-router-agent",
              description="Carbon-accounted agent compute: free honest "
                          "footprint quotes (joules + gCO2e, every "
                          "assumption stated), free carbon-ranked backend "
                          "routing, and paid certificates backed by REAL "
                          "verified offset retirement (Verra provenance, "
                          "x402-C verifiable). Every agent workload can pay "
                          "its entropy bill through restoration.")
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


@mcp.tool()
async def quote_footprint(workload: Dict[str, Any]) -> str:
    """FREE: honest energy/carbon footprint for an agent workload —
    {backend_id? (frontier_cloud | efficient_cloud | local_small),
    total_tokens, output_tokens, calls?, success_score?,
    grid_gco2e_per_kwh?, pue?, custom_backend? {id, wh_per_1k_tokens}}.
    Returns joules, gCO2e, useful bits, the retirement mass a certificate
    would carry, every model assumption with its source, and the Landauer
    context (GR1/GR2)."""
    return await _run({"action": "quote_footprint", "workload": workload})


@mcp.tool()
async def green_route(workload: Dict[str, Any],
                      allowed_backends: Optional[List[str]] = None) -> str:
    """FREE: rank compute backends by carbon for this workload — the
    greenest eligible path and the gCO2e saved per call. Carbon only
    (GR6); pair with /neurogenesis/mcp route_task for quality-floor
    routing."""
    payload: Dict[str, Any] = {"action": "green_route", "workload": workload}
    if allowed_backends:
        payload["allowed_backends"] = allowed_backends
    return await _run(payload)


@mcp.tool()
async def certify(workload: Dict[str, Any]) -> str:
    """PAID ($0.50 after free tier): compute the workload footprint, then
    RETIRE the required verified offset mass through the fleet's own
    clearinghouse — Verra provenance rides into the certificate; no
    retirement, no certificate (GR3, fail-closed). Returns a
    machine-verifiable certificate anyone can check for free (GR4)."""
    return await _run({"action": "certify", "workload": workload})


@mcp.tool()
async def verify_green_certificate(certificate_id: str) -> str:
    """FREE forever (GR5): recompute a certificate's footprint from its
    stored workload, compare against the certified numbers, and surface
    the clearinghouse purchase_id for the independent x402-C
    verify_retirement check on /offsets/mcp."""
    return await _run({"action": "verify_certificate",
                       "certificate_id": certificate_id})


@mcp.tool()
async def list_green_certificates(limit: int = 50) -> str:
    """FREE: the certificate ledger — counts, total grams retired, total
    clearinghouse cost (honest books, GR8)."""
    return await _run({"action": "list_certificates", "limit": limit})


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
