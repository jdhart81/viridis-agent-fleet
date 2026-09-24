"""Thin MCP adapter for the deterministic Viridis disclosure compiler."""

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
    "disclosure-compiler-agent",
    "Deterministic cited disclosure drafts with verified GHG lineage and audit hashes.",
)
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), indent=2, default=str)


@mcp.tool()
async def compile_disclosure(framework: str, company_facts: Dict[str, Any],
                             ghg_result: Optional[Dict[str, Any]] = None,
                             options: Optional[Dict[str, Any]] = None,
                             payment_ref: Optional[str] = None,
                             request_id: Optional[str] = None) -> str:
    """Compile a deterministic, cited disclosure draft from supplied company
    facts and an optional verified GHG-ledger result. Missing required
    datapoints remain explicit gaps; no prose or values are fabricated."""
    return await _run({"action": "compile_disclosure", "framework": framework,
                       "company_facts": company_facts,
                       "ghg_result": ghg_result, "options": options or {},
                       **({"payment_ref": payment_ref} if payment_ref else {}),
                       **({"request_id": request_id}
                          if request_id is not None else {})})


@mcp.tool()
async def list_frameworks() -> str:
    """List bundled framework IDs, coverage, source lineage, version, and the
    framework-pack digest."""
    return await _run({"action": "list_frameworks"})


@mcp.tool()
async def get_framework(framework: str) -> str:
    """Return one bundled framework's required datapoints, mappings, sources,
    and framework-pack lineage."""
    return await _run({"action": "get_framework", "framework": framework})


@mcp.tool()
async def verify_result(result_json: str) -> str:
    """Recompute a disclosure draft audit hash, notary payload, structural
    invariants, and framework-pack currency. Pass the prior result as JSON."""
    try:
        result = json.loads(result_json)
    except (TypeError, json.JSONDecodeError) as exc:
        return json.dumps({"status": "error", "error_type": "ValidationError",
                           "message": f"result_json is not valid JSON: {exc}"})
    return await _run({"action": "verify_result", "result": result})


@mcp.tool()
async def describe_agent() -> str:
    """Return deterministic capabilities, version, pack digest, pricing,
    composition, and the professional-review disclaimer."""
    return json.dumps(agent.describe(), indent=2)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), indent=2))
        print(json.dumps(asyncio.run(agent.health()), indent=2))
