import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mcp.server.fastmcp import FastMCP
from src.core import WuWeiRouterCore
mcp=FastMCP('wu-wei-router-agent')
agent=WuWeiRouterCore()

@mcp.tool()
async def plan_workload(profiles:list[dict],tasks:list[dict])->str:
    """$1 workload routing plan from declared costs and representative evaluation counts.

    Up to 20 profiles and 50 task groups. Inspect the public service schema and a free
    unpaid quote first. Does not execute tasks or establish actual savings.
    """
    payload={'action':'plan_workload','profiles':profiles,'tasks':tasks}
    error=agent._paid_preflight(payload)
    return json.dumps(error if error else await agent.process(payload))

@mcp.tool()
async def describe_agent()->str:
    """Free scope and price discovery."""
    return json.dumps(agent.describe())


# Only the approved Wilson routing/state surface is exposed; no lifecycle tools.
import os
if os.environ.get("WU_WEI_V2_ENABLED") == "1":
    @mcp.tool()
    async def register_compute_profile(profile: dict) -> str:
        """Register declared Wilson evaluation/cost data and optional power_w.

        Setup mutations use the hosted admission gate; no compute is executed.
        """
        return json.dumps(await agent.process({"action": "register_compute_profile", "profile": profile}))

    @mcp.tool()
    async def route_task(task: dict, profiles: list[dict] | None = None) -> str:
        """Recommend one workload group's Wilson-eligible route; never execute it.

        Supply profiles inline or use registered profiles. Energy and savings
        are modeled from declared data. The recommendation is fee-neutral.
        """
        payload = {"action": "route_task", "task": task}
        if profiles is not None:
            payload["profiles"] = profiles
        return json.dumps(await agent.process(payload))

    @mcp.tool()
    async def record_route_outcome(decision_id: str, successes: int, trials: int,
                                   duration_ms: int | None = None,
                                   cost_microusd: int | None = None) -> str:
        """Record caller-reported outcomes; no correctness or usefulness claim."""
        payload = {"action": "record_route_outcome", "decision_id": decision_id,
                   "successes": successes, "trials": trials}
        for key, value in (("duration_ms", duration_ms), ("cost_microusd", cost_microusd)):
            if value is not None:
                payload[key] = value
        return json.dumps(await agent.process(payload))

    @mcp.tool()
    async def compute_efficiency_report() -> str:
        """Free modeled routing audit; caller reports are not adoption evidence."""
        return json.dumps(await agent.process({"action": "compute_efficiency_report"}))

    @mcp.tool()
    async def export_state() -> str:
        """Free portable routing state, including separate audit-event identities."""
        return json.dumps(await agent.process({"action": "export_state"}))

    @mcp.tool()
    async def import_state(state: dict) -> str:
        """Validate and import portable Wilson state through the admission gate."""
        return json.dumps(await agent.process({"action": "import_state", "state": state}))
