import copy

import pytest

from scripts import commercial_truth_material_alerts as alerts


def snapshot(**overrides):
    truth = {
        "distinct_external_x402_payers": 4,
        "repeat_external_x402_purchases": 0,
        "external_x402_paid_results_delivered_observed": 1,
        "active_subscriptions": 0,
        "mrr_minor": 0,
        "market_independently_verified_jobs": 0,
        "paid_hive_direct_completions_minimum": 0,
        "seat_funnel": {
            "views": 22,
            "checkout_starts": 0,
            "retention_status": "unavailable_live_contract",
            "retention": None,
        },
        "reviewed_snapshot_funnel": {"views": 9, "checkout_starts": 0},
    }
    truth.update(overrides)
    return {
        "status": "ok",
        "generated_at": "2026-07-30T12:00:00+00:00",
        "commercial_truth": truth,
    }


def establish(current=None):
    result, state = alerts.evaluate(
        current or snapshot(), alerts.initial_state()
    )
    assert result["baseline_initialized"] is True
    assert result["alerts"] == []
    return state


@pytest.mark.parametrize(
    ("field", "value", "event_type"),
    [
        ("distinct_external_x402_payers", 5, "new_external_payer"),
        ("repeat_external_x402_purchases", 1, "repeat_purchase"),
        (
            "external_x402_paid_results_delivered_observed",
            2,
            "paid_result_delivered",
        ),
        ("active_subscriptions", 1, "subscription_activated"),
        ("market_independently_verified_jobs", 1, "paid_market_completion"),
        ("paid_hive_direct_completions_minimum", 1, "paid_hive_completion"),
    ],
)
def test_each_material_counter_alerts_once(field, value, event_type):
    state = establish()
    current = snapshot(**{field: value})
    current["generated_at"] = "2026-07-30T13:00:00+00:00"
    result, updated = alerts.evaluate(current, state)
    assert [event["event_type"] for event in result["alerts"]] == [event_type]
    repeated, _ = alerts.evaluate(current, updated)
    assert repeated["alerts"] == []


def test_each_checkout_surface_alerts():
    state = establish()
    current = snapshot()
    current["commercial_truth"]["seat_funnel"]["checkout_starts"] = 1
    current["commercial_truth"]["reviewed_snapshot_funnel"][
        "checkout_starts"
    ] = 1
    result, _ = alerts.evaluate(current, state)
    assert {event["event_type"] for event in result["alerts"]} == {
        "seat_checkout_started",
        "reviewed_snapshot_checkout_started",
    }


@pytest.mark.parametrize(("previous", "current"), [(0, 14900), (14900, 0)])
def test_mrr_increase_and_decrease_alert(previous, current):
    state = establish(snapshot(mrr_minor=previous))
    result, _ = alerts.evaluate(snapshot(mrr_minor=current), state)
    event = result["alerts"][0]
    assert event["event_type"] == "mrr_changed"
    assert event["previous"] == previous
    assert event["current"] == current


def test_noise_only_change_does_not_alert():
    baseline = snapshot()
    state = establish(baseline)
    current = copy.deepcopy(baseline)
    current["generated_at"] = "2026-07-30T13:00:00+00:00"
    current["commercial_truth"]["seat_funnel"]["views"] = 1000
    current["commercial_truth"]["reviewed_snapshot_funnel"]["views"] = 999
    current["commercial_truth"]["market_messages_total"] = 500
    result, _ = alerts.evaluate(current, state)
    assert result["alerts"] == []
    assert "page_views" in result["noise_ignored"]
    assert "market_messages" in result["noise_ignored"]


def test_degraded_mount_alerts_once_until_recovery():
    state = establish()
    failed = {
        "status": "error",
        "error_type": "SnapshotError",
        "message": "gateway has mount errors",
    }
    first, state = alerts.evaluate(failed, state)
    assert first["alerts"][0]["event_type"] == "degraded_mount"
    repeated, state = alerts.evaluate(failed, state)
    assert repeated["alerts"] == []
    _, state = alerts.evaluate(snapshot(), state)
    after_recovery, _ = alerts.evaluate(failed, state)
    assert after_recovery["alerts"][0]["event_type"] == "degraded_mount"


def test_source_failure_alerts_once():
    state = establish()
    failed = {
        "status": "error",
        "error_type": "TimeoutError",
        "message": "gateway source unavailable",
    }
    first, state = alerts.evaluate(failed, state)
    repeated, _ = alerts.evaluate(failed, state)
    assert first["alerts"][0]["event_type"] == "source_failure"
    assert repeated["alerts"] == []


