"""
MCP adapter for deterministic SmartScale CR80 pixel-geometry scaling.

Primary workflow:
1. An upstream human, UI, or vision system supplies a CR80 card pixel width.
2. The same upstream system supplies target-object pixel geometry.
3. SmartScale deterministically converts that geometry to millimetres.

The public MCP does not receive or inspect images.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
FLEET_ROOT = ROOT.parent
for path in (ROOT, FLEET_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - runtime dependency guard
    from fastmcp import FastMCP

from src.core import SmartScaleCore
from fleet_utils.mcp_output import FleetToolResult, structured_result

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
    "smartscale-agent",
    description=(
        "Deterministic CR80 pixel-geometry scaler. Callers supply the card and "
        "object pixel geometry; this MCP does not receive or inspect images."
    ),
)

agent = SmartScaleCore()


try:  # MCP tool annotations: let hosts and registries see which tools are safe reads
    from mcp.types import ToolAnnotations as _ToolAnnotations
except ImportError:  # pragma: no cover - stdlib shim keeps smoke tests runnable
    def _ToolAnnotations(**kw):
        return kw
_READ = _ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                         idempotentHint=True, openWorldHint=False)
_WRITE = _ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                          idempotentHint=False, openWorldHint=False)
_DESTRUCTIVE = _ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                idempotentHint=False, openWorldHint=False)


@mcp.tool(structured_output=True, annotations=_WRITE)
def credit_card_photo_instructions(
    measurement_goal: str = "",
    objects_to_measure: Optional[List[str]] = None,
) -> FleetToolResult:
    """Return safe capture guidance for upstream CR80 pixel picking.

    The image stays with the caller or upstream vision system; SmartScale only
    receives numeric pixel geometry.
    """
    result = agent.credit_card_photo_instructions(
        measurement_goal=measurement_goal,
        objects_to_measure=objects_to_measure or [],
    )
    return structured_result(result)


@mcp.tool(structured_output=True, annotations=_WRITE)
def scale_objects_from_credit_card(
    image_id: str,
    credit_card_pixel_width: float,
    objects: List[Dict[str, Any]],
    credit_card_pixel_height: Optional[float] = None,
    payment_ref: Optional[str] = None,
    request_id: Optional[str] = None,
) -> FleetToolResult:
    """Scale object pixel dimensions using a standard CR80 credit card reference.

    Args:
        image_id: Caller-defined source identifier; no image is uploaded.
        credit_card_pixel_width: Caller-supplied pixel width of a CR80-size card.
        objects: Objects to scale. Each object needs pixel_width and pixel_height;
            label, pixel_area, pixel_perimeter, and input confidence are optional.
        credit_card_pixel_height: Optional caller-supplied height for distortion check.
        payment_ref: Optional paid escrow reference consumed by the gateway.
        request_id: Optional retry-safe idempotency key (maximum 128 characters).
    """
    result = agent.process({
        "action": "measure_from_credit_card",
        "image_id": image_id,
        "credit_card_pixel_width": credit_card_pixel_width,
        "credit_card_pixel_height": credit_card_pixel_height,
        "objects": objects,
        **({"payment_ref": payment_ref} if payment_ref else {}),
        **({"request_id": request_id} if request_id is not None else {}),
    })
    return structured_result(result)


@mcp.tool(structured_output=True, annotations=_READ)
def describe() -> FleetToolResult:
    """Return SmartScale capabilities and input contract."""
    return structured_result({
        "status": "ok", "data": agent.describe(), "error": None,
    })


@mcp.tool(structured_output=True, annotations=_READ)
def health() -> FleetToolResult:
    """Return SmartScale health status."""
    return structured_result(agent.health())


try:  # report {"status": "error"} results to MCP clients as tool errors (isError)
    from fleet_utils.mcp_errors import flag_error_results
except ImportError:  # loaded without the fleet root on sys.path, as the gateway does
    import sys as _sys
    from pathlib import Path as _Path
    _fleet_root = _Path(__file__).resolve().parents[2]
    if (_fleet_root / "fleet_utils").is_dir() and str(_fleet_root) not in _sys.path:
        _sys.path.append(str(_fleet_root))
    try:
        from fleet_utils.mcp_errors import flag_error_results
    except ImportError:  # pragma: no cover - adapter copied without fleet_utils
        def flag_error_results(server):
            return 0
flag_error_results(mcp)


if __name__ == "__main__":
    mcp.run()
