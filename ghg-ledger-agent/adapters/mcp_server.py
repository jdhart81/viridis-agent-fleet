"""Thin MCP adapter for the deterministic Viridis GHG ledger."""

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
except ImportError:  # stdlib smoke shim
    class FastMCP:
        def __init__(self, name, **kwargs):
            self.name, self.tools = name, {}
        def tool(self, *args, **kwargs):
            def decorator(fn):
                self.tools[fn.__name__] = fn
                return fn
            return decorator
        def run(self):
            raise RuntimeError("mcp SDK is required to serve")

from src.core import build


def _server(name: str, description: str):
    try:
        return FastMCP(name, instructions=description)
    except TypeError:
        try:
            return FastMCP(name, description=description)
        except TypeError:
            return FastMCP(name)


mcp = _server(
    "ghg-ledger-agent",
    "Deterministic Scope 1/2/3 GHG inventories with bundled factors and audit hashes.",
)
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), indent=2, default=str)


@mcp.tool()
async def calculate_inventory(activities: List[Dict[str, Any]],
                              options: Optional[Dict[str, Any]] = None,
                              payment_ref: Optional[str] = None,
                              request_id: Optional[str] = None) -> str:
    """Calculate an auditable GHG inventory from explicit activity records.
    Returns per-line gas/CO2e results, Scope 1/2/3 and category rollups, dual
    Scope 2 reporting, indeterminate lines, factor lineage, notary payload, and
    an offset-clearinghouse dry-run weave. This is calculation, not advice.
    Price: $1.00 per call after 10 free calls/day. Pay at
    /x402/ghg-ledger/calculate_inventory with Base USDC, cash-fund payment_ref
    through escrow_checkout + confirm_escrow_funding, or use /seats."""
    return await _run({"action": "calculate_inventory", "activities": activities,
                       "options": options or {},
                       **({"payment_ref": payment_ref} if payment_ref else {}),
                       **({"request_id": request_id}
                          if request_id is not None else {})})


@mcp.tool()
async def classify_activity(activity: Dict[str, Any]) -> str:
    """Suggest scope and Scope 3 category from the bundled deterministic map.
    No inference is used; unknown activity types return no suggestion."""
    return await _run({"action": "classify_activity", "activity": activity})


@mcp.tool()
async def list_factor_packs() -> str:
    """List the bundled pack version/digest, supported regions and years,
    activity types, GWP set, and explicit MVP coverage."""
    return await _run({"action": "list_factor_packs"})


@mcp.tool()
async def get_factor_pack(region: str, year: int) -> str:
    """Return factors, GWP values, conversions, sources, and pack SHA for one
    exact bundled region/year. No nearest-region or nearest-year substitution."""
    return await _run({"action": "get_factor_pack", "region": region, "year": year})


@mcp.tool()
async def verify_result(result_json: str) -> str:
    """Recompute a prior inventory's audit hash and conservation checks. Pass
    the prior result object as JSON; tampering or stale factor lineage is flagged."""
    try:
        result = json.loads(result_json)
    except (TypeError, json.JSONDecodeError) as exc:
        return json.dumps({"status": "error", "error_type": "ValidationError",
                           "message": f"result_json is not valid JSON: {exc}"})
    return await _run({"action": "verify_result", "result": result})


@mcp.tool()
async def describe_agent() -> str:
    """Return fleet-standard capabilities, version, pack digest, and pricing."""
    return json.dumps(agent.describe(), indent=2)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), indent=2))
        print(json.dumps(asyncio.run(agent.health()), indent=2))
