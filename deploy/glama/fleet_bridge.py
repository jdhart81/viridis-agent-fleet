#!/usr/bin/env python3
"""
Viridis Agent Fleet — single-install stdio bridge.

Exposes the entire hosted fleet on mcp.viridisconservation.com as
ONE stdio MCP server, so a user can install the whole trust-and-settlement
economy with a single entry in Claude Desktop / Cursor. Tools are namespaced
`agent__tool` (e.g. `escrow__open_escrow`, `surety__slash_bond`); every call is
forwarded to the corresponding hosted agent.

Design for reliability (this is also the artifact Glama builds for its
automated safety/quality checks):

  * Tool LISTING is network-independent — it is served from a bundled manifest
    (`fleet_manifest.json`, generated from the live fleet). The server always
    advertises the bundled fleet tools (141 expected for 19 hosted agents plus
    the subscriptions infrastructure surface) even if the check sandbox blocks
    outbound network.
  * Tool CALLS forward to the live hosted endpoint at runtime (works wherever
    the container has network, i.e. real user installs).
  * Built on the low-level `mcp.server.Server` API (stable across SDK versions)
    — no reliance on FastMCP internals.
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s fleet-bridge %(levelname)s %(message)s")
log = logging.getLogger("fleet-bridge")

BASE = os.environ.get("VIRIDIS_BASE",
                      "https://mcp.viridisconservation.com").rstrip("/")
HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "fleet_manifest.json"
SEP = "__"

ROLE = {
    "identity": "verifiable agent identity + capability discovery",
    "trust": "decay-weighted reputation + trust attestations",
    "escrow": "trustless escrow & settlement (exactly-once)",
    "metering": "usage metering + SLA accounting (x402 meter)",
    "arbitration": "deterministic dispute rulings",
    "compute-ledger": "compute-is-carbon energy/carbon ledger",
    "covenant": "deny-by-default authority leases",
    "provenance": "genesis certificates, lineage, recalls",
    "offsets": "verified-credit carbon offset clearinghouse",
    "erc8004": "MCP-native bridge to ERC-8004 on-chain identity",
    "surety": "bonding + ruling-gated slashing (risk transfer)",
    "notary": "commit-reveal verifiable delivery proofs",
    "wavefunction": "demand-side agent/collective discovery",
    "smartscale": "credit-card-calibrated visual measurement",
    "protogen": "MCP CAD services (measure -> CAD)",
    "regulatory-radar": "CSRD/TNFD compliance-as-a-service",
    "narrative-engine": "grant/investor/policy narrative generation",
    "taxcredit-engine": "clean-energy tax-credit scenarios (45Q/45V/45Y/48E/45X)",
    "ghg-ledger": "deterministic GHG inventories (Scope 1/2/3 + dual Scope 2)",
    "subscriptions": "B2B monthly seats, entitlement quota, overage, and MRR",
}


def upstream_headers() -> Dict[str, str] | None:
    """Return opt-in bearer attribution for a *private* bridge install.

    The public Glama build must not set VIRIDIS_ACCOUNT_KEY: one shared key
    would pool every Glama user's usage into the same buyer account.  A human
    running this bridge privately may set the variable to forward their own
    account key without putting it in tool arguments or the manifest.
    """
    token = os.environ.get("VIRIDIS_ACCOUNT_KEY", "").strip()
    if not token:
        return None
    if len(token) > 256 or any(ord(ch) < 33 for ch in token):
        log.warning("VIRIDIS_ACCOUNT_KEY is malformed; forwarding anonymously")
        return None
    return {"Authorization": f"Bearer {token}"}


def load_manifest() -> Dict[str, list]:
    try:
        return json.loads(MANIFEST_PATH.read_text())
    except Exception as e:
        log.error("could not read %s (%s) — starting with empty tool set; "
                  "regenerate the manifest from the live fleet", MANIFEST_PATH, e)
        return {}


def build_tool_index(manifest: Dict[str, list]):
    """Return (mcp_types.Tool list, {fq_name: (path, upstream_tool)})."""
    from mcp import types
    tools = []
    route: Dict[str, tuple] = {}
    for path, items in manifest.items():
        for t in items:
            fq = f"{path}{SEP}{t['name']}"
            desc = (f"[{path} — {ROLE.get(path, '')}] "
                    f"{(t.get('description') or '').strip()}").strip()
            tools.append(types.Tool(
                name=fq, description=desc[:1024],
                inputSchema=t.get("inputSchema") or {"type": "object"}))
            route[fq] = (path, t["name"])
    return tools, route


async def forward(path: str, tool: str, args: Dict[str, Any]) -> str:
    """Forward a call to the hosted agent over streamable-http."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    url = f"{BASE}/{path}/mcp"
    async with streamablehttp_client(
            url, headers=upstream_headers()) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(tool, args or {})
            parts = []
            for c in res.content:
                parts.append(getattr(c, "text", None) or "")
            return "\n".join(p for p in parts if p) or "{}"


def main():
    from mcp import types
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.server.models import InitializationOptions
    from mcp.server import NotificationOptions

    manifest = load_manifest()
    tools, route = build_tool_index(manifest)
    log.info("fleet bridge: %d agents, %d tools (manifest); calls forward to %s",
             len(manifest), len(tools), BASE)

    server = Server("viridis-agent-fleet")

    @server.list_tools()
    async def list_tools() -> List[types.Tool]:
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any] | None):
        if name not in route:
            return [types.TextContent(type="text",
                    text=json.dumps({"status": "error",
                                     "error": f"unknown tool '{name}'"}))]
        path, tool = route[name]
        try:
            out = await forward(path, tool, arguments or {})
        except Exception as e:
            out = json.dumps({"status": "error", "error_type": type(e).__name__,
                              "error": str(e)[:300],
                              "hint": f"forwarding to {BASE}/{path}/mcp failed — "
                                      "this container needs outbound network to "
                                      "reach the hosted fleet"})
        return [types.TextContent(type="text", text=out)]

    async def _run():
        async with stdio_server() as (r, w):
            await server.run(r, w, InitializationOptions(
                server_name="viridis-agent-fleet",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={})))

    asyncio.run(_run())


if __name__ == "__main__":
    main()
