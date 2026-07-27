"""MCP adapter for the Viridis Security Preflight agent."""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    class FastMCP:
        def __init__(self, name: str, **kwargs):
            self.name, self.tools = name, {}

        def tool(self, *args, **kwargs):
            def decorate(function):
                self.tools[function.__name__] = function
                return function
            return decorate

        def run(self):
            raise RuntimeError("mcp SDK is not installed")

from src.core import SecurityPreflightCore


def _make_mcp():
    instructions = (
        "Scan caller-supplied agent manifests and tool policies. This service "
        "does not fetch or test deployed runtimes.")
    try:
        return FastMCP("security-preflight-agent", instructions=instructions)
    except TypeError:
        return FastMCP("security-preflight-agent")


mcp = _make_mcp()
agent = SecurityPreflightCore()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), indent=2)


@mcp.tool()
async def security_preflight(
        agent_id: str,
        manifest: Dict[str, Any],
        subject_profile_sha256: Optional[str] = None,
        policy: Optional[Dict[str, Any]] = None,
        sample_inputs: Optional[List[str]] = None,
        payment_ref: Optional[str] = None,
        request_id: Optional[str] = None) -> str:
    """Run a $1 static Security Preflight and return a signed receipt.

    New x402 payer wallets may receive the fleet-wide $0.01 introductory call.
    No deployed endpoint is fetched or tested. Importing the receipt into an
    Agent Market profile is a separate, explicit action.
    """
    return await _run({
        "action": "scan",
        "agent_id": agent_id,
        "manifest": manifest,
        **({
            "subject_profile_sha256": subject_profile_sha256,
        } if subject_profile_sha256 else {}),
        "policy": policy or {},
        "sample_inputs": sample_inputs or [],
        **({"payment_ref": payment_ref} if payment_ref else {}),
        **({"request_id": request_id} if request_id else {}),
    })


@mcp.tool()
async def get_security_receipt(receipt_id: str) -> str:
    """Read a previously issued public, input-redacted receipt."""
    return await _run({"action": "get_receipt", "receipt_id": receipt_id})


@mcp.tool()
async def describe_agent() -> str:
    """Describe scope, evidence boundary, inputs, and outputs."""
    return json.dumps(agent.describe(), indent=2)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), indent=2))
