import copy
from datetime import datetime, timezone

import pytest

from deploy.gateway.retention_cohorts import build_retention_cohorts
from scripts import commercial_truth_snapshot as snapshot


def fixtures():
    gateway = {
        "status": "ok",
        "mount_errors": {},
        "persistence": {"available": True, "errors": {}},
        "payment_gate": {
            "x402": {
                "http_settlement_telemetry": {
                    "total": {
                        "settlements_total": 7,
                        "self_settlements": 4,
                        "external_settlements": 3,
                        "distinct_external_payers": 3,
                        "repeat_external_purchases": 0,
                        "external_revenue_atomic": 270000,
                        "external_paid_results_delivered": 2,
                        "external_paid_results_receipted": 2,
                        "external_paid_results_failed": 0,
                        "external_paid_results_unknown": 1,
                        "external_buyer_feedback": 2,
                        "external_buyer_feedback_useful": 2,
                        "external_would_buy_again": 0,
                    },
                    "per_route": {
                        "regulatory-radar/scan_regulations": {
                            "settlements_total": 4,
                            "self_settlements": 1,
                            "external_settlements": 3,
                            "distinct_external_payers": 3,
                            "repeat_external_purchases": 0,
                            "external_revenue_atomic": 270000,
                            "first_external_settlement": {"tx_hash": "0xabc"},
                        },
                        "hive/solve": {
                            "settlements_total": 0,
                            "self_settlements": 0,
                            "external_settlements": 0,
                            "distinct_external_payers": 0,
                            "repeat_external_purchases": 0,
                            "external_revenue_atomic": 0,
                            "first_external_settlement": None,
                        },
                    },
                },
            },
            "a2a_escrow": {
                "consumed": {
                    "hive": {
                        "cash_escrows": 0,
                        "internal_escrows": 0,
                    },
                },
            },
        },
        "a2a_commerce": {
            "tasks": {"completed": 0},
        },
        "market_hive_bridge": {
            "jobs": 0,
            "artifacts": 0,
        },
        "subscriptions": {
            "status": "ok",
            "timestamp": "2026-07-26T00:00:00+00:00",
            "mrr_summary": {
                "active_subscriptions": 0,
                "mrr_minor": 0,
            },
            "frontdoor_funnel": {
                "page_views": 22,
                "checkouts_started": 0,
                "snapshot_page_views": 9,
                "snapshot_checkouts_started": 0,
                "snapshot_paid": 0,
                "seat_source_views": {
                    "direct": 10,
                    "x402_success": 2,
                },
                "seat_attributed_views": 12,
                "seat_unattributed_views": 10,
                "active_subscriptions": 0,
                "mrr_minor": 0,
            },
        },
    }
    market = {
        "status": "ok",
        "market": {
            "work_open": 3,
            "work_funding_verified": 0,
            "independently_verified_jobs": 0,
            "independently_useful_paid_deliveries": 0,
            "buyer_feedback_jobs": 0,
            "would_buy_again_count": 0,
            "messages_total": 0,
        },
    }
    return gateway, market


def build(gateway, market, **kwargs):
    return snapshot.build_snapshot(
        gateway,
        market,
        gateway_url="https://gateway.test/healthz",
        market_url="https://market.test/healthz",
        generated_at="2026-07-26T00:00:00+00:00",
        **kwargs,
    )


def test_cx5_exact_delivery_and_useful_require_buyer_confirmation():
    gateway, market = fixtures()
    total = gateway["payment_gate"]["x402"]["http_settlement_telemetry"]["total"]
    total["external_buyer_feedback"] = 0
    total["external_buyer_feedback_useful"] = 0
    before = build(gateway, market)["commercial_truth"]
    assert before["external_x402_paid_results_delivered_observed"] == 2
    assert before["external_x402_paid_results_delivered_exact"] == 0
    assert before["external_x402_buyer_feedback"]["useful"] == 0
    total["external_buyer_feedback"] = 1
    total["external_buyer_feedback_useful"] = 1
    after = build(gateway, market)["commercial_truth"]
    assert after["external_x402_paid_results_delivered_exact"] == 1
    assert after["external_x402_buyer_feedback"]["useful"] == 1


