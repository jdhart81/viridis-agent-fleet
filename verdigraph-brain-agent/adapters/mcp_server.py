"""
MCP adapter for verdigraph-brain-agent. One MCP tool per core action.
Thin wrapper — all logic lives in src/core.py (engine vendored in src/vg/).
"""
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
    HAS_MCP = True
except ImportError:  # pragma: no cover
    HAS_MCP = False

    class FastMCP:
        def __init__(self, name, **kw): self.name, self.tools = name, {}
        def tool(self, *a, **k):
            def deco(fn): self.tools[fn.__name__] = fn; return fn
            return deco
        def run(self): raise RuntimeError("`mcp` SDK not installed - pip install mcp")

from src.core import build


def _mk_mcp(name, description=""):
    try:
        return FastMCP(name, instructions=description)
    except TypeError:
        try:
            return FastMCP(name, description=description)
        except TypeError:
            return FastMCP(name)


mcp = _mk_mcp("verdigraph-brain-agent",
              description="Verifiable cognition for the agent economy: "
                          "compile any agent file (Verdigraph genome, Claude "
                          "project export, OpenAI Assistant config, prompt "
                          "list) into a deterministic, content-addressed "
                          "brain_id with a machine-checkable invariant "
                          "report. Same bytes -> same brain, every time. "
                          "Pin it in git, cite it in an audit, notarize it "
                          "on the fleet.")
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


@mcp.tool()
async def build_brain(content: str, format: str = "auto",
                      include_document: bool = False) -> str:
    """Compile an agent file into a deterministic, content-addressed brain.
    content = the file as a string; format = verdigraph_genome |
    claude_project_export | openai_assistant | prompt_list | auto.
    Returns brain_id, content_hash, node/edge counts, the 9-invariant
    firing report, and provenance. Identical bytes always produce the
    identical brain_id (VB1). include_document=true returns the full
    graph."""
    return await _run({"action": "build", "content": content,
                       "format": format,
                       "include_document": include_document})


@mcp.tool()
async def verify_brain(content: str, brain_id: str = "",
                       content_hash: str = "", format: str = "auto") -> str:
    """Machine-check a cognition claim: recompute the brain from the
    submitted content and compare against the claimed brain_id and/or
    content_hash. valid=true iff every claimed identifier matches the
    deterministic recomputation (VB3)."""
    payload: Dict[str, Any] = {"action": "verify", "content": content,
                               "format": format}
    if brain_id:
        payload["brain_id"] = brain_id
    if content_hash:
        payload["content_hash"] = content_hash
    return await _run(payload)


@mcp.tool()
async def detect_format(content: str) -> str:
    """Detect which supported agent-file format the content is
    (verdigraph_genome, claude_project_export, openai_assistant,
    prompt_list) before building."""
    return await _run({"action": "detect_format", "content": content})


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
