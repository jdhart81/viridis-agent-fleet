"""
Validation tests for ProtoGen — pins the manufacturing-plan input contract
enforced by validate_process_input.

validate_process_input(input_data) -> List[ValidationWarning]; RAISES
ValidationError on blocking invariant violations, RETURNS advisory warnings.

Added by Nightkeeper (2026-06-15, Night 56), C2 rollout (mvp stage).
Run with: python -m pytest protogen-agent/tests/test_validation.py
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from validation import (
    validate_process_input,
    ValidationError,
    ValidationWarning,
)


def _spec(**over):
    base = {
        "name": "Widget A",
        "description": "An injection-molded enclosure.",
        "primary_material": "plastic",
        "estimated_volume": 1000,
    }
    base.update(over)
    return base


# --- happy path ------------------------------------------------------------

def test_minimal_valid_spec_returns_list():
    out = validate_process_input(_spec())
    assert isinstance(out, list)
    assert all(isinstance(w, ValidationWarning) for w in out)


def test_full_valid_spec():
    out = validate_process_input(_spec(
        target_dimensions={"height_mm": 10.0, "width_mm": 20.0, "length_mm": 30.0},
        tolerances={"height_mm": "±0.1mm"},
        surface_finish="anodized",
        assembly_complexity="moderate",
        lead_time_weeks=12,
        target_unit_cost=4.50,
    ))
    assert out == []


# --- name / description ----------------------------------------------------

def test_missing_name_raises():
    s = _spec(); s.pop("name")
    with pytest.raises(ValidationError):
        validate_process_input(s)


def test_name_non_string_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_spec(name=123))


def test_name_too_long_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_spec(name="n" * 257))


def test_missing_description_raises():
    s = _spec(); s.pop("description")
    with pytest.raises(ValidationError):
        validate_process_input(s)


def test_description_too_long_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_spec(description="d" * 2049))


# --- primary_material ------------------------------------------------------

def test_unknown_material_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_spec(primary_material="unobtainium"))


def test_material_case_insensitive_ok():
    out = validate_process_input(_spec(primary_material="STEEL"))
    assert isinstance(out, list)


# --- estimated_volume ------------------------------------------------------

def test_missing_volume_raises():
    s = _spec(); s.pop("estimated_volume")
    with pytest.raises(ValidationError):
        validate_process_input(s)


def test_non_integer_volume_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_spec(estimated_volume="lots"))


def test_non_positive_volume_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_spec(estimated_volume=0))


def test_very_high_volume_warns_not_raises():
    out = validate_process_input(_spec(estimated_volume=20_000_000))
    assert any(w.field == "estimated_volume" for w in out)


# --- target_dimensions -----------------------------------------------------

def test_dimensions_not_dict_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_spec(target_dimensions=[1, 2, 3]))


def test_dimension_non_numeric_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_spec(target_dimensions={"height_mm": "tall"}))


def test_dimension_non_positive_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_spec(target_dimensions={"width_mm": -5}))


def test_dimension_very_large_warns():
    out = validate_process_input(_spec(target_dimensions={"length_mm": 50000}))
    assert any("length_mm" in w.field for w in out)


# --- tolerances ------------------------------------------------------------

def test_tolerances_not_dict_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_spec(tolerances="±0.1mm"))


def test_tolerance_non_string_value_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_spec(tolerances={"height_mm": 0.1}))


def test_tolerance_unclear_format_warns():
    out = validate_process_input(_spec(tolerances={"height_mm": "0.1mm"}))
    assert any("height_mm" in w.field for w in out)


# --- surface_finish / assembly_complexity ----------------------------------

def test_unknown_surface_finish_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_spec(surface_finish="chromed"))


def test_unknown_assembly_complexity_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_spec(assembly_complexity="impossible"))


# --- lead_time_weeks / target_unit_cost ------------------------------------

def test_non_integer_lead_time_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_spec(lead_time_weeks="soon"))


def test_non_positive_lead_time_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_spec(lead_time_weeks=0))


def test_lead_time_over_year_warns():
    out = validate_process_input(_spec(lead_time_weeks=60))
    assert any(w.field == "lead_time_weeks" for w in out)


def test_negative_unit_cost_raises():
    with pytest.raises(ValidationError):
        validate_process_input(_spec(target_unit_cost=-1.0))


def test_zero_unit_cost_warns_not_raises():
    out = validate_process_input(_spec(target_unit_cost=0))
    assert any(w.field == "target_unit_cost" for w in out)
