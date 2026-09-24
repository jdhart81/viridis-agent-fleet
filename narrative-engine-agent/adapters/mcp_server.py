"""
MCP adapter for narrative-engine-agent (ecological data -> decision-maker narratives).

One MCP tool per core action. Thin wrapper: all logic lives in src/core.py.
Runs with the official `mcp` SDK when installed; falls back to a stdlib shim
that keeps the tool functions importable/testable anywhere.
Run: python adapters/mcp_server.py            (smoke: describe + health)
     python adapters/mcp_server.py --serve    (stdio MCP server; needs `mcp`)
"""
import asyncio
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from mcp.server.fastmcp import FastMCP
    HAS_MCP = True
except ImportError:  # pragma: no cover - deploy-time dependency guard
    HAS_MCP = False

    class FastMCP:  # minimal shim: registers tools so smoke tests run stdlib-only
        def __init__(self, name: str, **kwargs):
            self.name, self.tools = name, {}

        def tool(self, *a, **k):
            def deco(fn):
                self.tools[fn.__name__] = fn
                return fn
            return deco

        def run(self):
            raise RuntimeError("`mcp` SDK not installed - pip install mcp")

import src.core as core_mod

CoreCls = [v for k, v in vars(core_mod).items()
           if inspect.isclass(v) and k.endswith("Core")][-1]

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
    "narrative-engine-agent",
    description="Translates ecological/agent data into audience-tailored "
                "narratives: grant proposals, investor decks, policy briefs.",
)
agent = CoreCls()


@mcp.tool()
async def translate_narrative(agent_output: Dict[str, Any], audience_type: str,
                        format_type: str, key_message: Optional[str] = None,
                        payment_ref: Optional[str] = None,
                        request_id: Optional[str] = None) -> str:
    """Translate raw ecological/agent data into a decision-maker-ready narrative.

    audience_type: board_member | general_public | grant_funder |
        institutional_investor | journalist | policymaker | regulator |
        retail_investor | scientist
    format_type: academic_paper | executive_summary | grant_proposal |
        investor_deck | newsletter | policy_brief | press_release
    """
    return json.dumps(await agent.process({
        "action": "translate", "agent_output": agent_output,
        "audience_type": audience_type, "format_type": format_type,
        "key_message": key_message,
        **({"payment_ref": payment_ref} if payment_ref else {}),
        **({"request_id": request_id} if request_id is not None else {}),
    }), default=str, indent=2)


@mcp.tool()
async def describe_agent() -> str:
    """Fleet-standard self-description: capabilities, inputs, outputs."""
    return json.dumps(agent.describe(), default=str, indent=2)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), default=str, indent=2))
        print(json.dumps(asyncio.run(agent.health()), default=str, indent=2))
