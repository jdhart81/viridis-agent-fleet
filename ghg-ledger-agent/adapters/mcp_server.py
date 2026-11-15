"""Thin MCP adapter for the deterministic Viridis GHG ledger."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    try:  # MCP SDK 2.x (serves 2026-07-28 and the handshake versions)
        from mcp.server.mcpserver import MCPServer as FastMCP
    except ModuleNotFoundError:  # MCP SDK 1.x
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


# TS1-TS4: a typed description of one activity, so a host can form a valid
# request from the schema alone.
# TS1 it describes, it does not reject: every field is optional and unknown
#     fields pass through, so a wrong request still reaches the engine and
#     comes back with the engine's own reason and first_call_help.
# TS2 the request the engine receives holds exactly the fields the caller
#     sent (no defaults are added), so audit hashes are unchanged.
# TS3 the activity types and regions named in the schema are read from the
#     bundled factor pack, never typed by hand.
# TS4 without pydantic (stdlib smoke shim) the argument is untyped.
try:
    from pydantic import BaseModel, ConfigDict, Field
    from src import core as _core

    _FACTORS = list(_core.PACK["factors"].values())
    ACTIVITY_TYPES = sorted({f["activity_type"] for f in _FACTORS})
    REGIONS = sorted({f["region"] for f in _FACTORS})

    class Activity(BaseModel):
        """One measured activity: what happened, how much, where and when."""
        model_config = ConfigDict(extra="allow")
        id: Optional[str] = Field(
            None, description="Your label for this line; it is echoed in the result.")
        activity_type: Optional[str] = Field(
            None, examples=["purchased_electricity"],
            description="What the activity is. One of: " + ", ".join(ACTIVITY_TYPES) + ".")
        quantity: Union[int, float, str, None] = Field(
            None, examples=[12000, "12000.5"],
            description="Amount in `unit`, zero or more. A number or a decimal string.")
        unit: Optional[str] = Field(
            None, examples=["kWh"],
            description=("Unit of `quantity`. Electricity: kWh or MWh. Natural gas: therm, "
                         "mmbtu or kWh. Liquid fuels: gallon_us or litre. Refrigerants: kg "
                         "or lb. Landfilled waste: short_ton or metric_tonne. Car travel: "
                         "mile or km. Purchased goods by spend: usd."))
        region: Optional[str] = Field(
            None, examples=["US"],
            description=("Where it happened. One of: " + ", ".join(REGIONS) + ". The "
                         "US-XXXX codes are EPA eGRID grid subregions, for electricity "
                         "only (US-CAMX California, US-ERCT Texas, US-NYUP upstate New "
                         "York, US-RFCE Mid-Atlantic, and so on); use US for fuels and "
                         "when the subregion is unknown; GLOBAL is for refrigerants."))
        year: Union[int, str, None] = Field(
            None, examples=[2025],
            description=("The year the activity took place. The latest bundled factor "
                         "dated on or before it is used and recorded on the line."))
        mobile_source_class: Optional[str] = Field(
            None, description=("Only for mobile fuels: nonroad_four_stroke for "
                               "mobile_combustion_gasoline, nonroad for "
                               "mobile_combustion_diesel."))

    _Activities = Union[List[Activity], Activity, str, None]
except ImportError:  # pragma: no cover - stdlib shim
    Activity = None
    _Activities = Any


def _plain(value: Any) -> Any:
    """TS2: back to exactly what the caller sent."""
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_unset=True)
    return value


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), indent=2, default=str)


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


@mcp.tool(annotations=_READ)
async def calculate_inventory(activities: _Activities = None,
                              options: Optional[Dict[str, Any]] = None,
                              payment_ref: Optional[str] = None,
                              request_id: Optional[str] = None) -> str:
    """Calculate an auditable GHG inventory from explicit activity records.
    Returns per-line gas/CO2e results, Scope 1/2/3 and category rollups, dual
    Scope 2 reporting, indeterminate lines, factor lineage, notary payload, and
    an offset-clearinghouse dry-run weave. This is calculation, not advice.
    Price: $1.00 per call after 10 free calls/day. Pay at
    /x402/ghg-ledger/calculate_inventory with Base USDC, cash-fund payment_ref
    through escrow_checkout + confirm_escrow_funding, or use /seats.
    Each activity needs activity_type, quantity, unit, region and year (the
    year the activity took place; the latest bundled factor dated on or before
    it is used and recorded on the line). list_factor_packs names the bundled
    activity types and regions. One activity object is accepted as a list of one.
    If a call returns indeterminate, the response includes first_call_help.
    Example arguments: {"activities": [{"id": "office-electricity", "activity_type": "purchased_electricity", "quantity": "12000", "unit": "kWh", "region": "US", "year": 2023}, {"id": "backup-generator", "activity_type": "stationary_combustion_diesel", "quantity": "400", "unit": "gallons", "region": "US", "year": 2025}], "options": {}}"""
    return await _run({"action": "calculate_inventory", "activities": _plain(activities),
                       "options": options or {},
                       **({"payment_ref": payment_ref} if payment_ref else {}),
                       **({"request_id": request_id}
                          if request_id is not None else {})})


@mcp.tool(annotations=_READ)
async def classify_activity(activity: Dict[str, Any]) -> str:
    """Suggest scope and Scope 3 category from the bundled deterministic map.
    No inference is used; unknown activity types return no suggestion."""
    return await _run({"action": "classify_activity", "activity": activity})


@mcp.tool(annotations=_READ)
async def list_factor_packs() -> str:
    """List the bundled pack version/digest, supported regions and years,
    activity types, GWP set, and explicit MVP coverage."""
    return await _run({"action": "list_factor_packs"})


@mcp.tool(annotations=_READ)
async def get_factor_pack(region: str, year: int) -> str:
    """Return factors, GWP values, conversions, sources, and pack SHA for one
    exact bundled region/year. No nearest-region or nearest-year substitution."""
    return await _run({"action": "get_factor_pack", "region": region, "year": year})


@mcp.tool(annotations=_READ)
async def verify_result(result_json: str) -> str:
    """Recompute a prior inventory's audit hash and conservation checks. Pass
    the prior result object as JSON; tampering or stale factor lineage is flagged."""
    try:
        result = json.loads(result_json)
    except (TypeError, json.JSONDecodeError) as exc:
        return json.dumps({"status": "error", "error_type": "ValidationError",
                           "message": f"result_json is not valid JSON: {exc}"})
    return await _run({"action": "verify_result", "result": result})


@mcp.tool(annotations=_READ)
async def describe_agent() -> str:
    """Return fleet-standard capabilities, version, pack digest, and pricing."""
    return json.dumps(agent.describe(), indent=2)


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
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), indent=2))
        print(json.dumps(asyncio.run(agent.health()), indent=2))
