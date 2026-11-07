"""Fleet contract for the Wavefunction Field mount (replaces the prototype shim)."""

import asyncio
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("WF_DB_PATH", str(tmp_path / "field.sqlite3"))
    monkeypatch.setenv("WF_FIELD_KEY_FILE", str(tmp_path / "field.key"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("wf_adapter_test", ROOT / "adapters/mcp_server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_versions_match_manifest(adapter):
    manifest = (ROOT / "agent.yaml").read_text()
    version = re.search(r'^version:\s*"([^"]+)"', manifest, re.MULTILINE).group(1)
    assert adapter.agent.describe()["version"] == version
    assert asyncio.run(adapter.agent.health())["version"] == version


def test_fleet_contract_status_and_never_raises(adapter):
    ok = asyncio.run(adapter.agent.process({"action": "field_info"}))
    assert ok["status"] == "ok" and ok["result"]["protocol"] == "wavefunction-field-v1"
    for bad in (None, 3, {"action": "nope"}, {"action": "route", "intent_id": "x"}):
        out = asyncio.run(adapter.agent.process(bad))
        assert out["status"] == "error" and out["error"]["error_type"]


def test_gateway_snapshot_of_core_is_empty(adapter):
    assert vars(adapter.agent) == {}


def test_tools_registered(adapter):
    async def names():
        return {t.name for t in await adapter.mcp.list_tools()}
    assert {"describe_agent", "field_info", "sense", "route", "submit_signed"} <= asyncio.run(names())