def test_absent_repeat_product_does_not_restart_completed_seat_bridge():
    gateway, market = fixtures()
    result = build(gateway, market)
    truth = result["commercial_truth"]
    assert truth["external_x402_settlements"] == 3
    assert truth["distinct_external_x402_payers"] == 3
    assert truth["external_x402_revenue_usdc"] == "0.270000"
    assert truth["repeat_external_x402_purchases"] == 0
    assert truth["external_x402_retention_cohorts"]["status"] == \
        "unavailable_live_contract"
    assert truth["external_x402_paid_results_delivered_exact"] == 2
    assert truth["external_x402_paid_results_receipted_exact"] == 2
    assert truth["external_x402_paid_results_failed"] == 0
    assert truth["external_x402_paid_results_unknown"] == 1
    assert truth["external_x402_delivery_instrumentation"] == \
        "durable_delivery_receipt_v1"
    assert truth["external_x402_buyer_feedback"] == {
        "status": "available_buyer_possession_aggregate",
        "received": 2,
        "useful": 2,
        "would_buy_again": 0,
        "independently_verified": False,
        "revenue_signal": False,
    }
    assert truth["self_x402_settlements_not_revenue"] == 4
    assert truth["market_open_work_not_funded_demand"] == 3
    assert truth["paid_hive_completions_exact"] == 0
    assert truth["paid_hive_completions_proven_zero"] is True
    assert truth["mrr_usd"] == "0.00"
    assert truth["seat_funnel"] == {
        "views": 22,
        "checkout_starts": 0,
        "active_subscriptions": 0,
        "mrr_minor": 0,
        "source_attribution_status": "available_privacy_safe_aggregate",
        "source_views": {"direct": 10, "x402_success": 2},
        "attributed_views": 12,
        "unattributed_views": 10,
        "source_lifecycle_status": "unavailable_live_contract",
        "source_lifecycle": None,
        "retention_status": "unavailable_live_contract",
        "retention": None,
    }
    assert truth["reviewed_snapshot_funnel"] == {
        "views": 9,
        "checkout_starts": 0,
        "paid": 0,
    }
    assert result["repeat_product"]["status"] == "absent"
    assert result["next_move"]["action"] == \
        "qualify_genuine_repeat_regulatory_radar_demand"
    assert result["next_move"]["distribution_scope"] == \
        "existing_regulatory_radar_scan_only"
    assert result["next_move"]["repeat_product_status"] == "absent"
    assert "exact_authorization_required" not in result["next_move"]
    assert "seat-bridge release chain" in result["next_move"]["reason"]
    assert result["next_move"]["external_write_authorized"] is False


def test_exact_live_repeat_product_unlocks_distribution_recommendation():
    gateway, market = fixtures()
    gateway["payment_gate"]["x402"]["http_front_door"] = [{
        "agent": "regulatory-radar",
        "tool": "monitor_changes",
        "endpoint":
            "https://gateway.test/x402/regulatory-radar/monitor_changes",
        "methods": ["GET", "POST"],
        "paid_execution_method": "POST",
        "price_minor": 25,
        "amount_atomic_usdc": "250000",
    }]
    result = build(gateway, market)
    assert result["repeat_product"]["status"] == "exact"
    assert result["next_move"]["action"] == \
        "repeat_purchase_distribution_regulatory_radar"
    assert result["next_move"]["external_write_authorized"] is False


def test_live_repeat_product_contract_drift_blocks_distribution():
    gateway, market = fixtures()
    gateway["payment_gate"]["x402"]["http_front_door"] = [{
        "agent": "regulatory-radar",
        "tool": "monitor_changes",
        "endpoint":
            "https://gateway.test/x402/regulatory-radar/monitor_changes",
        "methods": ["POST"],
        "paid_execution_method": "POST",
        "price_minor": 50,
        "amount_atomic_usdc": "500000",
    }]
    result = build(gateway, market)
    assert result["repeat_product"]["status"] == "drifted"
    assert result["next_move"]["action"] == \
        "repair_regulatory_radar_dated_watch_contract"


