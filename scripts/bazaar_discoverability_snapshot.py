#!/usr/bin/env python3
"""Read-only Coinbase Bazaar discoverability snapshot for Viridis routes.

The snapshot keeps endpoint health, merchant inventory, semantic search,
settlement, and revenue as separate facts. It never signs a request, sends a
message, retries with payment, or uses self-settlement to refresh recency.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


PAY_TO = "0xfEf2e570b645EB720Ee6c589d27450810982f329"
MERCHANT_URL = (
    "https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant"
    f"?payTo={PAY_TO}"
)
SEARCH_URL = (
    "https://api.cdp.coinbase.com/platform/v2/x402/discovery/search"
)
VIRIDIS_RESOURCE_PREFIX = "https://mcp.viridisconservation.com/x402/"
EXPECTED_MERCHANT_ROUTES = (
    "disclosure-compiler/compile_disclosure",
    "ghg-ledger/calculate_inventory",
    "quantity-takeoff/calculate_takeoff",
    "regulatory-radar/scan_regulations",
)
DEFAULT_QUERIES = (
    "energy climate compliance regulation",
    "California climate compliance SB 253 SB 261 API",
)


class SnapshotError(RuntimeError):
    """A required Bazaar response or invariant is absent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SnapshotError(message)


def _mapping(value: Any, path: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{path} is missing or not an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    require(isinstance(value, list), f"{path} is missing or not a list")
    return value


def _non_negative_int(value: Any, path: str) -> int:
    require(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0,
        f"{path} is missing or not a non-negative integer",
    )
    return value


def _resource_key(resource: str) -> str:
    require(
        resource.startswith(VIRIDIS_RESOURCE_PREFIX),
        "Viridis resource has an unexpected URL",
    )
    key = resource[len(VIRIDIS_RESOURCE_PREFIX):]
    require(bool(key) and "/" in key, "Viridis resource key is invalid")
    return key


def fetch_json(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "accept": "application/json",
            "user-agent": "viridis-bazaar-discoverability-snapshot/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        require(response.status == 200, f"{url} returned HTTP {response.status}")
        payload = json.load(response)
    return _mapping(payload, url)


def _merchant_route(item: Any, index: int) -> dict[str, Any] | None:
    row = _mapping(item, f"merchant.resources[{index}]")
    resource = row.get("resource")
    require(
        isinstance(resource, str) and resource.startswith("https://"),
        f"merchant.resources[{index}].resource is invalid",
    )
    if not resource.startswith(VIRIDIS_RESOURCE_PREFIX):
        return None
    quality = _mapping(
        row.get("quality"), f"merchant.resources[{index}].quality")
    accepts = _list(
        row.get("accepts"), f"merchant.resources[{index}].accepts")
    require(bool(accepts), f"merchant.resources[{index}].accepts is empty")
    first_accept = _mapping(
        accepts[0], f"merchant.resources[{index}].accepts[0]")
    return {
        "route": _resource_key(resource),
        "resource": resource,
        "amount_atomic": str(first_accept.get("amount", "")),
        "network": str(first_accept.get("network", "")),
        "last_updated": str(row.get("lastUpdated", "")),
        "last_called_at": str(quality.get("lastCalledAt", "")),
        "calls_30d": _non_negative_int(
            quality.get("l30DaysTotalCalls"),
            f"merchant.resources[{index}].quality.l30DaysTotalCalls",
        ),
        "unique_payers_30d": _non_negative_int(
            quality.get("l30DaysUniquePayers"),
            f"merchant.resources[{index}].quality.l30DaysUniquePayers",
        ),
    }


def build_snapshot(
    merchant: dict[str, Any],
    searches: dict[str, dict[str, Any]],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    pagination = _mapping(merchant.get("pagination"), "merchant.pagination")
    merchant_total = _non_negative_int(
        pagination.get("total"), "merchant.pagination.total")
    raw_resources = _list(merchant.get("resources"), "merchant.resources")
    require(
        merchant_total == len(raw_resources),
        "merchant pagination total does not match returned resources",
    )

    routes = []
    for index, item in enumerate(raw_resources):
        route = _merchant_route(item, index)
        if route is not None:
            routes.append(route)
    routes.sort(key=lambda item: item["route"])
    present = {item["route"] for item in routes}
    expected = set(EXPECTED_MERCHANT_ROUTES)
    missing = sorted(expected - present)
    unexpected = sorted(present - expected)

    search_results = []
    for query, payload in searches.items():
        result = _mapping(payload, f"searches[{query!r}]")
        resources = _list(
            result.get("resources"), f"searches[{query!r}].resources")
        found = []
        for rank, item in enumerate(resources, start=1):
            row = _mapping(item, f"searches[{query!r}].resources[{rank - 1}]")
            resource = row.get("resource")
            require(
                isinstance(resource, str) and resource.startswith("https://"),
                f"searches[{query!r}].resources[{rank - 1}].resource is invalid",
            )
            if resource.startswith(VIRIDIS_RESOURCE_PREFIX):
                found.append({
                    "rank": rank,
                    "route": _resource_key(resource),
                    "resource": resource,
                })
        search_results.append({
            "query": query,
            "partial_results": bool(result.get("partialResults", False)),
            "search_method": str(result.get("searchMethod", "")),
            "returned": len(resources),
            "viridis_found": bool(found),
            "viridis_results": found,
        })

    search_visible = any(item["viridis_found"] for item in search_results)
    if missing:
        status = "degraded"
        classification = "MERCHANT_INVENTORY_MISSING"
        action = "investigate_external_bazaar_inventory_drift"
        reason = (
            "one or more previously indexed Viridis resources are absent from "
            "the exact merchant inventory"
        )
    elif not search_visible:
        status = "degraded"
        classification = "SEMANTIC_DISCOVERABILITY_DEGRADED"
        action = "monitor_external_search_and_qualify_organic_buyer_demand"
        reason = (
            "the exact merchant inventory is present, but configured buyer-intent "
            "queries do not surface a Viridis resource"
        )
    else:
        status = "ok"
        classification = "DISCOVERABILITY_PRESENT"
        action = "continue_read_only_monitoring"
        reason = "merchant inventory and at least one buyer-intent search are present"

    return {
        "status": status,
        "classification": classification,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "boundaries": {
            "inventory_or_search_is_revenue": False,
            "inventory_or_search_is_buyer_demand": False,
            "snapshot_authorizes_outbound": False,
            "snapshot_authorizes_payment": False,
            "snapshot_authorizes_production_write": False,
            "self_settlement_allowed_to_refresh_recency": False,
        },
        "merchant_inventory": {
            "url": MERCHANT_URL,
            "pay_to": str(merchant.get("payTo", "")),
            "reported_total": merchant_total,
            "viridis_route_count": len(routes),
            "expected_routes": list(EXPECTED_MERCHANT_ROUTES),
            "missing_expected_routes": missing,
            "unexpected_viridis_routes": unexpected,
            "routes": routes,
        },
        "semantic_search": {
            "url": SEARCH_URL,
            "any_viridis_result": search_visible,
            "queries": search_results,
        },
        "next_move": {
            "action": action,
            "reason": reason,
            "external_write_authorized": False,
            "payment_authorized": False,
            "production_write_authorized": False,
            "do_not": [
                "self_pay_to_refresh_bazaar_recency",
                "weaken_required_input_validation",
                "claim_search_presence_as_demand_or_revenue",
            ],
        },
    }


def _search_url(query: str, limit: int) -> str:
    return SEARCH_URL + "?" + urllib.parse.urlencode({
        "query": query,
        "limit": limit,
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--query", action="append", dest="queries")
    args = parser.parse_args()
    try:
        require(args.timeout > 0, "timeout must be positive")
        require(1 <= args.limit <= 100, "limit must be between 1 and 100")
        queries = tuple(args.queries or DEFAULT_QUERIES)
        require(all(query.strip() for query in queries), "query cannot be blank")
        merchant = fetch_json(MERCHANT_URL, args.timeout)
        searches = {
            query: fetch_json(_search_url(query, args.limit), args.timeout)
            for query in queries
        }
        print(json.dumps(build_snapshot(merchant, searches), indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
