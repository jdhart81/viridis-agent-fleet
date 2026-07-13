#!/usr/bin/env python3
"""
Viridis Agent Fleet — single-install stdio bridge.

Exposes the entire hosted fleet (17 agents on mcp.viridisconservation.com) as
ONE stdio MCP server, so a user can install the whole trust-and-settlement
economy with a single entry in Claude Desktop / Cursor:

    { "command": "python3", "args": ["fleet_bridge.py"] }

Also the artifact Glama builds for its automated safety/quality checks: it
starts, connects to the live endpoints, lists their tools, and re-exposes them
namespaced `agent__tool` (e.g. `escrow__open_escrow`). Read-only introspection
at startup; every call is forwarded to the corresponding hosted agent.

Resilience: each endpoint is probed with a short timeout at startup; an
endpoint that is slow or down is skipped (logged) and never blocks the others —
the bridge always starts.
"""
import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List, Tuple

logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s fleet-bridge %(levelname)s %(message)s")
log = logging.getLogger("fleet-bridge")

BASE = os.environ.get("VIRIDIS_BASE",
                      "https://mcp.viridisconservation.com").rstrip("/")

# path -> role label (kept in sync with the gateway MOUNTS + ARD catalog)
AGENTS: List[Tuple[str, str]] = [
    ("identity", "verifiable agent identity + capability discovery"),
    ("trust", "decay-weighted reputation + trust attestations"),
    ("escrow", "trustless escrow & settlement (exactly-once)"),
    ("metering", "usage metering + SLA accounting (x402 meter)"),
    ("arbitration", "deterministic dispute rulings"),
    ("compute-ledger", "compute-is-carbon energy/carbon ledger"),
    ("covenant", "deny-by-default authority leases"),
    ("provenance", "genesis certificates, lineage, recalls"),
    ("offsets", "verified-credit carbon offset clearinghouse"),
    ("erc8004", "MCP-native bridge to ERC-8004 on-chain identity"),
    ("surety", "bonding + ruling-gated slashing (risk transfer)"),
    ("notary", "commit-reveal verifiable delivery proofs"),
    ("wavefunction", "demand-side agent/collective discovery"),
    ("smartscale", "credit-card-calibrated visual measurement"),
    ("protogen", "MCP CAD services (measure -> CAD)"),
    ("regulatory-radar", "CSRD/TNFD compliance-as-a-service"),
    ("narrative-engine", "grant/investor/policy narrative generation"),
]

CONNECT_TIMEOUT = float(os.environ.get("VIRIDIS_CONNECT_TIMEOUT", "8"))


def _sep() -> str:
    return "__"


async def _list_agent_tools(path: str):
    """Return the hosted agent's tool objects (short timeout; raises on fail)."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    url = f"{BASE}/{path}/mcp"

    async def _do():
        async with streamablehttp_client(url) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return (await s.list_tools()).tools
    return await asyncio.wait_for(_do(), timeout=CONNECT_TIMEOUT)


async def _call_agent_tool(path: str, tool: str, args: Dict[str, Any]) -> str:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    url = f"{BASE}/{path}/mcp"
    async with streamablehttp_client(url) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(tool, args or {})
            parts = []
            for c in res.content:
                parts.append(getattr(c, "text", None) or json.dumps(
                    getattr(c, "model_dump", lambda: {})(), default=str))
            return "\n".join(p for p in parts if p) or "{}"


async def discover() -> Dict[str, list]:
    """Map path -> tool list for every reachable agent (skips failures)."""
    out: Dict[str, list] = {}
    results = await asyncio.gather(
        *[_list_agent_tools(p) for p, _ in AGENTS], return_exceptions=True)
    for (path, _role), r in zip(AGENTS, results):
        if isinstance(r, Exception):
            log.warning("skip %s (%s: %s)", path, type(r).__name__, r)
            continue
        out[path] = r
        log.info("mounted %s (%d tools)", path, len(r))
    return out


def build_server(discovered: Dict[str, list]):
    """Assemble a FastMCP stdio server exposing namespaced fleet tools."""
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP(
        "viridis-agent-fleet",
        instructions=("The trust-and-settlement rails of the agent economy in "
                      "one server: identity, trust, escrow, metering, "
                      "arbitration, compute-carbon ledger, covenant, "
                      "provenance, offsets, ERC-8004 bridge, surety, notary, "
                      "discovery, plus measurement/CAD services. Tools are "
                      "namespaced <agent>__<tool>. Rails are free; the two "
                      "services (smartscale, protogen) offer 100 free "
                      "calls/day then paid. Live at " + BASE + "."))

    role = dict(AGENTS)
    for path, tools in discovered.items():
        for t in tools:
            fq = f"{path}{_sep()}{t.name}"
            desc = (f"[{path} — {role.get(path, '')}] "
                    f"{(t.description or '').strip()}").strip()
            schema = getattr(t, "inputSchema", None) or {"type": "object"}

            def _make(_path=path, _tool=t.name):
                async def _fn(**kwargs) -> str:
                    return await _call_agent_tool(_path, _tool, kwargs)
                return _fn

            # register with the tool's own input schema so callers get typed args
            mcp.add_tool(_make(), name=fq, description=desc[:1024],
                         structured_output=False)
            # attach the upstream schema (FastMCP builds its own from signature;
            # we override to preserve the hosted tool's contract)
            try:
                mcp._tool_manager._tools[fq].parameters = schema  # noqa: SLF001
            except Exception:
                pass
    return mcp


async def _amain():
    discovered = await discover()
    total = sum(len(v) for v in discovered.values())
    log.info("fleet bridge ready: %d agents, %d tools", len(discovered), total)
    if not discovered:
        log.error("no agents reachable at %s — check the gateway", BASE)
    return build_server(discovered)


def main():
    mcp = asyncio.run(_amain())
    mcp.run()   # stdio transport


if __name__ == "__main__":
    main()
