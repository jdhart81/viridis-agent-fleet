"""Exercise the patched FastMCP transport without opening a network port."""
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client

from adapters import mcp_server


@pytest.mark.asyncio
async def test_tools_and_metadata_remain_available():
    async with Client(mcp_server.mcp) as client:
        assert {tool.name for tool in await client.list_tools()} == {
            "process", "health", "describe"
        }
        assert not (await client.call_tool("health")).is_error
        assert not (await client.call_tool("describe")).is_error
        resources = await client.list_resources()
        assert "agent://metadata" in {str(resource.uri) for resource in resources}
        assert await client.read_resource("agent://metadata")


@pytest.mark.asyncio
async def test_async_entrypoint_awaits_transport(monkeypatch):
    run = AsyncMock()
    monkeypatch.setattr(mcp_server.mcp, "run_async", run)
    await mcp_server.main()
    run.assert_awaited_once_with()
