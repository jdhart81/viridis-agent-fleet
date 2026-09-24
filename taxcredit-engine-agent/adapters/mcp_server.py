"""Thin MCP adapter for the deterministic tax-credit engine."""

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
    "taxcredit-engine-agent",
    "Auditable US clean-energy tax-credit scenarios for 45Q, 45V, 45Y, 48E, and 45X.",
)
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), indent=2, default=str)


@mcp.tool()
async def calculate_tax_credit(credit: str, facts: Dict[str, Any],
                               payment_ref: Optional[str] = None,
                               request_id: Optional[str] = None) -> str:
    """Calculate an auditable tax-credit scenario. credit is 45Q, 45V, 45Y,
    48E, or 45X. facts must contain the explicit credit-specific eligibility
    facts; missing facts return indeterminate. This is not tax or filing advice.
    Price: $2.00 per call after 10 free calls/day. Pay at
    /x402/taxcredit-engine/calculate_tax_credit with Base USDC, cash-fund
    payment_ref through escrow_checkout + confirm_escrow_funding, or use /seats."""
    return await _run({"action": "calculate", "credit": credit, "facts": facts,
                       **({"payment_ref": payment_ref} if payment_ref else {}),
                       **({"request_id": request_id}
                          if request_id is not None else {})})


@mcp.tool()
async def list_rule_packs() -> str:
    """List supported credits and the current bundled rule-pack digest."""
    return await _run({"action": "list_rule_packs"})


@mcp.tool()
async def get_rule_pack(credit: str) -> str:
    """Return the bundled rules and official source metadata for one credit."""
    return await _run({"action": "get_rule_pack", "credit": credit})


@mcp.tool()
async def verify_tax_credit_result(result_json: str) -> str:
    """Verify an engine result's audit_sha256. Pass the prior result object as
    JSON; any changed amount, fact, rule step, or source digest fails."""
    try:
        result = json.loads(result_json)
    except (TypeError, json.JSONDecodeError) as exc:
        return json.dumps({"status": "error", "error_type": "ValidationError",
                           "message": f"result_json is not valid JSON: {exc}"})
    return await _run({"action": "verify_result", "result": result})


@mcp.tool()
async def describe_agent() -> str:
    """Return fleet-standard capabilities, version, and pricing."""
    return json.dumps(agent.describe(), indent=2)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), indent=2))
        print(json.dumps(asyncio.run(agent.health()), indent=2))
