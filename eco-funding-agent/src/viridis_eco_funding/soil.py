"""Belowground indicator from GSIP soil properties (v0.1 method convention).

Inputs use GSIP canonical units (global-soil-intelligence/gsip, SoilGrids 2.0 basis,
Poggio et al. 2021). Each indicator is mapped to [0, 1] by a documented piecewise-linear
response; the soil index G is their unweighted mean. These response curves are a v0.1
convention for screening, not a calibrated soil-health model: LIMITS.md says what they
do not establish. The curve parameters are part of the method version.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ._decimal import ONE, ZERO, clamp, pinned

# indicator -> (description, kind, parameters)
CURVES: dict[str, tuple[str, str, tuple[Decimal, ...]]] = {
    "soc_g_per_kg": ("soil organic carbon, saturating at 40 g/kg (4 % SOC)", "rising",
                     (Decimal(0), Decimal(40))),
    "ph": ("pH, optimal 6.0-7.5, zero at <= 4.0 or >= 9.0", "plateau",
           (Decimal("4.0"), Decimal("6.0"), Decimal("7.5"), Decimal("9.0"))),
    "bd_kg_per_dm3": ("bulk density, full score <= 1.30, zero >= 1.80 (root-restricting)",
                      "falling", (Decimal("1.30"), Decimal("1.80"))),
    "cec_cmol_per_kg": ("cation exchange capacity, saturating at 25 cmol(+)/kg", "rising",
                        (Decimal(0), Decimal(25))),
    "n_g_per_kg": ("total nitrogen, saturating at 3 g/kg", "rising", (Decimal(0), Decimal(3))),
}


@pinned
def indicator_score(name: str, value: Decimal) -> Decimal:
    _, kind, p = CURVES[name]
    if kind == "rising":
        low, high = p
        return clamp((value - low) / (high - low), ZERO, ONE)
    if kind == "falling":
        good, bad = p
        return clamp((bad - value) / (bad - good), ZERO, ONE)
    zero_low, opt_low, opt_high, zero_high = p
    if value <= zero_low or value >= zero_high:
        return ZERO
    if value < opt_low:
        return (value - zero_low) / (opt_low - zero_low)
    if value > opt_high:
        return (zero_high - value) / (zero_high - opt_high)
    return ONE


@pinned
def soil_index(spec: dict[str, Any]) -> dict[str, Any]:
    scores = {name: indicator_score(name, value) for name, value in spec["indicators"].items()}
    value = sum(scores.values(), ZERO) / Decimal(len(scores))
    return {
        "value": value,
        "sigma": spec["sigma"],
        "sigma_basis": spec["sigma_basis"],
        "indicator_scores": scores,
        "curves": {name: CURVES[name][0] for name in scores},
        "source": spec["source"],
    }