def test_verified_funded_work_takes_priority():
    gateway, market = fixtures()
    market["market"]["work_funding_verified"] = 1
    market["market"]["independently_verified_jobs"] = 1
    assert build(gateway, market)["next_move"]["action"] == \
        "fulfill_verified_funded_market_work"


def test_useful_delivery_without_repeat_requests_outcome():
    gateway, market = fixtures()
    market["market"].update({
        "work_funding_verified": 1,
        "independently_verified_jobs": 1,
        "independently_useful_paid_deliveries": 1,
        "buyer_feedback_jobs": 1,
        "would_buy_again_count": 0,
    })
    assert build(gateway, market)["next_move"]["action"] == \
        "request_buyer_outcome_and_repeat"


def test_paid_hive_channels_do_not_double_count_market_artifacts():
    gateway, market = fixtures()
    gateway["payment_gate"]["x402"]["http_settlement_telemetry"][
        "per_route"]["hive/solve"].update({
            "settlements_total": 1,
            "external_settlements": 1,
            "distinct_external_payers": 1,
            "external_revenue_atomic": 5000000,
        })
    total = gateway["payment_gate"]["x402"][
        "http_settlement_telemetry"]["total"]
    total.update({
        "settlements_total": 8,
        "external_settlements": 4,
        "distinct_external_payers": 4,
        "external_revenue_atomic": 5270000,
        "external_paid_results_unknown": 2,
    })
    gateway["payment_gate"]["a2a_escrow"]["consumed"]["hive"][
        "cash_escrows"] = 2
    gateway["market_hive_bridge"]["artifacts"] = 1
    result = build(gateway, market)
    truth = result["commercial_truth"]
    assert truth["paid_hive_completions_exact"] is None
    assert truth["paid_hive_completions_proven_zero"] is False
    assert truth["paid_hive_direct_completions_minimum"] == 3
    assert truth["hive_market_artifacts"] == 1


def test_legacy_settlements_keep_delivery_outcome_unknown():
    gateway, market = fixtures()
    total = gateway["payment_gate"]["x402"][
        "http_settlement_telemetry"]["total"]
    total.pop("external_paid_results_delivered")
    total.pop("external_paid_results_receipted")
    total.pop("external_paid_results_failed")
    total.pop("external_paid_results_unknown")
    total.pop("external_buyer_feedback")
    total.pop("external_buyer_feedback_useful")
    total.pop("external_would_buy_again")
    truth = build(gateway, market)["commercial_truth"]
    assert truth["external_x402_paid_results_delivered_exact"] is None
    assert truth["external_x402_paid_results_delivered_observed"] == 0
    assert truth["external_x402_paid_results_receipted_exact"] is None
    assert truth["external_x402_paid_results_unknown"] == 3
    assert truth["external_x402_delivery_instrumentation"] == \
        "legacy_uninstrumented"
    assert build(gateway, market)["next_move"]["action"] == \
        "promote_paid_delivery_outcome_instrumentation"


def test_instrumented_settlements_without_delivery_block_repeat_move():
    gateway, market = fixtures()
    total = gateway["payment_gate"]["x402"][
        "http_settlement_telemetry"]["total"]
    total.update({
        "external_paid_results_delivered": 0,
        "external_paid_results_receipted": 0,
        "external_paid_results_failed": 1,
        "external_paid_results_unknown": 2,
        "external_buyer_feedback": 0,
        "external_buyer_feedback_useful": 0,
        "external_would_buy_again": 0,
    })
    result = build(gateway, market)
    assert result["next_move"]["action"] == \
        "establish_one_verified_paid_result_delivery"
    assert result["next_move"]["external_write_authorized"] is False


def test_outcome_only_delivery_requires_buyer_verifiable_receipt_release():
    gateway, market = fixtures()
    total = gateway["payment_gate"]["x402"][
        "http_settlement_telemetry"]["total"]
    total.pop("external_paid_results_receipted")
    result = build(gateway, market)
    assert result["commercial_truth"][
        "external_x402_delivery_instrumentation"] == "durable_outcome_v1"
    assert result["next_move"]["action"] == \
        "promote_buyer_verifiable_paid_delivery_receipts"


