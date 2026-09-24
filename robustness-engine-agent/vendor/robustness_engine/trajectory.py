"""Deterministic trajectory measures over declared ordered outcome samples."""

from __future__ import annotations

from typing import Any

from .uncertainty import assess_interval_viability


TRAJECTORY_INTERPOLATION = "PIECEWISE_LINEAR_BETWEEN_DECLARED_SAMPLES"
TRAJECTORY_SEGMENT_POLICY = "CONSERVATIVE_ENDPOINT_STATE_SPAN"


def _rounded(value: float) -> float:
    rounded = round(float(value), 12)
    return 0.0 if rounded == 0 else rounded


def analyze_trajectory(
    invariant: dict[str, Any],
    trajectory: dict[str, Any],
) -> dict[str, Any]:
    """Analyze one already-validated trajectory without inventing samples.

    Shortfall area uses piecewise-linear interpolation of point margins. The
    possible and robust violation spans are deliberately conservative endpoint
    classifications, not estimates of continuous real-world failure duration.
    """

    samples = sorted(trajectory["samples"], key=lambda item: item["elapsed_hours"])
    evaluated: list[dict[str, Any]] = []
    for sample in samples:
        result = assess_interval_viability(
            invariant,
            sample["observed_value"],
            sample.get("observed_interval"),
        )
        evaluated.append({
            "elapsed_hours": _rounded(sample["elapsed_hours"]),
            "observed_value": sample["observed_value"],
            "observed_interval": result["observed_interval"],
            "point_margin": result["point_margin"],
            "margin_interval": result["margin_interval"],
            "viability_state": result["viability_state"],
            "evidence_refs": sorted(sample["evidence_refs"]),
        })

    possible_span = 0.0
    robust_span = 0.0
    shortfall_area = 0.0
    for left, right in zip(evaluated, evaluated[1:]):
        duration = right["elapsed_hours"] - left["elapsed_hours"]
        if left["viability_state"] != "ROBUST_PASS" or right["viability_state"] != "ROBUST_PASS":
            possible_span += duration
        if left["viability_state"] == "ROBUST_FAIL" and right["viability_state"] == "ROBUST_FAIL":
            robust_span += duration
        left_shortfall = max(0.0, -left["point_margin"])
        right_shortfall = max(0.0, -right["point_margin"])
        shortfall_area += duration * (left_shortfall + right_shortfall) / 2

    worst_index = min(
        range(len(evaluated)),
        key=lambda index: (evaluated[index]["point_margin"], index),
    )
    recovery_elapsed: float | None = None
    for index in range(worst_index, len(evaluated)):
        if all(
            sample["viability_state"] == "ROBUST_PASS"
            for sample in evaluated[index:]
        ):
            recovery_elapsed = evaluated[index]["elapsed_hours"]
            break

    aftershock_count = sum(
        1
        for left, right in zip(evaluated, evaluated[1:])
        if left["viability_state"] == "ROBUST_PASS"
        and right["viability_state"] != "ROBUST_PASS"
    )

    return {
        "candidate_id": trajectory["candidate_id"],
        "scenario_id": trajectory["scenario_id"],
        "invariant_id": trajectory["invariant_id"],
        "stakeholder_id": trajectory["stakeholder_id"],
        "scale": trajectory["scale"],
        "basis": trajectory["basis"],
        "interpolation": TRAJECTORY_INTERPOLATION,
        "segment_policy": TRAJECTORY_SEGMENT_POLICY,
        "sample_count": len(evaluated),
        "observed_span_hours": _rounded(
            evaluated[-1]["elapsed_hours"] - evaluated[0]["elapsed_hours"]
        ),
        "worst_point_margin": min(sample["point_margin"] for sample in evaluated),
        "worst_margin_interval": {
            "lower": min(sample["margin_interval"]["lower"] for sample in evaluated),
            "upper": min(sample["margin_interval"]["upper"] for sample in evaluated),
            "provenance": "DERIVED_INTERVAL",
        },
        "possible_violation_span_hours": _rounded(possible_span),
        "robust_violation_span_hours": _rounded(robust_span),
        "declared_linear_shortfall_area": _rounded(shortfall_area),
        "guaranteed_recovery_elapsed_hours": recovery_elapsed,
        "aftershock_count": aftershock_count,
        "samples": evaluated,
    }
