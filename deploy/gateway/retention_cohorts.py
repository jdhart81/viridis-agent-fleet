"""Privacy-safe retention cohorts for durable external x402 settlements."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


WINDOW_DAYS = (7, 14, 30)
ACQUISITION_SOURCES = frozenset({
    "direct",
    "github",
    "openclaw",
    "partner_integration",
    "search",
    "other",
    "unknown",
    "internal",
})


def acquisition_source(value: Any) -> str:
    """Normalize a buyer-declared finite source without retaining referrers."""
    source = str(value or "").strip().lower().replace("-", "_")
    return source if source in ACQUISITION_SOURCES else "unknown"


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _window(
    cohorts: list[dict[str, Any]],
    *,
    as_of: datetime,
    days: int,
) -> dict[str, int | None]:
    eligible = 0
    repeated = 0
    pending = 0
    for cohort in cohorts:
        deadline = cohort["first_at"] + timedelta(days=days)
        if as_of < deadline:
            pending += 1
            continue
        eligible += 1
        if any(
            event["sequence"] > cohort["first_sequence"]
            and event["timestamp"] <= deadline
            for event in cohort["events"]
        ):
            repeated += 1
    return {
        "eligible_payers": eligible,
        "repeat_payers": repeated,
        "pending_maturity": pending,
        "repeat_rate_bps":
            None if eligible == 0 else repeated * 10_000 // eligible,
    }


def _windows(
    cohorts: list[dict[str, Any]],
    *,
    as_of: datetime,
) -> dict[str, dict[str, int | None]]:
    return {
        f"{days}d": _window(cohorts, as_of=as_of, days=days)
        for days in WINDOW_DAYS
    }


def build_retention_cohorts(
    records: Iterable[dict[str, Any]],
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Aggregate payer retention without returning payer identifiers."""
    observed_at = as_of or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    observed_at = observed_at.astimezone(timezone.utc)

    payer_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    excluded = {
        "self_settlements": 0,
        "missing_payer": 0,
        "invalid_or_future_timestamp": 0,
    }
    for sequence, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        if record.get("self_settle") is True:
            excluded["self_settlements"] += 1
            continue
        payer = str(record.get("payer_wallet") or "").strip().lower()
        if not payer:
            excluded["missing_payer"] += 1
            continue
        timestamp = _instant(record.get("timestamp"))
        if timestamp is None or timestamp > observed_at:
            excluded["invalid_or_future_timestamp"] += 1
            continue
        route = str(record.get("route") or "unknown").strip() or "unknown"
        payer_events[payer].append({
            "timestamp": timestamp,
            "sequence": sequence,
            "route": route,
            "source": acquisition_source(record.get("acquisition_source")),
        })

    cohorts: list[dict[str, Any]] = []
    for events in payer_events.values():
        ordered = sorted(events, key=lambda event: (
            event["timestamp"], event["sequence"]
        ))
        first = ordered[0]
        cohorts.append({
            "first_at": first["timestamp"],
            "first_sequence": first["sequence"],
            "first_route": first["route"],
            "acquisition_source": first["source"],
            "events": ordered,
        })

    by_route: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cohort in cohorts:
        by_route[cohort["first_route"]].append(cohort)
        by_source[cohort["acquisition_source"]].append(cohort)

    return {
        "version": "viridis-x402-retention-cohorts-v1",
        "as_of": observed_at.isoformat(),
        "identity_handling": (
            "signed payer addresses are grouped in memory and never returned"
        ),
        "acquisition_source_evidence": (
            "finite buyer-declared label; historical records without one are "
            "grouped as unknown"
        ),
        "payer_count": len(cohorts),
        "windows": _windows(cohorts, as_of=observed_at),
        "by_first_route": {
            name: {
                "payer_count": len(group),
                "windows": _windows(group, as_of=observed_at),
            }
            for name, group in sorted(by_route.items())
        },
        "by_acquisition_source": {
            name: {
                "payer_count": len(group),
                "windows": _windows(group, as_of=observed_at),
            }
            for name, group in sorted(by_source.items())
        },
        "excluded": excluded,
    }
