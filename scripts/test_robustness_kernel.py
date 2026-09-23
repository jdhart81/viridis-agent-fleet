"""Release-gate tests for the shared Viridis robustness contract."""

from itertools import product
from fractions import Fraction

import pytest

from fleet_utils.robustness import (
    AuthorityLease,
    INFERENCE_EDGES,
    INFERENCE_POLICY,
    LINEAGE_IDENTITY_RULE,
    LINEAGE_RECALL_POLICY,
    ROBUST_COMPARISON_MODE,
    ROBUST_DOMINANCE_RULE,
    RobustnessContractError,
    classify_viability_interval,
    dependency_independence,
    evaluate_lineage,
    execution_authorized,
    expand_dependencies,
    lineage_artifact_id,
    numeric_interval,
    robustly_dominates,
    two_path_fallback_profile,
    validate_claim_assertions,
)


def _lineage_fixture():
    model_manifest = {"model_id": "fleet-test-model", "version": "1.0.0"}
    model_id = lineage_artifact_id("MODEL", model_manifest, [])
    adapter_manifest = {"adapter_id": "fleet-test-adapter", "version": "1.0.0"}
    adapter_id = lineage_artifact_id("ADAPTER", adapter_manifest, [model_id])
    artifacts = [
        {
            "artifact_id": model_id,
            "kind": "MODEL",
            "manifest": model_manifest,
            "parent_ids": [],
            "recall": None,
        },
        {
            "artifact_id": adapter_id,
            "kind": "ADAPTER",
            "manifest": adapter_manifest,
            "parent_ids": [model_id],
            "recall": None,
        },
    ]
    return artifacts, model_id, adapter_id


def test_shared_dependency_strictly_reduces_independence():
    assert dependency_independence({"shared", "left"}, {"shared", "right"}) < 1


def test_hidden_common_parent_lowers_directly_disjoint_paths_exactly():
    parents = {
        "left": ("parent",),
        "right": ("parent",),
        "parent": (),
    }
    profile = two_path_fallback_profile({"left"}, {"right"}, parents)

    assert profile.direct_independence == 1
    assert profile.expanded_independence == Fraction(2, 3)
    assert profile.shared_failure_domains == ("parent",)


def test_empty_paths_receive_no_independence_credit():
    assert dependency_independence(set(), set()) == 0


def test_dependency_gaps_and_cycles_fail_closed():
    with pytest.raises(RobustnessContractError, match="unknown direct"):
        expand_dependencies({"missing"}, {"known": ()})

    with pytest.raises(RobustnessContractError, match="unknown parent"):
        expand_dependencies({"child"}, {"child": ("missing",)})

    with pytest.raises(RobustnessContractError, match="cycle"):
        expand_dependencies({"a"}, {"a": ("b",), "b": ("a",)})


def test_execution_authority_truth_table_matches_complete_conjunction():
    for values in product((False, True), repeat=6):
        selected, advisory, action, active, scope, unexpired = values
        lease = AuthorityLease(advisory, action, active, scope, unexpired)
        expected = selected and not advisory and action and active and scope and unexpired
        assert execution_authorized(selected, lease) is expected


def test_advisory_revoked_or_expired_authority_fails_closed():
    assert not execution_authorized(True, AuthorityLease(True, True, True, True, True))
    assert not execution_authorized(True, AuthorityLease(False, True, False, True, True))
    assert not execution_authorized(True, AuthorityLease(False, True, True, True, False))


def test_claim_states_require_matching_evidence_and_have_no_inference_edges():
    states = validate_claim_assertions([
        {"state": "FORMALLY_PROVED", "evidence_classes": ["FORMAL_PROOF_RECEIPT"]},
        {"state": "AUTHORIZED", "evidence_classes": ["AUTHORIZATION_RECEIPT"]},
    ])
    assert states == ("FORMALLY_PROVED", "AUTHORIZED")
    assert INFERENCE_POLICY == "NONE"
    assert INFERENCE_EDGES == ()


def test_formal_proof_does_not_create_authorization_deployment_or_outcome():
    states = validate_claim_assertions([
        {"state": "FORMALLY_PROVED", "evidence_classes": ["FORMAL_PROOF_RECEIPT"]},
    ])
    assert states == ("FORMALLY_PROVED",)
    assert "AUTHORIZED" not in states
    assert "DEPLOYED" not in states
    assert "OBSERVED" not in states


def test_evidence_mismatch_and_duplicate_states_fail_closed():
    with pytest.raises(RobustnessContractError, match="mismatch"):
        validate_claim_assertions([
            {"state": "FORMALLY_PROVED", "evidence_classes": ["NUMERICAL_RESULT"]},
        ])

    with pytest.raises(RobustnessContractError, match="duplicate"):
        validate_claim_assertions([
            {"state": "ASSUMED", "evidence_classes": ["ASSUMPTION_RECORD"]},
            {"state": "ASSUMED", "evidence_classes": ["ASSUMPTION_RECORD"]},
        ])


def test_lineage_identity_is_canonical_and_ancestry_sensitive():
    artifacts, model_id, adapter_id = _lineage_fixture()

    assert model_id.startswith("sha256:")
    assert adapter_id != lineage_artifact_id(
        "ADAPTER",
        artifacts[1]["manifest"],
        [],
    )
    assert LINEAGE_IDENTITY_RULE == (
        "sha256(canonical_json({kind,manifest,parent_ids_sorted}))"
    )
    assert LINEAGE_RECALL_POLICY == "RECALL_CASCADES_TO_ALL_DESCENDANTS"


