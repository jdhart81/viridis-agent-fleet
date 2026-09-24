"""Structural and cross-reference validation for decision inputs."""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from .lineage import expected_artifact_id


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = PROJECT_ROOT / "schemas"

CLAIM_STATE_EVIDENCE_CLASSES = {
    "ASSUMED": {"ASSUMPTION_RECORD"},
    "HYPOTHESIZED": {"HYPOTHESIS_RATIONALE", "STAKEHOLDER_TESTIMONY"},
    "NUMERICALLY_SUPPORTED": {"NUMERICAL_RESULT"},
    "REPRODUCED": {"REPRODUCTION_RECEIPT"},
    "FORMALLY_PROVED": {"FORMAL_PROOF_RECEIPT"},
    "EMPIRICALLY_SUPPORTED": {"EMPIRICAL_OBSERVATION"},
    "AUTHORIZED": {"AUTHORIZATION_RECEIPT"},
    "DEPLOYED": {"DEPLOYMENT_RECEIPT"},
    "OBSERVED": {"OUTCOME_OBSERVATION"},
}


def _issue(code: str, message: str, path: str = "") -> dict[str, str]:
    return {"code": code, "message": message, "path": path}


def _duplicates(values: Iterable[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def _is_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _validate_numeric_interval(
    record: dict[str, Any],
    point_key: str,
    interval_key: str,
    prefix: str,
) -> list[dict[str, str]]:
    interval = record.get(interval_key)
    if interval is None:
        return []
    point = record.get(point_key)
    lower = interval.get("lower")
    upper = interval.get("upper")
    issues: list[dict[str, str]] = []
    if not all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        for value in (point, lower, upper)
    ):
        return [_issue(
            "NON_FINITE_INTERVAL",
            f"{interval_key} and {point_key} must contain finite numbers",
            f"{prefix}/{interval_key}",
        )]
    if lower > upper:
        issues.append(_issue(
            "INVERTED_INTERVAL",
            f"{interval_key}.lower cannot exceed {interval_key}.upper",
            f"{prefix}/{interval_key}",
        ))
    if point < lower or point > upper:
        issues.append(_issue(
            "POINT_OUTSIDE_INTERVAL",
            f"{point_key} must lie inside {interval_key}",
            f"{prefix}/{interval_key}",
        ))
    return issues


def validate_schema(instance: dict[str, Any], schema_name: str) -> list[dict[str, str]]:
    import json

    schema_path = SCHEMA_DIR / schema_name
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues: list[dict[str, str]] = []
    for error in sorted(
        validator.iter_errors(instance),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    ):
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        issues.append(_issue("SCHEMA_ERROR", error.message, path))
    return issues


def _check_unique_ids(
    records: list[dict[str, Any]],
    label: str,
    key: str = "id",
) -> list[dict[str, str]]:
    return [
        _issue("DUPLICATE_ID", f"Duplicate {label} identifier: {value}", f"/{label}")
        for value in _duplicates(str(record[key]) for record in records if key in record)
    ]


def validate_semantics(case: dict[str, Any], outcomes: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    if not _is_iso_datetime(case.get("evaluation_time")):
        issues.append(_issue("INVALID_DATETIME", "evaluation_time must be an ISO 8601 timestamp with a timezone", "/evaluation_time"))
    lease = case.get("governance", {}).get("action_policy", {}).get("authority_lease")
    if lease is not None and not _is_iso_datetime(lease.get("expires_at")):
        issues.append(_issue("INVALID_DATETIME", "authority lease expires_at must be an ISO 8601 timestamp with a timezone", "/governance/action_policy/authority_lease/expires_at"))

    if outcomes.get("case_id") != case.get("case_id"):
        issues.append(_issue("CASE_ID_MISMATCH", "Outcome bundle case_id does not match decision case", "/case_id"))
    if outcomes.get("case_version") != case.get("version"):
        issues.append(_issue("CASE_VERSION_MISMATCH", "Outcome bundle case_version does not match decision case", "/case_version"))

    stakeholders = {record["id"] for record in case.get("frame", {}).get("stakeholders", [])}
    scales = set(case.get("frame", {}).get("scales", []))
    candidates = {record["id"] for record in case.get("candidates", [])}
    scenarios = {record["id"] for record in case.get("scenarios", [])}
    mandatory_scenarios = {record["id"] for record in case.get("scenarios", []) if record.get("mandatory")}
    invariants = {record["id"] for record in case.get("invariants", [])}
    evidence_records = {record["id"]: record for record in case.get("evidence", [])}
    evidence = set(evidence_records)
    dependency_records = {record["id"]: record for record in outcomes.get("dependencies", [])}
    dependencies = set(dependency_records)
    lineage = outcomes.get("lineage", {})
    lineage_records = {
        record["artifact_id"]: record
        for record in lineage.get("artifacts", [])
    }
    lineage_ids = set(lineage_records)

    issues.extend(_check_unique_ids(case.get("frame", {}).get("stakeholders", []), "stakeholders"))
    issues.extend(_check_unique_ids(case.get("candidates", []), "candidates"))
    issues.extend(_check_unique_ids(case.get("scenarios", []), "scenarios"))
    issues.extend(_check_unique_ids(case.get("invariants", []), "invariants"))
    issues.extend(_check_unique_ids(case.get("evidence", []), "evidence"))
    issues.extend(_check_unique_ids(case.get("claims", []), "claims"))
    issues.extend(_check_unique_ids(outcomes.get("dependencies", []), "dependencies"))
    issues.extend(_check_unique_ids(lineage.get("artifacts", []), "lineage_artifacts", "artifact_id"))

    for index, artifact in enumerate(lineage.get("artifacts", [])):
        prefix = f"/lineage/artifacts/{index}"
        artifact_id = artifact["artifact_id"]
        expected_id = expected_artifact_id(artifact)
        if artifact_id != expected_id:
            issues.append(_issue(
                "LINEAGE_CONTENT_ADDRESS_MISMATCH",
                f"Lineage artifact ID does not match its immutable identity payload: expected {expected_id}",
                f"{prefix}/artifact_id",
            ))
        recall = artifact.get("recall")
        if recall is not None and not _is_iso_datetime(recall.get("effective_at")):
            issues.append(_issue(
                "INVALID_DATETIME",
                "lineage recall effective_at must be an ISO 8601 timestamp with a timezone",
                f"{prefix}/recall/effective_at",
            ))
        for parent_id in artifact["parent_ids"]:
            if parent_id == artifact_id:
                issues.append(_issue(
                    "LINEAGE_SELF_CYCLE",
                    f"Lineage artifact cannot be its own parent: {artifact_id}",
                    f"{prefix}/parent_ids",
                ))
            elif parent_id not in lineage_ids:
                issues.append(_issue(
                    "UNKNOWN_LINEAGE_PARENT",
                    f"Lineage artifact references unknown parent: {parent_id}",
                    f"{prefix}/parent_ids",
                ))

    lineage_visiting: set[str] = set()
    lineage_visited: set[str] = set()

    def visit_lineage(artifact_id: str, trail: tuple[str, ...]) -> None:
        if artifact_id in lineage_visited:
            return
        if artifact_id in lineage_visiting:
            cycle_start = trail.index(artifact_id) if artifact_id in trail else 0
            cycle = trail[cycle_start:] + (artifact_id,)
            issues.append(_issue(
                "LINEAGE_CYCLE",
                f"Lineage graph contains a cycle: {' -> '.join(cycle)}",
                "/lineage/artifacts",
            ))
            return
        lineage_visiting.add(artifact_id)
        record = lineage_records.get(artifact_id, {})
        for parent_id in record.get("parent_ids", []):
            if parent_id in lineage_records:
                visit_lineage(parent_id, trail + (artifact_id,))
        lineage_visiting.remove(artifact_id)
        lineage_visited.add(artifact_id)

    for artifact_id in sorted(lineage_ids):
        visit_lineage(artifact_id, ())

    model_artifact_id = lineage.get("model_artifact_id")
    model_artifact = lineage_records.get(model_artifact_id)
    if model_artifact is None:
        issues.append(_issue(
            "UNKNOWN_MODEL_ARTIFACT",
            f"model_artifact_id references unknown artifact: {model_artifact_id}",
            "/lineage/model_artifact_id",
        ))
    else:
        if model_artifact["kind"] != "MODEL":
            issues.append(_issue(
                "LINEAGE_ROLE_MISMATCH",
                "model_artifact_id must reference a MODEL artifact",
                "/lineage/model_artifact_id",
            ))
        if model_artifact["manifest"].get("model_id") != outcomes.get("model_id"):
            issues.append(_issue(
                "MODEL_ID_LINEAGE_MISMATCH",
                "model_id must match the content-addressed model manifest",
                "/model_id",
            ))

    required_artifact_ids = set(lineage.get("required_artifact_ids", []))
    for artifact_id in sorted(required_artifact_ids):
        if artifact_id not in lineage_ids:
            issues.append(_issue(
                "UNKNOWN_REQUIRED_ARTIFACT",
                f"required_artifact_ids references unknown artifact: {artifact_id}",
                "/lineage/required_artifact_ids",
            ))

    role_artifact_ids = {model_artifact_id, *lineage.get("adapter_artifact_ids", [])}
    for artifact_id in sorted(role_artifact_ids - required_artifact_ids):
        issues.append(_issue(
            "LINEAGE_ROLE_NOT_REQUIRED",
            f"Model and adapter roles must be required artifacts: {artifact_id}",
            "/lineage/required_artifact_ids",
        ))

    def has_ancestor(artifact_id: str, ancestor_id: str) -> bool:
        pending = list(lineage_records.get(artifact_id, {}).get("parent_ids", []))
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current == ancestor_id:
                return True
            if current in seen:
                continue
            seen.add(current)
            pending.extend(lineage_records.get(current, {}).get("parent_ids", []))
        return False

    for adapter_id in lineage.get("adapter_artifact_ids", []):
        adapter = lineage_records.get(adapter_id)
        if adapter is None:
            issues.append(_issue(
                "UNKNOWN_ADAPTER_ARTIFACT",
                f"adapter_artifact_ids references unknown artifact: {adapter_id}",
                "/lineage/adapter_artifact_ids",
            ))
            continue
        if adapter["kind"] != "ADAPTER":
            issues.append(_issue(
                "LINEAGE_ROLE_MISMATCH",
                f"adapter_artifact_ids must reference ADAPTER artifacts: {adapter_id}",
                "/lineage/adapter_artifact_ids",
            ))
        if model_artifact_id in lineage_records and not has_ancestor(adapter_id, model_artifact_id):
            issues.append(_issue(
                "ADAPTER_NOT_MODEL_BOUND",
                f"Adapter lineage does not descend from the declared model: {adapter_id}",
                "/lineage/adapter_artifact_ids",
            ))

    for claim_index, claim in enumerate(case.get("claims", [])):
        assertion_states = [assertion.get("state") for assertion in claim.get("assertions", [])]
        for duplicate in _duplicates(str(state) for state in assertion_states):
            issues.append(_issue(
                "DUPLICATE_CLAIM_STATE",
                f"Claim asserts the same epistemic state more than once: {duplicate}",
                f"/claims/{claim_index}/assertions",
            ))
        for assertion_index, assertion in enumerate(claim.get("assertions", [])):
            prefix = f"/claims/{claim_index}/assertions/{assertion_index}"
            state = assertion.get("state")
            permitted_classes = CLAIM_STATE_EVIDENCE_CLASSES.get(state, set())
            for evidence_ref in assertion.get("evidence_refs", []):
                evidence_record = evidence_records.get(evidence_ref)
                if evidence_record is None:
                    issues.append(_issue(
                        "UNKNOWN_EVIDENCE",
                        f"Claim state references unknown evidence: {evidence_ref}",
                        prefix,
                    ))
                    continue
                evidence_class = evidence_record.get("evidence_class")
                if evidence_class not in permitted_classes:
                    issues.append(_issue(
                        "CLAIM_STATE_SUPPORT_MISMATCH",
                        f"{state} cannot be supported by evidence class {evidence_class}: {evidence_ref}",
                        prefix,
                    ))

    for index, dependency in enumerate(outcomes.get("dependencies", [])):
        prefix = f"/dependencies/{index}"
        dependency_id = dependency.get("id")
        for parent_id in dependency.get("parent_ids", []):
            if parent_id == dependency_id:
                issues.append(_issue("DEPENDENCY_SELF_CYCLE", f"Dependency cannot be its own parent: {dependency_id}", prefix))
            elif parent_id not in dependencies:
                issues.append(_issue("UNKNOWN_DEPENDENCY_PARENT", f"Dependency references unknown parent: {parent_id}", prefix))
        for evidence_ref in dependency.get("evidence_refs", []):
            if evidence_ref not in evidence:
                issues.append(_issue("UNKNOWN_EVIDENCE", f"Dependency references unknown evidence: {evidence_ref}", prefix))

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit_dependency(dependency_id: str, trail: tuple[str, ...]) -> None:
        if dependency_id in visited:
            return
        if dependency_id in visiting:
            cycle_start = trail.index(dependency_id) if dependency_id in trail else 0
            cycle = trail[cycle_start:] + (dependency_id,)
            issues.append(_issue("DEPENDENCY_CYCLE", f"Dependency graph contains a cycle: {' -> '.join(cycle)}", "/dependencies"))
            return
        visiting.add(dependency_id)
        record = dependency_records.get(dependency_id, {})
        for parent_id in record.get("parent_ids", []):
            if parent_id in dependency_records:
                visit_dependency(parent_id, trail + (dependency_id,))
        visiting.remove(dependency_id)
        visited.add(dependency_id)

    for dependency_id in sorted(dependencies):
        visit_dependency(dependency_id, ())

    for index, invariant in enumerate(case.get("invariants", [])):
        if not isinstance(invariant.get("threshold"), (int, float)) or isinstance(invariant.get("threshold"), bool):
            issues.append(_issue("NON_NUMERIC_THRESHOLD", "Version 0.4 requires numeric invariant thresholds", f"/invariants/{index}/threshold"))
        for stakeholder in invariant.get("applies_to", []):
            if stakeholder not in stakeholders:
                issues.append(_issue("UNKNOWN_STAKEHOLDER", f"Invariant references unknown stakeholder: {stakeholder}", f"/invariants/{index}/applies_to"))

    assessment_keys: list[str] = []
    observed_coverage: set[tuple[str, str, str, str]] = set()
    for index, assessment in enumerate(outcomes.get("assessments", [])):
        prefix = f"/assessments/{index}"
        candidate_id = assessment.get("candidate_id")
        scenario_id = assessment.get("scenario_id")
        invariant_id = assessment.get("invariant_id")
        stakeholder_id = assessment.get("stakeholder_id")
        if candidate_id not in candidates:
            issues.append(_issue("UNKNOWN_CANDIDATE", f"Assessment references unknown candidate: {candidate_id}", prefix))
        if scenario_id not in scenarios:
            issues.append(_issue("UNKNOWN_SCENARIO", f"Assessment references unknown scenario: {scenario_id}", prefix))
        if invariant_id not in invariants:
            issues.append(_issue("UNKNOWN_INVARIANT", f"Assessment references unknown invariant: {invariant_id}", prefix))
        if stakeholder_id not in stakeholders:
            issues.append(_issue("UNKNOWN_STAKEHOLDER", f"Assessment references unknown stakeholder: {stakeholder_id}", prefix))
        if assessment.get("scale") not in scales:
            issues.append(_issue("UNKNOWN_SCALE", f"Assessment references unknown scale: {assessment.get('scale')}", prefix))
        value = assessment.get("observed_value")
        if isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isfinite(value):
            issues.append(_issue("NON_FINITE_VALUE", "Assessment observed_value must be finite", f"{prefix}/observed_value"))
        issues.extend(_validate_numeric_interval(
            assessment,
            "observed_value",
            "observed_interval",
            prefix,
        ))
        for evidence_ref in assessment.get("evidence_refs", []):
            if evidence_ref not in evidence:
                issues.append(_issue("UNKNOWN_EVIDENCE", f"Assessment references unknown evidence: {evidence_ref}", prefix))
        key = "|".join(str(assessment.get(part)) for part in (
            "candidate_id", "scenario_id", "invariant_id", "stakeholder_id", "scale", "time_point"
        ))
        assessment_keys.append(key)
        observed_coverage.add((candidate_id, scenario_id, invariant_id, stakeholder_id))

    for duplicate in _duplicates(assessment_keys):
        issues.append(_issue("DUPLICATE_ASSESSMENT", f"Duplicate assessment key: {duplicate}", "/assessments"))

    invariant_records = {record["id"]: record for record in case.get("invariants", [])}
    for candidate_id in sorted(candidates):
        for scenario_id in sorted(mandatory_scenarios):
            for invariant_id, invariant in sorted(invariant_records.items()):
                for stakeholder_id in invariant.get("applies_to", []):
                    required = (candidate_id, scenario_id, invariant_id, stakeholder_id)
                    if required not in observed_coverage:
                        issues.append(_issue(
                            "MISSING_MANDATORY_ASSESSMENT",
                            f"Missing mandatory assessment for candidate={candidate_id}, scenario={scenario_id}, invariant={invariant_id}, stakeholder={stakeholder_id}",
                            "/assessments",
                        ))

    trajectory_keys: list[str] = []
    for index, trajectory in enumerate(outcomes.get("trajectories", [])):
        prefix = f"/trajectories/{index}"
        candidate_id = trajectory.get("candidate_id")
        scenario_id = trajectory.get("scenario_id")
        invariant_id = trajectory.get("invariant_id")
        stakeholder_id = trajectory.get("stakeholder_id")
        scale = trajectory.get("scale")
        if candidate_id not in candidates:
            issues.append(_issue("UNKNOWN_CANDIDATE", f"Trajectory references unknown candidate: {candidate_id}", prefix))
        if scenario_id not in scenarios:
            issues.append(_issue("UNKNOWN_SCENARIO", f"Trajectory references unknown scenario: {scenario_id}", prefix))
        if invariant_id not in invariants:
            issues.append(_issue("UNKNOWN_INVARIANT", f"Trajectory references unknown invariant: {invariant_id}", prefix))
        if stakeholder_id not in stakeholders:
            issues.append(_issue("UNKNOWN_STAKEHOLDER", f"Trajectory references unknown stakeholder: {stakeholder_id}", prefix))
        elif invariant_id in invariant_records and stakeholder_id not in invariant_records[invariant_id].get("applies_to", []):
            issues.append(_issue(
                "TRAJECTORY_STAKEHOLDER_MISMATCH",
                f"Trajectory stakeholder {stakeholder_id} is outside invariant {invariant_id}",
                prefix,
            ))
        if scale not in scales:
            issues.append(_issue("UNKNOWN_SCALE", f"Trajectory references unknown scale: {scale}", prefix))

        trajectory_keys.append("|".join(str(part) for part in (
            candidate_id, scenario_id, invariant_id, stakeholder_id, scale
        )))
        elapsed_values: list[float] = []
        for sample_index, sample in enumerate(trajectory.get("samples", [])):
            sample_prefix = f"{prefix}/samples/{sample_index}"
            elapsed = sample.get("elapsed_hours")
            if (
                not isinstance(elapsed, (int, float))
                or isinstance(elapsed, bool)
                or not math.isfinite(elapsed)
            ):
                issues.append(_issue(
                    "NON_FINITE_TRAJECTORY_TIME",
                    "Trajectory elapsed_hours must be finite",
                    f"{sample_prefix}/elapsed_hours",
                ))
            else:
                elapsed_values.append(float(elapsed))
            value = sample.get("observed_value")
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and not math.isfinite(value)
            ):
                issues.append(_issue(
                    "NON_FINITE_VALUE",
                    "Trajectory observed_value must be finite",
                    f"{sample_prefix}/observed_value",
                ))
            issues.extend(_validate_numeric_interval(
                sample,
                "observed_value",
                "observed_interval",
                sample_prefix,
            ))
            for evidence_ref in sample.get("evidence_refs", []):
                if evidence_ref not in evidence:
                    issues.append(_issue(
                        "UNKNOWN_EVIDENCE",
                        f"Trajectory sample references unknown evidence: {evidence_ref}",
                        sample_prefix,
                    ))
        if any(right <= left for left, right in zip(elapsed_values, elapsed_values[1:])):
            issues.append(_issue(
                "NON_MONOTONIC_TRAJECTORY_TIME",
                "Trajectory samples must have strictly increasing elapsed_hours",
                f"{prefix}/samples",
            ))

    for duplicate in _duplicates(trajectory_keys):
        issues.append(_issue(
            "DUPLICATE_TRAJECTORY",
            f"Duplicate trajectory key: {duplicate}",
            "/trajectories",
        ))

    fallback_keys: list[str] = []
    for index, path in enumerate(outcomes.get("fallback_paths", [])):
        if path.get("candidate_id") not in candidates:
            issues.append(_issue("UNKNOWN_CANDIDATE", f"Fallback path references unknown candidate: {path.get('candidate_id')}", f"/fallback_paths/{index}"))
        fallback_keys.append(f"{path.get('candidate_id')}|{path.get('path_id')}")
        for dependency_id in path.get("dependency_ids", []):
            if dependency_id not in dependencies:
                issues.append(_issue("UNKNOWN_DEPENDENCY", f"Fallback path references unknown dependency: {dependency_id}", f"/fallback_paths/{index}/dependency_ids"))
    for duplicate in _duplicates(fallback_keys):
        issues.append(_issue("DUPLICATE_FALLBACK_PATH", f"Duplicate fallback path: {duplicate}", "/fallback_paths"))

    for collection in ("recovery", "externalities", "candidate_metrics"):
        for index, record in enumerate(outcomes.get(collection, [])):
            prefix = f"/{collection}/{index}"
            if record.get("candidate_id") not in candidates:
                issues.append(_issue("UNKNOWN_CANDIDATE", f"{collection} references unknown candidate: {record.get('candidate_id')}", prefix))
            scenario_id = record.get("scenario_id")
            if scenario_id is not None and scenario_id not in scenarios:
                issues.append(_issue("UNKNOWN_SCENARIO", f"{collection} references unknown scenario: {scenario_id}", prefix))
            stakeholder_id = record.get("stakeholder_id")
            if stakeholder_id is not None and stakeholder_id not in stakeholders:
                issues.append(_issue("UNKNOWN_STAKEHOLDER", f"{collection} references unknown stakeholder: {stakeholder_id}", prefix))
            for evidence_ref in record.get("evidence_refs", []):
                if evidence_ref not in evidence:
                    issues.append(_issue("UNKNOWN_EVIDENCE", f"{collection} references unknown evidence: {evidence_ref}", prefix))

    metric_keys = [f"{record.get('candidate_id')}|{record.get('name')}" for record in outcomes.get("candidate_metrics", [])]
    for duplicate in _duplicates(metric_keys):
        issues.append(_issue("DUPLICATE_CANDIDATE_METRIC", f"Duplicate candidate metric: {duplicate}", "/candidate_metrics"))

    reserved_dimensions = {
        "worst_viability_margin",
        "mandatory_scenario_pass_rate",
        "fallback_independence",
        "common_mode_exposure",
        "direct_fallback_independence",
        "direct_common_mode_exposure",
        "mean_detection_time_hours",
        "mean_containment_time_hours",
        "mean_recovery_time_hours",
        "mean_switching_cost",
        "irreversibility",
        "maximum_externality_magnitude",
        "minimum_assessment_confidence",
        "mean_assessment_confidence",
        "trajectory_count",
        "trajectory_coverage_rate",
        "worst_trajectory_margin",
        "maximum_possible_violation_span_hours",
        "maximum_robust_violation_span_hours",
        "maximum_declared_linear_shortfall_area",
        "latest_guaranteed_recovery_hours",
        "unrecovered_trajectory_count",
        "total_aftershock_count",
    }
    for index, metric in enumerate(outcomes.get("candidate_metrics", [])):
        issues.extend(_validate_numeric_interval(
            metric,
            "value",
            "value_interval",
            f"/candidate_metrics/{index}",
        ))
        if metric.get("name") in reserved_dimensions:
            issues.append(_issue("RESERVED_METRIC_NAME", f"Candidate metric uses reserved name: {metric.get('name')}", f"/candidate_metrics/{index}/name"))

    standard_directions = {
        "worst_viability_margin": "maximize",
        "mandatory_scenario_pass_rate": "maximize",
        "fallback_independence": "maximize",
        "common_mode_exposure": "minimize",
        "direct_fallback_independence": "maximize",
        "direct_common_mode_exposure": "minimize",
        "mean_detection_time_hours": "minimize",
        "mean_containment_time_hours": "minimize",
        "mean_recovery_time_hours": "minimize",
        "mean_switching_cost": "minimize",
        "irreversibility": "minimize",
        "maximum_externality_magnitude": "minimize",
        "minimum_assessment_confidence": "maximize",
        "mean_assessment_confidence": "maximize",
        "trajectory_count": "maximize",
        "trajectory_coverage_rate": "maximize",
        "worst_trajectory_margin": "maximize",
        "maximum_possible_violation_span_hours": "minimize",
        "maximum_robust_violation_span_hours": "minimize",
        "maximum_declared_linear_shortfall_area": "minimize",
        "latest_guaranteed_recovery_hours": "minimize",
        "unrecovered_trajectory_count": "minimize",
        "total_aftershock_count": "minimize",
    }
    metric_directions = {
        record["name"]: record["direction"]
        for record in outcomes.get("candidate_metrics", [])
    }
    for index, dimension in enumerate(case.get("governance", {}).get("comparison_dimensions", [])):
        name = dimension.get("name")
        expected = standard_directions.get(name, metric_directions.get(name))
        if expected is not None and dimension.get("direction") != expected:
            issues.append(_issue(
                "COMPARISON_DIRECTION_MISMATCH",
                f"Comparison dimension {name} must use direction {expected}",
                f"/governance/comparison_dimensions/{index}/direction",
            ))

    return sorted(issues, key=lambda item: (item["code"], item["path"], item["message"]))


def validate_inputs(case: dict[str, Any], outcomes: dict[str, Any]) -> list[dict[str, str]]:
    issues = validate_schema(case, "decision-case.schema.json")
    issues.extend(validate_schema(outcomes, "outcome-bundle.schema.json"))
    if not issues:
        issues.extend(validate_semantics(case, outcomes))
    return sorted(issues, key=lambda item: (item["code"], item["path"], item["message"]))
