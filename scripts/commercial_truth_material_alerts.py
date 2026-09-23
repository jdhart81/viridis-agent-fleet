#!/usr/bin/env python3
"""Emit once-only material commercial changes from truth snapshots.

This is a local decision feeder. It never sends a message, moves money, opens
Checkout, or calls a paid route. State contains aggregate counters and event
fingerprints only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "viridis-commercial-material-alert-state-v1"
DEFAULT_STATE = Path("runtime/commercial-truth-material-alert-state.json")


class AlertError(RuntimeError):
    """The supplied snapshot or prior state is not decision-grade."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AlertError(message)


def nonnegative_int(value: Any, path: str) -> int:
    require(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0,
        f"{path} is not a non-negative integer",
    )
    return value


def mapping(value: Any, path: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{path} is not an object")
    return value


def _event_id(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _metric_event(
    event_type: str,
    metric: str,
    previous: int,
    current: int,
    generated_at: str,
) -> dict[str, Any]:
    payload = {
        "event_type": event_type,
        "metric": metric,
        "previous": previous,
        "current": current,
        "delta": current - previous,
        "snapshot_generated_at": generated_at,
    }
    return {"event_id": _event_id(payload), **payload}


def commercial_counters(snapshot: dict[str, Any]) -> dict[str, int]:
    require(snapshot.get("status") == "ok", "snapshot status is not ok")
    truth = mapping(snapshot.get("commercial_truth"), "commercial_truth")
    seat = mapping(truth.get("seat_funnel"), "commercial_truth.seat_funnel")
    reviewed = mapping(
        truth.get("reviewed_snapshot_funnel"),
        "commercial_truth.reviewed_snapshot_funnel",
    )
    return {
        "external_payers": nonnegative_int(
            truth.get("distinct_external_x402_payers"),
            "commercial_truth.distinct_external_x402_payers",
        ),
        "repeat_purchases": nonnegative_int(
            truth.get("repeat_external_x402_purchases"),
            "commercial_truth.repeat_external_x402_purchases",
        ),
        "paid_results_delivered": nonnegative_int(
            truth.get("external_x402_paid_results_delivered_observed"),
            "commercial_truth.external_x402_paid_results_delivered_observed",
        ),
        "seat_checkout_starts": nonnegative_int(
            seat.get("checkout_starts"), "commercial_truth.seat_funnel.checkout_starts"
        ),
        "reviewed_snapshot_checkout_starts": nonnegative_int(
            reviewed.get("checkout_starts"),
            "commercial_truth.reviewed_snapshot_funnel.checkout_starts",
        ),
        "active_subscriptions": nonnegative_int(
            truth.get("active_subscriptions"),
            "commercial_truth.active_subscriptions",
        ),
        "mrr_minor": nonnegative_int(
            truth.get("mrr_minor"), "commercial_truth.mrr_minor"
        ),
        "paid_market_completions": nonnegative_int(
            truth.get("market_independently_verified_jobs"),
            "commercial_truth.market_independently_verified_jobs",
        ),
        "paid_hive_completions_minimum": nonnegative_int(
            truth.get("paid_hive_direct_completions_minimum"),
            "commercial_truth.paid_hive_direct_completions_minimum",
        ),
    }


def retention_counters(snapshot: dict[str, Any]) -> dict[str, int] | None:
    truth = mapping(snapshot.get("commercial_truth"), "commercial_truth")
    seat = mapping(truth.get("seat_funnel"), "commercial_truth.seat_funnel")
    status = str(seat.get("retention_status") or "")
    require(
        status in {
            "unavailable_live_contract",
            "available_privacy_safe_subscription_aggregate",
        },
        "commercial_truth.seat_funnel.retention_status is invalid",
    )
    if status == "unavailable_live_contract":
        require(
            seat.get("retention") is None,
            "unavailable seat retention must be null",
        )
        return None
    retention = mapping(
        seat.get("retention"), "commercial_truth.seat_funnel.retention")
    activation = mapping(
        retention.get("activation"),
        "commercial_truth.seat_funnel.retention.activation",
    )
    renewal = mapping(
        retention.get("renewal"),
        "commercial_truth.seat_funnel.retention.renewal",
    )
    return {
        "paid_not_activated": nonnegative_int(
            retention.get("paid_not_activated"),
            "commercial_truth.seat_funnel.retention.paid_not_activated",
        ),
        "active_unused_over_7d": nonnegative_int(
            activation.get("active_unused_over_7d"),
            (
                "commercial_truth.seat_funnel.retention.activation."
                "active_unused_over_7d"
            ),
        ),
        "active_used_last_value_unknown": nonnegative_int(
            activation.get("active_used_last_value_unknown"),
            (
                "commercial_truth.seat_funnel.retention.activation."
                "active_used_last_value_unknown"
            ),
        ),
        "renewal_due_within_7d": nonnegative_int(
            renewal.get("due_within_7d"),
            (
                "commercial_truth.seat_funnel.retention.renewal."
                "due_within_7d"
            ),
        ),
        "renewal_failed": nonnegative_int(
            renewal.get("failed"),
            "commercial_truth.seat_funnel.retention.renewal.failed",
        ),
        "renewal_canceled": nonnegative_int(
            renewal.get("canceled"),
            "commercial_truth.seat_funnel.retention.renewal.canceled",
        ),
    }


INCREASE_EVENTS = {
    "external_payers": "new_external_payer",
    "repeat_purchases": "repeat_purchase",
    "paid_results_delivered": "paid_result_delivered",
    "seat_checkout_starts": "seat_checkout_started",
    "reviewed_snapshot_checkout_starts": "reviewed_snapshot_checkout_started",
    "active_subscriptions": "subscription_activated",
    "paid_market_completions": "paid_market_completion",
    "paid_hive_completions_minimum": "paid_hive_completion",
}

RETENTION_RISK_EVENTS = {
    "paid_not_activated": (
        "seat_paid_not_activated",
        "Verify provider payment and activation receipts; do not grant access "
        "or contact the customer automatically.",
    ),
    "active_unused_over_7d": (
        "seat_unused_over_7d",
        "Review the recurring outcome and onboarding path; recommend one "
        "bounded recovery action without automatic outreach.",
    ),
    "active_used_last_value_unknown": (
        "seat_last_value_telemetry_gap",
        "Repair last-value telemetry before making a retention claim or "
        "starting outreach.",
    ),
    "renewal_due_within_7d": (
        "seat_renewal_due",
        "Observe the provider-backed renewal boundary; do not preemptively "
        "message the customer.",
    ),
    "renewal_failed": (
        "seat_renewal_failed",
        "Verify Stripe-backed status and entitlement, then recommend one "
        "manual recovery review.",
    ),
    "renewal_canceled": (
        "seat_canceled",
        "Record churn reason only through an authorized customer interaction.",
    ),
}


def _retention_event(
    event_type: str,
    metric: str,
    previous: int,
    current: int,
    generated_at: str,
    recommended_action: str,
) -> dict[str, Any]:
    payload = {
        "event_type": event_type,
        "metric": metric,
        "previous": previous,
        "current": current,
        "delta": current - previous,
        "snapshot_generated_at": generated_at,
        "recommended_action": recommended_action,
        "external_action_authorized": False,
    }
    return {"event_id": _event_id(payload), **payload}


def _failure_event(snapshot: dict[str, Any]) -> dict[str, Any]:
    message = str(snapshot.get("message") or "commercial truth source failed")
    lowered = message.lower()
    event_type = "degraded_mount" if "mount" in lowered else "source_failure"
    payload = {
        "event_type": event_type,
        "error_type": str(snapshot.get("error_type") or "UnknownError"),
        "message": message,
    }
    return {"event_id": _event_id(payload), **payload}


def initial_state() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "last_successful_snapshot": None,
        "active_failure_event_id": None,
    }


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return initial_state()
    state = json.loads(path.read_text(encoding="utf-8"))
    require(state.get("schema") == SCHEMA, "unsupported alert state schema")
    require(
        state.get("last_successful_snapshot") is None
        or isinstance(state.get("last_successful_snapshot"), dict),
        "last_successful_snapshot is invalid",
    )
    return state


def evaluate(
    current: dict[str, Any],
    state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    require(isinstance(current, dict), "current snapshot is not an object")
    require(state.get("schema") == SCHEMA, "unsupported alert state schema")

    next_state = {
        "schema": SCHEMA,
        "last_successful_snapshot": state.get("last_successful_snapshot"),
        "active_failure_event_id": state.get("active_failure_event_id"),
    }

    if current.get("status") != "ok":
        failure = _failure_event(current)
        alerts = []
        if failure["event_id"] != state.get("active_failure_event_id"):
            alerts.append(failure)
        next_state["active_failure_event_id"] = failure["event_id"]
        return (
            {
                "status": "alert",
                "baseline_initialized": False,
                "material_alert_count": len(alerts),
                "alerts": alerts,
                "noise_ignored": [],
                "external_action_authorized": False,
            },
            next_state,
        )

    current_counters = commercial_counters(current)
    current_retention = retention_counters(current)
    generated_at = str(current.get("generated_at") or "")
    require(generated_at, "snapshot generated_at is missing")
    previous_snapshot = state.get("last_successful_snapshot")
    next_state["last_successful_snapshot"] = {
        "generated_at": generated_at,
        "counters": current_counters,
        "retention_counters": current_retention,
    }
    next_state["active_failure_event_id"] = None

    if previous_snapshot is None:
        return (
            {
                "status": "ok",
                "baseline_initialized": True,
                "material_alert_count": 0,
                "alerts": [],
                "noise_ignored": [
                    "free_calls",
                    "crawler_fan_out",
                    "page_views",
                    "market_messages",
                    "self_settlements",
                    "internal_credits",
                ],
                "external_action_authorized": False,
            },
            next_state,
        )

    previous = mapping(
        previous_snapshot.get("counters"),
        "state.last_successful_snapshot.counters",
    )
    alerts: list[dict[str, Any]] = []
    for metric, event_type in INCREASE_EVENTS.items():
        before = nonnegative_int(previous.get(metric), f"previous.{metric}")
        after = current_counters[metric]
        require(after >= before, f"{metric} regressed")
        if after > before:
            alerts.append(
                _metric_event(event_type, metric, before, after, generated_at)
            )

    before_mrr = nonnegative_int(previous.get("mrr_minor"), "previous.mrr_minor")
    after_mrr = current_counters["mrr_minor"]
    if before_mrr != after_mrr:
        alerts.append(
            _metric_event(
                "mrr_changed", "mrr_minor", before_mrr, after_mrr, generated_at
            )
        )

    previous_retention = previous_snapshot.get("retention_counters")
    if previous_retention is None and current_retention is not None:
        for metric, (event_type, recommendation) in \
                RETENTION_RISK_EVENTS.items():
            current_value = current_retention[metric]
            if current_value > 0:
                alerts.append(_retention_event(
                    event_type,
                    metric,
                    0,
                    current_value,
                    generated_at,
                    recommendation,
                ))
    elif previous_retention is not None and current_retention is None:
        payload = {
            "event_type": "seat_retention_source_unavailable",
            "snapshot_generated_at": generated_at,
            "recommended_action":
                "Restore decision-grade subscription retention evidence; "
                "do not infer seat health from MRR alone.",
            "external_action_authorized": False,
        }
        alerts.append({"event_id": _event_id(payload), **payload})
    elif previous_retention is not None and current_retention is not None:
        prior_retention = mapping(
            previous_retention,
            "state.last_successful_snapshot.retention_counters",
        )
        for metric, (event_type, recommendation) in \
                RETENTION_RISK_EVENTS.items():
            before = nonnegative_int(
                prior_retention.get(metric),
                f"previous.retention.{metric}",
            )
            after = current_retention[metric]
            if after > before:
                alerts.append(_retention_event(
                    event_type,
                    metric,
                    before,
                    after,
                    generated_at,
                    recommendation,
                ))
            elif after < before:
                alerts.append(_retention_event(
                    f"{event_type}_resolved",
                    metric,
                    before,
                    after,
                    generated_at,
                    "Record the aggregate recovery; no customer action is "
                    "authorized.",
                ))

    return (
        {
            "status": "alert" if alerts else "ok",
            "baseline_initialized": False,
            "material_alert_count": len(alerts),
            "alerts": alerts,
            "noise_ignored": [
                "free_calls",
                "crawler_fan_out",
                "page_views",
                "market_messages",
                "self_settlements",
                "internal_credits",
            ],
            "external_action_authorized": False,
        },
        next_state,
    )


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-file", type=Path)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        if args.snapshot_file:
            current = json.loads(args.snapshot_file.read_text(encoding="utf-8"))
        else:
            current = json.load(sys.stdin)
        result, next_state = evaluate(current, load_state(args.state_file))
        if not args.dry_run:
            atomic_write(args.state_file, next_state)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (AlertError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({
            "status": "invalid",
            "material_alert_count": 1,
            "alerts": [{
                "event_type": "source_failure",
                "error_type": type(exc).__name__,
                "message": str(exc),
            }],
            "external_action_authorized": False,
        }, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
