"""MCP adapter for the Viridis Security Preflight agent."""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations
except ImportError:  # pragma: no cover
    class ToolAnnotations(dict):
        def __init__(self, **kwargs):
            super().__init__(kwargs)

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
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                            idempotentHint=True, openWorldHint=False)
ASSESSMENT = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                             idempotentHint=False, openWorldHint=False)


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), indent=2)


@mcp.tool(title="Static agent manifest assessment", annotations=ASSESSMENT)
async def security_preflight(
        agent_id: str,
        manifest: Dict[str, Any],
        subject_profile_sha256: Optional[str] = None,
        policy: Optional[Dict[str, Any]] = None,
        sample_inputs: Optional[List[str]] = None,
        payment_ref: Optional[str] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None) -> str:
    """Run a $1 static Security Preflight and return a signed receipt.

    Direct MCP requires the checkout caller and verified fixed-order session.
    The separate x402 HTTP rail retains its existing introductory quote policy.
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
        **({"_fixed_order_session": session_id} if session_id else {}),
    })


@mcp.tool(title="Inline source indicator scan", annotations=ASSESSMENT)
async def scan_source(agent_id: str, source: str, session_id: Optional[str] = None) -> str:
    """$1 bounded inline VulnCanon source scan; indicators, not proven exploits.

    Direct MCP requires the checkout caller and verified fixed-order session.
    At most 64 KiB, 2000 lines, 4096 characters per line. No model calls,
    repository fetching or code execution. Returns a redacted signed receipt.
    """
    return await _run({"action": "scan_source", "agent_id": agent_id, "source": source,
                       **({"_fixed_order_session": session_id} if session_id else {})})


@mcp.tool(title="Text injection indicator screening", annotations=ASSESSMENT)
async def screen_injection(agent_id: str, texts: List[str], session_id: Optional[str] = None) -> str:
    """$1 batch of 1–20 text samples screened for deterministic injection markers.

    Direct MCP requires the checkout caller and verified fixed-order session.
    Maximum 64 KiB total. Heuristic indicators, not calibrated probabilities
    or a guarantee of safety. No model calls or automatic follow-on purchase.
    """
    return await _run({"action": "screen_injection", "agent_id": agent_id, "texts": texts,
                       **({"_fixed_order_session": session_id} if session_id else {})})


@mcp.tool(title="Filtered public security receipt", annotations=READ_ONLY)
async def get_security_receipt(receipt_id: str) -> str:
    """Read an unsigned, filtered public view; retain original delivery for signature verification."""
    if not isinstance(receipt_id, str) or not re.fullmatch(r'vsr_[a-f0-9]{24}', receipt_id):
        return json.dumps({'status':'error','error_type':'ValidationError','message':'Invalid receipt ID'})
    record = await agent.process({"action": "get_receipt", "receipt_id": receipt_id})
    return json.dumps(agent.public_receipt_view(record), indent=2)


@mcp.tool(title="Security assessment scope and evidence", annotations=READ_ONLY)
async def describe_agent() -> str:
    """Describe scope, evidence boundary, inputs, and outputs."""
    return json.dumps(agent.describe(), indent=2)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), indent=2))
