from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.core import RobustnessAgent, RobustnessAgentConfig


AGENT_ROOT = Path(__file__).resolve().parents[1]


def fixture(name: str) -> tuple[dict, dict]:
    candidates = [AGENT_ROOT / "examples" / name]
    candidates.extend(parent / "examples" / name for parent in AGENT_ROOT.parents)
    root = next(path for path in candidates if (path / "case.json").is_file())
    return (
        json.loads((root / "case.json").read_text()),
        json.loads((root / "outcomes.json").read_text()),
    )


def run(coroutine):
    return asyncio.run(coroutine)


def test_health_is_explicitly_prototype_and_nonexecuting():
    health = run(RobustnessAgent().health())

    assert health["status"] == "ok"
    assert health["engine_version"] == "0.6.0"
    assert health["checks"]["decision_execution"] == "DISABLED"
    assert not health["checks"]["release_manifest"]["valid_for_final"]


def test_cyber_evaluation_returns_the_hash_bound_kernel_record():
    case, outcomes = fixture("cyber_identity")
    result = run(RobustnessAgent().process({
        "operation": "evaluate",
        "case": case,
        "outcomes": outcomes,
        "request_id": "test-1",
    }))

    record = result["decision_record"]
    assert result["status"] == "ok"
    assert result["request_id"] == "test-1"
    assert record["status"] == "DECISION"
    assert record["selected_candidate"] == "split_control_recovery"
    assert record["action_boundary"]["executed"] is False
    assert len(record["record_sha256"]) == 64


def test_kernel_hold_is_a_successful_fail_closed_service_result():
    case, outcomes = fixture("cyber_identity")
    case["governance"]["trajectory_policy"]["minimum_mandatory_coverage"] = 1
    result = run(RobustnessAgent().process({
        "operation": "evaluate",
        "case": case,
        "outcomes": outcomes,
    }))

    assert result["status"] == "ok"
    assert result["decision_record"]["status"] == "HOLD"
    assert result["decision_record"]["action_boundary"]["executed"] is False


def test_unknown_fields_operation_and_size_fail_closed():
    agent = RobustnessAgent(RobustnessAgentConfig(max_request_bytes=256))

    with pytest.raises(ValueError, match="Unknown request fields"):
        run(agent.process({"operation": "evaluate", "case": {}, "outcomes": {}, "extra": 1}))
    with pytest.raises(ValueError, match="operation"):
        run(agent.process({"operation": "execute", "case": {}, "outcomes": {}}))
    with pytest.raises(ValueError, match="request_id"):
        run(agent.process({
            "operation": "evaluate",
            "case": {},
            "outcomes": {},
            "request_id": 7,
        }))
    with pytest.raises(ValueError, match="size limit"):
        run(agent.process({
            "operation": "evaluate",
            "case": {"padding": "x" * 500},
            "outcomes": {},
        }))


def test_final_mode_refuses_health_without_audited_release_manifest():
    agent = RobustnessAgent(RobustnessAgentConfig(release_mode="final"))
    health = run(agent.health())

    assert health["status"] == "degraded"
    assert not health["checks"]["release_manifest"]["valid_for_final"]
    assert not health["checks"]["release_manifest"]["checks"]["running_artifact_digest"]
