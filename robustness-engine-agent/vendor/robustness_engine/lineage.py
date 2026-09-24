"""Content-addressed model and adapter lineage with cascading recall."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from typing import Any

from .canonical import canonical_hash


LINEAGE_IDENTITY_RULE = "sha256(canonical_json({kind,manifest,parent_ids_sorted}))"
LINEAGE_RECALL_POLICY = "RECALL_CASCADES_TO_ALL_DESCENDANTS"


def lineage_artifact_id(
    kind: str,
    manifest: dict[str, Any],
    parent_ids: list[str],
) -> str:
    """Return the stable content address for an immutable lineage node."""

    identity = {
        "kind": kind,
        "manifest": manifest,
        "parent_ids": sorted(parent_ids),
    }
    return f"sha256:{canonical_hash(identity)}"


def expected_artifact_id(artifact: dict[str, Any]) -> str:
    return lineage_artifact_id(
        artifact["kind"],
        artifact["manifest"],
        artifact["parent_ids"],
    )


def _active_recall_ids(
    artifacts: dict[str, dict[str, Any]],
    evaluation_time: str,
) -> tuple[set[str], set[str]]:
    evaluated_at = datetime.fromisoformat(evaluation_time.replace("Z", "+00:00"))
    active: set[str] = set()
    pending: set[str] = set()
    for artifact_id, artifact in artifacts.items():
        recall = artifact.get("recall")
        if recall is None:
            continue
        effective_at = datetime.fromisoformat(recall["effective_at"].replace("Z", "+00:00"))
        if effective_at <= evaluated_at:
            active.add(artifact_id)
        else:
            pending.add(artifact_id)
    return active, pending


def summarize_lineage(outcomes: dict[str, Any], evaluation_time: str) -> dict[str, Any]:
    """Compute point-in-time effective states and transitive recall impact."""

    lineage = outcomes["lineage"]
    artifacts = {artifact["artifact_id"]: artifact for artifact in lineage["artifacts"]}
    children: dict[str, set[str]] = defaultdict(set)
    for artifact_id, artifact in artifacts.items():
        for parent_id in artifact["parent_ids"]:
            children[parent_id].add(artifact_id)

    recalled, pending = _active_recall_ids(artifacts, evaluation_time)
    tainted_by: dict[str, set[str]] = defaultdict(set)
    for recalled_id in sorted(recalled):
        queue: deque[str] = deque([recalled_id])
        visited = {recalled_id}
        while queue:
            current = queue.popleft()
            tainted_by[current].add(recalled_id)
            for child_id in sorted(children.get(current, set())):
                if child_id not in visited:
                    visited.add(child_id)
                    queue.append(child_id)

    artifact_summaries: list[dict[str, Any]] = []
    for artifact_id in sorted(artifacts):
        artifact = artifacts[artifact_id]
        if artifact_id in recalled:
            effective_state = "RECALLED"
        elif tainted_by.get(artifact_id):
            effective_state = "QUARANTINED"
        else:
            effective_state = "ACTIVE"
        artifact_summaries.append({
            "artifact_id": artifact_id,
            "kind": artifact["kind"],
            "parent_ids": sorted(artifact["parent_ids"]),
            "effective_state": effective_state,
            "tainted_by": sorted(tainted_by.get(artifact_id, set())),
            "recall": artifact.get("recall"),
        })

    state_by_id = {
        artifact["artifact_id"]: artifact["effective_state"]
        for artifact in artifact_summaries
    }
    required_ids = sorted(lineage["required_artifact_ids"])
    blocked_required_ids = sorted(
        artifact_id
        for artifact_id in required_ids
        if state_by_id[artifact_id] in {"RECALLED", "QUARANTINED"}
    )

    return {
        "identity_rule": LINEAGE_IDENTITY_RULE,
        "recall_policy": LINEAGE_RECALL_POLICY,
        "evaluated_at": evaluation_time,
        "model_artifact_id": lineage["model_artifact_id"],
        "adapter_artifact_ids": sorted(lineage["adapter_artifact_ids"]),
        "required_artifact_ids": required_ids,
        "artifacts": artifact_summaries,
        "active_artifact_ids": sorted(
            artifact_id for artifact_id, state in state_by_id.items() if state == "ACTIVE"
        ),
        "recalled_artifact_ids": sorted(recalled),
        "quarantined_artifact_ids": sorted(
            artifact_id for artifact_id, state in state_by_id.items() if state == "QUARANTINED"
        ),
        "pending_recall_artifact_ids": sorted(pending),
        "blocked_required_artifact_ids": blocked_required_ids,
        "decision_usable": not blocked_required_ids,
    }


def lineage_hold_issues(summary: dict[str, Any]) -> list[dict[str, str]]:
    states = {
        artifact["artifact_id"]: artifact["effective_state"]
        for artifact in summary["artifacts"]
    }
    issues: list[dict[str, str]] = []
    for artifact_id in summary["blocked_required_artifact_ids"]:
        state = states[artifact_id]
        code = (
            "REQUIRED_ARTIFACT_RECALLED"
            if state == "RECALLED"
            else "REQUIRED_ARTIFACT_QUARANTINED"
        )
        issues.append({
            "code": code,
            "message": f"Required lineage artifact is {state.lower()}: {artifact_id}",
            "path": "/lineage/required_artifact_ids",
        })
    return issues
