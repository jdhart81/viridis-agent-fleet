import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest


CORE_PATH = Path(__file__).resolve().parents[1] / "src" / "core.py"
SPEC = importlib.util.spec_from_file_location(
    "security_preflight_validation_test_core", CORE_PATH)
CORE_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CORE_MODULE
assert SPEC.loader is not None
SPEC.loader.exec_module(CORE_MODULE)
PreflightError = CORE_MODULE.PreflightError
SecurityPreflightCore = CORE_MODULE.SecurityPreflightCore


def payload():
    return {
        "agent_id": "buyer-safe-agent",
        "manifest": {"tools": []},
        "policy": {},
        "sample_inputs": [],
    }


def set_value(data, path, value):
    current = data
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value


@pytest.mark.parametrize(
    ("field", "path", "value", "json_type", "limit"),
    [
        ("manifest.tools", ("manifest", "tools"), {}, "object", "100"),
        ("sample_inputs", ("sample_inputs",), "hi", "string", "20"),
        ("policy.allowed_tools", ("policy", "allowed_tools"),
         "read", "string", "100"),
        ("policy.denied_tools", ("policy", "denied_tools"),
         17, "number", "100"),
        ("policy.approval_required_tools",
         ("policy", "approval_required_tools"), True, "boolean", "100"),
    ],
)
def test_non_array_values_name_the_received_json_type(
        field, path, value, json_type, limit):
    data = payload()
    set_value(data, path, value)

    with pytest.raises(PreflightError) as raised:
        SecurityPreflightCore._validate_scan(data)

    message = str(raised.value)
    assert f"received {json_type}" in message
    assert limit not in message
    assert raised.value.field == field
    assert raised.value.error_type == "ValidationError"


def test_manifest_tool_count_error_includes_count_and_limit():
    data = payload()
    data["manifest"]["tools"] = [{}] * 101

    with pytest.raises(PreflightError) as raised:
        SecurityPreflightCore._validate_scan(data)

    assert "101" in str(raised.value)
    assert "100" in str(raised.value)
    assert raised.value.field == "manifest.tools"
    assert raised.value.error_type == "ValidationError"


def test_sample_input_count_error_includes_count_and_limit():
    data = payload()
    data["sample_inputs"] = ["sample"] * 21

    with pytest.raises(PreflightError) as raised:
        SecurityPreflightCore._validate_scan(data)

    assert "21" in str(raised.value)
    assert "20" in str(raised.value)
    assert raised.value.field == "sample_inputs"
    assert raised.value.error_type == "ValidationError"


@pytest.mark.parametrize(
    "field",
    [
        "policy.allowed_tools",
        "policy.denied_tools",
        "policy.approval_required_tools",
    ],
)
def test_policy_tool_count_error_includes_count_and_limit(field):
    data = payload()
    key = field.split(".", 1)[1]
    data["policy"][key] = [f"tool-{index}" for index in range(101)]

    with pytest.raises(PreflightError) as raised:
        SecurityPreflightCore._validate_scan(data)

    assert "101" in str(raised.value)
    assert "100" in str(raised.value)
    assert raised.value.field == field
    assert raised.value.error_type == "ValidationError"


def test_unknown_action_lists_all_known_actions():
    core = object.__new__(SecurityPreflightCore)
    result = asyncio.run(core.process({"action": "unknown"}))

    expected = ", ".join(sorted(SecurityPreflightCore.KNOWN_ACTIONS))
    assert result["message"] == (
        f"unknown action; supported actions: {expected}")
    assert result["field"] == "action"
    assert result["error_type"] == "ValidationError"
