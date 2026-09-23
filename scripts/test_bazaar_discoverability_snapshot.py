import copy

import pytest

from scripts import bazaar_discoverability_snapshot as snapshot


def route(key, *, calls=0, payers=0):
    return {
        "accepts": [{"amount": "10000", "network": "eip155:8453"}],
        "lastUpdated": "2026-08-20T00:00:00Z",
        "quality": {
            "l30DaysTotalCalls": calls,
            "l30DaysUniquePayers": payers,
            "lastCalledAt": "2026-07-27T16:47:17Z",
        },
        "resource": snapshot.VIRIDIS_RESOURCE_PREFIX + key,
        "serviceName": "Viridis Agent Fleet",
    }


def merchant():
    resources = [
        route(key, calls=3 if key.startswith("regulatory-radar") else 0,
              payers=3 if key.startswith("regulatory-radar") else 0)
        for key in snapshot.EXPECTED_MERCHANT_ROUTES
    ]
    return {
        "pagination": {"limit": 20, "offset": 0, "total": len(resources)},
        "payTo": snapshot.PAY_TO,
        "resources": resources,
    }


def search(*resources):
    return {
        "partialResults": False,
        "resources": list(resources),
        "searchMethod": "hybrid",
    }


def test_present_inventory_and_search_are_reported_without_commercial_claims():
    radar = route("regulatory-radar/scan_regulations", calls=3, payers=3)
    result = snapshot.build_snapshot(
        merchant(),
        {"buyer intent": search({
            "resource": "https://example.test/first",
        }, radar)},
        generated_at="2026-08-21T00:00:00+00:00",
    )
    assert result["status"] == "ok"
    assert result["classification"] == "DISCOVERABILITY_PRESENT"
    assert result["merchant_inventory"]["missing_expected_routes"] == []
    found = result["semantic_search"]["queries"][0]
    assert found["viridis_found"] is True
    assert found["viridis_results"] == [{
        "rank": 2,
        "route": "regulatory-radar/scan_regulations",
        "resource": radar["resource"],
    }]
    assert result["boundaries"]["inventory_or_search_is_revenue"] is False
    assert result["next_move"]["payment_authorized"] is False


def test_semantic_absence_is_degraded_but_never_authorizes_self_payment():
    result = snapshot.build_snapshot(
        merchant(),
        {"buyer intent": search({"resource": "https://example.test/only"})},
    )
    assert result["status"] == "degraded"
    assert result["classification"] == "SEMANTIC_DISCOVERABILITY_DEGRADED"
    assert result["merchant_inventory"]["viridis_route_count"] == 4
    assert result["semantic_search"]["any_viridis_result"] is False
    assert result["boundaries"][
        "self_settlement_allowed_to_refresh_recency"] is False
    assert "self_pay_to_refresh_bazaar_recency" in result["next_move"]["do_not"]


def test_missing_exact_merchant_route_is_stronger_than_search_presence():
    payload = merchant()
    payload["resources"] = payload["resources"][:-1]
    payload["pagination"]["total"] -= 1
    result = snapshot.build_snapshot(
        payload,
        {"buyer intent": search(route("regulatory-radar/scan_regulations"))},
    )
    assert result["status"] == "degraded"
    assert result["classification"] == "MERCHANT_INVENTORY_MISSING"
    assert result["merchant_inventory"]["missing_expected_routes"] == [
        "regulatory-radar/scan_regulations"
    ]


def test_inconsistent_merchant_count_fails_closed():
    payload = merchant()
    payload["pagination"]["total"] += 1
    with pytest.raises(
            snapshot.SnapshotError,
            match="pagination total does not match"):
        snapshot.build_snapshot(payload, {"buyer intent": search()})


def test_builder_does_not_mutate_sources():
    merchant_payload = merchant()
    searches = {"buyer intent": search()}
    before_merchant = copy.deepcopy(merchant_payload)
    before_searches = copy.deepcopy(searches)
    snapshot.build_snapshot(merchant_payload, searches)
    assert merchant_payload == before_merchant
    assert searches == before_searches


def test_search_url_encodes_query_and_limit():
    url = snapshot._search_url("SB 253 / SB 261", 20)
    assert "query=SB+253+%2F+SB+261" in url
    assert url.endswith("limit=20")
