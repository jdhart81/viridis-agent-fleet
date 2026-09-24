"""
MCP adapter for agent-metering-agent. One MCP tool per core action.
Thin wrapper — all logic lives in src/core.py.
Run: python adapters/mcp_server.py            (smoke: describe + health)
     python adapters/mcp_server.py --serve    (stdio MCP server; needs `mcp`)
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

    class FastMCP:  # stdlib shim so smoke tests run anywhere
        def __init__(self, name, **kw): self.name, self.tools = name, {}
        def tool(self, *a, **k):
            def deco(fn): self.tools[fn.__name__] = fn; return fn
            return deco
        def run(self): raise RuntimeError("`mcp` SDK not installed - pip install mcp")

from src.core import build

def _mk_mcp(name, description=""):
    """FastMCP compat across SDK versions (description -> instructions -> bare)."""
    try:
        return FastMCP(name, instructions=description)
    except TypeError:
        try:
            return FastMCP(name, description=description)
        except TypeError:
            return FastMCP(name)

mcp = _mk_mcp("agent-metering-agent",
              description="Usage metering + SLA accounting for agent services "
                          "(the meter behind x402 micropayments).")
agent = build()


async def _run(payload: Dict[str, Any]) -> str:
    return json.dumps(await agent.process(payload), default=str, indent=2)


@mcp.tool()
async def create_meter(provider: str, consumer: str, unit: str,
                 price_minor_per_unit: float, currency: str = "USD",
                 sla_target: float = 0.99) -> str:
    """Create a usage meter between a provider and a consumer agent.

    unit: what is being counted (call, token, kwh, ...). Price is in minor
    currency units (cents) per unit. Returns the meter_id."""
    return await _run({"action": "create_meter", "provider": provider, "consumer": consumer,
                 "unit": unit, "price_minor_per_unit": price_minor_per_unit,
                 "currency": currency, "sla_target": sla_target})


@mcp.tool()
async def record_usage(meter_id: str, event_id: str, quantity: float,
                 outcome: str = "ok", metadata: Optional[Dict[str, Any]] = None) -> str:
    """Record a usage event. Idempotent on event_id (safe to retry — never
    double-billed). outcome is 'ok' or 'error' and feeds the SLA report."""
    return await _run({"action": "record_usage", "meter_id": meter_id, "event_id": event_id,
                 "quantity": quantity, "outcome": outcome, "metadata": metadata or {}})


@mcp.tool()
async def usage_summary(meter_id: str) -> str:
    """Totals for a meter: event count, total quantity, accrued minor units."""
    return await _run({"action": "usage_summary", "meter_id": meter_id})


@mcp.tool()
async def sla_report(meter_id: str) -> str:
    """Pure SLA report: success_rate vs sla_target, breach flag. No mutation."""
    return await _run({"action": "sla_report", "meter_id": meter_id})


@mcp.tool()
async def close_period(meter_id: str) -> str:
    """Freeze all open events into an immutable invoice (exactly-once).
    The invoice amount is what agent-escrow-agent should settle."""
    return await _run({"action": "close_period", "meter_id": meter_id})


@mcp.tool()
async def verify_chain(meter_id: str) -> str:
    """Verify the tamper-evident event hash chain for a meter."""
    return await _run({"action": "verify_chain", "meter_id": meter_id})


@mcp.tool()
async def list_meters() -> str:
    """List all meters with event/invoice counts."""
    return await _run({"action": "list_meters"})


@mcp.tool()
async def list_events(meter_id: Optional[str] = None, provider: Optional[str] = None,
                      consumer_class: Optional[str] = None, channel: Optional[str] = None,
                      outcome: Optional[str] = None, since: Optional[str] = None,
                      until: Optional[str] = None, include_test: bool = False,
                      limit: int = 100, cursor: Optional[str] = None) -> str:
    """Read usage events (paginated, read-only). Filter by meter, provider,
    consumer_class (internal|external|unknown), channel, outcome (ok|error),
    and ISO date range [since, until). Test-flagged events are excluded
    unless include_test=true. Returns events + next_cursor."""
    payload = {"action": "list_events", "include_test": include_test, "limit": limit}
    for k, v in (("meter_id", meter_id), ("provider", provider),
                 ("consumer_class", consumer_class), ("channel", channel),
                 ("outcome", outcome), ("since", since), ("until", until),
                 ("cursor", cursor)):
        if v is not None:
            payload[k] = v
    return await _run(payload)


@mcp.tool()
async def usage_timeseries(bucket: str = "day", provider: Optional[str] = None,
                           meter_id: Optional[str] = None,
                           consumer_class: Optional[str] = None,
                           channel: Optional[str] = None, since: Optional[str] = None,
                           until: Optional[str] = None, include_test: bool = False) -> str:
    """Usage time series bucketed on each event's recorded_at (UTC;
    bucket=day|hour), grouped across meters by provider — a real time-series
    primitive, independent of meter creation times. Includes per-bucket
    breakdowns by consumer_class / channel / provider. est_accrued_minor is
    an estimate; authoritative billing stays with usage_summary."""
    payload = {"action": "usage_timeseries", "bucket": bucket,
               "include_test": include_test}
    for k, v in (("provider", provider), ("meter_id", meter_id),
                 ("consumer_class", consumer_class), ("channel", channel),
                 ("since", since), ("until", until)):
        if v is not None:
            payload[k] = v
    return await _run(payload)


@mcp.tool()
async def flag_meter(meter_id: str, is_test: bool, admin_token: str,
                     note: str = "") -> str:
    """Admin: flag/unflag a meter as test/synthetic so its events are
    excluded from usage statistics by default. Touches meter metadata only —
    never events, never the hash chain, never billing accruals. Requires the
    server's VIRIDIS_ADMIN_TOKEN."""
    return await _run({"action": "flag_meter", "meter_id": meter_id,
                       "is_test": is_test, "admin_token": admin_token,
                       "note": note})


@mcp.tool()
async def describe_agent() -> str:
    """Fleet-standard self-description."""
    return json.dumps(agent.describe(), default=str, indent=2)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        mcp.run()
    else:
        print(json.dumps(agent.describe(), default=str, indent=2))
        print(json.dumps(asyncio.run(agent.health()), default=str, indent=2))
