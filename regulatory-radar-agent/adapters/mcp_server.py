"""
MCP adapter for regulatory-radar-agent (CSRD/TNFD compliance-as-a-service).

One MCP tool per core action. Thin wrapper: all logic lives in src/core.py.
Runs with the official `mcp` SDK when installed; falls back to a stdlib shim
that keeps the tool functions importable/testable anywhere.
Run: python adapters/mcp_server.py            (smoke: describe + health)
     python adapters/mcp_server.py --serve    (stdio MCP server; needs `mcp`)
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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

from src.core import RegulatoryRadarCore

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
    "regulatory-radar-agent",
    description=(
        "California, US, and global climate compliance scans with "
        "source-linked deadlines."),
)
agent = RegulatoryRadarCore()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


@mcp.tool()
async def scan_regulations(jurisdiction: str, sector: Optional[str] = None,
                           payment_ref: Optional[str] = None,
                           request_id: Optional[str] = None) -> str:
    """Scan a jurisdiction (e.g. EU, US, california, or CA for Canada), optionally filtered by sector.

    Returns regulations with urgency flags and effective dates. Price: $0.25
    per call after 10 free calls/day. Pay at
    /x402/regulatory-radar/scan_regulations with Base USDC, cash-fund payment_ref through
    escrow_checkout + confirm_escrow_funding, or use /seats."""
    return await _run({"action": "scan", "jurisdiction": jurisdiction, "sector": sector,
                 **({"payment_ref": payment_ref} if payment_ref else {}),
                 **({"request_id": request_id}
                    if request_id is not None else {})})


@mcp.tool()
async def assess_compliance(company_name: str, sector: str, jurisdiction: str,
                      disclosures: Optional[List[str]] = None,
                      payment_ref: Optional[str] = None,
                      request_id: Optional[str] = None) -> str:
    """Assess a company's compliance posture against applicable regulations.

    Returns compliance level, percentage, gaps, and remediation priorities."""
    return await _run({"action": "assess", "company_name": company_name, "sector": sector,
                 "jurisdiction": jurisdiction, "disclosures": disclosures or [],
                 **({"payment_ref": payment_ref} if payment_ref else {}),
                 **({"request_id": request_id}
                    if request_id is not None else {})})


@mcp.tool()
async def monitor_changes(jurisdiction: str, since_days: int = 90,
                          topics: Optional[List[str]] = None,
                          payment_ref: Optional[str] = None,
                          request_id: Optional[str] = None) -> str:
    """Watch curated regulatory effective dates and deadlines in a bounded window.

    `since_days` controls both recently effective dates behind today and
    effective/deadline dates ahead of today. This is a source-linked watch
    over the curated Viridis dataset, not a live external regulatory feed."""
    return await _run({"action": "monitor_changes", "jurisdiction": jurisdiction,
                 "lookback_days": since_days, "topics": topics or [],
                 **({"payment_ref": payment_ref} if payment_ref else {}),
                 **({"request_id": request_id}
                    if request_id is not None else {})})


@mcp.tool()
async def build_evidence_pack(
    jurisdiction: str,
    topics: Optional[List[str]] = None,
    company_profile: Optional[Dict[str, Any]] = None,
    source_ids: Optional[List[str]] = None,
    since_days: int = 90,
    persist_snapshot: bool = True,
) -> str:
    """Build a live, source-hashed regulatory change evidence pack.

    Fetches only the product's registry-owned regulator URLs, reports source
    retrieval timestamps and SHA-256 hashes, distinguishes a first baseline
    from a detected change, emits a bounded text diff on later changes, and
    combines the evidence with a curated deadline calendar. Screening only;
    confirm legal applicability with the cited authority or qualified counsel.
    """
    return await _run({
        "action": "build_evidence_pack",
        "jurisdiction": jurisdiction,
        "topics": topics or [],
        "company_profile": company_profile or {},
        "source_ids": source_ids or [],
        "lookback_days": since_days,
        "persist_snapshot": persist_snapshot,
    })


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
