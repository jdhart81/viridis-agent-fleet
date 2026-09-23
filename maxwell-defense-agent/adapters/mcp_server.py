"""Mount through the fleet gateway so PaymentGate controls execution."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp.server.fastmcp import FastMCP
from src.core import MaxwellDefenseCore

mcp = FastMCP("maxwell-defense-agent")
agent = MaxwellDefenseCore()


@mcp.tool()
async def rehearse_defense(client_hashes_per_second: int, client_p95_budget_ms: int,
                           backend_cost_ms: int, peak_requests_per_second: int) -> str:
    """$1 bounded policy rehearsal. Returns a model and local hash measurement.

    Does not activate endpoint protection or establish energy savings.
    """
    payload = {"action": "rehearse_defense",
        "client_hashes_per_second": client_hashes_per_second,
        "client_p95_budget_ms": client_p95_budget_ms,
        "backend_cost_ms": backend_cost_ms,
        "peak_requests_per_second": peak_requests_per_second}
    # Validate before the fleet gate can consume a credit or settle a payment,
    # including hosts whose generic MCP gate predates preflight hooks.
    error = agent._paid_preflight(payload)
    if error:
        return json.dumps(error)
    return json.dumps(await agent.process(payload))


@mcp.tool()
async def describe_agent() -> str:
    """Free scope and price discovery."""
    return json.dumps(agent.describe())
