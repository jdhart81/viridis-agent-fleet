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
