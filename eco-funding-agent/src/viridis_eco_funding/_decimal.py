"""Pinned decimal arithmetic.

Every number in the valuation core is a :class:`decimal.Decimal` evaluated under one
pinned context. ``ln``, ``exp``, ``sqrt`` and ``log10`` in the decimal module are
correctly rounded (IBM General Decimal Arithmetic spec, implemented by libmpdec), so
results do not depend on the platform's floating-point library. That is what makes
Invariant 1 (byte-identical results and receipts) hold across operating systems and CPUs,
not just across repeated runs on one machine.

Binary floats are only accepted at the boundary, converted through ``repr`` (shortest
round-trip form), which is itself deterministic.
"""

from __future__ import annotations

import functools
from decimal import (
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)
from typing import Any, Callable, TypeVar

PRECISION = 40
"""Working precision (significant digits) for all intermediate arithmetic."""

OUTPUT_SIGNIFICANT_DIGITS = 12
"""Significant digits kept in published results (valuations, receipts)."""

INPUT_SIGNIFICANT_DIGITS = 15
"""Inputs are quantized to this many significant digits so a JSON round trip through
IEEE-754 doubles (which hold 15-17 significant digits) is lossless."""

CONTEXT = Context(
    prec=PRECISION,
    rounding=ROUND_HALF_EVEN,
    Emin=-999_999,
    Emax=999_999,
    traps=[InvalidOperation, DivisionByZero, Overflow],
)

ZERO = Decimal(0)
ONE = Decimal(1)

MAGNITUDE_EXPONENT_RANGE = (-300, 300)
"""Non-zero inputs must lie in 1e-300..1e300 in absolute value: inside the normal range of
IEEE-754 doubles, so every input survives a plain-JSON round trip exactly."""

FLUSH_TO_ZERO_BELOW = Decimal("1E-300")
"""Published values smaller than this in absolute value are published as 0 (monotone), so
every published number is also representable as a normal double."""

F = TypeVar("F", bound=Callable[..., Any])


def pinned(func: F) -> F:
    """Run ``func`` under the pinned decimal context."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with localcontext(CONTEXT):
            return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def to_decimal(value: Any, *, field: str = "value") -> Decimal:
    """Convert an input number to a finite Decimal.

    Accepts int, Decimal, numeric str and float (via ``repr``). Rejects bool, NaN and
    infinities so a malformed input can never silently become a number.
    """
    if isinstance(value, bool):
        raise ValueError(f"{field}: expected a number, got a boolean")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, float):
        result = Decimal(repr(value))
    elif isinstance(value, str):
        try:
            result = Decimal(value.strip())
        except InvalidOperation as exc:  # pragma: no cover - message path
            raise ValueError(f"{field}: {value!r} is not a number") from exc
    else:
        raise ValueError(f"{field}: expected a number, got {type(value).__name__}")
    if not result.is_finite():
        raise ValueError(f"{field}: must be finite")
    low, high = MAGNITUDE_EXPONENT_RANGE
    if not result.is_zero() and not low <= result.adjusted() <= high:
        raise ValueError(f"{field}: magnitude must be between 1e-300 and 1e300 (or exactly 0)")
    return result


@pinned
def round_sig(value: Decimal, digits: int) -> Decimal:
    """Round to ``digits`` significant digits, half-even. Monotone non-decreasing."""
    if value.is_zero():
        return ZERO
    exponent = value.adjusted() - digits + 1
    return value.quantize(Decimal(1).scaleb(exponent), rounding=ROUND_HALF_EVEN).normalize()


def quantize_input(value: Any, *, field: str) -> Decimal:
    return round_sig(to_decimal(value, field=field), INPUT_SIGNIFICANT_DIGITS)


def publish(value: Decimal) -> Decimal:
    """Round a derived value for publication (12 significant digits; |x| < 1e-300 -> 0).

    Both steps are monotone non-decreasing, so publication preserves Invariant 2."""
    rounded = round_sig(value, OUTPUT_SIGNIFICANT_DIGITS)
    return ZERO if rounded.copy_abs() < FLUSH_TO_ZERO_BELOW else rounded


@pinned
def ln(x: Decimal) -> Decimal:
    return x.ln()


@pinned
def exp(x: Decimal) -> Decimal:
    return x.exp()


@pinned
def sqrt(x: Decimal) -> Decimal:
    if x < 0:
        raise ValueError("sqrt of negative number")
    return x.sqrt()


@pinned
def log10(x: Decimal) -> Decimal:
    return x.log10()


@pinned
def power(base: Decimal, exponent: Decimal) -> Decimal:
    """base ** exponent for base > 0, computed as exp(exponent * ln(base))."""
    if base <= 0:
        raise ValueError("power requires a positive base")
    return (exponent * base.ln()).exp()


def clamp(x: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return low if x < low else high if x > high else x


@pinned
def floor_int(x: Decimal) -> int:
    return int(x.to_integral_value(rounding=ROUND_FLOOR))
