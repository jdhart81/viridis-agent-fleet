"""
Tests for fleet_utils.normalization — RangeNormalizer primitive.

Published Nightkeeper 2026-04-19 (Night 19, queue #4). NOT yet adopted by
existing agents — cross-pollination migration queued for future nights
(D-Score T/P/F/S component clipping is the first adoption target; Bounty
Hunter fit-score normalization is second).
"""

import math
import os
import sys

import pytest

# Ensure fleet root on path so `from fleet_utils import ...` works
# when this test is run directly (agent conftest doesn't apply here).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fleet_utils.normalization import (  # noqa: E402
    RangeNormalizer,
    NormalizeResult,
    clamp_to_range,
    _percentile,
    _coerce_finite_number,
)


# ─── Construction & invariants ────────────────────────────────────────────────

class TestConstruction:
    def test_default_constructor(self):
        n = RangeNormalizer(lo=0.0, hi=1.0)
        assert n.lo == 0.0 and n.hi == 1.0

    def test_unit_shortcut(self):
        n = RangeNormalizer.unit()
        assert n.lo == 0.0 and n.hi == 1.0

    def test_arbitrary_range(self):
        n = RangeNormalizer(lo=-10.0, hi=10.0)
        assert n.lo == -10.0 and n.hi == 10.0

    def test_inverted_bounds_raises(self):
        with pytest.raises(ValueError):
            RangeNormalizer(lo=1.0, hi=0.0)

    def test_equal_bounds_allowed_as_pinned(self):
        """lo == hi is degenerate-but-legal; apply always returns lo."""
        n = RangeNormalizer(lo=5.0, hi=5.0)
        assert n.apply(3.0).value == 5.0
        assert n.apply(7.0).value == 5.0
        assert n.apply(5.0).value == 5.0

    def test_nan_bound_raises(self):
        with pytest.raises(ValueError):
            RangeNormalizer(lo=float("nan"), hi=1.0)

    def test_inf_bound_raises(self):
        with pytest.raises(ValueError):
            RangeNormalizer(lo=0.0, hi=float("inf"))

    def test_bool_bound_raises(self):
        """Reject bool explicitly (mirror fleet_utils.require_number semantics)."""
        with pytest.raises(ValueError):
            RangeNormalizer(lo=False, hi=True)

    def test_string_numeric_bound_coerced(self):
        n = RangeNormalizer(lo="0.0", hi="1.0")
        assert n.lo == 0.0 and n.hi == 1.0


# ─── apply() — clipping behavior ──────────────────────────────────────────────

class TestApply:
    def test_value_inside_range_not_clipped(self):
        n = RangeNormalizer.unit()
        r = n.apply(0.5)
        assert r.value == 0.5
        assert r.clipped is False
        assert r.reason is None

    def test_value_below_min_clipped(self):
        n = RangeNormalizer.unit()
        r = n.apply(-0.5)
        assert r.value == 0.0
        assert r.clipped is True
        assert r.reason == "below min"

    def test_value_above_max_clipped(self):
        n = RangeNormalizer.unit()
        r = n.apply(1.5)
        assert r.value == 1.0
        assert r.clipped is True
        assert r.reason == "above max"

    def test_value_at_exact_min_not_clipped(self):
        n = RangeNormalizer.unit()
        r = n.apply(0.0)
        assert r.value == 0.0 and r.clipped is False

    def test_value_at_exact_max_not_clipped(self):
        n = RangeNormalizer.unit()
        r = n.apply(1.0)
        assert r.value == 1.0 and r.clipped is False

    def test_string_numeric_accepted(self):
        n = RangeNormalizer.unit()
        assert n.apply("0.5").value == 0.5

    def test_int_accepted(self):
        n = RangeNormalizer(lo=0.0, hi=100.0)
        assert n.apply(42).value == 42.0

    def test_nan_rejected(self):
        n = RangeNormalizer.unit()
        with pytest.raises(ValueError):
            n.apply(float("nan"))

    def test_inf_rejected(self):
        n = RangeNormalizer.unit()
        with pytest.raises(ValueError):
            n.apply(float("inf"))

    def test_neg_inf_rejected(self):
        n = RangeNormalizer.unit()
        with pytest.raises(ValueError):
            n.apply(float("-inf"))

    def test_bool_rejected(self):
        n = RangeNormalizer.unit()
        with pytest.raises(ValueError):
            n.apply(True)

    def test_non_numeric_rejected(self):
        n = RangeNormalizer.unit()
        with pytest.raises(ValueError):
            n.apply("banana")

    def test_dict_rejected(self):
        n = RangeNormalizer.unit()
        with pytest.raises(ValueError):
            n.apply({"v": 0.5})


