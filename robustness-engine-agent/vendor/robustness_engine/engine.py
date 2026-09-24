"""Deterministic reference implementation of the robustness decision kernel."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import fmean
from typing import Any, Iterable

from .canonical import canonical_hash
from .lineage import lineage_hold_issues, summarize_lineage
from .trajectory import analyze_trajectory
from .uncertainty import (
    ROBUST_COMPARISON_MODE,
    ROBUST_DOMINANCE_RULE,
    assess_interval_viability,
    profile_interval,
    robust_lexicographic_relation,
    robustly_no_worse,
)
from .validation import validate_inputs


ENGINE_VERSION = "0.6.0"

CLAIM_STATES = (
    "ASSUMED",
    "HYPOTHESIZED",
    "NUMERICALLY_SUPPORTED",
    "REPRODUCED",
    "FORMALLY_PROVED",
    "EMPIRICALLY_SUPPORTED",
    "AUTHORIZED",
    "DEPLOYED",
    "OBSERVED",
)


def _rounded(value: float) -> float:
    rounded = round(float(value), 12)
    return 0.0 if rounded == 0 else rounded


def _mean(values: Iterable[float]) -> float | None:
    materialized = list(values)
    return _rounded(fmean(materialized)) if materialized else None


def _empty_epistemic_summary() -> dict[str, Any]:
    return {
        "claims_evaluated": 0,
        "asserted_count_by_state": {state: 0 for state in CLAIM_STATES},
        "implication_policy": "NONE",
        "inference_edges": [],
    }


def _claim_ledger(case: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    evidence_classes = {
        record["id"]: record["evidence_class"]
        for record in case["evidence"]
    }
    summary = _empty_epistemic_summary()
    ledger: list[dict[str, Any]] = []

    for claim in sorted(case["claims"], key=lambda item: item["id"]):
        asserted_states: list[dict[str, Any]] = []
        asserted_names: set[str] = set()
        for assertion in sorted(claim["assertions"], key=lambda item: item["state"]):
            state = assertion["state"]
            refs = sorted(assertion["evidence_refs"])
            asserted_names.add(state)
            summary["asserted_count_by_state"][state] += 1
            asserted_states.append({
                "state": state,
                "evidence_refs": refs,
                "evidence_classes": sorted({evidence_classes[ref] for ref in refs}),
                "basis": assertion["basis"],
            })
        ledger.append({
            "claim_id": claim["id"],
            "statement": claim["statement"],
            "scope": claim["scope"],
            "asserted_states": asserted_states,
            "unasserted_states": [state for state in CLAIM_STATES if state not in asserted_names],
            "limitations": claim["limitations"],
        })

    summary["claims_evaluated"] = len(ledger)
    return ledger, summary


def _set_independence(dependency_sets: list[set[str]]) -> tuple[float | None, float | None]:
    if not dependency_sets:
        return None, None
    if len(dependency_sets) == 1:
        return 0.0, 1.0
    pairwise_independence: list[float] = []
    for left_index, left in enumerate(dependency_sets):
        for right in dependency_sets[left_index + 1 :]:
            union = left | right
            similarity = len(left & right) / len(union) if union else 1.0
            pairwise_independence.append(1.0 - similarity)

    all_dependencies = set().union(*dependency_sets)
    shared_by_all = set.intersection(*dependency_sets)
    common_mode = len(shared_by_all) / len(all_dependencies) if all_dependencies else 1.0
    return _mean(pairwise_independence), _rounded(common_mode)


def _dependency_closure(
    dependency_id: str,
    dependencies: dict[str, dict[str, Any]],
    memo: dict[str, set[str]],
) -> set[str]:
    if dependency_id in memo:
        return memo[dependency_id]
    closure = {dependency_id}
    for parent_id in dependencies[dependency_id]["parent_ids"]:
        closure.update(_dependency_closure(parent_id, dependencies, memo))
    memo[dependency_id] = closure
    return closure


def _fallback_profile(
    paths: list[dict[str, Any]],
    dependencies: dict[str, dict[str, Any]],
) -> tuple[dict[str, float | int | None], dict[str, Any]]:
    direct_sets = [set(path["dependency_ids"]) for path in paths]
    memo: dict[str, set[str]] = {}
    expanded_sets = [
        set().union(*(_dependency_closure(dependency_id, dependencies, memo) for dependency_id in path["dependency_ids"]))
        for path in paths
    ]
    direct_independence, direct_common_mode = _set_independence(direct_sets)
    expanded_independence, expanded_common_mode = _set_independence(expanded_sets)
    shared_failure_domains = sorted(set.intersection(*expanded_sets)) if expanded_sets else []
    direct_common_dependencies = sorted(set.intersection(*direct_sets)) if direct_sets else []
    path_closures = [
        {
            "path_id": path["path_id"],
            "direct_dependencies": sorted(direct),
            "expanded_failure_domains": sorted(expanded),
        }
        for path, direct, expanded in zip(paths, direct_sets, expanded_sets)
    ]
    return {
        "fallback_path_count": len(paths),
        "fallback_independence": expanded_independence,
        "common_mode_exposure": expanded_common_mode,
        "direct_fallback_independence": direct_independence,
        "direct_common_mode_exposure": direct_common_mode,
    }, {
        "direct_common_dependencies": direct_common_dependencies,
        "shared_failure_domains": shared_failure_domains,
        "path_dependency_closures": path_closures,
    }


def _candidate_evaluation(
    case: dict[str, Any],
    outcomes: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    candidate_id = candidate["id"]
    invariant_records = {record["id"]: record for record in case["invariants"]}
    mandatory_scenarios = {record["id"] for record in case["scenarios"] if record["mandatory"]}
    minimum_confidence = case["governance"].get("minimum_assessment_confidence", 0.0)

    assessments = sorted(
        (record for record in outcomes["assessments"] if record["candidate_id"] == candidate_id),
        key=lambda record: (
            record["scenario_id"],
            record["invariant_id"],
            record["stakeholder_id"],
            str(record["time_point"]),
        ),
    )
    margins: list[float] = []
    mandatory_margins: list[float] = []
    margin_intervals: list[dict[str, Any]] = []
    mandatory_margin_intervals: list[dict[str, Any]] = []
    confidences: list[float] = []
    breaches: list[dict[str, Any]] = []
    gate_failures: list[dict[str, Any]] = []
    uncertainty_holds: list[dict[str, Any]] = []
    scenario_point_viability: dict[str, list[bool]] = defaultdict(list)
    scenario_interval_states: dict[str, list[str]] = defaultdict(list)

    for assessment in assessments:
        invariant = invariant_records[assessment["invariant_id"]]
        interval_result = assess_interval_viability(
            invariant,
            assessment["observed_value"],
            assessment.get("observed_interval"),
        )
        viable = interval_result["point_viable"]
        margin = interval_result["point_margin"]
        interval_state = interval_result["viability_state"]
        margins.append(margin)
        margin_intervals.append(interval_result["margin_interval"])
        confidences.append(assessment["confidence"])
        scenario_point_viability[assessment["scenario_id"]].append(viable)
        scenario_interval_states[assessment["scenario_id"]].append(interval_state)
        if assessment["scenario_id"] in mandatory_scenarios:
            mandatory_margins.append(margin)
            mandatory_margin_intervals.append(interval_result["margin_interval"])

        assessment_detail = {
            "scenario_id": assessment["scenario_id"],
            "invariant_id": assessment["invariant_id"],
            "stakeholder_id": assessment["stakeholder_id"],
            "time_point": assessment["time_point"],
            "observed_value": assessment["observed_value"],
            "observed_interval": interval_result["observed_interval"],
            "operator": invariant["operator"],
            "threshold": invariant["threshold"],
            "margin": margin,
            "margin_interval": interval_result["margin_interval"],
            "viability_state": interval_state,
            "non_compensable": invariant["non_compensable"],
        }

        if interval_state == "ROBUST_FAIL":
            breach = {
                **assessment_detail,
            }
            breaches.append(breach)
            if invariant["non_compensable"] and assessment["scenario_id"] in mandatory_scenarios:
                gate_failures.append({
                    "code": "NON_COMPENSABLE_BREACH",
                    "message": (
                        f"{assessment['invariant_id']} failed for {assessment['stakeholder_id']} "
                        f"in mandatory scenario {assessment['scenario_id']} at {assessment['time_point']}"
                    ),
                    "details": breach,
                })
        elif (
            interval_state == "UNCERTAIN"
            and invariant["non_compensable"]
            and assessment["scenario_id"] in mandatory_scenarios
        ):
            uncertainty_holds.append({
                "code": "NON_COMPENSABLE_INTERVAL_UNCERTAIN",
                "message": (
                    f"{assessment['invariant_id']} interval crosses its non-compensable "
                    f"boundary for {assessment['stakeholder_id']} in mandatory scenario "
                    f"{assessment['scenario_id']} at {assessment['time_point']}"
                ),
                "details": assessment_detail,
            })

        if assessment["scenario_id"] in mandatory_scenarios and assessment["confidence"] < minimum_confidence:
            gate_failures.append({
                "code": "ASSESSMENT_CONFIDENCE_BELOW_FLOOR",
                "message": (
                    f"Assessment confidence {assessment['confidence']} is below required floor "
                    f"{minimum_confidence} for {assessment['scenario_id']} / {assessment['invariant_id']}"
                ),
                "details": {
                    "scenario_id": assessment["scenario_id"],
                    "invariant_id": assessment["invariant_id"],
                    "stakeholder_id": assessment["stakeholder_id"],
                    "confidence": assessment["confidence"],
                },
            })

    externalities = sorted(
        (record for record in outcomes["externalities"] if record["candidate_id"] == candidate_id),
        key=lambda record: (record["scenario_id"], record["stakeholder_id"], record["description"]),
    )
    for externality in externalities:
        if externality["prohibited"]:
            gate_failures.append({
                "code": "PROHIBITED_EXTERNALITY",
                "message": (
                    f"Prohibited externality affects {externality['stakeholder_id']} "
                    f"in scenario {externality['scenario_id']}: {externality['description']}"
                ),
                "details": externality,
            })

    paths = sorted(
        (record for record in outcomes["fallback_paths"] if record["candidate_id"] == candidate_id),
        key=lambda record: record["path_id"],
    )
    dependency_records = {record["id"]: record for record in outcomes["dependencies"]}
    fallback_profile, dependency_ledger = _fallback_profile(paths, dependency_records)
    recovery = [record for record in outcomes["recovery"] if record["candidate_id"] == candidate_id]
    custom_metric_records = {
        record["name"]: record
        for record in outcomes["candidate_metrics"]
        if record["candidate_id"] == candidate_id
    }
    custom_metrics = {
        name: record["value"]
        for name, record in custom_metric_records.items()
    }

    trajectory_records = sorted(
        (
            record
            for record in outcomes["trajectories"]
            if record["candidate_id"] == candidate_id
        ),
        key=lambda record: (
            record["scenario_id"],
            record["invariant_id"],
            record["stakeholder_id"],
            record["scale"],
        ),
    )
    trajectory_analysis = [
        analyze_trajectory(invariant_records[record["invariant_id"]], record)
        for record in trajectory_records
    ]
    expected_trajectory_keys = {
        (scenario_id, invariant["id"], stakeholder_id)
        for scenario_id in mandatory_scenarios
        for invariant in case["invariants"]
        for stakeholder_id in invariant["applies_to"]
    }
    observed_trajectory_keys = {
        (record["scenario_id"], record["invariant_id"], record["stakeholder_id"])
        for record in trajectory_records
        if record["scenario_id"] in mandatory_scenarios
    }
    trajectory_coverage_rate = (
        len(observed_trajectory_keys & expected_trajectory_keys)
        / len(expected_trajectory_keys)
        if expected_trajectory_keys
        else 1.0
    )
    minimum_trajectory_coverage = case["governance"]["trajectory_policy"][
        "minimum_mandatory_coverage"
    ]
    if trajectory_coverage_rate < minimum_trajectory_coverage:
        uncertainty_holds.append({
            "code": "TRAJECTORY_COVERAGE_BELOW_FLOOR",
            "message": (
                f"Mandatory trajectory coverage {trajectory_coverage_rate:.6g} is below "
                f"the declared floor {minimum_trajectory_coverage:.6g}"
            ),
            "details": {
                "coverage_rate": _rounded(trajectory_coverage_rate),
                "minimum_required": minimum_trajectory_coverage,
                "observed_key_count": len(observed_trajectory_keys & expected_trajectory_keys),
                "expected_key_count": len(expected_trajectory_keys),
            },
        })

    for trajectory in trajectory_analysis:
        invariant = invariant_records[trajectory["invariant_id"]]
        if trajectory["scenario_id"] not in mandatory_scenarios or not invariant["non_compensable"]:
            continue
        failed_samples = [
            sample for sample in trajectory["samples"]
            if sample["viability_state"] == "ROBUST_FAIL"
        ]
        uncertain_samples = [
            sample for sample in trajectory["samples"]
            if sample["viability_state"] == "UNCERTAIN"
        ]
        if failed_samples:
            gate_failures.append({
                "code": "NON_COMPENSABLE_TRAJECTORY_BREACH",
                "message": (
                    f"{trajectory['invariant_id']} robustly fails within the mandatory "
                    f"trajectory for {trajectory['scenario_id']} / {trajectory['stakeholder_id']}"
                ),
                "details": {
                    "scenario_id": trajectory["scenario_id"],
                    "invariant_id": trajectory["invariant_id"],
                    "stakeholder_id": trajectory["stakeholder_id"],
                    "failed_samples": failed_samples,
                },
            })
        elif uncertain_samples:
            uncertainty_holds.append({
                "code": "NON_COMPENSABLE_TRAJECTORY_UNCERTAIN",
                "message": (
                    f"{trajectory['invariant_id']} crosses its boundary within the mandatory "
                    f"trajectory for {trajectory['scenario_id']} / {trajectory['stakeholder_id']}"
                ),
                "details": {
                    "scenario_id": trajectory["scenario_id"],
                    "invariant_id": trajectory["invariant_id"],
                    "stakeholder_id": trajectory["stakeholder_id"],
                    "uncertain_samples": uncertain_samples,
                },
            })

    mandatory_point_passes = [
        all(scenario_point_viability[scenario_id])
        for scenario_id in sorted(mandatory_scenarios)
    ]
    mandatory_guaranteed_passes = [
        all(state == "ROBUST_PASS" for state in scenario_interval_states[scenario_id])
        for scenario_id in sorted(mandatory_scenarios)
    ]
    mandatory_possible_passes = [
        not any(state == "ROBUST_FAIL" for state in scenario_interval_states[scenario_id])
        for scenario_id in sorted(mandatory_scenarios)
    ]
    profile: dict[str, float | int | None] = {
        "worst_viability_margin": min(mandatory_margins) if mandatory_margins else None,
        "worst_exploratory_margin": min(margins) if margins else None,
        "mandatory_scenario_pass_rate": (
            sum(1 for passed in mandatory_point_passes if passed) / len(mandatory_point_passes)
            if mandatory_point_passes
            else None
        ),
        "mean_detection_time_hours": _mean(record["detection_time_hours"] for record in recovery),
        "mean_containment_time_hours": _mean(record["containment_time_hours"] for record in recovery),
        "mean_recovery_time_hours": _mean(record["recovery_time_hours"] for record in recovery),
        "mean_switching_cost": _mean(record["switching_cost"] for record in recovery),
        "irreversibility": _mean(record["irreversibility"] for record in recovery),
        # Externalities may measure unlike harms. Report the largest declared
        # normalized magnitude; preserve every raw entry in the fragility ledger.
        "maximum_externality_magnitude": max((record["magnitude"] for record in externalities), default=0.0),
        "minimum_assessment_confidence": min(confidences) if confidences else None,
        "mean_assessment_confidence": _mean(confidences),
        "trajectory_count": len(trajectory_analysis),
        "trajectory_coverage_rate": _rounded(trajectory_coverage_rate),
        "worst_trajectory_margin": min(
            (record["worst_point_margin"] for record in trajectory_analysis),
            default=None,
        ),
        "maximum_possible_violation_span_hours": max(
            (record["possible_violation_span_hours"] for record in trajectory_analysis),
            default=0.0,
        ),
        "maximum_robust_violation_span_hours": max(
            (record["robust_violation_span_hours"] for record in trajectory_analysis),
            default=0.0,
        ),
        "maximum_declared_linear_shortfall_area": max(
            (record["declared_linear_shortfall_area"] for record in trajectory_analysis),
            default=0.0,
        ),
        "latest_guaranteed_recovery_hours": max(
            (
                record["guaranteed_recovery_elapsed_hours"]
                for record in trajectory_analysis
                if record["guaranteed_recovery_elapsed_hours"] is not None
            ),
            default=None,
        ),
        "unrecovered_trajectory_count": sum(
            record["guaranteed_recovery_elapsed_hours"] is None
            for record in trajectory_analysis
        ),
        "total_aftershock_count": sum(
            record["aftershock_count"] for record in trajectory_analysis
        ),
    }
    profile.update(fallback_profile)
    profile.update(custom_metrics)

    profile_intervals = {
        name: profile_interval(value)
        for name, value in profile.items()
    }
    if mandatory_margin_intervals:
        profile_intervals["worst_viability_margin"] = {
            "lower": min(interval["lower"] for interval in mandatory_margin_intervals),
            "upper": min(interval["upper"] for interval in mandatory_margin_intervals),
            "provenance": "DERIVED_INTERVAL",
        }
    if margin_intervals:
        profile_intervals["worst_exploratory_margin"] = {
            "lower": min(interval["lower"] for interval in margin_intervals),
            "upper": min(interval["upper"] for interval in margin_intervals),
            "provenance": "DERIVED_INTERVAL",
        }
    if mandatory_point_passes:
        profile_intervals["mandatory_scenario_pass_rate"] = {
            "lower": _rounded(
                sum(1 for passed in mandatory_guaranteed_passes if passed)
                / len(mandatory_guaranteed_passes)
            ),
            "upper": _rounded(
                sum(1 for passed in mandatory_possible_passes if passed)
                / len(mandatory_possible_passes)
            ),
            "provenance": "DERIVED_INTERVAL",
        }
    for name, record in custom_metric_records.items():
        profile_intervals[name] = profile_interval(
            record["value"],
            record.get("value_interval"),
        )
    if trajectory_analysis:
        profile_intervals["worst_trajectory_margin"] = {
            "lower": min(
                record["worst_margin_interval"]["lower"]
                for record in trajectory_analysis
            ),
            "upper": min(
                record["worst_margin_interval"]["upper"]
                for record in trajectory_analysis
            ),
            "provenance": "DERIVED_INTERVAL",
        }

    return {
        "candidate_id": candidate_id,
        "candidate_name": candidate["name"],
        "admissible": not gate_failures and not uncertainty_holds,
        "gate_failures": sorted(gate_failures, key=lambda item: (item["code"], item["message"])),
        "uncertainty_holds": sorted(
            uncertainty_holds,
            key=lambda item: (item["code"], item["message"]),
        ),
        "breaches": breaches,
        "trajectory_analysis": trajectory_analysis,
        "profile": profile,
        "profile_intervals": profile_intervals,
        "fragility_ledger": {
            **dependency_ledger,
            "externalities": externalities,
            "irreversible_commitments": candidate.get("irreversible_commitments", []),
        },
    }


def _dominates(
    left: dict[str, Any],
    right: dict[str, Any],
    dimensions: list[dict[str, str]],
) -> bool:
    no_worse = True
    strictly_better = False
    for dimension in dimensions:
        name = dimension["name"]
        dimension_no_worse, dimension_strict = robustly_no_worse(
            left["profile_intervals"][name],
            right["profile_intervals"][name],
            dimension["direction"],
        )
        no_worse = no_worse and dimension_no_worse
        strictly_better = strictly_better or dimension_strict
    return no_worse and strictly_better


def _pareto_frontier(
    evaluations: list[dict[str, Any]],
    dimensions: list[dict[str, str]],
) -> list[dict[str, Any]]:
    return sorted(
        [
            candidate
            for candidate in evaluations
            if not any(
                other["candidate_id"] != candidate["candidate_id"]
                and _dominates(other, candidate, dimensions)
                for other in evaluations
            )
        ],
        key=lambda item: item["candidate_id"],
    )


def _select_candidate(
    frontier: list[dict[str, Any]],
    governance: dict[str, Any],
) -> tuple[str | None, list[str]]:
    rule = governance["selection_rule"]
    if rule == "pareto_only":
        return None, ["Authorized governance selection is required from the Pareto frontier"]
    if rule == "unique_pareto":
        if len(frontier) == 1:
            return frontier[0]["candidate_id"], []
        return None, ["Multiple non-dominated candidates remain"]
    if rule == "lexicographic":
        dimensions = governance["comparison_dimensions"]
        winners = sorted(
            candidate["candidate_id"]
            for candidate in frontier
            if all(
                other["candidate_id"] == candidate["candidate_id"]
                or robust_lexicographic_relation(candidate, other, dimensions) == -1
                for other in frontier
            )
        )
        if len(winners) == 1:
            return winners[0], []
        unresolved = ", ".join(candidate["candidate_id"] for candidate in frontier)
        return None, [
            f"Robust lexicographic comparison is tied or interval-overlapping: {unresolved}"
        ]
    raise ValueError(f"Unsupported selection rule: {rule}")


def _scope_covers(scopes: list[str], requested: str) -> bool:
    for scope in scopes:
        if scope == "*" or scope == requested:
            return True
        if scope.endswith(".*") and requested.startswith(scope[:-1]):
            return True
    return False


def _action_boundary(case: dict[str, Any], selected: str | None) -> dict[str, Any]:
    policy = case.get("governance", {}).get("action_policy", {})
    lease = policy.get("authority_lease")
    reasons: list[str] = []
    authorized = True

    if selected is None:
        authorized = False
        reasons.append("No candidate has been selected")
    if policy.get("mode") != "bounded_execution":
        authorized = False
        reasons.append("Decision case is advisory-only")
    if "decision.execute" not in policy.get("authorized_actions", []):
        authorized = False
        reasons.append("Action policy does not authorize decision.execute")
    if not lease:
        authorized = False
        reasons.append("No authority lease is attached")
    else:
        if lease.get("state") != "ACTIVE":
            authorized = False
            reasons.append(f"Authority lease is {lease.get('state')}")
        if not _scope_covers(lease.get("scopes", []), "decision.execute"):
            authorized = False
            reasons.append("Authority lease does not cover decision.execute")
        evaluation_time = datetime.fromisoformat(case["evaluation_time"].replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(lease["expires_at"].replace("Z", "+00:00"))
        if evaluation_time >= expires_at:
            authorized = False
            reasons.append("Authority lease is expired at the declared evaluation time")

    return {
        "execution_status": "AUTHORIZED_NOT_EXECUTED" if authorized else "NOT_AUTHORIZED",
        "executed": False,
        "selected_candidate": selected,
        "authorized_actions": policy.get("authorized_actions", []) if authorized else [],
        "authority_lease_id": lease.get("lease_id") if lease else None,
        "reasons": sorted(set(reasons)),
    }


def evaluate_case(case: dict[str, Any], outcomes: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one case and return a deterministic, hash-bound decision record."""

    input_hashes = {
        "case_sha256": canonical_hash(case),
        "outcomes_sha256": canonical_hash(outcomes),
    }
    issues = validate_inputs(case, outcomes)
    if issues:
        record: dict[str, Any] = {
            "engine_version": ENGINE_VERSION,
            "status": "HOLD",
            "case_id": case.get("case_id"),
            "case_version": case.get("version"),
            "evaluation_time": case.get("evaluation_time"),
            "comparison_mode": ROBUST_COMPARISON_MODE,
            "dominance_rule": ROBUST_DOMINANCE_RULE,
            "input_hashes": input_hashes,
            "lineage_summary": None,
            "claim_ledger": [],
            "epistemic_summary": _empty_epistemic_summary(),
            "issues": issues,
            "evaluations": [],
            "admissible_candidates": [],
            "pareto_frontier": [],
            "selected_candidate": None,
            "action_boundary": {
                "execution_status": "NOT_AUTHORIZED",
                "executed": False,
                "selected_candidate": None,
                "authorized_actions": [],
                "authority_lease_id": None,
                "reasons": ["Decision case is structurally invalid"],
            },
        }
        record["record_sha256"] = canonical_hash(record)
        return record

    lineage_summary = summarize_lineage(outcomes, case["evaluation_time"])
    lineage_issues = lineage_hold_issues(lineage_summary)
    if lineage_issues:
        record = {
            "engine_version": ENGINE_VERSION,
            "status": "HOLD",
            "case_id": case["case_id"],
            "case_version": case["version"],
            "evaluation_time": case["evaluation_time"],
            "model_id": outcomes["model_id"],
            "comparison_mode": ROBUST_COMPARISON_MODE,
            "dominance_rule": ROBUST_DOMINANCE_RULE,
            "input_hashes": input_hashes,
            "lineage_summary": lineage_summary,
            "claim_ledger": [],
            "epistemic_summary": _empty_epistemic_summary(),
            "issues": lineage_issues,
            "evaluations": [],
            "admissible_candidates": [],
            "pareto_frontier": [],
            "selected_candidate": None,
            "action_boundary": {
                "execution_status": "NOT_AUTHORIZED",
                "executed": False,
                "selected_candidate": None,
                "authorized_actions": [],
                "authority_lease_id": None,
                "reasons": ["Required model or adapter lineage is recalled or quarantined"],
            },
        }
        record["record_sha256"] = canonical_hash(record)
        return record

    claim_ledger, epistemic_summary = _claim_ledger(case)
    evaluations = [
        _candidate_evaluation(case, outcomes, candidate)
        for candidate in sorted(case["candidates"], key=lambda item: item["id"])
    ]
    admissible = [evaluation for evaluation in evaluations if evaluation["admissible"]]
    dimensions = case["governance"]["comparison_dimensions"]

    uncertainty_issues = [
        {
            "code": hold["code"],
            "message": f"{evaluation['candidate_id']}: {hold['message']}",
            "path": f"/evaluations/{evaluation['candidate_id']}/uncertainty_holds",
        }
        for evaluation in evaluations
        if not evaluation["gate_failures"]
        for hold in evaluation["uncertainty_holds"]
    ]

    missing_dimensions: list[dict[str, str]] = []
    for evaluation in admissible:
        for dimension in dimensions:
            value = evaluation["profile"].get(dimension["name"])
            if value is None:
                missing_dimensions.append({
                    "code": "MISSING_COMPARISON_DIMENSION",
                    "message": f"{evaluation['candidate_id']} has no value for comparison dimension {dimension['name']}",
                    "path": f"/evaluations/{evaluation['candidate_id']}/profile/{dimension['name']}",
                })

    if uncertainty_issues:
        status = "HOLD"
        frontier = []
        selected = None
        selection_notes = [
            "A potentially admissible candidate crosses a mandatory non-compensable interval boundary"
        ]
    elif not admissible:
        status = "NO_ADMISSIBLE_OPTION"
        frontier: list[dict[str, Any]] = []
        selected = None
        selection_notes = ["Every candidate failed at least one hard gate"]
    elif missing_dimensions:
        status = "HOLD"
        frontier = []
        selected = None
        selection_notes = ["A declared comparison dimension is missing"]
    else:
        frontier = _pareto_frontier(admissible, dimensions)
        selected, selection_notes = _select_candidate(frontier, case["governance"])
        status = "DECISION" if selected is not None else "DECISION_READY"

    record = {
        "engine_version": ENGINE_VERSION,
        "status": status,
        "case_id": case["case_id"],
        "case_version": case["version"],
        "evaluation_time": case["evaluation_time"],
        "model_id": outcomes["model_id"],
        "comparison_mode": ROBUST_COMPARISON_MODE,
        "dominance_rule": ROBUST_DOMINANCE_RULE,
        "input_hashes": input_hashes,
        "lineage_summary": lineage_summary,
        "claim_ledger": claim_ledger,
        "epistemic_summary": epistemic_summary,
        "issues": sorted(
            uncertainty_issues + missing_dimensions,
            key=lambda item: (item["code"], item["path"], item["message"]),
        ),
        "decision_rule": case["governance"]["decision_rule"],
        "selection_rule": case["governance"]["selection_rule"],
        "evaluations": evaluations,
        "admissible_candidates": sorted(evaluation["candidate_id"] for evaluation in admissible),
        "pareto_frontier": [evaluation["candidate_id"] for evaluation in frontier],
        "selected_candidate": selected,
        "action_boundary": _action_boundary(case, selected),
        "selection_notes": selection_notes,
        "dissent": case.get("dissent", []),
    }
    record["record_sha256"] = canonical_hash(record)
    return record