def test_receipt_contract_without_external_receipt_blocks_repeat_move():
    gateway, market = fixtures()
    total = gateway["payment_gate"]["x402"][
        "http_settlement_telemetry"]["total"]
    total["external_paid_results_receipted"] = 0
    result = build(gateway, market)
    assert result["next_move"]["action"] == \
        "establish_one_receipted_paid_result_delivery"


def test_receipts_without_direct_feedback_contract_block_repeat_move():
    gateway, market = fixtures()
    total = gateway["payment_gate"]["x402"][
        "http_settlement_telemetry"]["total"]
    total.pop("external_buyer_feedback")
    total.pop("external_buyer_feedback_useful")
    total.pop("external_would_buy_again")
    result = build(gateway, market)
    assert result["commercial_truth"]["external_x402_buyer_feedback"] == {
        "status": "unavailable_live_contract",
        "received": None,
        "useful": None,
        "would_buy_again": None,
    }
    assert result["next_move"]["action"] == \
        "promote_direct_buyer_feedback_contract"


def test_live_feedback_contract_without_feedback_requests_one_usefulness_receipt():
    gateway, market = fixtures()
    total = gateway["payment_gate"]["x402"][
        "http_settlement_telemetry"]["total"]
    total.update({
        "external_buyer_feedback": 0,
        "external_buyer_feedback_useful": 0,
        "external_would_buy_again": 0,
    })
    result = build(gateway, market)
    assert result["next_move"]["action"] == \
        "establish_one_buyer_usefulness_receipt"


def test_live_contract_without_seat_sources_discloses_blind_spot():
    gateway, market = fixtures()
    funnel = gateway["subscriptions"]["frontdoor_funnel"]
    funnel.pop("seat_source_views")
    funnel.pop("seat_attributed_views")
    funnel.pop("seat_unattributed_views")
    seat = build(gateway, market)["commercial_truth"]["seat_funnel"]
    assert seat["source_attribution_status"] == \
        "unavailable_live_contract"
    assert seat["source_views"] is None
    assert seat["attributed_views"] is None
    assert seat["unattributed_views"] == 22


def test_complete_seat_source_lifecycle_joins_scorecard():
    gateway, market = fixtures()
    funnel = gateway["subscriptions"]["frontdoor_funnel"]
    funnel["checkouts_started"] = 1
    funnel["seat_funnel_by_source"] = {
        "github": {
            "checkout_starts": 1,
            "paid": 1,
            "activated": 1,
            "renewed": 1,
        },
        "unattributed": {
            "checkout_starts": 0,
            "paid": 0,
            "activated": 0,
            "renewed": 0,
        },
    }
    seat = build(gateway, market)["commercial_truth"]["seat_funnel"]
    assert seat["source_lifecycle_status"] == \
        "available_provider_verified_privacy_safe_aggregate"
    assert seat["source_lifecycle"]["github"] == {
        "checkout_starts": 1,
        "paid": 1,
        "activated": 1,
        "renewed": 1,
    }


def test_subscription_retention_risk_joins_scorecard_without_overwriting_x402():
    gateway, market = fixtures()
    gateway["subscriptions"]["mrr_summary"].update({
        "active_subscriptions": 2,
        "mrr_minor": 29800,
    })
    gateway["subscriptions"]["frontdoor_funnel"].update({
        "active_subscriptions": 2,
        "mrr_minor": 29800,
    })
    gateway["subscriptions"]["retention_summary"] = {
        "schema": "seat-retention-v1",
        "subscriptions": 3,
        "active_subscriptions": 2,
        "activation": {
            "active_used": 1,
            "active_unused": 1,
            "active_unused_over_7d": 1,
            "active_used_last_value_unknown": 0,
        },
        "renewal": {
            "healthy": 1,
            "due_within_7d": 1,
            "failed": 1,
            "canceled": 0,
            "expired": 0,
        },
        "last_value_at": "2026-07-25T12:00:00Z",
        "last_value_status": "complete_for_observed_usage",
        "paid_not_activated": 0,
        "paid_not_activated_status":
            "unavailable_without_provider_checkout_reconciliation",
    }
    truth = build(gateway, market)["commercial_truth"]
    seat = truth["seat_funnel"]
    assert seat["retention_status"] == \
        "available_privacy_safe_subscription_aggregate"
    assert seat["retention"] == {
        "subscriptions": 3,
        "active_subscriptions": 2,
        "activation": {
            "active_used": 1,
            "active_unused": 1,
            "active_unused_over_7d": 1,
            "active_used_last_value_unknown": 0,
        },
        "renewal": {
            "healthy": 1,
            "due_within_7d": 1,
            "failed": 1,
            "canceled": 0,
            "expired": 0,
        },
        "last_value_at": "2026-07-25T12:00:00+00:00",
        "last_value_status": "complete_for_observed_usage",
        "paid_not_activated": 0,
        "paid_not_activated_status":
            "unavailable_without_provider_checkout_reconciliation",
    }
    assert truth["external_x402_retention_cohorts"] == {
        "status": "unavailable_live_contract",
        "windows": None,
        "by_first_route": None,
        "by_acquisition_source": None,
    }


