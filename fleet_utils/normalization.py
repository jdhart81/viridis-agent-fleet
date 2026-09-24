"""
Fleet-wide numeric range normalization primitives.

Promoted Nightkeeper 2026-04-19 (Night 19, queue #4).

Pattern origin: D-Score's T/P/F/S component clipping to [0,1] and
Bounty Hunter's score normalization. Both agents (and at least 6 others)
implement variations of the same thing: take a numeric value, squeeze
it into a target range, either by clipping at the boundaries or by
winsorizing against percentile thresholds.

This module offers ONE configurable class — `RangeNormalizer` — that
handles the three flavors we see in the fleet:

  1. Unit interval clamp (most common):  clamp x to [0, 1]
  2. Arbitrary range clamp:               clamp x to [lo, hi]
  3. Winsorized quantile clamp:           clamp to [q_low, q_high] of a
                                          reference sample (useful for
                                          scorers that want to squash
                                          outliers without dropping them)

Design contract:
  - Stateless for clamping modes; winsorization fits against a sample,
    then re-normalizes the same or new inputs against those bounds.
  - Pure functions only; no I/O, no logging side effects (callers
    decide whether to log clip events).
  - Returns a `NormalizeResult` namedtuple so callers can inspect
    whether a clip occurred without re-computing bounds.
  - No numpy dependency — operates on plain Python numerics and/or
    lists so it's drop-in safe for agents without numpy installed.

Usage:

    from fleet_utils import RangeNormalizer

    # Unit interval
    norm = RangeNormalizer.unit()
    r = norm.apply(1.5)
    # r = NormalizeResult(value=1.0, clipped=True, reason='above max')

    # Arbitrary range
    norm = RangeNormalizer(lo=0.0, hi=100.0)
    norm.apply(42).value  # → 42.0
    norm.apply(150).value # → 100.0

    # Winsorized to 5%/95% of sample
    norm = RangeNormalizer.winsorize(sample=[0, 1, 2, 3, 100], q_low=0.05, q_high=0.95)
    norm.apply(100).value # → winsorized to 95th percentile

Invariants:
    - lo < hi (or lo == hi is accepted as a "pinned" degenerate case
      that yields a constant value; warned at construction time)
    - If value is bool → raised as ValueError (mirrors fleet_utils
      numeric semantics: bool is not a number for our purposes)
    - NaN / ±Inf inputs → raised as ValueError (poison values)
    - Sample for winsorize must be non-empty list/tuple of numerics
    - q_low, q_high ∈ [0, 1], q_low < q_high
"""

from dataclasses import dataclass
from typing import Any, Iterable, List, NamedTuple, Optional, Sequence, Union

Number = Union[int, float]


class NormalizeResult(NamedTuple):
    """Outcome of a single normalize() call."""
    value: float
    clipped: bool
    reason: Optional[str] = None


def _coerce_finite_number(raw: Any, field: str = "value") -> float:
    """Reject bool/NaN/Inf/non-numeric with a clean ValueError message."""
    if isinstance(raw, bool):
        raise ValueError(f"{field}: bool is not a numeric value (got {raw!r})")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{field}: expected numeric, got {type(raw).__name__}={raw!r}")
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(f"{field}: must be finite (no NaN/Inf), got {raw!r}")
    return v


def _percentile(sorted_values: List[float], q: float) -> float:
    """
    Linear-interpolation percentile (matches numpy default `linear`).

    sorted_values must already be sorted ascending. q ∈ [0, 1].
    """
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    # linear interpolation: position = q * (n - 1)
    pos = q * (n - 1)
    lo_idx = int(pos)
    hi_idx = min(lo_idx + 1, n - 1)
    frac = pos - lo_idx
    return sorted_values[lo_idx] * (1 - frac) + sorted_values[hi_idx] * frac


