"""MD1-MD4: every input described; serverInfo.version is the agent release."""
import json

from starlette.testclient import TestClient

from adapters import mcp_server
from adapters.tool_docs import TOOL_DOCS, COMMON
from src.core import VERSION


def test_md1_every_input_described():
    report = mcp_server.TOOL_DOCS_REPORT
    assert report["inputs"]["missing"] == []
    assert report["inputs"]["described"] + report["inputs"]["already"] >= 131
    for tool in mcp_server.mcp._tool_manager._tools.values():
        for arg, prop in tool.parameters.get("properties", {}).items():
            text = prop.get("description", "")
            assert 8 <= len(text) <= 300, (tool.name, arg)


def test_md1_docs_name_only_real_tools_and_inputs():
    tools = mcp_server.mcp._tool_manager._tools
    for tool, args in TOOL_DOCS.items():
        assert tool in tools, tool
        assert set(args) <= set(tools[tool].parameters.get("properties", {})), tool
    assert "auth" in COMMON and "idempotency_key" in COMMON


def test_md3_initialize_reports_the_agent_release():
    import main
    with TestClient(main.app) as client:
        r = client.post("/mcp", headers={"content-type": "application/json",
                                         "accept": "application/json, text/event-stream",
                                         "host": "127.0.0.1:8410"},
                        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                            "protocolVersion": "2025-06-18", "capabilities": {},
                            "clientInfo": {"name": "t", "version": "0"}}})
        text = r.text
        for line in text.splitlines():
            if line.startswith("data:"):
                text = line[5:]
        info = json.loads(text)["result"]["serverInfo"]
    assert info["version"] == VERSION