def provider_reconciliation(**overrides):
    payload = {
        "status": "ok",
        "schema": "seat-provider-activation-reconciliation-v1",
        "provider_sessions": 4,
        "live_sessions": 3,
        "test_sessions_excluded": 1,
        "complete_paid": 3,
        "activated": 2,
        "paid_not_activated": 1,
        "open_unpaid": 0,
        "expired_unpaid": 0,
        "payment_pending": 0,
        "provider_anomalies": 0,
        "ledger_subscriptions": 3,
        "ledger_subscriptions_observed_in_window": 2,
        "ledger_subscriptions_without_window_session": 1,
        "observed_at": "2026-07-26T00:00:00Z",
        "created_after_epoch": 1779926400,
        "pages": 1,
        "coverage": "bounded_complete",
        "paid_not_activated_status": "available_provider_reconciled",
        "provider_mutation": False,
        "customer_action_authorized": False,
        "identifiers_returned": 0,
    }
    payload.update(overrides)
    return payload


def test_provider_reconciliation_promotes_paid_activation_evidence():
    gateway, market = fixtures()
    gateway["subscriptions"]["mrr_summary"].update({
        "active_subscriptions": 2,
        "mrr_minor": 29800,
    })
    gateway["subscriptions"]["frontdoor_funnel"].update({
        "active_subscriptions": 2,
        "mrr_minor": 29800,
    })
    gateway["subscriptions"]["retention_summary"] = {
        "schema": "seat-retention-v1",
        "subscriptions": 3,
        "active_subscriptions": 2,
        "activation": {
            "active_used": 1,
            "active_unused": 1,
            "active_unused_over_7d": 0,
            "active_used_last_value_unknown": 0,
        },
        "renewal": {
            "healthy": 2,
            "due_within_7d": 0,
            "failed": 1,
            "canceled": 0,
            "expired": 0,
        },
        "last_value_at": "2026-07-25T12:00:00Z",
        "last_value_status": "complete_for_observed_usage",
        "paid_not_activated": 0,
        "paid_not_activated_status":
            "unavailable_without_provider_checkout_reconciliation",
    }
    seat = build(
        gateway,
        market,
        subscription_reconciliation=provider_reconciliation(),
    )["commercial_truth"]["seat_funnel"]
    assert seat["retention_status"] == \
        "available_provider_reconciled_privacy_safe_aggregate"
    assert seat["retention"]["paid_not_activated"] == 1
    assert seat["retention"]["paid_not_activated_status"] == \
        "available_provider_reconciled"
    assert seat["retention"]["provider_reconciliation"] == {
        "observed_at": "2026-07-26T00:00:00+00:00",
        "created_after_epoch": 1779926400,
        "pages": 1,
        "provider_sessions": 4,
        "live_sessions": 3,
        "test_sessions_excluded": 1,
        "complete_paid": 3,
        "activated": 2,
        "paid_not_activated": 1,
        "provider_anomalies": 0,
        "coverage": "bounded_complete",
    }


