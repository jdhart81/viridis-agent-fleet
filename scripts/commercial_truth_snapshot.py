#!/usr/bin/env python3
"""Read-only commercial truth snapshot for the Viridis A2A business.

This joins the live gateway and Agent Market health surfaces without treating
open listings, internal ledger credits, self-payments, pricing hints, or
seller-authored counters as stronger evidence than they are.  It performs no
message, payment, job, or state-changing call.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any


DEFAULT_GATEWAY = "https://mcp.viridisconservation.com/healthz"
DEFAULT_MARKET = "https://mcp.viridisconservation.com/network/healthz"
USDC_ATOMIC_PER_UNIT = Decimal("1000000")
RADAR_WATCH_ROUTE = "regulatory-radar/monitor_changes"
RADAR_WATCH_AGENT = "regulatory-radar"
RADAR_WATCH_TOOL = "monitor_changes"
RADAR_WATCH_PRICE_MINOR = 25
RADAR_WATCH_AMOUNT_ATOMIC = "250000"
DEFAULT_MAX_SOURCE_AGE_SECONDS = 300
SOURCE_FUTURE_TOLERANCE_SECONDS = 60


class SnapshotError(RuntimeError):
    """A required source or invariant is absent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SnapshotError(message)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _timestamp(value: Any, path: str) -> datetime:
    require(isinstance(value, str) and value.strip(), f"{path} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotError(f"{path} is not a valid timestamp") from exc
    require(parsed.tzinfo is not None, f"{path} has no timezone")
    return parsed.astimezone(timezone.utc)


def fetch_json(
    url: str,
    timeout: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={
            "accept": "application/json",
            "user-agent": "viridis-commercial-truth-snapshot/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        require(response.status == 200, f"{url} returned HTTP {response.status}")
        payload = json.load(response)
        observed_at = datetime.now(timezone.utc)
        http_date = response.headers.get("Date")
    require(isinstance(payload, dict), f"{url} did not return a JSON object")
    require(http_date, f"{url} response has no HTTP Date")
    try:
        parsed_http_date = parsedate_to_datetime(http_date)
    except (TypeError, ValueError) as exc:
        raise SnapshotError(f"{url} returned an invalid HTTP Date") from exc
    require(
        parsed_http_date.tzinfo is not None,
        f"{url} HTTP Date has no timezone",
    )
    return payload, {
        "url": url,
        "observed_at": _iso(observed_at),
        "http_date": _iso(parsed_http_date),
    }


def mapping(value: Any, path: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{path} is missing or not an object")
    return value


def integer(value: Any, path: str) -> int:
    require(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0,
        f"{path} is missing or not a non-negative integer",
    )
    return value


def exact_usdc(atomic: int) -> str:
    value = Decimal(atomic) / USDC_ATOMIC_PER_UNIT
    return format(value.quantize(Decimal("0.000001")), "f")


def _fresh_source(
    observation: dict[str, Any],
    path: str,
    *,
    generated_at: datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    observed_at = _timestamp(
        observation.get("observed_at"), f"{path}.observed_at")
    http_date = _timestamp(
        observation.get("http_date"), f"{path}.http_date")
    observed_age = (generated_at - observed_at).total_seconds()
    http_age = (generated_at - http_date).total_seconds()
    require(
        observed_age >= -SOURCE_FUTURE_TOLERANCE_SECONDS,
        f"{path}.observed_at is in the future",
    )
    require(
        http_age >= -SOURCE_FUTURE_TOLERANCE_SECONDS,
        f"{path}.http_date is in the future",
    )
    require(
        observed_age <= max_age_seconds,
        f"{path} observation is stale",
    )
    require(
        http_age <= max_age_seconds,
        f"{path} HTTP response is stale",
    )
    return {
        "url": str(observation.get("url", "")),
        "observed_at": _iso(observed_at),
        "http_date": _iso(http_date),
        "http_age_seconds": max(0, int(http_age)),
        "max_age_seconds": max_age_seconds,
        "status": "fresh",
    }


def _delivery_metrics(
    raw: dict[str, Any],
    path: str,
) -> dict[str, Any]:
    names = (
        "external_paid_results_delivered",
        "external_paid_results_failed",
        "external_paid_results_unknown",
    )
    present = [name in raw for name in names]
    require(
        all(present) or not any(present),
        f"{path} has a partial paid-delivery schema",
    )
    external = integer(
        raw.get("external_settlements"), f"{path}.external_settlements")
    if not any(present):
        require(
            "external_paid_results_receipted" not in raw,
            f"{path} has receipt telemetry without delivery telemetry",
        )
        return {
            "instrumentation": "legacy_uninstrumented",
            "delivered": 0,
            "failed": 0,
            "unknown": external,
            "delivered_exact": None,
            "receipted": 0,
            "receipted_exact": None,
        }
    delivered = integer(raw.get(names[0]), f"{path}.{names[0]}")
    failed = integer(raw.get(names[1]), f"{path}.{names[1]}")
    unknown = integer(raw.get(names[2]), f"{path}.{names[2]}")
    require(
        delivered + failed + unknown == external,
        f"{path} paid-delivery conservation failed",
    )
    receipt_present = "external_paid_results_receipted" in raw
    receipted = (
        integer(
            raw.get("external_paid_results_receipted"),
            f"{path}.external_paid_results_receipted",
        )
        if receipt_present
        else 0
    )
    require(
        receipted <= delivered,
        f"{path} receipted paid results exceed delivered paid results",
    )
    return {
        "instrumentation": (
            "durable_delivery_receipt_v1"
            if receipt_present
            else "durable_outcome_v1"
        ),
        "delivered": delivered,
        "failed": failed,
        "unknown": unknown,
        "delivered_exact": delivered,
        "receipted": receipted,
        "receipted_exact": receipted if receipt_present else None,
    }


def _buyer_feedback_metrics(
    raw: dict[str, Any],
    path: str,
    *,
    delivered: int,
) -> dict[str, Any]:
    names = (
        "external_buyer_feedback",
        "external_buyer_feedback_useful",
        "external_would_buy_again",
    )
    present = [name in raw for name in names]
    require(
        all(present) or not any(present),
        f"{path} has a partial direct buyer-feedback schema",
    )
    if not any(present):
        return {
            "status": "unavailable_live_contract",
            "received": None,
            "useful": None,
            "would_buy_again": None,
        }
    received = integer(raw.get(names[0]), f"{path}.{names[0]}")
    useful = integer(raw.get(names[1]), f"{path}.{names[1]}")
    repurchase = integer(raw.get(names[2]), f"{path}.{names[2]}")
    require(received <= delivered, f"{path} feedback exceeds delivered results")
    require(useful <= received, f"{path} useful feedback exceeds feedback")
    require(
        repurchase <= received,
        f"{path} would-buy-again exceeds feedback",
    )
    return {
        "status": "available_buyer_possession_aggregate",
        "received": received,
        "useful": useful,
        "would_buy_again": repurchase,
        "independently_verified": False,
        "revenue_signal": False,
    }


def _nonnegative_mapping(value: Any, path: str) -> dict[str, int]:
    raw = mapping(value, path)
    return {
        str(name): integer(count, f"{path}.{name}")
        for name, count in raw.items()
    }


def _route(
    per_route: dict[str, Any],
    name: str,
) -> dict[str, int | None | dict[str, Any]]:
    raw = mapping(per_route.get(name), f"x402.per_route.{name}")
    return {
        "settlements_total": integer(
            raw.get("settlements_total"), f"{name}.settlements_total"),
        "self_settlements": integer(
            raw.get("self_settlements"), f"{name}.self_settlements"),
        "external_settlements": integer(
            raw.get("external_settlements"), f"{name}.external_settlements"),
        "distinct_external_payers": integer(
            raw.get("distinct_external_payers"),
            f"{name}.distinct_external_payers",
        ),
        "repeat_external_purchases": integer(
            raw.get("repeat_external_purchases"),
            f"{name}.repeat_external_purchases",
        ),
        "external_revenue_atomic": integer(
            raw.get("external_revenue_atomic"),
            f"{name}.external_revenue_atomic",
        ),
        "first_external_settlement": raw.get("first_external_settlement"),
    }


def _repeat_product_contract(x402: dict[str, Any]) -> dict[str, Any]:
    """Return exact live readiness for the product used by repeat outreach.

    Settlement telemetry alone cannot prove that a route is callable.  The
    gateway's current HTTP front-door contract is the runtime inventory used
    by buyers and by the growth worker.
    """
    raw_routes = x402.get("http_front_door")
    if raw_routes is None:
        routes: list[Any] = []
    else:
        require(
            isinstance(raw_routes, list),
            "gateway.payment_gate.x402.http_front_door is not a list",
        )
        routes = raw_routes
    matches = [
        route for route in routes
        if isinstance(route, dict)
        and route.get("agent") == RADAR_WATCH_AGENT
        and route.get("tool") == RADAR_WATCH_TOOL
    ]
    require(len(matches) <= 1, "dated-watch HTTP route is duplicated")
    if not matches:
        return {
            "route": RADAR_WATCH_ROUTE,
            "status": "absent",
            "live": False,
            "contract_exact": False,
            "expected_price_minor": RADAR_WATCH_PRICE_MINOR,
            "expected_amount_atomic_usdc": RADAR_WATCH_AMOUNT_ATOMIC,
        }
    route = matches[0]
    methods = route.get("methods")
    contract_exact = (
        route.get("price_minor") == RADAR_WATCH_PRICE_MINOR
        and str(route.get("amount_atomic_usdc"))
        == RADAR_WATCH_AMOUNT_ATOMIC
        and isinstance(methods, list)
        and "POST" in methods
        and route.get("paid_execution_method") == "POST"
        and isinstance(route.get("endpoint"), str)
        and route["endpoint"].startswith("https://")
    )
    return {
        "route": RADAR_WATCH_ROUTE,
        "status": "exact" if contract_exact else "drifted",
        "live": True,
        "contract_exact": contract_exact,
        "expected_price_minor": RADAR_WATCH_PRICE_MINOR,
        "expected_amount_atomic_usdc": RADAR_WATCH_AMOUNT_ATOMIC,
        "observed_price_minor": route.get("price_minor"),
        "observed_amount_atomic_usdc": route.get("amount_atomic_usdc"),
        "endpoint": route.get("endpoint"),
    }


def _cohort_window(
    value: Any,
    path: str,
    payer_count: int,
) -> dict[str, int | None]:
    raw = mapping(value, path)
    eligible = integer(raw.get("eligible_payers"), f"{path}.eligible_payers")
    repeated = integer(raw.get("repeat_payers"), f"{path}.repeat_payers")
    pending = integer(raw.get("pending_maturity"), f"{path}.pending_maturity")
    rate = raw.get("repeat_rate_bps")
    require(repeated <= eligible, f"{path} repeats exceed eligible payers")
    require(
        eligible + pending == payer_count,
        f"{path} cohort denominator does not conserve",
    )
    expected_rate = None if eligible == 0 else repeated * 10_000 // eligible
    require(rate == expected_rate, f"{path} repeat rate is inconsistent")
    return {
        "eligible_payers": eligible,
        "repeat_payers": repeated,
        "pending_maturity": pending,
        "repeat_rate_bps": rate,
    }


def _retention_contract(
    telemetry: dict[str, Any],
    external_payers: int,
) -> dict[str, Any]:
    raw_value = telemetry.get("retention_cohorts")
    if raw_value is None:
        return {
            "status": "unavailable_live_contract",
            "windows": None,
            "by_first_route": None,
            "by_acquisition_source": None,
        }
    raw = mapping(raw_value, "x402.retention_cohorts")
    require(
        raw.get("version") == "viridis-x402-retention-cohorts-v1",
        "x402 retention cohort version is unsupported",
    )
    payer_count = integer(
        raw.get("payer_count"), "x402.retention_cohorts.payer_count")
    require(
        payer_count == external_payers,
        "x402 retention payer count disagrees with settlement telemetry",
    )

    windows_raw = mapping(raw.get("windows"), "x402.retention_cohorts.windows")
    windows = {
        name: _cohort_window(
            windows_raw.get(name),
            f"x402.retention_cohorts.windows.{name}",
            payer_count,
        )
        for name in ("7d", "14d", "30d")
    }

    def groups(field: str) -> dict[str, Any]:
        raw_groups = mapping(
            raw.get(field), f"x402.retention_cohorts.{field}")
        result = {}
        total_group_payers = 0
        for name, value in raw_groups.items():
            group = mapping(value, f"x402.retention_cohorts.{field}.{name}")
            count = integer(
                group.get("payer_count"),
                f"x402.retention_cohorts.{field}.{name}.payer_count",
            )
            group_windows_raw = mapping(
                group.get("windows"),
                f"x402.retention_cohorts.{field}.{name}.windows",
            )
            result[str(name)] = {
                "payer_count": count,
                "windows": {
                    window: _cohort_window(
                        group_windows_raw.get(window),
                        (
                            f"x402.retention_cohorts.{field}.{name}."
                            f"windows.{window}"
                        ),
                        count,
                    )
                    for window in ("7d", "14d", "30d")
                },
            }
            total_group_payers += count
        require(
            total_group_payers == payer_count,
            f"x402.retention_cohorts.{field} does not conserve payer count",
        )
        return result

    return {
        "status": "available_privacy_safe_aggregate",
        "as_of": str(raw.get("as_of") or ""),
        "acquisition_source_evidence": str(
            raw.get("acquisition_source_evidence") or ""),
        "payer_count": payer_count,
        "windows": windows,
        "by_first_route": groups("by_first_route"),
        "by_acquisition_source": groups("by_acquisition_source"),
    }


def build_snapshot(
    gateway: dict[str, Any],
    market_health: dict[str, Any],
    *,
    gateway_url: str,
    market_url: str,
    generated_at: str | None = None,
    source_observations: dict[str, dict[str, Any]] | None = None,
    max_source_age_seconds: int = DEFAULT_MAX_SOURCE_AGE_SECONDS,
    subscription_reconciliation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    require(
        isinstance(max_source_age_seconds, int)
        and max_source_age_seconds > 0,
        "max_source_age_seconds must be a positive integer",
    )
    generated = (
        _timestamp(generated_at, "generated_at")
        if generated_at is not None else datetime.now(timezone.utc)
    )
    observations = source_observations or {
        "gateway_health": {
            "url": gateway_url,
            "observed_at": _iso(generated),
            "http_date": _iso(generated),
        },
        "agent_market_health": {
            "url": market_url,
            "observed_at": _iso(generated),
            "http_date": _iso(generated),
        },
    }
    source_freshness = {
        name: _fresh_source(
            mapping(observations.get(name), f"sources.{name}"),
            f"sources.{name}",
            generated_at=generated,
            max_age_seconds=max_source_age_seconds,
        )
        for name in ("gateway_health", "agent_market_health")
    }
    require(gateway.get("status") == "ok", "gateway health is not ok")
    require(market_health.get("status") == "ok", "Agent Market health is not ok")
    require(gateway.get("mount_errors") == {}, "gateway has mount errors")
    persistence = mapping(gateway.get("persistence"), "gateway.persistence")
    require(persistence.get("available") is True, "gateway persistence unavailable")
    require(persistence.get("errors") == {}, "gateway persistence has errors")

    payment_gate = mapping(gateway.get("payment_gate"), "gateway.payment_gate")
    x402 = mapping(payment_gate.get("x402"), "gateway.payment_gate.x402")
    telemetry = mapping(
        x402.get("http_settlement_telemetry"),
        "gateway.payment_gate.x402.http_settlement_telemetry",
    )
    repeat_product = _repeat_product_contract(x402)
    total = mapping(telemetry.get("total"), "x402.total")
    delivery = _delivery_metrics(total, "x402.total")
    direct_feedback = _buyer_feedback_metrics(
        total,
        "x402.total",
        delivered=delivery["delivered"],
    )
    per_route = mapping(telemetry.get("per_route"), "x402.per_route")

    external_settlements = integer(
        total.get("external_settlements"), "x402.total.external_settlements")
    external_payers = integer(
        total.get("distinct_external_payers"),
        "x402.total.distinct_external_payers",
    )
    repeat_purchases = integer(
        total.get("repeat_external_purchases"),
        "x402.total.repeat_external_purchases",
    )
    external_revenue_atomic = integer(
        total.get("external_revenue_atomic"),
        "x402.total.external_revenue_atomic",
    )
    self_settlements = integer(
        total.get("self_settlements"), "x402.total.self_settlements")
    retention = _retention_contract(telemetry, external_payers)
    require(
        external_payers <= external_settlements,
        "distinct external payers exceed external settlements",
    )
    require(
        repeat_purchases <= external_settlements,
        "repeat external purchases exceed external settlements",
    )
    require(
        external_settlements + self_settlements
        == integer(total.get("settlements_total"), "x402.total.settlements_total"),
        "x402 self/external settlement conservation failed",
    )

    regulatory = _route(per_route, "regulatory-radar/scan_regulations")
    hive_route = _route(per_route, "hive/solve")
    require(
        regulatory["external_settlements"] <= external_settlements,
        "Regulatory Radar external settlements exceed fleet total",
    )
    require(
        hive_route["external_settlements"] <= external_settlements,
        "Hive external settlements exceed fleet total",
    )

    a2a = mapping(gateway.get("a2a_commerce"), "gateway.a2a_commerce")
    a2a_tasks = mapping(a2a.get("tasks"), "gateway.a2a_commerce.tasks")
    a2a_completed = integer(a2a_tasks.get("completed"), "a2a.tasks.completed")

    a2a_escrow = mapping(payment_gate.get("a2a_escrow"), "payment_gate.a2a_escrow")
    consumed = mapping(a2a_escrow.get("consumed"), "payment_gate.a2a_escrow.consumed")
    hive_consumed = mapping(consumed.get("hive"), "a2a_escrow.consumed.hive")
    hive_cash_escrows = integer(
        hive_consumed.get("cash_escrows"), "a2a_escrow.hive.cash_escrows")
    hive_internal_escrows = integer(
        hive_consumed.get("internal_escrows"),
        "a2a_escrow.hive.internal_escrows",
    )

    bridge = mapping(gateway.get("market_hive_bridge"), "market_hive_bridge")
    hive_market_jobs = integer(bridge.get("jobs"), "market_hive_bridge.jobs")
    hive_market_artifacts = integer(
        bridge.get("artifacts"), "market_hive_bridge.artifacts")

    subscriptions = mapping(gateway.get("subscriptions"), "gateway.subscriptions")
    require(
        subscriptions.get("status") == "ok",
        "subscriptions health is not ok",
    )
    subscription_timestamp = _timestamp(
        subscriptions.get("timestamp"), "subscriptions.timestamp")
    subscription_age = (generated - subscription_timestamp).total_seconds()
    require(
        subscription_age >= -SOURCE_FUTURE_TOLERANCE_SECONDS,
        "subscriptions.timestamp is in the future",
    )
    require(
        subscription_age <= max_source_age_seconds,
        "subscriptions health is stale",
    )
    mrr = mapping(subscriptions.get("mrr_summary"), "subscriptions.mrr_summary")
    active_subscriptions = integer(
        mrr.get("active_subscriptions"), "subscriptions.active_subscriptions")
    mrr_minor = integer(mrr.get("mrr_minor"), "subscriptions.mrr_minor")
    frontdoor = mapping(
        subscriptions.get("frontdoor_funnel"),
        "subscriptions.frontdoor_funnel",
    )
    seat_views = integer(
        frontdoor.get("page_views"), "subscriptions.frontdoor.page_views")
    checkout_starts = integer(
        frontdoor.get("checkouts_started"),
        "subscriptions.frontdoor.checkouts_started",
    )
    snapshot_views = integer(
        frontdoor.get("snapshot_page_views"),
        "subscriptions.frontdoor.snapshot_page_views",
    )
    snapshot_checkout_starts = integer(
        frontdoor.get("snapshot_checkouts_started"),
        "subscriptions.frontdoor.snapshot_checkouts_started",
    )
    snapshot_paid = integer(
        frontdoor.get("snapshot_paid"),
        "subscriptions.frontdoor.snapshot_paid",
    )
    require(
        checkout_starts <= seat_views,
        "seat checkout starts exceed seat views",
    )
    require(
        snapshot_paid <= snapshot_checkout_starts <= snapshot_views,
        "snapshot funnel conservation failed",
    )
    require(
        integer(
            frontdoor.get("active_subscriptions"),
            "subscriptions.frontdoor.active_subscriptions",
        ) == active_subscriptions,
        "frontdoor active subscriptions disagree with MRR summary",
    )
    require(
        integer(
            frontdoor.get("mrr_minor"),
            "subscriptions.frontdoor.mrr_minor",
        ) == mrr_minor,
        "frontdoor MRR disagrees with MRR summary",
    )
    raw_seat_sources = frontdoor.get("seat_source_views")
    if raw_seat_sources is None:
        seat_source_views = None
        seat_source_status = "unavailable_live_contract"
        seat_attributed_views = None
        seat_unattributed_views = seat_views
    else:
        seat_source_views = _nonnegative_mapping(
            raw_seat_sources, "subscriptions.frontdoor.seat_source_views")
        seat_attributed_views = integer(
            frontdoor.get("seat_attributed_views"),
            "subscriptions.frontdoor.seat_attributed_views",
        )
        seat_unattributed_views = integer(
            frontdoor.get("seat_unattributed_views"),
            "subscriptions.frontdoor.seat_unattributed_views",
        )
        require(
            sum(seat_source_views.values()) == seat_attributed_views,
            "seat source views disagree with attributed views",
        )
        require(
            seat_attributed_views + seat_unattributed_views == seat_views,
            "seat source attribution does not conserve seat views",
        )
        seat_source_status = "available_privacy_safe_aggregate"

    raw_source_funnel = frontdoor.get("seat_funnel_by_source")
    if raw_source_funnel is None:
        seat_source_lifecycle = None
        seat_source_lifecycle_status = "unavailable_live_contract"
    else:
        source_funnel = mapping(
            raw_source_funnel,
            "subscriptions.frontdoor.seat_funnel_by_source",
        )
        seat_source_lifecycle = {}
        for source, value in source_funnel.items():
            source_value = mapping(
                value,
                f"subscriptions.frontdoor.seat_funnel_by_source.{source}",
            )
            seat_source_lifecycle[str(source)] = {
                stage: integer(
                    source_value.get(stage),
                    (
                        "subscriptions.frontdoor.seat_funnel_by_source."
                        f"{source}.{stage}"
                    ),
                )
                for stage in (
                    "checkout_starts", "paid", "activated", "renewed")
            }
            require(
                seat_source_lifecycle[str(source)]["paid"]
                == seat_source_lifecycle[str(source)]["activated"],
                f"seat source {source} paid/activation mismatch",
            )
        require(
            sum(
                value["checkout_starts"]
                for value in seat_source_lifecycle.values()
            ) == checkout_starts,
            "seat source checkout starts disagree with funnel",
        )
        seat_source_lifecycle_status = (
            "available_provider_verified_privacy_safe_aggregate")

    raw_seat_retention = subscriptions.get("retention_summary")
    if raw_seat_retention is None:
        seat_retention = None
        seat_retention_status = "unavailable_live_contract"
    else:
        seat_retention_contract = mapping(
            raw_seat_retention, "subscriptions.retention_summary")
        require(
            seat_retention_contract.get("schema") == "seat-retention-v1",
            "unsupported seat retention schema",
        )
        retention_subscriptions = integer(
            seat_retention_contract.get("subscriptions"),
            "subscriptions.retention_summary.subscriptions",
        )
        retention_active = integer(
            seat_retention_contract.get("active_subscriptions"),
            "subscriptions.retention_summary.active_subscriptions",
        )
        require(
            retention_active == active_subscriptions,
            "retention active subscriptions disagree with MRR",
        )
        activation_raw = mapping(
            seat_retention_contract.get("activation"),
            "subscriptions.retention_summary.activation",
        )
        activation = {
            name: integer(
                activation_raw.get(name),
                f"subscriptions.retention_summary.activation.{name}",
            )
            for name in (
                "active_used",
                "active_unused",
                "active_unused_over_7d",
                "active_used_last_value_unknown",
            )
        }
        require(
            activation["active_used"] + activation["active_unused"]
            == retention_active,
            "seat activation counts do not conserve active subscriptions",
        )
        require(
            activation["active_unused_over_7d"]
            <= activation["active_unused"],
            "long-unused seats exceed unused seats",
        )
        require(
            activation["active_used_last_value_unknown"]
            <= activation["active_used"],
            "unknown last-value seats exceed used seats",
        )
        renewal_raw = mapping(
            seat_retention_contract.get("renewal"),
            "subscriptions.retention_summary.renewal",
        )
        renewal = {
            name: integer(
                renewal_raw.get(name),
                f"subscriptions.retention_summary.renewal.{name}",
            )
            for name in (
                "healthy", "due_within_7d", "failed", "canceled", "expired")
        }
        require(
            sum(renewal.values()) == retention_subscriptions,
            "seat renewal counts do not conserve subscriptions",
        )
        paid_not_activated = integer(
            seat_retention_contract.get("paid_not_activated"),
            "subscriptions.retention_summary.paid_not_activated",
        )
        paid_not_activated_status = str(
            seat_retention_contract.get("paid_not_activated_status") or "")
        require(
            paid_not_activated_status in {
                "available_provider_reconciled",
                "unavailable_without_provider_checkout_reconciliation",
            },
            "seat paid-not-activated status is invalid",
        )
        if paid_not_activated_status.startswith("unavailable"):
            require(
                paid_not_activated == 0,
                "unavailable paid-not-activated evidence cannot assert seats",
            )
        last_value_at = seat_retention_contract.get("last_value_at")
        if last_value_at is not None:
            last_value = _timestamp(
                last_value_at,
                "subscriptions.retention_summary.last_value_at",
            )
            require(
                (generated - last_value).total_seconds()
                >= -SOURCE_FUTURE_TOLERANCE_SECONDS,
                "seat last-value timestamp is in the future",
            )
            last_value_at = _iso(last_value)
        last_value_status = str(
            seat_retention_contract.get("last_value_status") or "")
        require(
            last_value_status in {
                "complete_for_observed_usage",
                "historical_gaps_present",
            },
            "seat last-value status is invalid",
        )
        seat_retention = {
            "subscriptions": retention_subscriptions,
            "active_subscriptions": retention_active,
            "activation": activation,
            "renewal": renewal,
            "last_value_at": last_value_at,
            "last_value_status": last_value_status,
            "paid_not_activated": paid_not_activated,
            "paid_not_activated_status": paid_not_activated_status,
        }
        seat_retention_status = (
            "available_privacy_safe_subscription_aggregate")

    if subscription_reconciliation is not None:
        reconciliation = mapping(
            subscription_reconciliation, "subscription_reconciliation")
        require(
            reconciliation.get("status") == "ok",
            "subscription reconciliation is not ok",
        )
        require(
            reconciliation.get("schema")
            == "seat-provider-activation-reconciliation-v1",
            "unsupported subscription reconciliation schema",
        )
        require(
            reconciliation.get("coverage") == "bounded_complete",
            "subscription reconciliation coverage is incomplete",
        )
        require(
            reconciliation.get("provider_mutation") is False,
            "subscription reconciliation mutated provider state",
        )
        require(
            reconciliation.get("customer_action_authorized") is False,
            "subscription reconciliation authorizes customer action",
        )
        require(
            integer(
                reconciliation.get("identifiers_returned"),
                "subscription_reconciliation.identifiers_returned",
            ) == 0,
            "subscription reconciliation exposed identifiers",
        )
        observed = _timestamp(
            reconciliation.get("observed_at"),
            "subscription_reconciliation.observed_at",
        )
        age = (generated - observed).total_seconds()
        require(
            age >= -SOURCE_FUTURE_TOLERANCE_SECONDS,
            "subscription reconciliation is from the future",
        )
        require(
            age <= max_source_age_seconds,
            "subscription reconciliation is stale",
        )
        provider_sessions = integer(
            reconciliation.get("provider_sessions"),
            "subscription_reconciliation.provider_sessions",
        )
        live_sessions = integer(
            reconciliation.get("live_sessions"),
            "subscription_reconciliation.live_sessions",
        )
        test_sessions = integer(
            reconciliation.get("test_sessions_excluded"),
            "subscription_reconciliation.test_sessions_excluded",
        )
        complete_paid = integer(
            reconciliation.get("complete_paid"),
            "subscription_reconciliation.complete_paid",
        )
        activated = integer(
            reconciliation.get("activated"),
            "subscription_reconciliation.activated",
        )
        paid_not_activated = integer(
            reconciliation.get("paid_not_activated"),
            "subscription_reconciliation.paid_not_activated",
        )
        ledger_subscriptions = integer(
            reconciliation.get("ledger_subscriptions"),
            "subscription_reconciliation.ledger_subscriptions",
        )
        require(
            provider_sessions == live_sessions + test_sessions,
            "subscription reconciliation provider sessions do not conserve",
        )
        require(
            complete_paid == activated + paid_not_activated,
            "subscription reconciliation paid sessions do not conserve",
        )
        require(
            seat_retention is not None,
            "provider reconciliation requires the seat retention contract",
        )
        require(
            ledger_subscriptions == seat_retention["subscriptions"],
            "provider reconciliation disagrees with the seat ledger",
        )
        seat_retention["paid_not_activated"] = paid_not_activated
        seat_retention["paid_not_activated_status"] = (
            "available_provider_reconciled")
        seat_retention["provider_reconciliation"] = {
            "observed_at": _iso(observed),
            "created_after_epoch": integer(
                reconciliation.get("created_after_epoch"),
                "subscription_reconciliation.created_after_epoch",
            ),
            "pages": integer(
                reconciliation.get("pages"),
                "subscription_reconciliation.pages",
            ),
            "provider_sessions": provider_sessions,
            "live_sessions": live_sessions,
            "test_sessions_excluded": test_sessions,
            "complete_paid": complete_paid,
            "activated": activated,
            "paid_not_activated": paid_not_activated,
            "provider_anomalies": integer(
                reconciliation.get("provider_anomalies"),
                "subscription_reconciliation.provider_anomalies",
            ),
            "coverage": "bounded_complete",
        }
        seat_retention_status = (
            "available_provider_reconciled_privacy_safe_aggregate")

    market = mapping(market_health.get("market"), "market.health.market")
    work_open = integer(market.get("work_open"), "market.work_open")
    work_funding_verified = integer(
        market.get("work_funding_verified"), "market.work_funding_verified")
    verified_jobs = integer(
        market.get("independently_verified_jobs"),
        "market.independently_verified_jobs",
    )
    useful_deliveries = integer(
        market.get("independently_useful_paid_deliveries"),
        "market.independently_useful_paid_deliveries",
    )
    buyer_feedback_jobs = integer(
        market.get("buyer_feedback_jobs"), "market.buyer_feedback_jobs")
    would_buy_again = integer(
        market.get("would_buy_again_count"), "market.would_buy_again_count")
    messages_total = integer(
        market.get("messages_total"), "market.messages_total")
    require(
        useful_deliveries <= verified_jobs,
        "useful paid deliveries exceed independently verified jobs",
    )
    require(
        would_buy_again <= buyer_feedback_jobs,
        "would-buy-again count exceeds buyer feedback jobs",
    )

    if work_funding_verified > useful_deliveries:
        next_move = {
            "action": "fulfill_verified_funded_market_work",
            "reason": (
                "verified funded work exists without an independently useful "
                "paid delivery"),
            "external_write_authorized": False,
        }
    elif useful_deliveries > would_buy_again:
        next_move = {
            "action": "request_buyer_outcome_and_repeat",
            "reason": (
                "an independently useful delivery exists without a positive "
                "repeat-purchase signal"),
            "external_write_authorized": False,
        }
    elif (external_settlements > 0
          and delivery["instrumentation"] == "legacy_uninstrumented"):
        next_move = {
            "action": "promote_paid_delivery_outcome_instrumentation",
            "reason": (
                "external cash settlements exist, but the live ledger cannot "
                "distinguish a delivered paid result from a post-settlement "
                "tool failure; historical outcomes remain unknown"),
            "production_write_authorized": False,
            "external_write_authorized": False,
        }
    elif (external_settlements > 0
          and delivery["delivered_exact"] == 0):
        next_move = {
            "action": "establish_one_verified_paid_result_delivery",
            "reason": (
                "settlement exists, but no paid result is durably classified "
                "as delivered; repeat or seat conversion should not be "
                "claimed before the outcome is known"),
            "production_write_authorized": False,
            "external_write_authorized": False,
        }
    elif (external_settlements > 0
          and delivery["receipted_exact"] is None):
        next_move = {
            "action": "promote_buyer_verifiable_paid_delivery_receipts",
            "reason": (
                "paid-result outcomes are seller-classified, but the live "
                "response does not yet bind returned JSON to its settlement "
                "with a buyer-verifiable content digest"),
            "production_write_authorized": False,
            "external_write_authorized": False,
        }
    elif (external_settlements > 0
          and delivery["receipted_exact"] == 0):
        next_move = {
            "action": "establish_one_receipted_paid_result_delivery",
            "reason": (
                "the delivery-receipt contract is live, but no external paid "
                "result has yet produced a persisted buyer-verifiable receipt"),
            "production_write_authorized": False,
            "external_write_authorized": False,
        }
    elif (delivery["receipted_exact"]
          and direct_feedback["status"] == "unavailable_live_contract"):
        next_move = {
            "action": "promote_direct_buyer_feedback_contract",
            "reason": (
                "paid delivery receipts exist, but ordinary x402 buyers have "
                "no live bounded channel to report usefulness and repeat "
                "intent"),
            "production_write_authorized": False,
            "external_write_authorized": False,
        }
    elif (delivery["receipted_exact"]
          and direct_feedback["received"] == 0):
        next_move = {
            "action": "establish_one_buyer_usefulness_receipt",
            "reason": (
                "the direct feedback contract is live, but no buyer has yet "
                "classified a receipted paid result as useful or not useful"),
            "external_write_authorized": False,
        }
    elif repeat_purchases == 0 and regulatory["external_settlements"] > 0:
        if repeat_product["status"] == "exact":
            next_move = {
                "action": "repeat_purchase_distribution_regulatory_radar",
                "reason": (
                    "Regulatory Radar has independently paid buyers, the "
                    "bounded dated-watch follow-up is live at its exact "
                    "contract, and the fleet has no repeat external purchase"),
                "external_write_authorized": False,
            }
        elif repeat_product["status"] == "drifted":
            next_move = {
                "action": "repair_regulatory_radar_dated_watch_contract",
                "reason": (
                    "Regulatory Radar has independently paid buyers but its "
                    "dated-watch repeat product is live with contract drift; "
                    "outreach must remain blocked"),
                "external_write_authorized": False,
            }
        else:
            next_move = {
                "action": "qualify_genuine_repeat_regulatory_radar_demand",
                "distribution_scope":
                    "existing_regulatory_radar_scan_only",
                "repeat_product_status": "absent",
                "reason": (
                    "Regulatory Radar has independently paid buyers and its "
                    "existing scan route can be purchased again, but the "
                    "fleet has no genuine repeat purchase. The optional "
                    "dated-watch route is absent and remains a separate "
                    "inventory gap; its absence must not restart the already "
                    "completed paid-success seat-bridge release chain or "
                    "manufacture test traffic"),
                "external_write_authorized": False,
            }
    elif external_settlements == 0:
        next_move = {
            "action": "first_external_buyer_distribution",
            "reason": "the fleet has no independent external settlement",
            "external_write_authorized": False,
        }
    else:
        next_move = {
            "action": "scale_verified_winning_route",
            "reason": "repeat demand exists and can be expanded carefully",
            "external_write_authorized": False,
        }

    paid_hive_direct_minimum = (
        int(hive_route["external_settlements"]) + hive_cash_escrows)
    paid_hive_zero_proven = (
        paid_hive_direct_minimum == 0
        and hive_market_jobs == 0
        and hive_market_artifacts == 0
    )
    return {
        "status": "ok",
        "generated_at": _iso(generated),
        "classification": "read_only_commercial_evidence_snapshot",
        "sources": {
            "gateway_health": gateway_url,
            "agent_market_health": market_url,
        },
        "source_freshness": {
            **source_freshness,
            "subscriptions": {
                "timestamp": _iso(subscription_timestamp),
                "age_seconds": max(0, int(subscription_age)),
                "max_age_seconds": max_source_age_seconds,
                "status": "fresh",
            },
        },
        "commercial_truth": {
            "external_x402_settlements": external_settlements,
            "distinct_external_x402_payers": external_payers,
            "external_x402_revenue_atomic_usdc": external_revenue_atomic,
            "external_x402_revenue_usdc": exact_usdc(external_revenue_atomic),
            "repeat_external_x402_purchases": repeat_purchases,
            "external_x402_retention_cohorts": retention,
            "external_x402_paid_results_delivered_exact":
                direct_feedback["received"],
            "external_x402_paid_results_delivered_observed":
                delivery["delivered"],
            "external_x402_paid_results_receipted_exact":
                delivery["receipted_exact"],
            "external_x402_paid_results_receipted_observed":
                delivery["receipted"],
            "external_x402_paid_results_failed": delivery["failed"],
            "external_x402_paid_results_unknown": delivery["unknown"],
            "external_x402_delivery_instrumentation":
                delivery["instrumentation"],
            "external_x402_buyer_feedback": direct_feedback,
            "self_x402_settlements_not_revenue": self_settlements,
            "a2a_completed_tasks": a2a_completed,
            "paid_hive_completions_exact":
                0 if paid_hive_zero_proven else None,
            "paid_hive_completions_proven_zero": paid_hive_zero_proven,
            "paid_hive_direct_completions_minimum": paid_hive_direct_minimum,
            "paid_hive_x402_external_settlements":
                hive_route["external_settlements"],
            "paid_hive_a2a_cash_escrows": hive_cash_escrows,
            "hive_internal_escrows_not_cash": hive_internal_escrows,
            "hive_market_jobs": hive_market_jobs,
            "hive_market_artifacts": hive_market_artifacts,
            "hive_completion_attribution_note": (
                "Market jobs/artifacts are reported separately because they "
                "can overlap their funding and settlement evidence; they are "
                "never added to direct-rail completions without an exact "
                "job-level join"),
            "market_open_work_not_funded_demand": work_open,
            "market_work_funding_verified": work_funding_verified,
            "market_independently_verified_jobs": verified_jobs,
            "market_independently_useful_paid_deliveries": useful_deliveries,
            "market_buyer_feedback_jobs": buyer_feedback_jobs,
            "market_would_buy_again_count": would_buy_again,
            "market_messages_total": messages_total,
            "active_subscriptions": active_subscriptions,
            "mrr_minor": mrr_minor,
            "mrr_usd": format(Decimal(mrr_minor) / Decimal(100), ".2f"),
            "seat_funnel": {
                "views": seat_views,
                "checkout_starts": checkout_starts,
                "active_subscriptions": active_subscriptions,
                "mrr_minor": mrr_minor,
                "source_attribution_status": seat_source_status,
                "source_views": seat_source_views,
                "attributed_views": seat_attributed_views,
                "unattributed_views": seat_unattributed_views,
                "source_lifecycle_status":
                    seat_source_lifecycle_status,
                "source_lifecycle": seat_source_lifecycle,
                "retention_status": seat_retention_status,
                "retention": seat_retention,
            },
            "reviewed_snapshot_funnel": {
                "views": snapshot_views,
                "checkout_starts": snapshot_checkout_starts,
                "paid": snapshot_paid,
            },
        },
        "winning_route": {
            "route": "regulatory-radar/scan_regulations",
            **regulatory,
            "external_revenue_usdc": exact_usdc(
                int(regulatory["external_revenue_atomic"])),
        },
        "repeat_product": repeat_product,
        "next_move": next_move,
        "boundaries": {
            "open_work_is_revenue": False,
            "internal_escrows_are_cash": False,
            "self_settlements_are_external_revenue": False,
            "seller_pricing_hints_are_independent_evidence": False,
            "snapshot_authorizes_outbound": False,
            "snapshot_moves_money": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway-health-url", default=DEFAULT_GATEWAY)
    parser.add_argument("--market-health-url", default=DEFAULT_MARKET)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--max-source-age-seconds",
        type=int,
        default=DEFAULT_MAX_SOURCE_AGE_SECONDS,
    )
    parser.add_argument(
        "--subscription-reconciliation-file",
        help=(
            "optional JSON from the admin subscription activation "
            "reconciliation tool"),
    )
    args = parser.parse_args()
    try:
        gateway, gateway_observation = fetch_json(
            args.gateway_health_url, args.timeout)
        market, market_observation = fetch_json(
            args.market_health_url, args.timeout)
        subscription_reconciliation = None
        if args.subscription_reconciliation_file:
            with open(
                    args.subscription_reconciliation_file,
                    encoding="utf-8") as handle:
                subscription_reconciliation = json.load(handle)
        result = build_snapshot(
            gateway,
            market,
            gateway_url=args.gateway_health_url,
            market_url=args.market_health_url,
            source_observations={
                "gateway_health": gateway_observation,
                "agent_market_health": market_observation,
            },
            max_source_age_seconds=args.max_source_age_seconds,
            subscription_reconciliation=subscription_reconciliation,
        )
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
