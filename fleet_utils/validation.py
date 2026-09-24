"""
Fleet-wide input validation primitives.

Promoted from carbon-bridge-agent/src/validation.py (Nightkeeper 2026-04-18).

The original `_require_number` helper appeared in carbon-bridge first to gate
TFAC/carbon pricing — it bundles the recurring "coerce-to-float, reject NaN/
Inf/bool, optionally enforce sign and bounds" pattern that 8+ agents in the
fleet need. Promoting it to fleet_utils lets future agents import the same
helper rather than reimplementing it.

Compatibility note: each agent already has its OWN ValidationError class
(local to its module). Rather than force a fleet-wide migration, this module
ALSO exports a minimal ValidationError, AND offers a `bind_to_error` factory
that lets callers parameterize which error class to raise. This keeps existing
agents working unchanged while new code can import from fleet_utils.

Usage:

    # Pattern A — callers using fleet_utils.ValidationError directly:
    from fleet_utils.validation import require_number, ValidationError
    try:
        n = require_number({"x": "3.14"}, "x", positive=True)
    except ValidationError as e:
        ...

    # Pattern B — callers with their own ValidationError class:
    from fleet_utils.validation import bind_to_error
    from src.validation import ValidationError as MyError  # local class
    require_number = bind_to_error(MyError)
    n = require_number({"x": 3.14}, "x", positive=True)
"""

from typing import Any, Callable, Dict, Optional


class ValidationError(Exception):
    """
    Default fleet-wide validation error with structured metadata.

    Mirrors the (field, value, constraint) shape used by every per-agent
    ValidationError in the fleet so error responses stay uniform.
    """

    def __init__(self, field: str, value: Any, constraint: str):
        self.field = field
        self.value = value
        self.constraint = constraint
        super().__init__(f"Field '{field}={value}' violates: {constraint}")


def _build_require_number(error_cls: type) -> Callable[..., float]:
    """
    Build a `require_number` function that raises `error_cls` instances.

    Factory pattern keeps the validation logic in one place but lets each
    agent keep its own ValidationError class (no cross-module isinstance
    breakage).
    """

    def require_number(
        container: Dict[str, Any],
        field: str,
        *,
        positive: bool = False,
        allow_zero: bool = False,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
    ) -> float:
        """
        Coerce `container[field]` to float with structured error on failure.

        Invariants enforced:
          - field must be present in container
          - value must NOT be a bool (bool is a subclass of int — reject explicitly)
          - value must be numeric (coercible via float())
          - value must be finite (no NaN, no ±Inf)
          - if positive=True (and not allow_zero): value must be > 0
          - if min_value is set: value must be >= min_value
          - if max_value is set: value must be <= max_value

        Args:
            container: dict to read the value from
            field: key to look up
            positive: if True, value must be > 0 (or >= 0 if allow_zero)
            allow_zero: only meaningful with positive=True; allows 0
            min_value: optional lower bound (inclusive)
            max_value: optional upper bound (inclusive)

        Returns:
            The validated float value.

        Raises:
            error_cls: structured (field, raw, constraint) on any failure.
        """
        if field not in container:
            raise error_cls(field, None, "field is required")
        raw = container[field]
        # bool is a subclass of int — reject explicitly so `True` doesn't
        # silently quote as 1.0 in pricing/risk/area calculations.
        if isinstance(raw, bool):
            raise error_cls(field, raw, "must be numeric, not bool")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise error_cls(field, raw, "must be numeric")
        # NaN / Inf check — both corrupt downstream arithmetic silently.
        if value != value or value in (float("inf"), float("-inf")):
            raise error_cls(field, raw, "must be finite (no NaN/Inf)")
        if positive and value <= 0 and not allow_zero:
            raise error_cls(field, raw, "must be > 0")
        if positive and value < 0 and allow_zero:
            raise error_cls(field, raw, "must be >= 0")
        if min_value is not None and value < min_value:
            raise error_cls(field, raw, f"must be >= {min_value}")
        if max_value is not None and value > max_value:
            raise error_cls(field, raw, f"must be <= {max_value}")
        return value

    return require_number


def bind_to_error(error_cls: type) -> Callable[..., float]:
    """
    Public factory: returns a `require_number` bound to the given error class.

    Use this when your agent has its own ValidationError class and you want
    structured errors of THAT type to propagate up unchanged.
    """
    if not isinstance(error_cls, type) or not issubclass(error_cls, Exception):
        raise TypeError(
            f"error_cls must be an Exception subclass, got {type(error_cls).__name__}"
        )
    return _build_require_number(error_cls)


# Default `require_number` raises fleet_utils.ValidationError.
# Use `bind_to_error(MyValidationError)` to bind it to a different class.
require_number = _build_require_number(ValidationError)


__all__ = [
    "ValidationError",
    "require_number",
    "bind_to_error",
]
