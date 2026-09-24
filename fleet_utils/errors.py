"""
Shared error-envelope helper for the Viridis agent fleet.

MOTIVATION (Nightkeeper C4, queued N55 → landed N56):
Across the fleet, two error-exit shapes diverged:
  * The non-dict *guard* path (regulatory-radar N54, sentinel-watch N54,
    proof-of-conservation N56) emits:
        {status, error_type, field, value, constraint, message, timestamp}
    and OMITS a legacy ``error`` key.
  * The unknown-*action* path (carbon-bridge N54, sentinel-watch N55) emits the
    enriched envelope PLUS a backward-compat ``error`` key.

This module gives every error exit a single canonical builder so the schema is
identical fleet-wide. Callers that must preserve a legacy ``error`` key opt in
via ``include_legacy_error=True`` (gradual convergence, no breakage).

INVARIANTS (verified in test_errors.py):
  I1. Output always contains, in this order:
      status, error_type, field, value, constraint, message, timestamp.
  I2. ``status`` is always the literal "error".
  I3. ``timestamp`` is an ISO-8601 string; caller-supplied value is preserved,
      otherwise ``datetime.utcnow().isoformat()`` is used.
  I4. ``error_type`` and ``message`` are required, non-empty strings.
  I5. The legacy ``error`` key is present IFF ``include_legacy_error=True``;
      its value defaults to ``message`` unless ``legacy_error`` is given.
  I6. The function never mutates caller inputs and never raises on valid input.

Usage:
    from fleet_utils import error_envelope

    # guard path (no legacy key)
    return error_envelope(
        "ValidationError", "input_data must be a dict",
        field="input_data", value=type(x).__name__,
        constraint="input_data must be a dict",
    )

    # unknown-action path (keep legacy `error` for older consumers)
    return error_envelope(
        "UnknownOperation", f"Unknown action: {action}",
        include_legacy_error=True,
    )
"""

from datetime import datetime
from typing import Any, Dict, Optional

__all__ = ["error_envelope", "ERROR_ENVELOPE_KEYS"]

# Canonical key order (I1). Consumers may rely on this exact set/order.
ERROR_ENVELOPE_KEYS = (
    "status",
    "error_type",
    "field",
    "value",
    "constraint",
    "message",
    "timestamp",
)


def error_envelope(
    error_type: str,
    message: str,
    *,
    field: Optional[str] = None,
    value: Any = None,
    constraint: Optional[str] = None,
    timestamp: Optional[str] = None,
    include_legacy_error: bool = False,
    legacy_error: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build the fleet-canonical structured error response.

    Args:
        error_type: Short error category, e.g. "ValidationError",
            "UnknownOperation". Required, non-empty.
        message: Human-readable description. Required, non-empty.
        field: Offending input field name, if applicable.
        value: Offending value (or a safe repr like ``type(x).__name__``).
        constraint: The violated invariant, e.g. "input_data must be a dict".
        timestamp: ISO-8601 string; defaults to ``datetime.utcnow().isoformat()``.
        include_legacy_error: When True, also emit a backward-compat ``error``
            key (for agents whose older consumers read ``error``).
        legacy_error: Explicit value for the legacy ``error`` key; defaults to
            ``message`` when ``include_legacy_error`` is True.

    Returns:
        A new dict with the canonical key order (I1); plus an ``error`` key
        only when ``include_legacy_error`` is True (I5).

    Raises:
        ValueError: if ``error_type`` or ``message`` is not a non-empty string
            (I4) — a programming error in the caller, surfaced loudly rather
            than silently producing a malformed envelope.
    """
    if not isinstance(error_type, str) or not error_type.strip():
        raise ValueError("error_type must be a non-empty string")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be a non-empty string")

    envelope: Dict[str, Any] = {
        "status": "error",
        "error_type": error_type,
        "field": field,
        "value": value,
        "constraint": constraint,
        "message": message,
        "timestamp": timestamp if timestamp is not None else datetime.utcnow().isoformat(),
    }
    if include_legacy_error:
        envelope["error"] = legacy_error if legacy_error is not None else message
    return envelope
