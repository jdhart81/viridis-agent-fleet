"""
Tests for narrative-engine-agent input validation module.

Covers happy-path and error-path for:
  - validate_translate_input
  - validate_process_input

Nightkeeper Night 54: validation test coverage (MISSING_TEST close-out).
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.validation import (
    validate_translate_input,
    validate_process_input,
    ValidationError,
    ValidationWarning,
    VALID_AUDIENCE_TYPES,
    VALID_FORMAT_TYPES,
    VALID_ACTIONS,
)


class TestTranslateValidation:
    """validate_translate_input — happy path + field constraints."""

    def _valid(self, **over):
        base = {"agent_output": {"d_score": 0.7},
                "audience_type": "policymaker",
                "format_type": "policy_brief"}
        base.update(over)
        return base

    def test_valid_input(self):
        r = validate_translate_input(self._valid())
        assert r["audience_type"] == "policymaker"
        assert r["format_type"] == "policy_brief"

    def test_missing_agent_output_rejected(self):
        d = self._valid()
        del d["agent_output"]
        with pytest.raises(ValidationError) as ei:
            validate_translate_input(d)
        assert ei.value.field == "agent_output"

    def test_agent_output_must_be_dict(self):
        with pytest.raises(ValidationError) as ei:
            validate_translate_input(self._valid(agent_output=["not", "a", "dict"]))
        assert ei.value.field == "agent_output"

    def test_empty_agent_output_rejected(self):
        with pytest.raises(ValidationError) as ei:
            validate_translate_input(self._valid(agent_output={}))
        assert ei.value.field == "agent_output"

    def test_invalid_audience_type_rejected(self):
        with pytest.raises(ValidationError) as ei:
            validate_translate_input(self._valid(audience_type="aliens"))
        assert ei.value.field == "audience_type"

    def test_invalid_format_type_rejected(self):
        with pytest.raises(ValidationError) as ei:
            validate_translate_input(self._valid(format_type="tiktok"))
        assert ei.value.field == "format_type"

    def test_every_valid_audience_accepted(self):
        for aud in VALID_AUDIENCE_TYPES:
            r = validate_translate_input(self._valid(audience_type=aud))
            assert r["audience_type"] == aud

    def test_every_valid_format_accepted(self):
        for fmt in VALID_FORMAT_TYPES:
            r = validate_translate_input(self._valid(format_type=fmt))
            assert r["format_type"] == fmt


class TestProcessValidation:
    """validate_process_input — action gating."""

    def test_valid_translate_action(self):
        r = validate_process_input({
            "action": "translate",
            "agent_output": {"d_score": 0.5},
            "audience_type": "scientist",
            "format_type": "academic_paper",
        })
        assert r is not None

    def test_missing_action_rejected(self):
        with pytest.raises(ValidationError) as ei:
            validate_process_input({})
        assert ei.value.field == "action"

    def test_unknown_action_rejected(self):
        with pytest.raises(ValidationError) as ei:
            validate_process_input({"action": "frobnicate"})
        assert ei.value.field == "action"
