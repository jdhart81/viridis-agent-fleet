"""Thin MCP adapter for the deterministic Viridis quantity-takeoff engine."""

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
except ImportError:  # stdlib contract-test shim
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
    "quantity-takeoff-agent",
    "Deterministic auditable construction material quantities with bundled factors, locked waste, conservative purchase rounding, and notary-ready audit hashes.",
)
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), indent=2, default=str)


@mcp.tool()
async def calculate_takeoff(items: List[Dict[str, Any]],
                            options: Optional[Dict[str, Any]] = None,
                            payment_ref: Optional[str] = None,
                            request_id: Optional[str] = None) -> str:
    """Calculate an auditable material takeoff from explicit geometry or a
    supported SmartScale/ProtoGen measurement payload. Returns net, explicit
    waste-adjusted, and conservative purchase quantities. This is a planning
    estimate, not a guaranteed material order or professional certification."""
    return await _run({"action": "calculate_takeoff", "items": items,
                       "options": options or {},
                       **({"payment_ref": payment_ref} if payment_ref else {}),
                       **({"request_id": request_id}
                          if request_id is not None else {})})


@mcp.tool()
async def list_assemblies() -> str:
    """List supported assemblies, required dimensions, formulas, waste
    defaults, and the current material-pack digest."""
    return await _run({"action": "list_assemblies"})


@mcp.tool()
async def get_assembly(assembly_type: str) -> str:
    """Return one assembly's formula, required dimensions, material factors,
    purchase increment, sources, and material-pack lineage."""
    return await _run({"action": "get_assembly", "assembly_type": assembly_type})


@mcp.tool()
async def list_material_pack() -> str:
    """List the bundled material pack version, digest, coverage, shapes,
    rebar sizes, roof pitches, and explicit unsupported policy."""
    return await _run({"action": "list_material_pack"})


@mcp.tool()
async def get_material_pack() -> str:
    """Return the bundled factors, densities, coverages, waste defaults,
    purchase increments, unit conversions, sources, and raw-pack SHA."""
    return await _run({"action": "get_material_pack"})


@mcp.tool()
async def verify_result(result_json: str) -> str:
    """Recompute a takeoff audit hash, notary payload, pack currency, and QT9
    unit-resolved conservation. Pass the prior result object as JSON."""
    try:
        result = json.loads(result_json)
    except (TypeError, json.JSONDecodeError) as exc:
        return json.dumps({"status": "error", "error_type": "ValidationError",
                           "message": f"result_json is not valid JSON: {exc}"})
    return await _run({"action": "verify_result", "result": result})


@mcp.tool()
async def describe_agent() -> str:
    """Return fleet-standard capabilities, version, pack digest, disclaimer,
    composition role, and pricing."""
    return json.dumps(agent.describe(), indent=2)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), indent=2))
        print(json.dumps(asyncio.run(agent.health()), indent=2))