# ─── clamp() shorthand ────────────────────────────────────────────────────────

class TestClamp:
    def test_clamp_returns_float(self):
        n = RangeNormalizer.unit()
        v = n.clamp(0.5)
        assert v == 0.5 and isinstance(v, float)

    def test_clamp_clips_above(self):
        n = RangeNormalizer.unit()
        assert n.clamp(2.0) == 1.0

    def test_clamp_clips_below(self):
        n = RangeNormalizer.unit()
        assert n.clamp(-1.0) == 0.0

    def test_clamp_matches_np_clip_semantics(self):
        """np.clip(x, lo, hi) = max(lo, min(hi, x)). RangeNormalizer matches."""
        n = RangeNormalizer(lo=-5.0, hi=5.0)
        for x in [-10, -5, -2.5, 0, 2.5, 5, 10]:
            expected = max(-5.0, min(5.0, x))
            assert n.clamp(x) == expected, f"clamp({x}) differed"


# ─── apply_many() vectorized ──────────────────────────────────────────────────

class TestApplyMany:
    def test_apply_many_returns_list(self):
        n = RangeNormalizer.unit()
        results = n.apply_many([0.1, 0.5, 0.9])
        assert len(results) == 3
        assert all(isinstance(r, NormalizeResult) for r in results)

    def test_apply_many_preserves_order(self):
        n = RangeNormalizer.unit()
        results = n.apply_many([-1, 0.5, 2, 0.0])
        assert [r.value for r in results] == [0.0, 0.5, 1.0, 0.0]
        assert [r.clipped for r in results] == [True, False, True, False]

    def test_apply_many_empty_list(self):
        n = RangeNormalizer.unit()
        assert n.apply_many([]) == []

    def test_apply_many_raises_on_bad_element(self):
        """A bad element in the middle poisons the whole batch."""
        n = RangeNormalizer.unit()
        with pytest.raises(ValueError):
            n.apply_many([0.1, "banana", 0.9])


# ─── winsorize() classmethod ──────────────────────────────────────────────────

class TestWinsorize:
    def test_winsorize_default_quantiles(self):
        """Default q_low=0.05, q_high=0.95 against a uniform sample."""
        sample = list(range(101))  # 0..100
        n = RangeNormalizer.winsorize(sample)
        # 5th percentile of 0..100 is 5.0, 95th is 95.0
        assert n.lo == 5.0
        assert n.hi == 95.0

    def test_winsorize_custom_quantiles(self):
        sample = list(range(101))
        n = RangeNormalizer.winsorize(sample, q_low=0.0, q_high=1.0)
        assert n.lo == 0.0 and n.hi == 100.0

    def test_winsorize_clips_outliers(self):
        """An extreme outlier gets clipped to the winsorized upper bound."""
        sample = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 100]  # 100 is outlier
        n = RangeNormalizer.winsorize(sample, q_low=0.0, q_high=0.9)
        # 90th percentile of sorted sample is ~10 (not 100)
        assert n.apply(100).value < 100
        assert n.apply(100).clipped is True

    def test_winsorize_empty_sample_raises(self):
        with pytest.raises(ValueError):
            RangeNormalizer.winsorize([])

    def test_winsorize_non_list_sample_raises(self):
        with pytest.raises(ValueError):
            RangeNormalizer.winsorize({"a": 1, "b": 2})

    def test_winsorize_q_low_ge_q_high_raises(self):
        with pytest.raises(ValueError):
            RangeNormalizer.winsorize([1, 2, 3], q_low=0.9, q_high=0.1)

    def test_winsorize_q_low_negative_raises(self):
        with pytest.raises(ValueError):
            RangeNormalizer.winsorize([1, 2, 3], q_low=-0.1, q_high=0.9)

    def test_winsorize_q_high_over_1_raises(self):
        with pytest.raises(ValueError):
            RangeNormalizer.winsorize([1, 2, 3], q_low=0.1, q_high=1.1)

    def test_winsorize_sample_with_bool_raises(self):
        with pytest.raises(ValueError):
            RangeNormalizer.winsorize([1, True, 3])

    def test_winsorize_sample_with_nan_raises(self):
        with pytest.raises(ValueError):
            RangeNormalizer.winsorize([1, float("nan"), 3])

    def test_winsorize_single_element_sample(self):
        n = RangeNormalizer.winsorize([42.0], q_low=0.0, q_high=1.0)
        assert n.lo == 42.0 and n.hi == 42.0


