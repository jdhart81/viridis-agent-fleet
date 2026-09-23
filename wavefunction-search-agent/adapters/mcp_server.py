"""
MCP adapter for wavefunction-search-agent — the DEMAND SIDE of the fleet.

Discovery loop it completes: find an agent/collective (here) -> verify it
(identity / erc8004 bridge) -> trust it (oracle) -> hire it (escrow+metering).

The core is a prototype with a stage-based process(); this adapter wraps it
in a fleet-standard shim (health/describe + action routing) WITHOUT touching
the core — its 34 tests stay canonical.
"""
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from mcp.server.fastmcp import FastMCP
    HAS_MCP = True
except ImportError:  # pragma: no cover
    HAS_MCP = False

    class FastMCP:  # stdlib shim so smoke tests run anywhere
        def __init__(self, name, **kw): self.name, self.tools = name, {}
        def tool(self, *a, **k):
            def deco(fn): self.tools[fn.__name__] = fn; return fn
            return deco
        def run(self): raise RuntimeError("`mcp` SDK not installed - pip install mcp")

from src.core import VERSION as CORE_VERSION, WavefunctionSearchCore


class FleetShim:
    """Fleet-standard surface over the prototype core (health/describe/process)."""

    NAME = "wavefunction-search-agent"
    VERSION = CORE_VERSION

    def __init__(self):
        self.core = WavefunctionSearchCore()

    async def health(self) -> dict:
        return {"status": "ok", "agent": self.NAME, "version": self.VERSION,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "checks": {"wavefunctions": len(
                               getattr(self.core, "user_wavefunctions", {})),
                           "collectives": len(getattr(self.core, "collectives", {}))}}

    def describe(self) -> dict:
        return {"name": self.NAME, "version": self.VERSION,
                "capabilities": ["intake", "collapse", "find_matches",
                                 "register_collective"],
                "inputs": {"stage": "intake|collapse|find_matches",
                           "action": "register_collective"},
                "outputs": {"status": "ok|error"},
                "a2a_role": "discovery"}

    async def process(self, input_data: dict) -> dict:
        try:
            if not isinstance(input_data, dict):
                return {"status": "error", "reason": "input must be an object"}
            if input_data.get("action") == "register_collective":
                c = self.core.register_collective(
                    input_data.get("collective_id", ""),
                    input_data.get("name", ""),
                    input_data.get("mission", ""),
                    input_data.get("domain_profile") or {},
                    input_data.get("constitutional_scores") or {},
                    int(input_data.get("capacity", 10)))
                return {"status": "ok", "collective_id": getattr(c, "collective_id",
                        input_data.get("collective_id", ""))}
            return await self.core.process(input_data)
        except Exception as e:   # fleet contract: never raise
            return {"status": "error", "reason": str(e)}


def _mk_mcp(name, description=""):
    try:
        return FastMCP(name, instructions=description)
    except TypeError:
        try:
            return FastMCP(name, description=description)
        except TypeError:
            return FastMCP(name)


mcp = _mk_mcp("wavefunction-search-agent",
              description="Demand-side discovery for the agent economy: turn "
                          "ambiguous intentions into commitments and match them "
                          "to constitutionally-aligned agents and collectives. "
                          "Pairs with the identity registry and ERC-8004 bridge.")
agent = FleetShim()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


@mcp.tool()
async def intake(user_id: str, dialogue: List[Dict[str, str]]) -> str:
    """Distill a user's dialogue into an intention wavefunction (explicit
    intentions + confidence). dialogue: [{role, content}, ...]."""
    return await _run({"stage": "intake", "user_id": user_id,
                       "dialogue": dialogue})


@mcp.tool()
async def collapse(user_id: str, stake_amount: float = 100.0) -> str:
    """Collapse the user's wavefunction into an actionable commitment,
    weighted by stake."""
    return await _run({"stage": "collapse", "user_id": user_id,
                       "stake_amount": stake_amount})


@mcp.tool()
async def find_matches(user_id: str) -> str:
    """Match the user's collapsed intention to constitutionally-aligned
    agents/collectives, ranked by alignment score."""
    return await _run({"stage": "find_matches", "user_id": user_id})


@mcp.tool()
async def register_collective(collective_id: str, name: str, mission: str,
                              domain_profile: Optional[Dict[str, float]] = None,
                              constitutional_scores: Optional[Dict[str, float]] = None,
                              capacity: int = 10) -> str:
    """Register an agent/collective into the match index (mission +
    domain profile + constitutional alignment scores + capacity)."""
    return await _run({"action": "register_collective",
                       "collective_id": collective_id, "name": name,
                       "mission": mission,
                       "domain_profile": domain_profile or {},
                       "constitutional_scores": constitutional_scores or {},
                       "capacity": capacity})


@mcp.tool()
async def describe_agent() -> str:
    """Return capabilities and input contract."""
    return json.dumps(agent.describe(), indent=2)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), indent=2))
        print(json.dumps(asyncio.run(agent.health()), indent=2))
