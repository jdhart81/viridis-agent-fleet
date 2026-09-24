"""
ProtoGen Validation Module
Validates process() input for manufacturing plan generation.
Validates product specifications: name, description, material type, volume, dimensions, tolerances, etc.
Follows fleet-standard ValidationError/ValidationWarning contract.
"""

import math
from typing import Any, Dict, Optional, List


class ValidationError(Exception):
    """Raised when a validation check fails (blocking)."""
    def __init__(self, field: str, message: str, error_type: str = "invalid_input"):
        self.field = field
        self.message = message
        self.error_type = error_type
        super().__init__(f"ValidationError [{field}]: {message}")


class ValidationWarning:
    """Non-blocking validation warnings (logged but not raised)."""
    def __init__(self, field: str, message: str, warning_type: str = "suspicious"):
        self.field = field
        self.message = message
        self.warning_type = warning_type


def validate_process_input(input_data: Dict[str, Any]) -> List[ValidationWarning]:
    """
    Validate process() input for manufacturing plan generation.
    
    Invariants:
      - name: non-empty string (1-256 chars)
      - description: non-empty string (1-2048 chars)
      - primary_material: one of [steel, aluminum, plastic, composite, rubber, glass, ceramic, titanium, copper]
      - estimated_volume: positive integer (units, e.g., 1000 = 1000 units)
      - target_dimensions: optional dict with keys height_mm, width_mm, length_mm (all positive floats)
      - tolerances: optional dict with tolerance strings (e.g., "±0.1mm")
      - surface_finish: one of [raw, polished, brushed, anodized, painted, coated, plated]
      - assembly_complexity: one of [simple, moderate, complex, very_complex]
      - lead_time_weeks: positive integer (1-52 weeks)
      - target_unit_cost: optional positive float (cost per unit)
    """
    warnings = []
    
    # name: required, 1-256 chars
    name = input_data.get("name", "")
    if not name or not isinstance(name, str):
        raise ValidationError("name", "name must be a non-empty string", "invalid_input")
    if len(name) > 256:
        raise ValidationError("name", "name must be <= 256 characters", "invalid_input")
    
    # description: required, 1-2048 chars
    description = input_data.get("description", "")
    if not description or not isinstance(description, str):
        raise ValidationError("description", "description must be a non-empty string", "invalid_input")
    if len(description) > 2048:
        raise ValidationError("description", "description must be <= 2048 characters", "invalid_input")
    
    # primary_material: one of known materials
    primary_material = input_data.get("primary_material", "")
    valid_materials = ["steel", "aluminum", "plastic", "composite", "rubber", "glass", "ceramic", "titanium", "copper"]
    if not primary_material or not isinstance(primary_material, str):
        raise ValidationError("primary_material", "primary_material must be a non-empty string", "invalid_input")
    if primary_material.lower() not in valid_materials:
        raise ValidationError("primary_material", f"primary_material must be one of {valid_materials}, got '{primary_material}'", "invalid_input")
    
    # estimated_volume: positive integer
    estimated_volume = input_data.get("estimated_volume")
    if estimated_volume is None:
        raise ValidationError("estimated_volume", "estimated_volume is required", "invalid_input")
    try:
        estimated_volume = int(estimated_volume)
    except (ValueError, TypeError):
        raise ValidationError("estimated_volume", "estimated_volume must be an integer", "invalid_input")
    if estimated_volume <= 0:
        raise ValidationError("estimated_volume", f"estimated_volume must be positive, got {estimated_volume}", "invalid_input")
    if estimated_volume > 10_000_000:
        warnings.append(ValidationWarning("estimated_volume", f"Very high volume {estimated_volume:,} may require special manufacturing strategy", "suspicious"))
    
    # target_dimensions: optional dict with height_mm, width_mm, length_mm (all positive floats)
    target_dimensions = input_data.get("target_dimensions", {})
    if target_dimensions is not None:
        if not isinstance(target_dimensions, dict):
            raise ValidationError("target_dimensions", "target_dimensions must be a dict", "invalid_input")
        for dim_key in ["height_mm", "width_mm", "length_mm"]:
            if dim_key in target_dimensions:
                try:
                    dim_val = float(target_dimensions[dim_key])
                except (ValueError, TypeError):
                    raise ValidationError(f"target_dimensions.{dim_key}", f"{dim_key} must be a number", "invalid_input")
                if not math.isfinite(dim_val) or dim_val <= 0:
                    raise ValidationError(
                        f"target_dimensions.{dim_key}",
                        f"{dim_key} must be finite and positive, got {dim_val}",
                        "invalid_input")
                if dim_val > 10_000:
                    warnings.append(ValidationWarning(f"target_dimensions.{dim_key}", f"{dim_key} very large ({dim_val}mm), may require special tooling", "suspicious"))
    
    # tolerances: optional dict with tolerance strings
    tolerances = input_data.get("tolerances")
    if tolerances is not None:
        if not isinstance(tolerances, dict):
            raise ValidationError("tolerances", "tolerances must be a dict", "invalid_input")
        for tol_key, tol_val in tolerances.items():
            if not isinstance(tol_val, str):
                raise ValidationError(f"tolerances.{tol_key}", f"tolerance value must be a string (e.g., '±0.1mm'), got {type(tol_val)}", "invalid_input")
            # Basic sanity check: should contain ± or similar
            if not any(c in tol_val for c in ['±', '+', '-', '%']):
                warnings.append(ValidationWarning(f"tolerances.{tol_key}", f"tolerance format unclear: '{tol_val}' (should use ± notation)", "suspicious"))
    
    # surface_finish: one of known finishes
    surface_finish = input_data.get("surface_finish", "raw")
    valid_finishes = ["raw", "polished", "brushed", "anodized", "painted", "coated", "plated"]
    if surface_finish not in valid_finishes:
        raise ValidationError("surface_finish", f"surface_finish must be one of {valid_finishes}, got '{surface_finish}'", "invalid_input")
    
    # assembly_complexity: one of known levels
    assembly_complexity = input_data.get("assembly_complexity", "moderate")
    valid_complexities = ["simple", "moderate", "complex", "very_complex"]
    if assembly_complexity not in valid_complexities:
        raise ValidationError("assembly_complexity", f"assembly_complexity must be one of {valid_complexities}, got '{assembly_complexity}'", "invalid_input")
    
    # lead_time_weeks: positive integer, 1-52 weeks
    lead_time_weeks = input_data.get("lead_time_weeks", 12)
    try:
        lead_time_weeks = int(lead_time_weeks)
    except (ValueError, TypeError):
        raise ValidationError("lead_time_weeks", "lead_time_weeks must be an integer", "invalid_input")
    if lead_time_weeks <= 0:
        raise ValidationError("lead_time_weeks", f"lead_time_weeks must be positive, got {lead_time_weeks}", "invalid_input")
    if lead_time_weeks > 52:
        warnings.append(ValidationWarning("lead_time_weeks", f"lead_time_weeks {lead_time_weeks} > 52 weeks (1 year) may impact cash flow", "suspicious"))
    
    # target_unit_cost: optional positive float
    target_unit_cost = input_data.get("target_unit_cost")
    if target_unit_cost is not None:
        try:
            target_unit_cost = float(target_unit_cost)
        except (ValueError, TypeError):
            raise ValidationError("target_unit_cost", "target_unit_cost must be a number", "invalid_input")
        if not math.isfinite(target_unit_cost) or target_unit_cost < 0:
            raise ValidationError(
                "target_unit_cost",
                f"target_unit_cost must be finite and non-negative, got "
                f"{target_unit_cost}",
                "invalid_input")
        if target_unit_cost == 0:
            warnings.append(ValidationWarning("target_unit_cost", "target_unit_cost is 0 (may indicate prototype/free product)", "suspicious"))
    
    return warnings
