"""Tests for fleet_utils.mcp_errors (invariants E1 to E8 in the module docstring)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import anyio
import pytest

from fleet_utils.mcp_errors import flag_error_results, is_error_result

mcp_types = pytest.importorskip("mcp.types")
from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

from fleet_utils.mcp_output import FleetToolResult, structured_result  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ERROR = {"status": "error", "error_type": "ValidationError", "message": "bad input"}
OK = {"status": "ok", "data": {"answer": 42}}
_READ = mcp_types.ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                  idempotentHint=True, openWorldHint=False)


def _server():
    mcp = FastMCP("probe-target")

    @mcp.tool(annotations=_READ)
    async def async_text(fail: bool = False) -> str:
        """Async tool returning JSON text."""
        return json.dumps(ERROR if fail else OK, indent=2)

    @mcp.tool()
    def sync_text(fail: bool = False) -> str:
        """Sync tool returning JSON text."""
        return json.dumps(ERROR if fail else OK)

    @mcp.tool(structured_output=True)
    async def structured(fail: bool = False) -> FleetToolResult:
        """Tool using the fleet structured-output contract."""
        return structured_result(ERROR if fail else OK)

    @mcp.tool()
    def plain_text() -> str:
        """Non-JSON text that mentions an error."""
        return 'status: "error" is just prose here'

    @mcp.tool()
    def json_list() -> str:
        """A JSON value that is not an object."""
        return json.dumps([{"status": "error"}])

    @mcp.tool()
    def raises() -> str:
        """A tool that raises."""
        raise RuntimeError("boom")

    return mcp, {"async_text": async_text, "sync_text": sync_text}


async def _call(mcp, name, args=None):
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        return await client.call_tool(name, args or {})


async def _list(mcp):
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        return [t.model_dump() for t in (await client.list_tools()).tools]


def _run(coro_fn, *args):
    return anyio.run(coro_fn, *args)


def test_is_error_result_shapes():
    assert is_error_result(json.dumps(ERROR))
    assert is_error_result(ERROR)
    assert is_error_result(json.dumps(ERROR).encode())
    assert not is_error_result(json.dumps(OK))
    assert not is_error_result({"status": "ERROR"})
    assert not is_error_result("not json")
    assert not is_error_result(json.dumps([ERROR]))
    assert not is_error_result(None)


@pytest.mark.parametrize("name", ["async_text", "sync_text", "structured"])
def test_error_envelope_sets_is_error_and_keeps_body(name):
    plain, _ = _server()
    before = _run(_call, plain, name, {"fail": True})
    flagged, _ = _server()
    assert flag_error_results(flagged) == 6
    after = _run(_call, flagged, name, {"fail": True})

    assert before.isError is False  # the bug this module fixes
    assert after.isError is True  # E1
    assert [c.model_dump() for c in after.content] == \
        [c.model_dump() for c in before.content]  # E2
    assert after.structuredContent == before.structuredContent  # E2


@pytest.mark.parametrize("name,args", [("async_text", {}), ("sync_text", {}),
                                       ("structured", {}), ("plain_text", {}),
                                       ("json_list", {})])
def test_other_results_unchanged(name, args):
    plain, _ = _server()
    flagged, _ = _server()
    flag_error_results(flagged)
    before = _run(_call, plain, name, args)
    after = _run(_call, flagged, name, args)
    assert after.isError is False  # E3
    assert after.model_dump() == before.model_dump()


def test_exceptions_propagate_as_before():
    plain, _ = _server()
    flagged, _ = _server()
    flag_error_results(flagged)
    before = _run(_call, plain, "raises")
    after = _run(_call, flagged, "raises")
    assert after.isError is True and after.model_dump() == before.model_dump()  # E8


def test_direct_calls_and_listing_unchanged_and_idempotent():
    plain, _ = _server()
    flagged, fns = _server()
    assert flag_error_results(flagged) == 6
    assert flag_error_results(flagged) == 0  # E5
    assert anyio.run(lambda: fns["async_text"](fail=True)) == json.dumps(ERROR, indent=2)  # E4
    assert fns["sync_text"](fail=True) == json.dumps(ERROR)  # E4
    assert _run(_list, flagged) == _run(_list, plain)  # E7


def test_noop_without_mcp_sdk():
    code = (
        "import sys; sys.modules['mcp'] = None; sys.modules['mcp.types'] = None\n"
        "from fleet_utils.mcp_errors import flag_error_results\n"
        "class Shim: tools = {}\n"
        "assert flag_error_results(Shim()) == 0\n"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    subprocess.run([sys.executable, "-c", code], check=True, env=env, cwd=ROOT)  # E6


ADAPTERS = sorted(
    p for p in ROOT.glob("*/adapters/mcp_server.py")
    if not p.parts[-3].startswith((".", "_"))
)


@pytest.mark.parametrize("adapter", ADAPTERS, ids=lambda p: p.parts[-3])
def test_every_fleet_adapter_flags_errors(adapter):
    """Each adapter wraps all of its registered tools at import time."""
    code = (
        "import importlib\n"
        "mod = importlib.import_module('adapters.mcp_server')\n"
        "tools = mod.mcp._tool_manager.list_tools()\n"
        "bare = [t.name for t in tools if not getattr(t.fn, '__fleet_flags_errors__', False)]\n"
        "assert tools and not bare, bare\n"
    )
    agent = adapter.parents[1]
    env = {**os.environ,
           "PYTHONPATH": os.pathsep.join(filter(None, (str(ROOT), str(agent),
                                                       os.environ.get("PYTHONPATH"))))}
    r = subprocess.run([sys.executable, "-c", code], cwd=agent, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
