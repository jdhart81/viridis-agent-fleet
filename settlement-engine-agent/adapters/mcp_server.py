"""
MCP adapter for settlement-engine-agent. One MCP tool per core action.
Thin wrapper — all logic lives in src/core.py. The serving path has no
network, no keys and no trading (S3); ingestion adapters (examples/) feed
observations in as data with source hashes (S4).
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


mcp = _mk_mcp("settlement-engine-agent",
              description="Progressive-settlement engine: for any contract, grant or pay-for-success agreement that "
                          "settles on an officially published series (ISO electricity prices, election counts, "
                          "restoration survival, canopy, soil carbon), it reports what is already published, what the "
                          "remainder must do for an outcome to settle, which strikes are decided by arithmetic alone, "
                          "and produces recomputable settlements with the evidence hashes. Facts and model estimates "
                          "are always separate. No forecasting, no trading, no keys.")
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


@mcp.tool()
async def register_series(name: str, unit: str, aggregate: str, n_expected: int, source: str, period_start: str, period_end: str,
                          strikes: Optional[List[float]] = None, value_min: Optional[float] = None, value_max: Optional[float] = None,
                          meta: Optional[Dict[str, Any]] = None) -> str:
    """FREE: declare a progressively published series. aggregate: mean (prices), sum (totals), share (survival/success 0/1 per
    slot), last (closing value). n_expected: number of observation slots in the period. value_min/value_max: the physical
    bounds of one observation; without them nothing is decided until the period is complete (S5)."""
    return await _run({"action": "register_series", "name": name, "unit": unit, "aggregate": aggregate, "n_expected": n_expected,
                       "source": source, "period_start": period_start, "period_end": period_end, "strikes": strikes or [],
                       "value_min": value_min, "value_max": value_max, "meta": meta or {}})


@mcp.tool()
async def ingest(series_id: str, observations: List[Dict[str, Any]]) -> str:
    """FREE: append observations [{slot, value, source_url, source_sha256 (64 hex of the source document), observed_at}].
    A re-posted slot replaces the value and is logged as a revision (S7). Each observation is hashed (S4)."""
    return await _run({"action": "ingest", "series_id": series_id, "observations": observations})


@mcp.tool()
async def period_status(series_id: str) -> str:
    """FREE: published share, published aggregate, remaining slots, and per strike the required remainder, the decided
    flag (arithmetic + declared bounds only) and a labelled model estimate kept separate from the facts (S1)."""
    return await _run({"action": "period_status", "series_id": series_id})


@mcp.tool()
async def required_remainder(series_id: str, strike: float) -> str:
    """FREE: what the remaining slots must average / sum to / hit for the aggregate to reach the strike, plus decided."""
    return await _run({"action": "required_remainder", "series_id": series_id, "strike": strike})


@mcp.tool()
async def decided_strikes() -> str:
    """FREE: every strike across registered series that is decided by the published part alone."""
    return await _run({"action": "decided_strikes"})


@mcp.tool()
async def explain(series_id: str) -> str:
    """FREE: deterministic plain-language reading of a series (no LLM in the serving path)."""
    return await _run({"action": "explain", "series_id": series_id})


@mcp.tool()
async def list_series() -> str:
    """FREE: registered series cards."""
    return await _run({"action": "list_series"})


@mcp.tool()
async def compile_contract(series_id: str, strike: float, rule: str, closes_at: str, parties: Optional[Dict[str, str]] = None,
                           terms: Optional[str] = None) -> str:
    """PAID: compile a Verified Outcome Contract v0 — a series, a strike, a settlement rule (above | at_or_above | below |
    at_or_below) and a closing time, content-addressed; the contract_id is the sha256 of its canonical form."""
    return await _run({"action": "compile_contract", "series_id": series_id, "strike": strike, "rule": rule, "closes_at": closes_at,
                       "parties": parties or {}, "terms": terms})


@mcp.tool()
async def get_contract(contract_id: str) -> str:
    """FREE: a compiled contract and its settlement ids."""
    return await _run({"action": "get_contract", "contract_id": contract_id})


@mcp.tool()
async def settle_contract(contract_id: str, now: str) -> str:
    """PAID: evaluate a contract against the ledger at an explicit time: YES / NO / UNDECIDED with the exact arithmetic and
    every observation hash used. A decided strike settles before closure; an incomplete, undecided series at closure is
    UNDECIDED, never a guess (S10). Settlements are immutable and recomputable (S8)."""
    return await _run({"action": "settle_contract", "contract_id": contract_id, "now": now})


@mcp.tool()
async def verify_settlement(settlement_id: Optional[str] = None, settlement: Optional[Dict[str, Any]] = None) -> str:
    """FREE: recompute a settlement from its stored evidence (hash, aggregate, result each checked separately)."""
    return await _run({"action": "verify_settlement", "settlement_id": settlement_id, "settlement": settlement})


@mcp.tool()
async def describe_agent() -> str:
    """FREE: actions, invariants S1–S10 and limits."""
    return await _run({"action": "describe"})


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), indent=2))
