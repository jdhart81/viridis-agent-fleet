from datetime import datetime, timezone

import pytest

from deploy.gateway.retention_cohorts import (
    acquisition_source,
    build_retention_cohorts,
)


AS_OF = datetime(2026, 7, 31, tzinfo=timezone.utc)


def record(payer, timestamp, route="radar/scan", source=None, **extra):
    return {
        "payer_wallet": payer,
        "timestamp": timestamp,
        "route": route,
        "acquisition_source": source,
        "self_settle": False,
        **extra,
    }


def test_7_14_30_day_maturity_and_repeat_windows():
    result = build_retention_cohorts([
        record("0xA", "2026-06-20T00:00:00Z"),
        record("0xA", "2026-06-25T00:00:00Z"),
        record("0xB", "2026-07-20T00:00:00Z"),
        record("0xB", "2026-07-29T00:00:00Z"),
        record("0xC", "2026-07-28T00:00:00Z"),
    ], as_of=AS_OF)
    assert result["payer_count"] == 3
    assert result["windows"]["7d"] == {
        "eligible_payers": 2,
        "repeat_payers": 1,
        "pending_maturity": 1,
        "repeat_rate_bps": 5000,
    }
    assert result["windows"]["14d"] == {
        "eligible_payers": 1,
        "repeat_payers": 1,
        "pending_maturity": 2,
        "repeat_rate_bps": 10000,
    }
    assert result["windows"]["30d"]["eligible_payers"] == 1


def test_repeat_after_window_does_not_count_for_short_window():
    result = build_retention_cohorts([
        record("0xA", "2026-06-20T00:00:00Z"),
        record("0xA", "2026-07-01T00:00:00Z"),
    ], as_of=AS_OF)
    assert result["windows"]["7d"]["repeat_payers"] == 0
    assert result["windows"]["14d"]["repeat_payers"] == 1


def test_first_route_and_acquisition_source_groups_conserve():
    result = build_retention_cohorts([
        record("0xA", "2026-06-01T00:00:00Z",
               route="radar/scan", source="github"),
        record("0xA", "2026-06-02T00:00:00Z",
               route="hive/solve", source="other"),
        record("0xB", "2026-06-03T00:00:00Z",
               route="hive/solve", source="openclaw"),
        record("0xC", "2026-06-04T00:00:00Z",
               route="radar/scan"),
    ], as_of=AS_OF)
    assert result["by_first_route"]["radar/scan"]["payer_count"] == 2
    assert result["by_first_route"]["hive/solve"]["payer_count"] == 1
    assert result["by_acquisition_source"]["github"]["payer_count"] == 1
    assert result["by_acquisition_source"]["openclaw"]["payer_count"] == 1
    assert result["by_acquisition_source"]["unknown"]["payer_count"] == 1
    assert sum(
        group["payer_count"]
        for group in result["by_first_route"].values()
    ) == result["payer_count"]
    assert sum(
        group["payer_count"]
        for group in result["by_acquisition_source"].values()
    ) == result["payer_count"]


def test_wallets_are_never_returned():
    result = build_retention_cohorts([
        record("0xSecretPublicAddress", "2026-06-01T00:00:00Z"),
    ], as_of=AS_OF)
    assert "0xsecretpublicaddress" not in str(result).lower()


def test_exclusions_are_explicit_and_do_not_enter_denominator():
    result = build_retention_cohorts([
        record("0xSelf", "2026-06-01T00:00:00Z", self_settle=True),
        record("", "2026-06-01T00:00:00Z"),
        record("0xBad", "not-a-time"),
        record("0xFuture", "2026-08-01T00:00:00Z"),
        record("0xGood", "2026-06-01T00:00:00Z"),
    ], as_of=AS_OF)
    assert result["payer_count"] == 1
    assert result["excluded"] == {
        "self_settlements": 1,
        "missing_payer": 1,
        "invalid_or_future_timestamp": 2,
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("GitHub", "github"),
        ("partner-integration", "partner_integration"),
        ("a raw referrer", "unknown"),
        (None, "unknown"),
    ],
)
def test_acquisition_source_is_finite(raw, expected):
    assert acquisition_source(raw) == expected


def test_zero_eligible_payers_has_no_made_up_rate():
    result = build_retention_cohorts([
        record("0xNew", "2026-07-30T00:00:00Z"),
    ], as_of=AS_OF)
    assert result["windows"]["7d"]["eligible_payers"] == 0
    assert result["windows"]["7d"]["repeat_rate_bps"] is None


def test_naive_as_of_fails_closed():
    with pytest.raises(ValueError, match="timezone"):
        build_retention_cohorts([], as_of=datetime(2026, 7, 31))
