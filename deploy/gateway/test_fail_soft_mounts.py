import sys
from pathlib import Path

from starlette.testclient import TestClient

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import viridis_mcp_gateway as gateway


def test_one_leaf_import_failure_degrades_without_bricking_fleet(
        tmp_path, monkeypatch):
    original = gateway._load_adapter

    def fail_smartscale(path, agent_dir):
        if path == "smartscale":
            raise ImportError("synthetic smartscale import failure")
        return original(path, agent_dir)

    monkeypatch.setattr(gateway, "_load_adapter", fail_smartscale)
    monkeypatch.setattr(gateway, "EXTERNAL_MEMBERS", [])
    monkeypatch.setenv("STATE_DB", str(Path(tmp_path) / "state.db"))

    with TestClient(gateway.build_app()) as client:
        health_response = client.get("/healthz")
        directory_response = client.get("/")

    assert health_response.status_code == 503
    health = health_response.json()
    assert health["status"] == "degraded"
    assert health["agents"]["smartscale"]["status"] == "degraded"
    assert "smartscale" in health["mount_errors"]
    assert health["agents"]["identity"]["status"] == "ok"
    assert set(health["metering_persistence"]) == {
        "snapshot_seq", "last_persisted_at"}

    assert directory_response.status_code == 200
    directory = directory_response.json()
    assert directory["status"] == "degraded"
    assert "identity" in directory["agents"]
    assert "smartscale" not in directory["agents"]
