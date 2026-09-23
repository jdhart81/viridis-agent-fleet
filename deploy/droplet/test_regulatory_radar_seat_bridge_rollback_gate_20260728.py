import hashlib
import json

import pytest

from deploy.droplet import (
    regulatory_radar_seat_bridge_rollback_gate_20260728 as gate,
)


def write(path, payload):
    if isinstance(payload, dict):
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    else:
        path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def evidence(tmp_path):
    rows = {
        f"agent-{index}": {
            "attributes": 1,
            "current_core_loaded": True,
        }
        for index in range(34)
    }
    rows["security-preflight"] = {
        "attributes": 2,
        "current_core_loaded": True,
    }
    snapshot = tmp_path / "snapshot.json"
    health = tmp_path / "health.json"
    final = tmp_path / "final.json"
    before = tmp_path / "before.sha256"
    after = tmp_path / "after.sha256"
    pins = {
        "snapshot_sha256": write(
            snapshot,
            {
                "status": "ok",
                "errors": {},
                "adapter_load_errors": {},
                "rows": rows,
            },
        ),
        "health_sha256": write(
            health,
            {
                "status": "ok",
                "http_status": 503,
                "gateway_status": "degraded",
                "agent_count": 28,
                "degraded_agents": ["hive"],
                "security_preflight_version": "1.1.0",
                "payment_enabled": False,
            },
        ),
        "final_state_sha256": write(
            final,
            {
                "integrity": "ok",
                "rows": 35,
                "sha256": gate.EXPECTED_OLD_IMAGE_FINAL_SHA256,
            },
        ),
        "source_before_sha256": write(
            before,
            f"{gate.EXPECTED_NORMALIZED_SOURCE_SHA256}  source.db\n",
        ),
        "source_after_sha256": write(
            after,
            f"{gate.EXPECTED_NORMALIZED_SOURCE_SHA256}  source.db\n",
        ),
    }
    return (snapshot, health, final, before, after, pins)


def verify(evidence):
    snapshot, health, final, before, after, pins = evidence
    return gate.verify_rollback_drill(
        snapshot,
        health,
        final,
        before,
        after,
        **pins,
    )


def test_gate_accepts_exact_old_image_rollback_drill(evidence):
    result = verify(evidence)
    assert result["status"] == "ok"
    assert result["agent_state_rows"] == 35
    assert result["normalized_source_unchanged"] is True
    assert result["old_image_clean_stop_integrity"] == "ok"


def test_gate_refuses_evidence_byte_drift(evidence):
    evidence[0].write_text("{}\n", encoding="utf-8")
    with pytest.raises(gate.RollbackGateFailure, match="bytes do not match"):
        verify(evidence)


def test_gate_refuses_snapshot_adapter_error(evidence):
    snapshot, _, _, _, _, pins = evidence
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    payload["adapter_load_errors"] = {"security-preflight": "boom"}
    pins["snapshot_sha256"] = write(snapshot, payload)
    with pytest.raises(gate.RollbackGateFailure, match="adapter load"):
        verify(evidence)


def test_gate_refuses_security_snapshot_regression(evidence):
    snapshot, _, _, _, _, pins = evidence
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    payload["rows"]["security-preflight"]["attributes"] = 3
    pins["snapshot_sha256"] = write(snapshot, payload)
    with pytest.raises(gate.RollbackGateFailure, match="Security Preflight"):
        verify(evidence)


def test_gate_refuses_unexpected_loopback_health(evidence):
    _, health, _, _, _, pins = evidence
    payload = json.loads(health.read_text(encoding="utf-8"))
    payload["degraded_agents"] = ["security-preflight"]
    pins["health_sha256"] = write(health, payload)
    with pytest.raises(gate.RollbackGateFailure, match="health evidence"):
        verify(evidence)


def test_gate_refuses_mutated_normalized_source(evidence):
    _, _, _, _, after, pins = evidence
    pins["source_after_sha256"] = write(after, f"{'0' * 64}  source.db\n")
    with pytest.raises(gate.RollbackGateFailure, match="mutated"):
        verify(evidence)
