import math

import pytest

from fleet_utils.mcp_output import structured_result


def test_structured_result_preserves_mapping():
    result = {"status": "ok", "data": {"answer": 42}, "error": None}
    assert structured_result(result) == result


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_structured_result_rejects_nonfinite_json(value):
    with pytest.raises(ValueError):
        structured_result({"status": "ok", "data": {"value": value}})


def test_structured_result_requires_status_and_mapping():
    with pytest.raises(ValueError):
        structured_result({"data": {}})
    with pytest.raises(TypeError):
        structured_result("encoded JSON")  # type: ignore[arg-type]