@dataclass
class RangeNormalizer:
    """
    Clamp numeric values into a target range, with optional winsorization.

    Three construction paths:
      - `RangeNormalizer(lo, hi)`: static clamp to [lo, hi]
      - `RangeNormalizer.unit()`: shortcut for [0, 1]
      - `RangeNormalizer.winsorize(sample, q_low, q_high)`: derive clamp
        bounds from percentiles of a sample

    Attributes:
        lo: lower clamp bound
        hi: upper clamp bound

    Invariants (enforced at __post_init__):
        - lo and hi must be finite floats
        - lo <= hi (equality is degenerate-but-allowed; every apply()
          returns `lo` unchanged)
    """
    lo: float
    hi: float

    def __post_init__(self):
        # Validate bounds are real numbers, not bools/NaN/Inf
        self.lo = _coerce_finite_number(self.lo, "lo")
        self.hi = _coerce_finite_number(self.hi, "hi")
        if self.lo > self.hi:
            raise ValueError(
                f"RangeNormalizer: lo ({self.lo}) must be <= hi ({self.hi})"
            )

    @classmethod
    def unit(cls) -> "RangeNormalizer":
        """Shortcut: clamp to [0, 1] (most common case in the fleet)."""
        return cls(lo=0.0, hi=1.0)

    @classmethod
    def winsorize(
        cls,
        sample: Sequence[Number],
        q_low: float = 0.05,
        q_high: float = 0.95,
    ) -> "RangeNormalizer":
        """
        Derive clamp bounds from percentiles of a reference sample.

        Useful when the fleet has a known distribution and wants to squash
        outliers to the q_low/q_high percentiles rather than dropping them
        or hard-coding bounds.

        Invariants:
          - sample must be a non-empty iterable of finite numerics
          - 0.0 <= q_low < q_high <= 1.0
        """
        if not isinstance(sample, (list, tuple)) or len(sample) == 0:
            raise ValueError("winsorize: sample must be a non-empty list/tuple")
        if not (0.0 <= q_low < q_high <= 1.0):
            raise ValueError(
                f"winsorize: require 0.0 <= q_low < q_high <= 1.0; "
                f"got q_low={q_low}, q_high={q_high}"
            )
        cleaned = sorted(_coerce_finite_number(v, f"sample[{i}]")
                         for i, v in enumerate(sample))
        lo = _percentile(cleaned, q_low)
        hi = _percentile(cleaned, q_high)
        return cls(lo=lo, hi=hi)

    def apply(self, raw: Any) -> NormalizeResult:
        """
        Apply the clamp. Returns NormalizeResult(value, clipped, reason).

        `clipped=True` iff the input was outside [lo, hi] (strictly).
        `reason` is 'below min' / 'above max' when clipped; None otherwise.
        """
        value = _coerce_finite_number(raw, "value")
        if value < self.lo:
            return NormalizeResult(value=self.lo, clipped=True, reason="below min")
        if value > self.hi:
            return NormalizeResult(value=self.hi, clipped=True, reason="above max")
        return NormalizeResult(value=value, clipped=False, reason=None)

    def apply_many(self, raws: Iterable[Any]) -> List[NormalizeResult]:
        """Vectorized apply — returns list in the same order as input."""
        return [self.apply(r) for r in raws]

    def clamp(self, raw: Any) -> float:
        """
        Shorthand: return just the clamped value (discards clipped flag).

        Use when the caller doesn't care whether a clip occurred — matches
        the `np.clip(x, lo, hi)` semantics that dscore-agent and
        bounty-hunter-agent inline throughout their scoring code.
        """
        return self.apply(raw).value


def clamp_to_range(
    value: Any,
    lo: Number,
    hi: Number,
    field: str = "value",
) -> NormalizeResult:
    """
    One-shot warn+clamp primitive — no class construction required.

    Promoted Nightkeeper Night 25 (2026-04-24, queue #3). Pattern needed in
    ≥3 agents (sentinel-watch radius_km/threshold; evoterra soil fractions;
    dscore T/P/F/S components) where the caller just wants:

        "Clamp this one number to [lo, hi], tell me if you had to clip."

    Functionally equivalent to:

        RangeNormalizer(lo=lo, hi=hi).apply(value)

    …but without requiring callers to instantiate and cache a normalizer.
    This matches the simpler `clamp_to_range(value, lo, hi) -> (value, warning)`
    idiom already inlined across the fleet.

    Invariants (enforced):
      - lo, hi are finite numerics (bool/NaN/Inf rejected via
        _coerce_finite_number with the field names "lo" and "hi").
      - lo <= hi (equality allowed: returns `lo` as a pinned constant).
      - value is a finite numeric (bool/NaN/Inf rejected with ValueError
        using the caller-supplied `field` for the error message).
      - Return type is always a NormalizeResult; `reason` is None when
        no clip occurred, "below min" or "above max" otherwise.

    Examples:
        >>> clamp_to_range(0.5, 0.0, 1.0)
        NormalizeResult(value=0.5, clipped=False, reason=None)

        >>> clamp_to_range(1.5, 0.0, 1.0, field="silt_fraction")
        NormalizeResult(value=1.0, clipped=True, reason='above max')

        >>> r = clamp_to_range(-3, 0, 500, field="radius_km")
        >>> r.clipped, r.value, r.reason
        (True, 0.0, 'below min')
    """
    # Validate lo/hi BEFORE the value so bound errors surface first
    # (callers can distinguish "my bounds are bad" from "my value is bad").
    lo_f = _coerce_finite_number(lo, "lo")
    hi_f = _coerce_finite_number(hi, "hi")
    if lo_f > hi_f:
        raise ValueError(
            f"clamp_to_range: lo ({lo_f}) must be <= hi ({hi_f})"
        )
    value_f = _coerce_finite_number(value, field)
    if value_f < lo_f:
        return NormalizeResult(value=lo_f, clipped=True, reason="below min")
    if value_f > hi_f:
        return NormalizeResult(value=hi_f, clipped=True, reason="above max")
    return NormalizeResult(value=value_f, clipped=False, reason=None)


__all__ = [
    "RangeNormalizer",
    "NormalizeResult",
    "clamp_to_range",
]
