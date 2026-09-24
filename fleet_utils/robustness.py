"""Governed robustness primitives for the Viridis agent fleet.

This module carries the small cross-agent contract that is stable enough to
share:

1. fallback independence is measured over expanded failure domains;
2. selection and execution authority are separate;
3. epistemic states require matching evidence and imply nothing else;
4. content-addressed lineage propagates recall to every descendant; and
5. interval-valued outcomes compare worst cases against other best cases.

The Lean 4 package ``Viridis.RobustnessKernel`` formally proves the nonempty
shared-dependency and Boolean authority results. Graph completeness, receipt
authenticity, empirical validity, deployment, and outcomes remain outside that
proof.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from typing import Iterable, Mapping, Sequence


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

CLAIM_STATE_EVIDENCE = {
    "ASSUMED": frozenset({"ASSUMPTION_RECORD"}),
    "HYPOTHESIZED": frozenset({"HYPOTHESIS_RATIONALE", "STAKEHOLDER_TESTIMONY"}),
    "NUMERICALLY_SUPPORTED": frozenset({"NUMERICAL_RESULT"}),
    "REPRODUCED": frozenset({"REPRODUCTION_RECEIPT"}),
    "FORMALLY_PROVED": frozenset({"FORMAL_PROOF_RECEIPT"}),
    "EMPIRICALLY_SUPPORTED": frozenset({"EMPIRICAL_OBSERVATION"}),
    "AUTHORIZED": frozenset({"AUTHORIZATION_RECEIPT"}),
    "DEPLOYED": frozenset({"DEPLOYMENT_RECEIPT"}),
    "OBSERVED": frozenset({"OUTCOME_OBSERVATION"}),
}

INFERENCE_POLICY = "NONE"
INFERENCE_EDGES: tuple[tuple[str, str], ...] = ()
LINEAGE_IDENTITY_RULE = "sha256(canonical_json({kind,manifest,parent_ids_sorted}))"
LINEAGE_RECALL_POLICY = "RECALL_CASCADES_TO_ALL_DESCENDANTS"
ROBUST_COMPARISON_MODE = "ROBUST_INTERVAL_DOMINANCE"
ROBUST_DOMINANCE_RULE = "WORST_CASE_NO_WORSE_THAN_OTHER_BEST_CASE"


class RobustnessContractError(ValueError):
    """Fail-closed error for malformed robustness inputs."""


@dataclass(frozen=True)
class AuthorityLease:
    """The five explicit authority conditions checked after selection."""

    advisory_only: bool
    action_allowed: bool
    active: bool
    scope_matches: bool
    unexpired: bool


@dataclass(frozen=True)
class FallbackProfile:
    """Exact direct and expanded pairwise diagnostic for two fallback paths."""

    direct_independence: Fraction
    expanded_independence: Fraction
    direct_dependencies: tuple[tuple[str, ...], tuple[str, ...]]
    expanded_dependencies: tuple[tuple[str, ...], tuple[str, ...]]
    shared_failure_domains: tuple[str, ...]


@dataclass(frozen=True)
class LineageStatus:
    """Point-in-time recall status for a content-addressed lineage DAG."""

    active_artifact_ids: tuple[str, ...]
    recalled_artifact_ids: tuple[str, ...]
    quarantined_artifact_ids: tuple[str, ...]
    pending_recall_artifact_ids: tuple[str, ...]
    blocked_required_artifact_ids: tuple[str, ...]

    @property
    def decision_usable(self) -> bool:
        return not self.blocked_required_artifact_ids


@dataclass(frozen=True)
class NumericInterval:
    """Closed numeric interval used by the fleet's conservative comparator."""

    lower: float
    upper: float


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RobustnessContractError(f"{label} must be a finite number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise RobustnessContractError(f"{label} must be a finite number")
    return numeric


def numeric_interval(
    point: object,
    lower: object | None = None,
    upper: object | None = None,
) -> NumericInterval:
    """Validate an interval witness around a point estimate, failing closed."""

    point_value = _finite_number(point, "point")
    lower_value = point_value if lower is None else _finite_number(lower, "lower")
    upper_value = point_value if upper is None else _finite_number(upper, "upper")
    if lower_value > upper_value:
        raise RobustnessContractError("interval lower bound exceeds upper bound")
    if not lower_value <= point_value <= upper_value:
        raise RobustnessContractError("point lies outside declared interval")
    return NumericInterval(lower=lower_value, upper=upper_value)


def classify_viability_interval(
    operator: str,
    threshold: object,
    interval: NumericInterval,
) -> str:
    """Return ROBUST_PASS, ROBUST_FAIL, or UNCERTAIN for an invariant."""

    threshold_value = _finite_number(threshold, "threshold")
    if not isinstance(interval, NumericInterval):
        raise RobustnessContractError("interval must be a NumericInterval")

    if operator == ">=":
        if interval.lower >= threshold_value:
            return "ROBUST_PASS"
        if interval.upper < threshold_value:
            return "ROBUST_FAIL"
    elif operator == ">":
        if interval.lower > threshold_value:
            return "ROBUST_PASS"
        if interval.upper <= threshold_value:
            return "ROBUST_FAIL"
    elif operator == "<=":
        if interval.upper <= threshold_value:
            return "ROBUST_PASS"
        if interval.lower > threshold_value:
            return "ROBUST_FAIL"
    elif operator == "<":
        if interval.upper < threshold_value:
            return "ROBUST_PASS"
        if interval.lower >= threshold_value:
            return "ROBUST_FAIL"
    elif operator == "==":
        if interval.lower == interval.upper == threshold_value:
            return "ROBUST_PASS"
        if threshold_value < interval.lower or threshold_value > interval.upper:
            return "ROBUST_FAIL"
    else:
        raise RobustnessContractError(f"unsupported viability operator: {operator!r}")
    return "UNCERTAIN"


def robust_interval_relation(
    left: NumericInterval,
    right: NumericInterval,
    direction: str,
) -> tuple[bool, bool]:
    """Return conservative (no-worse, strictly-better) interval relations."""

    if not isinstance(left, NumericInterval) or not isinstance(right, NumericInterval):
        raise RobustnessContractError("both values must be NumericInterval instances")
    if direction == "maximize":
        return left.lower >= right.upper, left.lower > right.upper
    if direction == "minimize":
        return left.upper <= right.lower, left.upper < right.lower
    raise RobustnessContractError(f"unsupported comparison direction: {direction!r}")


def robustly_dominates(
    left_profile: Mapping[str, NumericInterval],
    right_profile: Mapping[str, NumericInterval],
    dimensions: Mapping[str, str],
) -> bool:
    """Require worst-case no-worse in every dimension and strict in one."""

    if not dimensions:
        raise RobustnessContractError("at least one comparison dimension is required")
    strictly_better = False
    for dimension, direction in dimensions.items():
        if dimension not in left_profile or dimension not in right_profile:
            raise RobustnessContractError(
                f"missing comparison dimension: {dimension}"
            )
        no_worse, strict = robust_interval_relation(
            left_profile[dimension],
            right_profile[dimension],
            direction,
        )
        if not no_worse:
            return False
        strictly_better = strictly_better or strict
    return strictly_better


def _parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise RobustnessContractError(f"{label} must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RobustnessContractError(
            f"{label} must be an ISO 8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise RobustnessContractError(f"{label} must include a timezone")
    return parsed


def lineage_artifact_id(
    kind: str,
    manifest: Mapping[str, object],
    parent_ids: Iterable[str],
) -> str:
    """Return the canonical content address for one immutable lineage node."""

    identity = {
        "kind": kind,
        "manifest": dict(manifest),
        "parent_ids": sorted(parent_ids),
    }
    payload = json.dumps(
        identity,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def evaluate_lineage(
    artifacts: Sequence[Mapping[str, object]],
    required_artifact_ids: Iterable[str],
    evaluation_time: str,
) -> LineageStatus:
    """Validate lineage and quarantine descendants of effective recalls."""

    evaluated_at = _parse_timestamp(evaluation_time, "evaluation_time")
    records: dict[str, Mapping[str, object]] = {}
    for artifact in artifacts:
        artifact_id = artifact.get("artifact_id")
        kind = artifact.get("kind")
        manifest = artifact.get("manifest")
        parent_ids = artifact.get("parent_ids")
        if not isinstance(artifact_id, str) or artifact_id in records:
            raise RobustnessContractError(
                f"missing or duplicate lineage artifact ID: {artifact_id!r}"
            )
        if not isinstance(kind, str) or not isinstance(manifest, Mapping):
            raise RobustnessContractError(f"invalid lineage manifest: {artifact_id}")
        if (
            not isinstance(parent_ids, (list, tuple, set, frozenset))
            or not all(isinstance(parent_id, str) for parent_id in parent_ids)
        ):
            raise RobustnessContractError(f"invalid lineage parents: {artifact_id}")
        if artifact_id != lineage_artifact_id(kind, manifest, parent_ids):
            raise RobustnessContractError(
                f"lineage content address mismatch: {artifact_id}"
            )
        records[artifact_id] = artifact

    parents = {
        artifact_id: tuple(record.get("parent_ids", ()))
        for artifact_id, record in records.items()
    }
    for artifact_id, parent_ids in parents.items():
        for parent_id in parent_ids:
            if parent_id == artifact_id:
                raise RobustnessContractError(
                    f"lineage self-cycle includes: {artifact_id}"
                )
            if parent_id not in records:
                raise RobustnessContractError(
                    f"lineage artifact {artifact_id} references unknown parent: {parent_id}"
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(artifact_id: str) -> None:
        if artifact_id in visited:
            return
        if artifact_id in visiting:
            raise RobustnessContractError(f"lineage cycle includes: {artifact_id}")
        visiting.add(artifact_id)
        for parent_id in parents[artifact_id]:
            visit(parent_id)
        visiting.remove(artifact_id)
        visited.add(artifact_id)

    for artifact_id in sorted(records):
        visit(artifact_id)

    required = frozenset(required_artifact_ids)
    unknown_required = sorted(required - records.keys())
    if unknown_required:
        raise RobustnessContractError(
            f"unknown required lineage artifacts: {', '.join(unknown_required)}"
        )

    recalled: set[str] = set()
    pending: set[str] = set()
    for artifact_id, record in records.items():
        recall = record.get("recall")
        if recall is None:
            continue
        if not isinstance(recall, Mapping):
            raise RobustnessContractError(f"invalid recall receipt: {artifact_id}")
        if not isinstance(recall.get("reason"), str) or not recall.get("reason"):
            raise RobustnessContractError(f"recall reason is required: {artifact_id}")
        if not isinstance(recall.get("authority"), str) or not recall.get("authority"):
            raise RobustnessContractError(f"recall authority is required: {artifact_id}")
        effective_at = _parse_timestamp(
            recall.get("effective_at"),
            f"recall effective_at for {artifact_id}",
        )
        if effective_at <= evaluated_at:
            recalled.add(artifact_id)
        else:
            pending.add(artifact_id)

    children: dict[str, set[str]] = defaultdict(set)
    for artifact_id, parent_ids in parents.items():
        for parent_id in parent_ids:
            children[parent_id].add(artifact_id)

    tainted: set[str] = set(recalled)
    queue: deque[str] = deque(sorted(recalled))
    while queue:
        current = queue.popleft()
        for child_id in sorted(children.get(current, set())):
            if child_id not in tainted:
                tainted.add(child_id)
                queue.append(child_id)

    quarantined = tainted - recalled
    active = records.keys() - tainted
    blocked = required & tainted
    return LineageStatus(
        active_artifact_ids=tuple(sorted(active)),
        recalled_artifact_ids=tuple(sorted(recalled)),
        quarantined_artifact_ids=tuple(sorted(quarantined)),
        pending_recall_artifact_ids=tuple(sorted(pending)),
        blocked_required_artifact_ids=tuple(sorted(blocked)),
    )


def dependency_independence(left: Iterable[str], right: Iterable[str]) -> Fraction:
    """Return exact one-minus-Jaccard overlap for two dependency sets.

    The fleet defines two empty paths as having zero useful independence. The
    audited Lean strict-reduction theorems concern nonempty/shared sets, so this
    explicit empty-set policy does not extend their claim.
    """

    left_set = frozenset(left)
    right_set = frozenset(right)
    union = left_set | right_set
    if not union:
        return Fraction(0, 1)
    return Fraction(1, 1) - Fraction(len(left_set & right_set), len(union))


def expand_dependencies(
    direct: Iterable[str],
    parents: Mapping[str, Iterable[str]],
) -> frozenset[str]:
    """Close dependencies over a declared parent DAG, failing on gaps/cycles."""

    direct_set = frozenset(direct)
    unknown_direct = sorted(direct_set - parents.keys())
    if unknown_direct:
        raise RobustnessContractError(
            f"unknown direct dependencies: {', '.join(unknown_direct)}"
        )

    memo: dict[str, frozenset[str]] = {}
    visiting: set[str] = set()

    def visit(node: str) -> frozenset[str]:
        if node in memo:
            return memo[node]
        if node in visiting:
            raise RobustnessContractError(f"dependency cycle includes: {node}")
        if node not in parents:
            raise RobustnessContractError(f"unknown dependency: {node}")

        visiting.add(node)
        closure = {node}
        for parent in parents[node]:
            if parent not in parents:
                raise RobustnessContractError(
                    f"dependency {node} references unknown parent: {parent}"
                )
            closure.update(visit(parent))
        visiting.remove(node)
        memo[node] = frozenset(closure)
        return memo[node]

    expanded: set[str] = set()
    for dependency in sorted(direct_set):
        expanded.update(visit(dependency))
    return frozenset(expanded)


def two_path_fallback_profile(
    left: Iterable[str],
    right: Iterable[str],
    parents: Mapping[str, Iterable[str]],
) -> FallbackProfile:
    """Compare direct labels with their transitive failure-domain closures."""

    left_direct = frozenset(left)
    right_direct = frozenset(right)
    left_expanded = expand_dependencies(left_direct, parents)
    right_expanded = expand_dependencies(right_direct, parents)
    return FallbackProfile(
        direct_independence=dependency_independence(left_direct, right_direct),
        expanded_independence=dependency_independence(left_expanded, right_expanded),
        direct_dependencies=(tuple(sorted(left_direct)), tuple(sorted(right_direct))),
        expanded_dependencies=(tuple(sorted(left_expanded)), tuple(sorted(right_expanded))),
        shared_failure_domains=tuple(sorted(left_expanded & right_expanded)),
    )


def execution_authorized(selected: bool, lease: AuthorityLease) -> bool:
    """Return true only when selection and every authority condition pass."""

    return (
        selected
        and not lease.advisory_only
        and lease.action_allowed
        and lease.active
        and lease.scope_matches
        and lease.unexpired
    )


def validate_claim_assertions(
    assertions: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    """Validate evidence-class support without deriving additional states.

    Each assertion must contain ``state`` and ``evidence_classes``. At least one
    supplied evidence class must match the state's contract. Duplicate states,
    unknown states, missing evidence, and class mismatches fail closed.
    """

    seen: set[str] = set()
    validated: list[str] = []
    for assertion in assertions:
        state = assertion.get("state")
        if not isinstance(state, str) or state not in CLAIM_STATE_EVIDENCE:
            raise RobustnessContractError(f"unknown claim state: {state!r}")
        if state in seen:
            raise RobustnessContractError(f"duplicate claim state: {state}")

        raw_classes = assertion.get("evidence_classes")
        if (
            not isinstance(raw_classes, (list, tuple, set, frozenset))
            or not raw_classes
            or not all(isinstance(item, str) for item in raw_classes)
        ):
            raise RobustnessContractError(f"missing evidence classes for: {state}")
        evidence_classes = frozenset(raw_classes)
        allowed = CLAIM_STATE_EVIDENCE[state]
        if evidence_classes.isdisjoint(allowed):
            raise RobustnessContractError(
                f"evidence class mismatch for {state}: expected one of "
                f"{', '.join(sorted(allowed))}"
            )

        seen.add(state)
        validated.append(state)

    return tuple(state for state in CLAIM_STATES if state in validated)
