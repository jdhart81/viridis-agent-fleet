#!/usr/bin/env python3
"""Emulate the Viridis gateway mount and exercise every tool over HTTP JSON-RPC.

Loads ``adapters/mcp_server.py`` the way ``deploy/gateway/viridis_mcp_gateway.py`` does
(evict ``src*`` modules, put the agent root first on sys.path, import by file location),
checks the ``mcp`` / ``agent`` contract, mounts the server at ``/eco-funding`` in a
Starlette app on 127.0.0.1, and calls all five tools as an outside agent would.

Run with the gateway's interpreter (mcp==1.28.1) and with mcp 2.x:
    python deploy/fleet/gateway_check.py [--write-tools deploy/fleet/tools.json]
Exit 0 on success. Talks to loopback only.
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
MOUNT = "eco-funding"


def load_adapter():
    for name in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
        del sys.modules[name]
    root = str(AGENT_ROOT)
    while root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)
    spec = importlib.util.spec_from_file_location(
        f"gateway_adapter_{MOUNT.replace('-', '_')}", AGENT_ROOT / "adapters" / "mcp_server.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_app(server):
    from starlette.applications import Starlette
    from starlette.routing import Mount

    settings = getattr(server, "settings", None)
    if settings is not None and hasattr(settings, "stateless_http"):  # mcp 1.x
        settings.stateless_http = True
        settings.json_response = True
        inner = server.streamable_http_app()
    else:  # mcp 2.x
        inner = server.streamable_http_app(stateless_http=True, json_response=True)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with inner.router.lifespan_context(inner):
            yield

    return Starlette(routes=[Mount(f"/{MOUNT}", app=inner)], lifespan=lifespan)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def rpc(url: str, method: str, params: dict, ident: int) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": ident, "method": method, "params": params}).encode()
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "content-type": "application/json", "accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2025-06-18"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # loopback, no proxy
    with opener.open(request, timeout=60) as response:
        text = response.read().decode()
    if text.startswith("event:") or text.startswith("data:"):
        text = next(line[5:].strip() for line in text.splitlines() if line.startswith("data:"))
    return json.loads(text)


def tool_payload(reply: dict) -> dict:
    result = reply["result"]
    if result.get("structuredContent"):
        data = result["structuredContent"]
        return data.get("result", data) if set(data) == {"result"} else data
    return json.loads(result["content"][0]["text"])


def main(argv: list[str]) -> int:
    import uvicorn

    module = load_adapter()
    server, agent = module.mcp, module.agent
    described = agent.describe()
    assert {"name", "version", "capabilities"} <= set(described), "describe() contract"
    assert agent.health()["status"] == "ok", "health() self-test"

    port = free_port()
    config = uvicorn.Config(build_app(server), host="127.0.0.1", port=port, log_level="warning")
    uv = uvicorn.Server(config)
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not uv.started and time.time() < deadline:
        time.sleep(0.05)
    url = f"http://127.0.0.1:{port}/{MOUNT}/mcp"
    try:
        init = rpc(url, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                       "clientInfo": {"name": "gateway-check", "version": "1"}}, 1)
        assert "result" in init, init
        tools = rpc(url, "tools/list", {}, 2)["result"]["tools"]
        names = sorted(t["name"] for t in tools)
        assert names == sorted(["describe_method", "explain_valuation", "simulate_pool",
                                "value_site", "verify_receipt"]), names
        for t in tools:
            ann = t.get("annotations") or {}
            assert ann.get("readOnlyHint") is True and ann.get("destructiveHint") is False, t["name"]

        site = json.loads((AGENT_ROOT / "examples" / "data" / "woodland_site.json").read_text())
        pool = json.loads((AGENT_ROOT / "examples" / "data" / "woodland_pool.json").read_text())
        valued = tool_payload(rpc(url, "tools/call", {"name": "value_site", "arguments": {"site": site}}, 3))
        assert valued["status"] == "ok" and "conjecture" in valued["explanation"], valued.get("message")
        mounts = {step["mount"] for step in valued["next_steps"]}
        assert {"notary", "regulatory-radar", "ghg-ledger"} <= mounts, mounts
        receipt = valued["result"]["receipt"]
        verified = tool_payload(rpc(url, "tools/call", {"name": "verify_receipt",
                                                         "arguments": {"receipt": receipt}}, 4))
        assert verified["result"]["valid"] is True, verified
        sim = tool_payload(rpc(url, "tools/call", {"name": "simulate_pool", "arguments": {
            "pool": pool, "observations": [{"id": "q0", "period": 0, "receipt": receipt}]}}, 5))
        assert sim["result"]["invariants"] == {"conservation": True, "release_requires_met_rule": True}
        method = tool_payload(rpc(url, "tools/call", {"name": "describe_method", "arguments": {}}, 6))
        assert "conjecture" in method["explanation"]
        bad = tool_payload(rpc(url, "tools/call", {"name": "value_site", "arguments": {"site": {"site_id": "x"}}}, 7))
        assert bad["status"] == "error" and bad["error_type"] == "invalid_input", bad

        if "--write-tools" in argv:
            target = Path(argv[argv.index("--write-tools") + 1])
            target.write_text(json.dumps({"server": "viridis-eco-funding", "mount": f"/{MOUNT}/mcp",
                                          "tool_count": len(tools),
                                          "tools": sorted(tools, key=lambda t: t["name"])},
                                         indent=2, sort_keys=True) + "\n")
        import mcp
        version = getattr(mcp, "__version__", None)
        if version is None:
            from importlib.metadata import version as _v
            version = _v("mcp")
        print(json.dumps({"ok": True, "mcp": version, "endpoint": f"/{MOUNT}/mcp", "tools": names,
                          "receipt_seal": valued["result"]["receipt_seal"],
                          "released_minor": sim["result"]["totals"]["released_minor"]}))
        return 0
    finally:
        uv.should_exit = True
        thread.join(timeout=10)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
