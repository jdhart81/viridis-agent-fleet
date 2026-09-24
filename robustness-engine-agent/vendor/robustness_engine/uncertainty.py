"""Interval semantics for viability gates and robust comparison."""

from __future__ import annotations

from typing import Any


ROBUST_COMPARISON_MODE = "ROBUST_INTERVAL_DOMINANCE"
ROBUST_DOMINANCE_RULE = "WORST_CASE_NO_WORSE_THAN_OTHER_BEST_CASE"


def _rounded(value: float) -> float:
    rounded = round(float(value), 12)
    return 0.0 if rounded == 0 else rounded


def declared_interval(
    point: float,
    declaration: dict[str, Any] | None,
) -> tuple[float, float, str]:
    """Return lower, upper, and provenance for a point or declared interval."""

    if declaration is None:
        value = float(point)
        return value, value, "POINT_ESTIMATE"
    return (
        float(declaration["lower"]),
        float(declaration["upper"]),
        "DECLARED_INTERVAL",
    )


def viability_margin(invariant: dict[str, Any], observed: float) -> tuple[bool, float]:
    threshold = float(invariant["threshold"])
    normalizer = float(invariant.get("normalization") or max(abs(threshold), 1.0))
    operator = invariant["operator"]

    if operator == ">=":
        return observed >= threshold, _rounded((observed - threshold) / normalizer)
    if operator == ">":
        return observed > threshold, _rounded((observed - threshold) / normalizer)
    if operator == "<=":
        return observed <= threshold, _rounded((threshold - observed) / normalizer)
    if operator == "<":
        return observed < threshold, _rounded((threshold - observed) / normalizer)
    if operator == "==":
        viable = observed == threshold
        return viable, _rounded(-abs(observed - threshold) / normalizer)
    raise ValueError(f"Unsupported invariant operator: {operator}")


def assess_interval_viability(
    invariant: dict[str, Any],
    observed: float,
    declaration: dict[str, Any] | None,
) -> dict[str, Any]:
    """Classify an interval as guaranteed pass, guaranteed fail, or uncertain."""

    lower, upper, provenance = declared_interval(observed, declaration)
    point_viable, point_margin = viability_margin(invariant, observed)
    _, lower_endpoint_margin = viability_margin(invariant, lower)
    _, upper_endpoint_margin = viability_margin(invariant, upper)
    threshold = float(invariant["threshold"])
    operator = invariant["operator"]

    if operator in {">=", ">"}:
        margin_lower = lower_endpoint_margin
        margin_upper = upper_endpoint_margin
    elif operator in {"<=", "<"}:
        margin_lower = upper_endpoint_margin
        margin_upper = lower_endpoint_margin
    else:
        margin_lower = min(lower_endpoint_margin, upper_endpoint_margin)
        margin_upper = (
            0.0
            if lower <= threshold <= upper
            else max(lower_endpoint_margin, upper_endpoint_margin)
        )

    if operator == ">=":
        state = "ROBUST_PASS" if lower >= threshold else (
            "ROBUST_FAIL" if upper < threshold else "UNCERTAIN"
        )
    elif operator == ">":
        state = "ROBUST_PASS" if lower > threshold else (
            "ROBUST_FAIL" if upper <= threshold else "UNCERTAIN"
        )
    elif operator == "<=":
        state = "ROBUST_PASS" if upper <= threshold else (
            "ROBUST_FAIL" if lower > threshold else "UNCERTAIN"
        )
    elif operator == "<":
        state = "ROBUST_PASS" if upper < threshold else (
            "ROBUST_FAIL" if lower >= threshold else "UNCERTAIN"
        )
    else:
        lower_equal = lower == threshold
        upper_equal = upper == threshold
        if lower_equal and upper_equal:
            state = "ROBUST_PASS"
        elif upper < threshold or lower > threshold:
            state = "ROBUST_FAIL"
        else:
            state = "UNCERTAIN"

    return {
        "point_viable": point_viable,
        "point_margin": point_margin,
        "observed_interval": {
            "lower": _rounded(lower),
            "upper": _rounded(upper),
            "provenance": provenance,
            "basis": declaration["basis"] if declaration is not None else "Point estimate",
        },
        "margin_interval": {
            "lower": _rounded(margin_lower),
            "upper": _rounded(margin_upper),
            "provenance": "DERIVED_INTERVAL" if declaration is not None else "POINT_ESTIMATE",
        },
        "viability_state": state,
    }


def profile_interval(
    value: float | int | None,
    declaration: dict[str, Any] | None = None,
    *,
    derived: bool = False,
) -> dict[str, Any] | None:
    if value is None:
        return None
    lower, upper, provenance = declared_interval(float(value), declaration)
    if derived:
        provenance = "DERIVED_INTERVAL"
    return {
        "lower": _rounded(lower),
        "upper": _rounded(upper),
        "provenance": provenance,
    }


def robustly_no_worse(
    left: dict[str, float | str],
    right: dict[str, float | str],
    direction: str,
) -> tuple[bool, bool]:
    """Return guaranteed no-worse and guaranteed-strictly-better flags."""

    if direction == "maximize":
        return left["lower"] >= right["upper"], left["lower"] > right["upper"]
    return left["upper"] <= right["lower"], left["upper"] < right["lower"]


def robust_lexicographic_relation(
    left: dict[str, Any],
    right: dict[str, Any],
    dimensions: list[dict[str, str]],
) -> int | None:
    """Return -1 if left wins, 1 if right wins, 0 if tied, None if unresolved."""

    for dimension in dimensions:
        name = dimension["name"]
        left_interval = left["profile_intervals"][name]
        right_interval = right["profile_intervals"][name]
        if left_interval == right_interval:
            continue
        left_no_worse, left_strict = robustly_no_worse(
            left_interval,
            right_interval,
            dimension["direction"],
        )
        right_no_worse, right_strict = robustly_no_worse(
            right_interval,
            left_interval,
            dimension["direction"],
        )
        if left_no_worse and left_strict and not right_no_worse:
            return -1
        if right_no_worse and right_strict and not left_no_worse:
            return 1
        return None
    return 0
