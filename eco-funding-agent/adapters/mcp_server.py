"""Viridis fleet gateway adapter for viridis-eco-funding.

The gateway (mcp==1.28.1) loads this file unmodified and mounts ``mcp`` at
``/eco-funding/mcp``; ``agent`` is the core it uses for /health and the fleet
directory. All logic lives in ``src/viridis_eco_funding`` (standard library only).

Standalone:  python adapters/mcp_server.py --serve      (stdio)
             python adapters/mcp_server.py               (prints describe + health)

Five read-only tools; no money movement; the intelligence-bound term is a conjecture.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
SRC = str(ROOT / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from viridis_eco_funding.fleet import AGENT_NAME, INSTRUCTIONS, build  # noqa: E402

try:  # mcp 1.x, as pinned by the gateway
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations
    _ANNOTATION_KEYS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
except ImportError:  # pragma: no cover - exercised only on mcp 2.x
    from mcp.server.mcpserver import MCPServer as FastMCP
    from mcp.types import ToolAnnotations
    _ANNOTATION_KEYS = ("read_only_hint", "destructive_hint", "idempotent_hint", "open_world_hint")


def _annotations(open_world: bool) -> ToolAnnotations:
    return ToolAnnotations(**dict(zip(_ANNOTATION_KEYS, (True, False, True, open_world))))


PURE = _annotations(False)
PUBLIC_READ = _annotations(True)

mcp = FastMCP(AGENT_NAME, instructions=INSTRUCTIONS)
agent = build()


async def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
    return await agent.process(payload)


@mcp.tool(annotations=PUBLIC_READ)
async def value_site(site: Dict[str, Any], bind_vergecommon: bool = False) -> Dict[str, Any]:
    """Value a site's ecological complexity (schema vef-site/0.1: D-Score components, habitat
    patches and links, optional GSIP soil indicators, optional NPP and temperature). Produces
    a sealed, reproducible receipt in which every quantity states its formula, units, inputs
    and uncertainty. bind_vergecommon=true reads the named VergeCommon public project (GET
    only) as provenance. Intelligence-bound quantities are labelled 'conjecture'. Not a price.
    Free rail."""
    return await _run({"action": "value_site", "site": site, "bind_vergecommon": bind_vergecommon})


@mcp.tool(annotations=PURE)
async def explain_valuation(valuation_or_site: Dict[str, Any]) -> Dict[str, Any]:
    """Explain a valuation step by step: each quantity's formula, inputs, value, units,
    uncertainty and status (published method, v0.1 convention, input, or conjecture), plus
    limits. Accepts a valuation (receipt.result) or raw site inputs. Free rail."""
    return await _run({"action": "explain_valuation", "valuation_or_site": valuation_or_site})


@mcp.tool(annotations=PUBLIC_READ)
async def verify_receipt(receipt: Dict[str, Any], refetch_source: bool = False) -> Dict[str, Any]:
    """Re-run a valuation receipt offline and check its input, result and seal digests; valid
    only if reproduced byte for byte. refetch_source=true also reads the bound VergeCommon
    public record (GET only). Shows reproducibility, not truth of inputs. Free rail."""
    return await _run({"action": "verify_receipt", "receipt": receipt,
                       "refetch_source": refetch_source})


@mcp.tool(annotations=PURE)
async def simulate_pool(pool: Dict[str, Any],
                        observations: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Simulate a pledge pool (schema vef-pool/0.1) under milestone and outcome-linked release
    rules, given dated receipts or hypothetical readings per period. Integer accounting:
    releases + remaining = pledges; nothing released without a met rule. SIMULATION ONLY: no
    funds are held or moved; any real funding pool needs legal review before money moves."""
    return await _run({"action": "simulate_pool", "pool": pool, "observations": observations})


@mcp.tool(annotations=PURE)
async def describe_method() -> Dict[str, Any]:
    """Describe the method: formulas, constants, declared defaults, statuses, the seven
    invariants, citations and limits. Call first. Free rail."""
    return await _run({"action": "describe_method"})


# Fleet contract C4 (fleet E1-E8): inside a fleet tree, report {"status": "error"} results to
# MCP clients as tool errors (isError) without changing the body. Standalone there is no
# fleet_utils, and this is a no-op.
try:
    from fleet_utils.mcp_errors import flag_error_results
except ImportError:  # loaded without the fleet root on sys.path, as the gateway does
    _fleet_root = Path(__file__).resolve().parents[2]
    if (_fleet_root / "fleet_utils").is_dir() and str(_fleet_root) not in sys.path:
        sys.path.append(str(_fleet_root))
    try:
        from fleet_utils.mcp_errors import flag_error_results
    except ImportError:  # standalone repository: nothing to wire
        def flag_error_results(server: Any) -> int:
            return 0
flag_error_results(mcp)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), indent=2))
        print(json.dumps(agent.health(), indent=2))