def test_counter_regression_fails_closed():
    state = establish()
    with pytest.raises(alerts.AlertError, match="external_payers regressed"):
        alerts.evaluate(
            snapshot(distinct_external_x402_payers=3),
            state,
        )


def test_missing_material_metric_fails_closed():
    current = snapshot()
    current["commercial_truth"].pop("mrr_minor")
    with pytest.raises(alerts.AlertError, match="mrr_minor"):
        alerts.evaluate(current, alerts.initial_state())


def test_evaluation_does_not_mutate_inputs():
    current = snapshot()
    state = alerts.initial_state()
    current_before = copy.deepcopy(current)
    state_before = copy.deepcopy(state)
    alerts.evaluate(current, state)
    assert current == current_before
    assert state == state_before


def with_retention(current=None, **risk_overrides):
    current = current or snapshot()
    risk = {
        "paid_not_activated": 0,
        "active_unused_over_7d": 0,
        "active_used_last_value_unknown": 0,
        "renewal_due_within_7d": 0,
        "renewal_failed": 0,
        "renewal_canceled": 0,
    }
    risk.update(risk_overrides)
    current["commercial_truth"]["seat_funnel"].update({
        "retention_status":
            "available_privacy_safe_subscription_aggregate",
        "retention": {
            "paid_not_activated": risk["paid_not_activated"],
            "activation": {
                "active_unused_over_7d":
                    risk["active_unused_over_7d"],
                "active_used_last_value_unknown":
                    risk["active_used_last_value_unknown"],
            },
            "renewal": {
                "due_within_7d": risk["renewal_due_within_7d"],
                "failed": risk["renewal_failed"],
                "canceled": risk["renewal_canceled"],
            },
        },
    })
    return current


@pytest.mark.parametrize(
    ("metric", "event_type"),
    [
        ("paid_not_activated", "seat_paid_not_activated"),
        ("active_unused_over_7d", "seat_unused_over_7d"),
        (
            "active_used_last_value_unknown",
            "seat_last_value_telemetry_gap",
        ),
        ("renewal_due_within_7d", "seat_renewal_due"),
        ("renewal_failed", "seat_renewal_failed"),
        ("renewal_canceled", "seat_canceled"),
    ],
)
def test_each_seat_retention_risk_alerts_once(metric, event_type):
    state = establish(with_retention())
    current = with_retention(**{metric: 1})
    current["generated_at"] = "2026-07-30T13:00:00+00:00"
    result, updated = alerts.evaluate(current, state)
    assert [event["event_type"] for event in result["alerts"]] == [event_type]
    event = result["alerts"][0]
    assert event["external_action_authorized"] is False
    assert event["recommended_action"]
    repeated, _ = alerts.evaluate(current, updated)
    assert repeated["alerts"] == []


def test_retention_risk_resolution_is_material_without_outreach():
    state = establish(with_retention(renewal_failed=1))
    recovered = with_retention(renewal_failed=0)
    recovered["generated_at"] = "2026-07-30T13:00:00+00:00"
    result, _ = alerts.evaluate(recovered, state)
    event = result["alerts"][0]
    assert event["event_type"] == "seat_renewal_failed_resolved"
    assert event["delta"] == -1
    assert event["external_action_authorized"] is False


def test_first_available_retention_contract_surfaces_existing_risk():
    state = establish()
    current = with_retention(active_unused_over_7d=2)
    current["generated_at"] = "2026-07-30T13:00:00+00:00"
    result, _ = alerts.evaluate(current, state)
    assert result["alerts"][0]["event_type"] == "seat_unused_over_7d"
    assert result["alerts"][0]["current"] == 2


def test_retention_source_loss_alerts_once():
    state = establish(with_retention())
    unavailable = snapshot()
    unavailable["generated_at"] = "2026-07-30T13:00:00+00:00"
    first, state = alerts.evaluate(unavailable, state)
    repeated, _ = alerts.evaluate(unavailable, state)
    assert first["alerts"][0]["event_type"] == \
        "seat_retention_source_unavailable"
    assert repeated["alerts"] == []


def test_malformed_retention_contract_fails_closed():
    current = with_retention()
    current["commercial_truth"]["seat_funnel"]["retention"][
        "activation"].pop("active_unused_over_7d")
    with pytest.raises(alerts.AlertError, match="active_unused_over_7d"):
        alerts.evaluate(current, alerts.initial_state())
