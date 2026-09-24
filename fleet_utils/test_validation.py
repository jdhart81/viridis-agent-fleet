"""
Tests for fleet_utils.validation — promoted require_number helper.

Covers the invariants documented in fleet_utils/validation.py:
  - field-required check
  - bool rejection (since bool is a subclass of int)
  - non-numeric rejection
  - NaN / ±Inf rejection
  - positive / allow_zero behavior
  - min_value / max_value bounds
  - bind_to_error factory wires custom ValidationError classes
"""

import math
import sys
import os

# Add repo root to path so `from fleet_utils...` works whether tests run
# from this directory or from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fleet_utils.validation import (
    ValidationError,
    require_number,
    bind_to_error,
)


# ─── Default require_number (raises fleet_utils.ValidationError) ──────────────

class TestRequireNumberHappyPath:
    def test_int_value(self):
        assert require_number({"x": 3}, "x") == 3.0

    def test_float_value(self):
        assert require_number({"x": 3.14}, "x") == 3.14

    def test_string_numeric_coerced(self):
        assert require_number({"x": "2.5"}, "x") == 2.5

    def test_negative_value_allowed_by_default(self):
        """Without positive=True, negative numbers are fine."""
        assert require_number({"x": -42}, "x") == -42.0


class TestRequireNumberFieldMissing:
    def test_missing_field_raises(self):
        try:
            require_number({}, "x")
        except ValidationError as e:
            assert e.field == "x"
            assert "required" in e.constraint
            return
        raise AssertionError("expected ValidationError")

    def test_field_present_with_none_is_invalid(self):
        """None can't be coerced to float — must raise (not 'missing')."""
        try:
            require_number({"x": None}, "x")
        except ValidationError as e:
            assert e.field == "x"
            return
        raise AssertionError("expected ValidationError")


class TestRequireNumberBoolRejection:
    def test_true_rejected(self):
        try:
            require_number({"x": True}, "x")
        except ValidationError as e:
            assert "bool" in e.constraint
            return
        raise AssertionError("expected ValidationError on True")

    def test_false_rejected(self):
        try:
            require_number({"x": False}, "x")
        except ValidationError as e:
            assert "bool" in e.constraint
            return
        raise AssertionError("expected ValidationError on False")


class TestRequireNumberNonNumeric:
    def test_string_non_numeric_raises(self):
        try:
            require_number({"x": "abc"}, "x")
        except ValidationError as e:
            assert e.field == "x"
            return
        raise AssertionError("expected ValidationError")

    def test_list_raises(self):
        try:
            require_number({"x": [1, 2]}, "x")
        except ValidationError:
            return
        raise AssertionError("expected ValidationError")

    def test_dict_raises(self):
        try:
            require_number({"x": {"a": 1}}, "x")
        except ValidationError:
            return
        raise AssertionError("expected ValidationError")


class TestRequireNumberFiniteness:
    def test_nan_raises(self):
        try:
            require_number({"x": float("nan")}, "x")
        except ValidationError as e:
            assert "finite" in e.constraint or "NaN" in e.constraint
            return
        raise AssertionError("expected ValidationError on NaN")

    def test_string_nan_raises(self):
        """'nan' string coerces to NaN via float() — must still be rejected."""
        try:
            require_number({"x": "nan"}, "x")
        except ValidationError:
            return
        raise AssertionError("expected ValidationError on 'nan'")

    def test_positive_inf_raises(self):
        try:
            require_number({"x": math.inf}, "x")
        except ValidationError as e:
            assert "finite" in e.constraint or "Inf" in e.constraint
            return
        raise AssertionError("expected ValidationError on +Inf")

    def test_negative_inf_raises(self):
        try:
            require_number({"x": -math.inf}, "x")
        except ValidationError:
            return
        raise AssertionError("expected ValidationError on -Inf")


