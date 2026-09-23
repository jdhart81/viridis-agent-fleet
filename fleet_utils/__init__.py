"""
Fleet-wide shared utilities for the Viridis agent ecosystem.

Provides reusable patterns extracted from individual agents:
- WeightedBooleanScorer: Score entities by weighted boolean factors (from Energy AI)
- MultiFactorScorer: Score by weighted numeric sub-scores (from Bounty Hunter)
- require_number: NaN/Inf/bool-safe float coercion with bounds (from Carbon-Bridge)
- bind_to_error: factory binding require_number to a caller's ValidationError class
- RangeNormalizer: clamp/winsorize numerics into a target range (from D-Score + Bounty Hunter)
- clamp_to_range: one-shot warn+clamp primitive (no normalizer instance required)
- error_envelope: fleet-canonical structured error response builder (unifies guard + unknown-action schemas)
"""

from fleet_utils.scoring import WeightedBooleanScorer, MultiFactorScorer
from fleet_utils.validation import (
    ValidationError,
    require_number,
    bind_to_error,
)
from fleet_utils.normalization import RangeNormalizer, NormalizeResult, clamp_to_range
from fleet_utils.errors import error_envelope, ERROR_ENVELOPE_KEYS
from fleet_utils.mcp_output import FleetToolResult, structured_result

__all__ = [
    "WeightedBooleanScorer",
    "MultiFactorScorer",
    "ValidationError",
    "require_number",
    "bind_to_error",
    "RangeNormalizer",
    "NormalizeResult",
    "clamp_to_range",
    "error_envelope",
    "ERROR_ENVELOPE_KEYS",
    "FleetToolResult",
    "structured_result",
]