def test_effective_model_recall_quarantines_required_adapter():
    artifacts, model_id, adapter_id = _lineage_fixture()
    artifacts[0]["recall"] = {
        "reason": "Synthetic model defect",
        "authority": "Test authority",
        "effective_at": "2026-08-05T00:00:00Z",
    }
    status = evaluate_lineage(
        artifacts,
        [model_id, adapter_id],
        "2026-08-06T00:00:00Z",
    )

    assert status.recalled_artifact_ids == (model_id,)
    assert status.quarantined_artifact_ids == (adapter_id,)
    assert status.blocked_required_artifact_ids == tuple(sorted((model_id, adapter_id)))
    assert not status.decision_usable


def test_future_and_unrelated_recalls_do_not_block_required_lineage():
    artifacts, model_id, adapter_id = _lineage_fixture()
    artifacts[0]["recall"] = {
        "reason": "Scheduled retirement",
        "authority": "Test authority",
        "effective_at": "2026-08-07T00:00:00Z",
    }
    unused_manifest = {"dataset_id": "unused", "version": "1.0.0"}
    unused_id = lineage_artifact_id("DATASET", unused_manifest, [])
    artifacts.append({
        "artifact_id": unused_id,
        "kind": "DATASET",
        "manifest": unused_manifest,
        "parent_ids": [],
        "recall": {
            "reason": "Unused test data withdrawn",
            "authority": "Test authority",
            "effective_at": "2026-08-05T00:00:00Z",
        },
    })
    status = evaluate_lineage(
        artifacts,
        [model_id, adapter_id],
        "2026-08-06T00:00:00Z",
    )

    assert status.pending_recall_artifact_ids == (model_id,)
    assert status.recalled_artifact_ids == (unused_id,)
    assert status.blocked_required_artifact_ids == ()
    assert status.decision_usable


def test_lineage_tampering_and_unknown_parents_fail_closed():
    artifacts, _, _ = _lineage_fixture()
    artifacts[0]["manifest"]["version"] = "tampered"
    with pytest.raises(RobustnessContractError, match="content address mismatch"):
        evaluate_lineage(artifacts, [], "2026-08-06T00:00:00Z")

    artifacts, _, adapter_id = _lineage_fixture()
    artifacts[1]["parent_ids"] = ["sha256:" + "0" * 64]
    artifacts[1]["artifact_id"] = lineage_artifact_id(
        "ADAPTER",
        artifacts[1]["manifest"],
        artifacts[1]["parent_ids"],
    )
    with pytest.raises(RobustnessContractError, match="unknown parent"):
        evaluate_lineage(artifacts, [adapter_id], "2026-08-06T00:00:00Z")


def test_numeric_intervals_validate_point_bounds_and_finiteness():
    assert numeric_interval(4) == numeric_interval(4, 4, 4)
    assert numeric_interval(4, 3, 5).lower == 3

    with pytest.raises(RobustnessContractError, match="exceeds"):
        numeric_interval(4, 5, 3)
    with pytest.raises(RobustnessContractError, match="outside"):
        numeric_interval(4, 5, 6)
    with pytest.raises(RobustnessContractError, match="finite"):
        numeric_interval(float("nan"))


def test_interval_viability_uses_three_states_for_every_operator():
    cases = {
        ">=": ((5, 6, "ROBUST_PASS"), (3, 4, "ROBUST_FAIL"), (4, 5, "UNCERTAIN")),
        ">": ((6, 7, "ROBUST_PASS"), (4, 5, "ROBUST_FAIL"), (5, 6, "UNCERTAIN")),
        "<=": ((3, 5, "ROBUST_PASS"), (6, 7, "ROBUST_FAIL"), (5, 6, "UNCERTAIN")),
        "<": ((3, 4, "ROBUST_PASS"), (5, 6, "ROBUST_FAIL"), (4, 5, "UNCERTAIN")),
        "==": ((5, 5, "ROBUST_PASS"), (6, 7, "ROBUST_FAIL"), (4, 6, "UNCERTAIN")),
    }
    for operator, witnesses in cases.items():
        for lower, upper, expected in witnesses:
            interval = numeric_interval((lower + upper) / 2, lower, upper)
            assert classify_viability_interval(operator, 5, interval) == expected


def test_separated_intervals_can_establish_robust_dominance():
    left = {
        "availability": numeric_interval(9, 8, 10),
        "latency": numeric_interval(2, 1, 3),
    }
    right = {
        "availability": numeric_interval(6, 5, 7),
        "latency": numeric_interval(4, 3, 5),
    }
    dimensions = {"availability": "maximize", "latency": "minimize"}

    assert robustly_dominates(left, right, dimensions)
    assert ROBUST_COMPARISON_MODE == "ROBUST_INTERVAL_DOMINANCE"
    assert ROBUST_DOMINANCE_RULE == (
        "WORST_CASE_NO_WORSE_THAN_OTHER_BEST_CASE"
    )


def test_overlapping_or_only_touching_intervals_do_not_establish_dominance():
    dimensions = {"value": "maximize"}
    assert not robustly_dominates(
        {"value": numeric_interval(6, 5, 7)},
        {"value": numeric_interval(5, 4, 6)},
        dimensions,
    )
    assert not robustly_dominates(
        {"value": numeric_interval(7, 6, 8)},
        {"value": numeric_interval(5, 4, 6)},
        dimensions,
    )
