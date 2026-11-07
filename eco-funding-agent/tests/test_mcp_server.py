"""MCP server: exactly five read-only tools, working over in-process calls, stdio and
Streamable HTTP."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import threading
import time

import pytest
from conftest import ROOT, clone

pytest.importorskip("mcp")
pytest.importorskip("mcp.server.mcpserver", reason="standalone vef-mcp server needs mcp 2.x")

from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

from viridis_eco_funding.mcp_server import TOOL_NAMES, build_server, main  # noqa: E402
from viridis_eco_funding.vergecommon import ReadOnlyVergeCommonClient  # noqa: E402

EXPECTED = {"value_site", "explain_valuation", "verify_receipt", "simulate_pool", "describe_method"}


def call(server, name, args):
    result = asyncio.run(server.call_tool(name, args))
    return result


def payload(result):
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


def test_exactly_the_five_tools():
    tools = asyncio.run(build_server().list_tools())
    assert {t.name for t in tools} == EXPECTED == set(TOOL_NAMES)


def test_tools_end_to_end_in_process(woodland_site, example_pool, synthetic_record):
    def fake_client():
        return ReadOnlyVergeCommonClient(opener=lambda req, timeout: _resp(synthetic_record))

    server = build_server(client_factory=fake_client)
    valued = payload(call(server, "value_site", {"site": woodland_site, "bind_vergecommon": True}))
    receipt = valued["receipt"]
    assert receipt["source"]["project_kind"] == "woodland"
    assert valued["receipt_seal"] == receipt["seal"]["digest"]

    verified = payload(call(server, "verify_receipt", {"receipt": receipt, "refetch_source": True}))
    assert verified["valid"] is True

    explained = payload(call(server, "explain_valuation", {"valuation_or_site": receipt["result"]}))
    assert explained["steps"][0]["quantity"] == "component_T"

    sim = payload(call(server, "simulate_pool", {"pool": example_pool, "observations": [
        {"id": "baseline", "period": 0, "receipt": receipt}]}))
    assert sim["invariants"] == {"conservation": True, "release_requires_met_rule": True}

    method = payload(call(server, "describe_method", {}))
    assert method["method_version"] == "vef-method/0.1.0"


def test_tool_errors_are_readable(woodland_site):
    from mcp.server.mcpserver.exceptions import ToolError

    server = build_server()
    cases = [("value_site", {"site": {"site_id": "x"}}, "biodiversity"),
             ("simulate_pool", {"pool": {"pool_id": "x"}}, "horizon_periods"),
             ("verify_receipt", {"receipt": {"source": None}, "refetch_source": True},
              "no VergeCommon source"),
             ("explain_valuation", {"valuation_or_site": {"site_id": "x"}}, "biodiversity")]
    for name, args, message in cases:
        with pytest.raises(ToolError, match=message):
            call(server, name, args)


def _resp(obj):
    import io

    class R(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *e):
            return False

    return R(json.dumps(obj).encode())


async def _session_roundtrip(read, write, site):
    async with ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        result = await session.call_tool("value_site", {"site": site})
        data = json.loads(result.content[0].text)
        verify = await session.call_tool("verify_receipt", {"receipt": data["receipt"]})
        bad = await session.call_tool("value_site", {"site": {"site_id": "x"}})
        assert bad.is_error and "biodiversity" in bad.content[0].text  # readable over the wire
        return names, data, json.loads(verify.content[0].text)


def test_stdio_transport(woodland_site):
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "viridis_eco_funding.mcp_server"],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")})

    async def run():
        async with stdio_client(params) as (read, write):
            return await _session_roundtrip(read, write, woodland_site)

    names, data, verify = asyncio.run(run())
    assert names == EXPECTED
    assert "conjecture" in data["explanation"]
    assert verify["valid"] is True


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_streamable_http_transport(woodland_site):
    port = _free_port()
    thread = threading.Thread(
        target=main, args=(["--transport", "streamable-http", "--port", str(port)],), daemon=True)
    thread.start()
    deadline = time.time() + 20
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.1)

    async def run():
        async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as streams:
            read, write = streams[0], streams[1]
            return await _session_roundtrip(read, write, clone(woodland_site))

    names, data, verify = asyncio.run(run())
    assert names == EXPECTED
    assert verify["valid"] is True
