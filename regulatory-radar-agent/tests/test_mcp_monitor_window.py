"""MCP window parameter must reach the core under its canonical name."""
import json

import pytest

from adapters import mcp_server


class RecordingCore:
    def __init__(self):
        self.calls = []

    async def process(self, payload):
        self.calls.append(payload)
        return {"status": "success", "received": payload}


@pytest.mark.asyncio
async def test_monitor_changes_maps_since_days_and_topics(monkeypatch):
    core = RecordingCore()
    monkeypatch.setattr(mcp_server, "agent", core)

    result = json.loads(await mcp_server.monitor_changes(
        "US", since_days=45, topics=["emissions", "climate"]))

    assert result["status"] == "success"
    assert core.calls == [{
        "action": "monitor_changes",
        "jurisdiction": "US",
        "lookback_days": 45,
        "topics": ["emissions", "climate"],
    }]
