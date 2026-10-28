"""The scan_regulations MCP tool must expose the core's free-text query filter.

The core (scan_regulations / validate_scan_input) accepts and applies a `query`
text filter, but the MCP adapter previously dropped it from its signature, so
MCP callers could not reach it. This pins the passthrough so the public MCP
surface stays faithful to the core's documented capability.
"""
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
async def test_scan_regulations_forwards_query(monkeypatch):
    core = RecordingCore()
    monkeypatch.setattr(mcp_server, "agent", core)

    result = json.loads(await mcp_server.scan_regulations(
        "EU", sector="energy", query="methane"))

    assert result["status"] == "success"
    assert core.calls == [{
        "action": "scan",
        "jurisdiction": "EU",
        "sector": "energy",
        "query": "methane",
    }]


@pytest.mark.asyncio
async def test_scan_regulations_omits_empty_query(monkeypatch):
    core = RecordingCore()
    monkeypatch.setattr(mcp_server, "agent", core)

    await mcp_server.scan_regulations("US")

    # No query key when none supplied — byte-identical to the pre-change payload.
    assert core.calls == [{
        "action": "scan",
        "jurisdiction": "US",
        "sector": None,
    }]