@pytest.mark.parametrize("mutation", [
    lambda payload: payload.update({"identifiers_returned": 1}),
    lambda payload: payload.update({"provider_mutation": True}),
    lambda payload: payload.update({"coverage": "partial"}),
    lambda payload: payload.update({"complete_paid": 4}),
    lambda payload: payload.update({"observed_at": "2026-07-20T00:00:00Z"}),
])
def test_provider_reconciliation_drift_fails_closed(mutation):
    gateway, market = fixtures()
    gateway["subscriptions"]["retention_summary"] = {
        "schema": "seat-retention-v1",
        "subscriptions": 0,
        "active_subscriptions": 0,
        "activation": {
            "active_used": 0,
            "active_unused": 0,
            "active_unused_over_7d": 0,
            "active_used_last_value_unknown": 0,
        },
        "renewal": {
            "healthy": 0,
            "due_within_7d": 0,
            "failed": 0,
            "canceled": 0,
            "expired": 0,
        },
        "last_value_at": None,
        "last_value_status": "complete_for_observed_usage",
        "paid_not_activated": 0,
        "paid_not_activated_status":
            "unavailable_without_provider_checkout_reconciliation",
    }
    reconciliation = provider_reconciliation(
        provider_sessions=0,
        live_sessions=0,
        test_sessions_excluded=0,
        complete_paid=0,
        activated=0,
        paid_not_activated=0,
        ledger_subscriptions=0,
    )
    mutation(reconciliation)
    with pytest.raises(snapshot.SnapshotError):
        build(
            gateway,
            market,
            subscription_reconciliation=reconciliation,
        )


@pytest.mark.parametrize("mutation", [
    lambda payload: payload["activation"].update({"active_unused": 2}),
    lambda payload: payload["renewal"].update({"failed": 2}),
    lambda payload: payload.update({
        "paid_not_activated": 1,
        "paid_not_activated_status":
            "unavailable_without_provider_checkout_reconciliation",
    }),
    lambda payload: payload.update({
        "last_value_at": "2026-07-27T12:00:00Z",
    }),
])
def test_subscription_retention_drift_fails_closed(mutation):
    gateway, market = fixtures()
    retention = {
        "schema": "seat-retention-v1",
        "subscriptions": 1,
        "active_subscriptions": 1,
        "activation": {
            "active_used": 1,
            "active_unused": 0,
            "active_unused_over_7d": 0,
            "active_used_last_value_unknown": 0,
        },
        "renewal": {
            "healthy": 1,
            "due_within_7d": 0,
            "failed": 0,
            "canceled": 0,
            "expired": 0,
        },
        "last_value_at": "2026-07-25T12:00:00Z",
        "last_value_status": "complete_for_observed_usage",
        "paid_not_activated": 0,
        "paid_not_activated_status":
            "unavailable_without_provider_checkout_reconciliation",
    }
    gateway["subscriptions"]["mrr_summary"].update({
        "active_subscriptions": 1,
        "mrr_minor": 14900,
    })
    gateway["subscriptions"]["frontdoor_funnel"].update({
        "active_subscriptions": 1,
        "mrr_minor": 14900,
    })
    mutation(retention)
    gateway["subscriptions"]["retention_summary"] = retention
    with pytest.raises(snapshot.SnapshotError):
        build(gateway, market)


def test_seat_source_lifecycle_conservation_fails_closed():
    gateway, market = fixtures()
    gateway["subscriptions"]["frontdoor_funnel"][
        "seat_funnel_by_source"] = {
            "github": {
                "checkout_starts": 1,
                "paid": 1,
                "activated": 0,
                "renewed": 0,
            },
        }
    with pytest.raises(snapshot.SnapshotError):
        build(gateway, market)


def test_privacy_safe_retention_cohorts_join_the_scorecard():
    gateway, market = fixtures()
    records = [
        {
            "payer_wallet": f"0x{index}",
            "timestamp": "2026-07-01T00:00:00Z",
            "route": "regulatory-radar/scan_regulations",
            "acquisition_source": source,
            "self_settle": False,
        }
        for index, source in enumerate(("github", "openclaw", None), start=1)
    ]
    gateway["payment_gate"]["x402"]["http_settlement_telemetry"][
        "retention_cohorts"
    ] = build_retention_cohorts(
        records,
        as_of=datetime(2026, 7, 26, tzinfo=timezone.utc),
    )
    cohorts = build(gateway, market)["commercial_truth"][
        "external_x402_retention_cohorts"]
    assert cohorts["status"] == "available_privacy_safe_aggregate"
    assert cohorts["payer_count"] == 3
    assert cohorts["windows"]["7d"]["eligible_payers"] == 3
    assert cohorts["windows"]["7d"]["repeat_rate_bps"] == 0
    assert cohorts["by_first_route"][
        "regulatory-radar/scan_regulations"]["payer_count"] == 3
    assert cohorts["by_acquisition_source"]["unknown"]["payer_count"] == 1
    assert "0x1" not in str(cohorts)