# ─── Helper functions (internal but worth covering) ──────────────────────────

class TestHelpers:
    def test_coerce_valid_int(self):
        assert _coerce_finite_number(5) == 5.0

    def test_coerce_valid_str_numeric(self):
        assert _coerce_finite_number("3.14") == 3.14

    def test_coerce_bool_raises(self):
        with pytest.raises(ValueError):
            _coerce_finite_number(True)

    def test_coerce_nan_raises(self):
        with pytest.raises(ValueError):
            _coerce_finite_number(float("nan"))

    def test_coerce_posinf_raises(self):
        with pytest.raises(ValueError):
            _coerce_finite_number(float("inf"))

    def test_percentile_min(self):
        assert _percentile([0, 1, 2, 3, 4], 0.0) == 0

    def test_percentile_max(self):
        assert _percentile([0, 1, 2, 3, 4], 1.0) == 4

    def test_percentile_median(self):
        assert _percentile([0, 1, 2, 3, 4], 0.5) == 2.0

    def test_percentile_interpolated(self):
        """q=0.25 of [0,1,2,3,4] is position 1.0 → 1.0."""
        assert _percentile([0, 1, 2, 3, 4], 0.25) == 1.0

    def test_percentile_single_element(self):
        assert _percentile([7.0], 0.5) == 7.0


# ─── NormalizeResult namedtuple ───────────────────────────────────────────────

class TestNormalizeResult:
    def test_is_namedtuple(self):
        """NormalizeResult should be a namedtuple (unpackable, positional)."""
        r = NormalizeResult(value=0.5, clipped=False, reason=None)
        v, c, rs = r
        assert v == 0.5 and c is False and rs is None

    def test_reason_optional(self):
        r = NormalizeResult(value=0.5, clipped=False)
        assert r.reason is None

    def test_immutable(self):
        r = NormalizeResult(value=0.5, clipped=False)
        with pytest.raises(AttributeError):
            r.value = 99


# ─── clamp_to_range — one-shot primitive (Night 25) ───────────────────────────

