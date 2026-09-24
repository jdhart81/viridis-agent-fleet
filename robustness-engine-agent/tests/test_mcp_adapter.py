"""The public MCP adapter exposes the one non-actuating core operation."""
import asyncio
import json
from pathlib import Path

from adapters import mcp_server
from src.core import RobustnessAgent


ROOT = Path(__file__).resolve().parents[1]


def fixture():
    source = ROOT / "examples" / "cyber_identity"
    return (json.loads((source / "case.json").read_text()),
            json.loads((source / "outcomes.json").read_text()))


def test_one_mcp_tool_matches_core_evaluation():
    case, outcomes = fixture()
    actual = asyncio.run(mcp_server.evaluate_robustness_case(
        case, outcomes, request_id="public-adapter-test"))
    expected = asyncio.run(RobustnessAgent().process({
        "operation": "evaluate", "case": case, "outcomes": outcomes,
        "request_id": "public-adapter-test"}))
    assert actual == expected
    assert actual["decision_record"]["action_boundary"]["executed"] is False


def test_mcp_tool_preserves_fail_closed_hold():
    case, outcomes = fixture()
    case["governance"]["trajectory_policy"]["minimum_mandatory_coverage"] = 1
    actual = asyncio.run(mcp_server.evaluate_robustness_case(case, outcomes))
    assert actual["decision_record"]["status"] == "HOLD"
    assert actual["decision_record"]["action_boundary"]["executed"] is False


def test_mcp_tool_rejects_invalid_request_without_execution():
    actual = asyncio.run(mcp_server.evaluate_robustness_case({}, {}, request_id=""))
    assert actual["status"] == "error"
    assert actual["error_type"] == "ValidationError"