class TestRequireNumberPositive:
    def test_positive_passes_for_positive(self):
        assert require_number({"x": 5}, "x", positive=True) == 5.0

    def test_positive_rejects_zero_by_default(self):
        try:
            require_number({"x": 0}, "x", positive=True)
        except ValidationError as e:
            assert "> 0" in e.constraint
            return
        raise AssertionError("expected ValidationError")

    def test_positive_rejects_negative(self):
        try:
            require_number({"x": -1}, "x", positive=True)
        except ValidationError:
            return
        raise AssertionError("expected ValidationError")

    def test_positive_allow_zero_passes_for_zero(self):
        assert require_number(
            {"x": 0}, "x", positive=True, allow_zero=True
        ) == 0.0

    def test_positive_allow_zero_rejects_negative(self):
        try:
            require_number({"x": -1}, "x", positive=True, allow_zero=True)
        except ValidationError as e:
            assert ">= 0" in e.constraint
            return
        raise AssertionError("expected ValidationError")


class TestRequireNumberBounds:
    def test_min_value_passes(self):
        assert require_number({"x": 5}, "x", min_value=0) == 5.0

    def test_min_value_at_boundary_passes(self):
        """min is inclusive."""
        assert require_number({"x": 0}, "x", min_value=0) == 0.0

    def test_min_value_below_raises(self):
        try:
            require_number({"x": -0.001}, "x", min_value=0)
        except ValidationError as e:
            assert ">= 0" in e.constraint
            return
        raise AssertionError("expected ValidationError")

    def test_max_value_passes(self):
        assert require_number({"x": 5}, "x", max_value=10) == 5.0

    def test_max_value_at_boundary_passes(self):
        """max is inclusive."""
        assert require_number({"x": 10}, "x", max_value=10) == 10.0

    def test_max_value_above_raises(self):
        try:
            require_number({"x": 11}, "x", max_value=10)
        except ValidationError as e:
            assert "<= 10" in e.constraint
            return
        raise AssertionError("expected ValidationError")

    def test_combined_bounds(self):
        """Probability bounds [0, 1] is the canonical case."""
        assert require_number({"x": 0.5}, "x", min_value=0, max_value=1) == 0.5

    def test_combined_bounds_below(self):
        try:
            require_number({"x": -0.1}, "x", min_value=0, max_value=1)
        except ValidationError:
            return
        raise AssertionError("expected ValidationError")

    def test_combined_bounds_above(self):
        try:
            require_number({"x": 1.1}, "x", min_value=0, max_value=1)
        except ValidationError:
            return
        raise AssertionError("expected ValidationError")


# ─── bind_to_error factory ────────────────────────────────────────────────────

class _AgentLocalError(Exception):
    """Mimics an agent's locally defined ValidationError class."""

    def __init__(self, field, value, constraint):
        self.field = field
        self.value = value
        self.constraint = constraint
        super().__init__(f"{field}={value} bad: {constraint}")


class TestBindToError:
    def test_bind_returns_new_function(self):
        bound = bind_to_error(_AgentLocalError)
        assert callable(bound)
        # The bound function is not the same object as the default one
        assert bound is not require_number

    def test_bound_function_raises_custom_error(self):
        bound = bind_to_error(_AgentLocalError)
        try:
            bound({"x": -1}, "x", positive=True)
        except _AgentLocalError as e:
            assert e.field == "x"
            return
        except ValidationError:
            raise AssertionError(
                "should have raised _AgentLocalError, not fleet ValidationError"
            )
        raise AssertionError("expected _AgentLocalError")

    def test_bound_function_does_not_raise_default_error(self):
        """Custom-bound function should NOT raise fleet ValidationError."""
        bound = bind_to_error(_AgentLocalError)
        try:
            bound({"x": "abc"}, "x")
        except _AgentLocalError:
            return  # correct
        except ValidationError:
            raise AssertionError("leaked default ValidationError")
        raise AssertionError("expected _AgentLocalError")

    def test_bind_to_non_exception_raises(self):
        """bind_to_error must reject non-Exception arguments."""
        try:
            bind_to_error(int)  # not an Exception subclass
        except TypeError:
            return
        raise AssertionError("expected TypeError")

    def test_bind_to_non_class_raises(self):
        try:
            bind_to_error("ValidationError")
        except TypeError:
            return
        raise AssertionError("expected TypeError")