def test_retention_cohort_denominator_mismatch_fails_closed():
    gateway, market = fixtures()
    gateway["payment_gate"]["x402"]["http_settlement_telemetry"][
        "retention_cohorts"
    ] = build_retention_cohorts(
        [{
            "payer_wallet": "0xOnlyOne",
            "timestamp": "2026-07-01T00:00:00Z",
            "route": "regulatory-radar/scan_regulations",
            "self_settle": False,
        }],
        as_of=datetime(2026, 7, 26, tzinfo=timezone.utc),
    )
    with pytest.raises(snapshot.SnapshotError, match="payer count"):
        build(gateway, market)


def test_stale_http_source_fails_closed():
    gateway, market = fixtures()
    stale = "2026-07-25T23:00:00+00:00"
    observations = {
        "gateway_health": {
            "url": "https://gateway.test/healthz",
            "observed_at": stale,
            "http_date": stale,
        },
        "agent_market_health": {
            "url": "https://market.test/healthz",
            "observed_at": "2026-07-26T00:00:00+00:00",
            "http_date": "2026-07-26T00:00:00+00:00",
        },
    }
    with pytest.raises(snapshot.SnapshotError, match="stale"):
        build(gateway, market, source_observations=observations)


@pytest.mark.parametrize(("path", "mutate"), [
    (
        "missing market funding",
        lambda g, m: m["market"].pop("work_funding_verified"),
    ),
    (
        "bad settlement conservation",
        lambda g, m: g["payment_gate"]["x402"][
            "http_settlement_telemetry"]["total"].update({
                "settlements_total": 99,
            }),
    ),
    (
        "usefulness exceeds verification",
        lambda g, m: m["market"].update({
            "independently_useful_paid_deliveries": 1,
        }),
    ),
    (
        "mount error",
        lambda g, m: g.update({"mount_errors": {"hive": "broken"}}),
    ),
    (
        "malformed HTTP route inventory",
        lambda g, m: g["payment_gate"]["x402"].update({
            "http_front_door": "not-a-list",
        }),
    ),
    (
        "duplicated dated-watch route",
        lambda g, m: g["payment_gate"]["x402"].update({
            "http_front_door": [
                {"agent": "regulatory-radar", "tool": "monitor_changes"},
                {"agent": "regulatory-radar", "tool": "monitor_changes"},
            ],
        }),
    ),
    (
        "partial paid delivery telemetry",
        lambda g, m: g["payment_gate"]["x402"][
            "http_settlement_telemetry"]["total"].pop(
                "external_paid_results_failed"),
    ),
    (
        "paid delivery conservation",
        lambda g, m: g["payment_gate"]["x402"][
            "http_settlement_telemetry"]["total"].update({
                "external_paid_results_delivered": 99,
            }),
    ),
    (
        "seat funnel MRR mismatch",
        lambda g, m: g["subscriptions"]["frontdoor_funnel"].update({
            "mrr_minor": 14900,
        }),
    ),
    (
        "seat source conservation",
        lambda g, m: g["subscriptions"]["frontdoor_funnel"].update({
            "seat_attributed_views": 13,
        }),
    ),
])
def test_missing_or_inconsistent_evidence_fails_closed(path, mutate):
    gateway, market = fixtures()
    mutate(gateway, market)
    with pytest.raises(snapshot.SnapshotError):
        build(gateway, market)


def test_builder_does_not_mutate_inputs():
    gateway, market = fixtures()
    before_gateway = copy.deepcopy(gateway)
    before_market = copy.deepcopy(market)
    build(gateway, market)
    assert gateway == before_gateway
    assert market == before_market
