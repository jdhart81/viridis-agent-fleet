"""
MCP adapter for ProtoGen CAD services.

ProtoGen is a Viridis LLC revenue agent that provides a callable CAD design
environment to the rest of the fleet. Other agents can create a workspace,
generate a parametric CAD design contract, and export that design for handoff
to a real CAD kernel, human designer, or manufacturing quote workflow.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - runtime dependency guard
    from fastmcp import FastMCP

from src.core import ProtoGenCore

def _mk_mcp(name, description=""):
    """FastMCP compat across SDK versions (description -> instructions -> bare)."""
    try:
        return FastMCP(name, instructions=description)
    except TypeError:
        try:
            return FastMCP(name, description=description)
        except TypeError:
            return FastMCP(name)

mcp = _mk_mcp(
    "protogen-agent",
    description=(
        "Viridis revenue MCP CAD agent. Creates CAD workspaces, generates "
        "parametric CAD contracts, exports design scripts, and supports "
        "manufacturing planning for other agents."
    ),
)

agent = ProtoGenCore()


@mcp.tool()
async def create_cad_workspace(
    project_name: str,
    owner_agent: str,
    design_goal: str,
    constraints: Optional[Dict[str, Any]] = None,
    payment_ref: Optional[str] = None,
    request_id: Optional[str] = None,
) -> str:
    """Create a ProtoGen CAD workspace for another agent or workflow."""
    # Routed through process() so the payment gate + metering apply (PG1-PG16).
    # The direct-method path bypassed both — that was the free side door.
    result = await agent.process({
        "action": "create_cad_workspace",
        "project_name": project_name,
        "owner_agent": owner_agent,
        "design_goal": design_goal,
        "constraints": constraints or {},
        **({"payment_ref": payment_ref} if payment_ref else {}),
        **({"request_id": request_id} if request_id is not None else {}),
    })
    return json.dumps(result, indent=2)


@mcp.tool()
async def generate_cad_design(
    workspace_id: str,
    part_name: str,
    dimensions_mm: Dict[str, float],
    material: str = "aluminum",
    design_intent: str = "",
    features: Optional[List[Dict[str, Any]]] = None,
    output_formats: Optional[List[str]] = None,
    payment_ref: Optional[str] = None,
    request_id: Optional[str] = None,
) -> str:
    """Generate a parametric CAD design contract in a ProtoGen workspace."""
    result = await agent.process({
        "action": "generate_cad_design",
        "workspace_id": workspace_id,
        "part_name": part_name,
        "dimensions_mm": dimensions_mm,
        "material": material,
        "design_intent": design_intent,
        "features": features or [],
        "output_formats": output_formats,
        **({"payment_ref": payment_ref} if payment_ref else {}),
        **({"request_id": request_id} if request_id is not None else {}),
    })
    return json.dumps(result, indent=2)


@mcp.tool()
async def export_cad_design(design_id: str, export_format: str = "openscad",
                            payment_ref: Optional[str] = None) -> str:
    """Export a CAD design as OpenSCAD, STEP contract metadata, or manufacturing brief."""
    result = await agent.process({
        "action": "export_cad_design",
        "design_id": design_id,
        "export_format": export_format,
        **({"payment_ref": payment_ref} if payment_ref else {}),
    })
    return json.dumps(result, indent=2)


@mcp.tool()
async def manufacturing_plan_from_spec(product_spec: Dict[str, Any],
                                       payment_ref: Optional[str] = None,
                                       request_id: Optional[str] = None) -> str:
    """Generate a manufacturing plan, BOM, DFM notes, and cost estimate from a product spec."""
    payload = dict(product_spec)
    if payment_ref:
        payload["payment_ref"] = payment_ref
    if request_id is not None:
        payload["request_id"] = request_id
    result = await agent.process(payload)
    return json.dumps(result, indent=2)


@mcp.tool()
def describe() -> str:
    """Return ProtoGen capabilities and current CAD environment status."""
    return json.dumps(agent.describe(), indent=2)


@mcp.tool()
def health() -> str:
    """Return ProtoGen health and workspace counts."""
    return json.dumps(agent.health(), indent=2)


if __name__ == "__main__":
    mcp.run()
