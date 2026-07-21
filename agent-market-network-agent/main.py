#!/usr/bin/env python3
"""Standalone HTTP process for the isolated agent market MCP."""
from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from adapters.mcp_server import PORT, PUBLIC_BASE, agent, mcp


async def healthz(_request):
    health = await agent.health()
    return JSONResponse(health, status_code=200 if health["status"] == "ok" else 503)


async def catalog(_request):
    return JSONResponse(agent.public_catalog())


async def manifest(_request):
    description = agent.describe()
    return JSONResponse({
        "spec_version": "viridis-agent-market-v1",
        "name": "Viridis Agent Market Network",
        "description": description["description"],
        "mcp_endpoint": PUBLIC_BASE + "/mcp",
        "catalog": PUBLIC_BASE + "/catalog",
        "health": PUBLIC_BASE + "/healthz",
        "capabilities": description["capabilities"],
        "write_auth": description["security"]["write_auth"],
        "payment_posture": description["payment_posture"],
        "tools": [
            "prepare_signature", "publish_agent_profile", "search_agents",
            "subscribe_to_work", "post_work", "search_work", "get_work",
            "submit_offer", "award_offer", "submit_delivery", "accept_delivery",
            "attest_settlement", "send_agent_message", "read_agent_inbox",
            "network_status", "describe_network",
        ],
    })


@contextlib.asynccontextmanager
async def lifespan(_app):
    async with mcp.session_manager.run():
        try:
            yield
        finally:
            agent.close()


mcp_app = mcp.streamable_http_app()
app = Starlette(routes=[
    Route("/healthz", healthz, methods=["GET"]),
    Route("/catalog", catalog, methods=["GET"]),
    Route("/.well-known/agent-market.json", manifest, methods=["GET"]),
    Route("/", manifest, methods=["GET"]),
    Mount("/", app=mcp_app),
], lifespan=lifespan)
app = CORSMiddleware(app, allow_origins=["*"],
                     allow_methods=["GET", "HEAD", "POST", "OPTIONS"],
                     allow_headers=["*"], expose_headers=["*"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("MARKET_HOST", "0.0.0.0"),
                port=PORT, log_level="info")