class TestClampToRange:
    """
    Tests for the top-level `clamp_to_range(value, lo, hi, field)` helper.

    Invariants pinned:
      - In-range values pass through unchanged (clipped=False, reason=None).
      - Values below lo clip to lo (clipped=True, reason='below min').
      - Values above hi clip to hi (clipped=True, reason='above max').
      - Equivalent to RangeNormalizer(lo, hi).apply(value).
      - lo/hi bounds are validated first — bad bounds raise before value is checked.
      - NaN/Inf/bool value inputs raise ValueError using the caller's `field`.
      - lo == hi is a pinned degenerate case; returns lo with clipped flag set
        ONLY when value != lo.
    """

    # --- happy-path clamping ---
    def test_in_range_passes_through(self):
        r = clamp_to_range(0.5, 0.0, 1.0)
        assert r == NormalizeResult(value=0.5, clipped=False, reason=None)

    def test_below_min_clips_to_lo(self):
        r = clamp_to_range(-2.0, 0.0, 1.0)
        assert r.value == 0.0
        assert r.clipped is True
        assert r.reason == "below min"

    def test_above_max_clips_to_hi(self):
        r = clamp_to_range(1.5, 0.0, 1.0)
        assert r.value == 1.0
        assert r.clipped is True
        assert r.reason == "above max"

    def test_at_lo_boundary_not_clipped(self):
        r = clamp_to_range(0.0, 0.0, 1.0)
        assert r == NormalizeResult(value=0.0, clipped=False, reason=None)

    def test_at_hi_boundary_not_clipped(self):
        r = clamp_to_range(1.0, 0.0, 1.0)
        assert r == NormalizeResult(value=1.0, clipped=False, reason=None)

    # --- parity with RangeNormalizer.apply ---
    def test_parity_with_range_normalizer(self):
        """clamp_to_range must return the same NormalizeResult as RangeNormalizer.apply."""
        for value, lo, hi in [
            (0.5, 0.0, 1.0),
            (-3, 0, 500),
            (9999, -100, 100),
            (42, 0, 100),
        ]:
            direct = clamp_to_range(value, lo, hi)
            via_class = RangeNormalizer(lo=float(lo), hi=float(hi)).apply(value)
            assert direct == via_class, f"mismatch for ({value}, {lo}, {hi})"

    # --- field name propagation ---
    def test_default_field_name(self):
        with pytest.raises(ValueError, match="value:"):
            clamp_to_range(float("nan"), 0.0, 1.0)

    def test_custom_field_name_surfaces_in_error(self):
        with pytest.raises(ValueError, match="silt_fraction:"):
            clamp_to_range(float("nan"), 0.0, 1.0, field="silt_fraction")

    def test_custom_field_name_for_bool(self):
        with pytest.raises(ValueError, match="radius_km:"):
            clamp_to_range(True, 0.0, 500.0, field="radius_km")

    # --- bounds validation ---
    def test_inverted_bounds_raises(self):
        with pytest.raises(ValueError, match="lo .* must be <= hi"):
            clamp_to_range(0.5, 1.0, 0.0)

    def test_nan_lo_rejected(self):
        with pytest.raises(ValueError, match="lo:"):
            clamp_to_range(0.5, float("nan"), 1.0)

    def test_inf_hi_rejected(self):
        with pytest.raises(ValueError, match="hi:"):
            clamp_to_range(0.5, 0.0, float("inf"))

    def test_bool_bound_rejected(self):
        with pytest.raises(ValueError, match="lo:"):
            clamp_to_range(0.5, True, 1.0)

    # --- value validation ---
    def test_nan_value_rejected(self):
        with pytest.raises(ValueError):
            clamp_to_range(float("nan"), 0.0, 1.0)

    def test_inf_value_rejected(self):
        with pytest.raises(ValueError):
            clamp_to_range(float("inf"), 0.0, 1.0)

    def test_bool_value_rejected(self):
        with pytest.raises(ValueError, match="value:"):
            clamp_to_range(False, 0.0, 1.0)

    def test_non_numeric_value_rejected(self):
        with pytest.raises(ValueError):
            clamp_to_range("not a number", 0.0, 1.0)

    # --- degenerate pinned case (lo == hi) ---
    def test_equal_bounds_pins_to_lo(self):
        """When lo == hi, any in-range value (== lo) returns lo; off-value clips."""
        r_equal = clamp_to_range(5.0, 5.0, 5.0)
        assert r_equal.value == 5.0 and r_equal.clipped is False
        r_below = clamp_to_range(3.0, 5.0, 5.0)
        assert r_below.value == 5.0 and r_below.clipped is True
        assert r_below.reason == "below min"
        r_above = clamp_to_range(7.0, 5.0, 5.0)
        assert r_above.value == 5.0 and r_above.clipped is True
        assert r_above.reason == "above max"

    # --- type coercion ---
    def test_int_bounds_accepted(self):
        r = clamp_to_range(50, 0, 100)
        assert r.value == 50.0
        assert isinstance(r.value, float)

    def test_return_value_always_float(self):
        r = clamp_to_range(3, 0, 10)
        assert isinstance(r.value, float)
        assert r.value == 3.0
