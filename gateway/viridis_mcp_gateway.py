#!/usr/bin/env python3
"""
Viridis Agent Stable — MCP Gateway (deployment round 1).

One process, thirteen hosted MCP servers. Each agent's existing
adapters/mcp_server.py is loaded unmodified and mounted at the path its
registry manifest already declares:

    https://<host>/identity/mcp        agent-identity-registry-agent
    https://<host>/trust/mcp           agent-trust-oracle-agent
    https://<host>/escrow/mcp          agent-escrow-agent
    https://<host>/metering/mcp        agent-metering-agent
    https://<host>/arbitration/mcp     agent-arbitration-agent
    https://<host>/compute-ledger/mcp  agent-compute-ledger-agent
    https://<host>/covenant/mcp        agent-covenant-agent
    https://<host>/provenance/mcp      agent-provenance-agent
    https://<host>/offsets/mcp         agent-offset-clearinghouse-agent
    https://<host>/smartscale/mcp      smartscale-agent
    https://<host>/protogen/mcp        protogen-agent
    https://<host>/regulatory-radar/mcp regulatory-radar-agent
    https://<host>/narrative-engine/mcp narrative-engine-agent

Plus GET /healthz (fleet-wide health) and GET / (directory).

Run:
    pip install mcp uvicorn
    python3 deploy/gateway/viridis_mcp_gateway.py --port 8402

State note: cores are in-memory (stdlib-only by design). Round 1 ships
stateless-restart semantics; the persistence adapter is a tracked follow-up.
"""
import argparse
import contextlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# mount path -> agent directory (paths match deploy/mcp-publish manifests)
MOUNTS = {
    "identity":         "agent-identity-registry-agent",
    "trust":            "agent-trust-oracle-agent",
    "escrow":           "agent-escrow-agent",
    "metering":         "agent-metering-agent",
    "arbitration":      "agent-arbitration-agent",
    "compute-ledger":   "agent-compute-ledger-agent",
    "covenant":         "agent-covenant-agent",
    "provenance":       "agent-provenance-agent",
    "offsets":          "agent-offset-clearinghouse-agent",
    "smartscale":       "smartscale-agent",
    "protogen":         "protogen-agent",
    "regulatory-radar": "regulatory-radar-agent",
    "narrative-engine": "narrative-engine-agent",
}


def _load_adapter(path: str, agent_dir: str):
    """Load an agent's adapter module in isolation.

    Every adapter does `sys.path.insert(0, <its root>)` and imports `src.core`.
    Between loads we evict all `src*` modules and put the agent's root at the
    front of sys.path, so each adapter binds to ITS OWN core.
    """
    for mod in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
        del sys.modules[mod]
    agent_root = str(ROOT / agent_dir)
    while agent_root in sys.path:
        sys.path.remove(agent_root)
    sys.path.insert(0, agent_root)
    spec = importlib.util.spec_from_file_location(
        f"gateway_adapter_{path.replace('-', '_')}",
        ROOT / agent_dir / "adapters" / "mcp_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def build_app():
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    adapters = {}
    for path, agent_dir in MOUNTS.items():
        adapters[path] = _load_adapter(path, agent_dir)
    servers = {path: mod.mcp for path, mod in adapters.items()}
    cores = {path: mod.agent for path, mod in adapters.items()}

    # stateless_http: no session persistence needed for these tools; makes the
    # endpoints trivially load-balancer-friendly.
    # Round-1 posture: endpoints are open. The MCP streamable-http default
    # DNS-rebinding guard only trusts localhost and 421s real callers, so we
    # accept any Host — the gateway must work behind fly.dev and
    # mcp.viridis.earth. (Auth/allowlist attaches before money moves.)
    _sec = None
    try:
        from mcp.server.transport_security import TransportSecuritySettings
        _sec = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
            allowed_hosts=["*"], allowed_origins=["*"])
    except Exception:
        _sec = None
    for s in servers.values():
        s.settings.stateless_http = True
        if _sec is not None:
            try:
                s.settings.transport_security = _sec
            except Exception:
                pass

    routes = [Mount(f"/{path}", app=s.streamable_http_app())
              for path, s in servers.items()]

    async def healthz(request):
        import asyncio
        checks = {}
        for path, core in cores.items():
            h = core.health()
            checks[path] = (await h) if asyncio.iscoroutine(h) else h
        ok = all(c.get("status") == "ok" for c in checks.values())
        return JSONResponse({"status": "ok" if ok else "degraded",
                             "gateway": "viridis-agent-stable",
                             "agents": checks}, status_code=200 if ok else 503)

    async def directory(request):
        return JSONResponse({
            "gateway": "viridis-agent-stable",
            "agents": {path: {"endpoint": f"/{path}/mcp",
                              **{k: cores[path].describe()[k]
                                 for k in ("name", "version", "capabilities")}}
                       for path in MOUNTS},
        })

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with contextlib.AsyncExitStack() as stack:
            for s in servers.values():
                await stack.enter_async_context(s.session_manager.run())
            yield

    return Starlette(routes=[Route("/", directory), Route("/healthz", healthz),
                             *routes],
                     lifespan=lifespan)


app = None  # built lazily; `uvicorn viridis_mcp_gateway:get_app --factory` also works


def get_app():
    global app
    if app is None:
        app = build_app()
    return app


if __name__ == "__main__":
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8402)  # HTTP 402: payment required — the x402 wink
    args = ap.parse_args()
    print(f"Viridis Agent Stable gateway: {len(MOUNTS)} agents on "
          f"http://{args.host}:{args.port}  (paths: {', '.join('/' + p + '/mcp' for p in MOUNTS)})")
    uvicorn.run(get_app(), host=args.host, port=args.port, log_level="warning")
