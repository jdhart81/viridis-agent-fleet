"""MCP surface for the non-actuating Robustness Engine core.

The single core operation, ``evaluate``, has one corresponding MCP tool.
Transport errors never turn a governed HOLD into an execution instruction.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # Keep the stdlib core and adapter smoke tests portable.
    class FastMCP:
        def __init__(self, name: str, **kwargs):
            self.name = name
            self.tools = {}

        def tool(self, **kwargs):
            def register(function):
                self.tools[function.__name__] = function
                return function
            return register

        def run(self):
            raise RuntimeError("MCP serving requires the mcp package")

from src.core import RobustnessAgent


mcp = FastMCP(
    "robustness-engine-agent",
    instructions="Evaluate governed robustness cases; results never execute decisions.",
)
agent = RobustnessAgent()


@mcp.tool()
async def evaluate_robustness_case(
    case: dict[str, Any],
    outcomes: dict[str, Any],
    request_id: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic decision record or a fail-closed HOLD."""
    payload = {"operation": "evaluate", "case": case, "outcomes": outcomes}
    if request_id is not None:
        payload["request_id"] = request_id
    try:
        return await agent.process(payload)
    except ValueError as exc:
        return {"status": "error", "error_type": "ValidationError",
                "message": str(exc)}


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), indent=2))
        print(json.dumps(asyncio.run(agent.health()), indent=2))
