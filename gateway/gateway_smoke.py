#!/usr/bin/env python3
"""Live-gateway smoke: real MCP client over streamable-http against a running
gateway (default http://127.0.0.1:8402). Run the gateway first, then this.
Exits non-zero on any failure. 7 protocol checks across 5 agents."""
import asyncio, json, os
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

BASE = os.environ.get("BASE", "http://127.0.0.1:8402").rstrip("/")

async def call(path, tool, args):
    async with streamablehttp_client(f"{BASE}/{path}/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(tool, args)
            return res.content[0].text

async def tools(path):
    async with streamablehttp_client(f"{BASE}/{path}/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return [t.name for t in (await s.list_tools()).tools]

async def main():
    checks = []
    def check(label, ok):
        checks.append((label, ok)); print(("  OK   " if ok else "  FAIL ") + label)

    t = await tools("identity")
    check(f"identity: tools/list over HTTP ({len(t)} tools)", "register_agent" in t)
    reg = json.loads(await call("identity", "register_agent",
                                {"agent_id": "live-worker", "capabilities": ["cad"]}))
    check("identity: register over live MCP", reg["status"] == "ok"
          and reg["data"]["did"].startswith("did:"))
    disc = json.loads(await call("identity", "discover_agents", {"capabilities": ["cad"]}))
    check("identity: state persists across MCP sessions", disc["data"]["count"] == 1)
    cov = json.loads(await call("covenant", "grant_covenant",
                                {"principal": "justin", "agent_id": "live-worker",
                                 "scopes": ["offsets.buy"], "budget_minor": 1000,
                                 "expires_at": "2099-01-01T00:00:00+00:00"}))
    cid = cov["data"]["covenant_id"]
    act = json.loads(await call("covenant", "check_act",
                                {"covenant_id": cid, "act_id": "a1",
                                 "scope": "offsets.buy", "amount_minor": 90}))
    check("covenant: authorized act over live MCP", act["data"]["allowed"] is True)
    await call("offsets", "list_credit",
               {"issuer": "viridis", "project_id": "hdfm-7", "mass_g": 1000,
                "price_minor_per_kg": 900, "verification_ref": "dscore:site7"})
    buy = json.loads(await call("offsets", "buy_offset",
                                {"buyer": "live-worker", "purchase_id": "p1", "mass_g": 80}))
    check("offsets: verified credit retired over live MCP",
          buy["data"]["fills"][0]["mass_g"] == 80)
    m = await call("smartscale", "scale_objects_from_credit_card",
                   {"image_id": "i", "credit_card_pixel_width": 856.0,
                    "objects": [{"name": "box", "pixel_width": 1712.0,
                                 "pixel_height": 856.0}]})
    check("smartscale: measurement over live MCP (171.2 mm)", "171.2" in m)
    led = json.loads(await call("compute-ledger", "record_work",
                                {"agent_id": "live-worker", "entry_id": "e1",
                                 "power_w": 200.0, "duration_s": 3600.0, "bit_ops": 1e19}))
    check("compute-ledger: Landauer-validated entry over live MCP",
          led["status"] == "ok" and 0 < led["data"]["landauer_efficiency"] <= 1)
    fails = [l for l, ok in checks if not ok]
    print(f"\nLIVE GATEWAY: {len(checks)-len(fails)}/{len(checks)} protocol checks passed")
    raise SystemExit(1 if fails else 0)

asyncio.run(main())
