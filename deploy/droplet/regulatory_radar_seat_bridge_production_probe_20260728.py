#!/usr/bin/env python3
"""Read-only production gate for the Regulatory Radar paid-success seat bridge.

The public modes perform cache-busted GET requests only to the exact Viridis
health endpoint.  The runtime mode is streamed into the live gateway container
and checks the exact image files, commerce metadata, and a deliberately empty
payment.  It never calls a paid route, signs or settles a payment, opens
checkout, or mutates a subscription.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


PUBLIC_BASE = "https://mcp.viridisconservation.com"
LOOPBACK_BASE = "http://127.0.0.1:8402"
X402_HTTP_PATH = Path("/fleet/deploy/gateway/x402_http.py")
X402_RAIL_PATH = Path("/fleet/deploy/gateway/x402_rail.py")
PAYMENT_GATE_PATH = Path("/fleet/deploy/gateway/payment_gate.py")
STATE_STORE_PATH = Path("/fleet/deploy/gateway/state_store.py")
GATEWAY_PATH = Path("/fleet/deploy/gateway/viridis_mcp_gateway.py")
SECURITY_PREFLIGHT_PATH = Path("/fleet/security-preflight-agent/src/core.py")

EXPECTED_X402_HTTP_SHA256 = (
    "33d0b79f19171f7f1ff89d92b41f4f0995a61592957720fb3a2c156628c2b980"
)
EXPECTED_PAYMENT_GATE_SHA256 = (
    "99990768fc1526fb520df20596b4fb3a3096efac44b4f93bb30ca8a3890e244f"
)
EXPECTED_STATE_STORE_SHA256 = (
    "e34b2c1bd9a0618e59e8864bacae2e1fd10404ddc41e60b4beb61bceaf7ccc73"
)
EXPECTED_GATEWAY_SHA256 = (
    "22c343594ee26db8d391ca67ef6a42306df6eaa8baf0d99f4e9f73c3d6806bec"
)
EXPECTED_SECURITY_PREFLIGHT_SHA256 = (
    "d0363968474aacc5f816bd6f87a284d3620f8df5eb96e54030cc78e119a9034a"
)
EXPECTED_SIGNER_PUBLIC_KEY_SHA256 = (
    "f4814e4634295083316fda3fdaebe0df19717b0135608b76a44cb566211bcf4a"
)
EXPECTED_PLAN_CATALOG_SHA256 = (
    "eb5534fecd55d0f8269e65f7ef1806fe12b7d2e90cc0f7c7f535789aef13bf5b"
)
EXPECTED_SEAT = {
    "plan_id": "compliance-seat",
    "price_monthly_minor": 14900,
    "currency": "usd",
    "interval": "month",
    "included_calls_per_month": 1000,
    "covered_agents": ["disclosure-compiler", "regulatory-radar"],
    "checkout_url": "https://mcp.viridisconservation.com/seats",
    "checkout_status_authoritative_source": "live_plan_catalog",
    "auto_checkout": False,
    "buyer_action_required": True,
    "note": (
        "compliance-seat: $149/mo covers 1,000 calls across "
        "disclosure-compiler + regulatory-radar"
    ),
}
MONOTONIC_TELEMETRY = (
    "settlements_total",
    "external_settlements",
    "distinct_external_payers",
    "repeat_external_purchases",
    "external_revenue_atomic",
)
MONOTONIC_SUBSCRIPTIONS = (
    "active_subscriptions",
    "checkouts_started",
    "mrr_minor",
)


class ProbeFailure(RuntimeError):
    """A production promotion invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeFailure(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _health_url(base: str) -> str:
    require(
        base in {PUBLIC_BASE, LOOPBACK_BASE},
        "probe refuses every origin except exact public HTTPS or loopback",
    )
    query = urllib.parse.urlencode({"seat-bridge-probe": time.time_ns()})
    return f"{base}/healthz?{query}"


def get_health(base: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        _health_url(base),
        headers={
            "accept": "application/json",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "user-agent": "viridis-seat-bridge-production-probe/1.0",
        },
        method="GET",
    )
    try:
        response = urllib.request.urlopen(request, timeout=30)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        payload = json.load(response)
        status = int(response.status)
    require(isinstance(payload, dict), "health did not return an object")
    return status, payload


def _route(
    routes: list[dict[str, Any]],
    agent: str,
    tool: str,
    amount: str,
) -> dict[str, Any]:
    matches = [
        item
        for item in routes
        if item.get("agent") == agent and item.get("tool") == tool
    ]
    require(len(matches) == 1, f"{agent}/{tool} route missing or duplicated")
    route = matches[0]
    require(
        str(route.get("amount_atomic_usdc")) == amount,
        f"{agent}/{tool} price changed",
    )
    require(route.get("v2_enabled") is True, f"{agent}/{tool} v2 is not enabled")
    require(route.get("x402_version") == 2, f"{agent}/{tool} is not x402 v2")
    return route


def commercial_snapshot(
    base: str,
    *,
    health_getter: Callable[[str], tuple[int, dict[str, Any]]] = get_health,
) -> dict[str, Any]:
    http_status, health = health_getter(base)
    require(http_status == 200, f"health returned HTTP {http_status}")
    require(health.get("status") == "ok", "gateway health is not ok")
    require(health.get("mount_errors") == {}, "gateway has mount errors")
    persistence = health.get("persistence", {})
    require(persistence.get("available") is True, "persistence unavailable")
    require(persistence.get("errors") == {}, "persistence has errors")

    agents = health.get("agents", {})
    require(isinstance(agents, dict), "health agents is not an object")
    require(len(agents) == 28, f"expected 28 agents, found {len(agents)}")
    non_ok = {
        name: details.get("status")
        for name, details in agents.items()
        if not isinstance(details, dict)
        or details.get("status") not in {"ok", "healthy"}
    }
    require(non_ok == {}, f"agents are not healthy: {sorted(non_ok)}")

    security = agents.get("security-preflight", {})
    expected_security = {
        "status": "ok",
        "version": "1.1.0",
        "signer_required": True,
        "signer_ready": True,
        "receipt_store": "persistent-sqlite",
        "receipt_store_ready": True,
        "raw_inputs_stored": False,
        "runtime_fetches_enabled": False,
        "signer_public_key_sha256": EXPECTED_SIGNER_PUBLIC_KEY_SHA256,
    }
    for key, expected in expected_security.items():
        require(
            security.get(key) == expected,
            f"Security Preflight production invariant changed: {key}",
        )

    x402 = health.get("payment_gate", {}).get("x402", {})
    require(x402.get("enabled") is True, "public x402 rail is not enabled")
    require(x402.get("errors") == {}, "public x402 rail has errors")
    routes = x402.get("http_front_door", [])
    require(isinstance(routes, list), "x402 route inventory is not a list")
    _route(routes, "regulatory-radar", "scan_regulations", "250000")
    _route(routes, "security-preflight", "security_preflight", "1000000")

    telemetry = x402.get("http_settlement_telemetry", {}).get("total")
    require(isinstance(telemetry, dict), "settlement telemetry is missing")
    for key in (*MONOTONIC_TELEMETRY, "self_settlements"):
        value = telemetry.get(key)
        require(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0,
            f"settlement telemetry is invalid: {key}",
        )
    require(
        telemetry["settlements_total"]
        == telemetry["external_settlements"] + telemetry["self_settlements"],
        "settlement totals are internally inconsistent",
    )

    subscriptions = health.get("subscriptions", {})
    require(subscriptions.get("status") == "ok", "subscriptions health is not ok")
    checks = subscriptions.get("checks", {})
    require(
        checks.get("stripe_provider_attached") is True,
        "Stripe subscription provider is not attached",
    )
    require(
        checks.get("durable_activation_commit_attached") is True,
        "durable subscription commit is not attached",
    )
    require(
        checks.get("plan_catalog_sha256") == EXPECTED_PLAN_CATALOG_SHA256,
        "subscription plan catalog changed",
    )
    require(
        checks.get("plan_catalog_version") == "0.3.0",
        "subscription plan catalog version changed",
    )
    for key in MONOTONIC_SUBSCRIPTIONS:
        value = checks.get(key)
        require(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0,
            f"subscription counter is invalid: {key}",
        )

    return {
        "schema": "viridis-seat-bridge-public-snapshot-v1",
        "status": "ok",
        "base": base,
        "agent_count": len(agents),
        "security_preflight": {
            key: security[key] for key in expected_security
        },
        "x402": {
            "enabled": True,
            "radar_amount_atomic_usdc": 250000,
            "security_preflight_amount_atomic_usdc": 1000000,
            "telemetry_total": {
                key: telemetry.get(key)
                for key in (
                    *MONOTONIC_TELEMETRY,
                    "self_settlements",
                    "first_external_settlement",
                )
            },
        },
        "subscriptions": {
            "plan_catalog_sha256": checks["plan_catalog_sha256"],
            "plan_catalog_version": checks["plan_catalog_version"],
            **{key: checks[key] for key in MONOTONIC_SUBSCRIPTIONS},
        },
        "probe_effects": {
            "request_method": "GET",
            "paid_route_called": False,
            "payment_signed": False,
            "payment_settled": False,
            "checkout_opened": False,
            "subscription_mutated": False,
        },
    }


def verify_public(
    base: str,
    baseline: dict[str, Any],
    *,
    health_getter: Callable[[str], tuple[int, dict[str, Any]]] = get_health,
) -> dict[str, Any]:
    require(
        baseline.get("schema") == "viridis-seat-bridge-public-snapshot-v1",
        "baseline schema changed",
    )
    current = commercial_snapshot(base, health_getter=health_getter)
    before_telemetry = baseline.get("x402", {}).get("telemetry_total", {})
    after_telemetry = current["x402"]["telemetry_total"]
    deltas: dict[str, int] = {}
    for key in MONOTONIC_TELEMETRY:
        before = before_telemetry.get(key)
        after = after_telemetry.get(key)
        require(
            isinstance(before, int) and after >= before,
            f"commercial telemetry regressed: {key}",
        )
        deltas[key] = after - before
    require(
        after_telemetry["self_settlements"]
        == before_telemetry.get("self_settlements"),
        "self-settlement count changed during the transaction",
    )
    require(
        after_telemetry["first_external_settlement"]
        == before_telemetry.get("first_external_settlement"),
        "first external settlement evidence changed",
    )

    before_subscriptions = baseline.get("subscriptions", {})
    after_subscriptions = current["subscriptions"]
    subscription_deltas: dict[str, int] = {}
    for key in MONOTONIC_SUBSCRIPTIONS:
        before = before_subscriptions.get(key)
        after = after_subscriptions.get(key)
        require(
            isinstance(before, int) and after >= before,
            f"subscription counter regressed: {key}",
        )
        subscription_deltas[key] = after - before
    require(
        after_subscriptions["plan_catalog_sha256"]
        == before_subscriptions.get("plan_catalog_sha256"),
        "subscription catalog digest changed during promotion",
    )
    require(
        after_subscriptions["plan_catalog_version"]
        == before_subscriptions.get("plan_catalog_version"),
        "subscription catalog version changed during promotion",
    )

    return {
        **current,
        "baseline_verified": True,
        "commercial_deltas": deltas,
        "subscription_deltas": subscription_deltas,
        "operator_caused_commercial_mutation": False,
    }


def _require_digest(path: Path, expected: str, label: str) -> None:
    require(path.is_file(), f"runtime {label} is missing")
    require(_sha256(path) == expected, f"runtime {label} digest mismatch")


def _runtime_module(path: Path, name: str) -> Any:
    require(path.is_file(), f"runtime module is missing: {path}")
    parent = str(path.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    module = importlib.import_module(name)
    require(
        Path(module.__file__).resolve() == path.resolve(),
        f"runtime imported {name} from an unexpected path",
    )
    return module


def verify_runtime(
    base: str,
    *,
    x402_http_module: Any | None = None,
    x402_rail_module: Any | None = None,
    health_getter: Callable[[str], tuple[int, dict[str, Any]]] = get_health,
    x402_http_path: Path = X402_HTTP_PATH,
    x402_rail_path: Path = X402_RAIL_PATH,
    payment_gate_path: Path = PAYMENT_GATE_PATH,
    state_store_path: Path = STATE_STORE_PATH,
    gateway_path: Path = GATEWAY_PATH,
    security_preflight_path: Path = SECURITY_PREFLIGHT_PATH,
    expected_x402_http_sha256: str = EXPECTED_X402_HTTP_SHA256,
    expected_payment_gate_sha256: str = EXPECTED_PAYMENT_GATE_SHA256,
    expected_state_store_sha256: str = EXPECTED_STATE_STORE_SHA256,
    expected_gateway_sha256: str = EXPECTED_GATEWAY_SHA256,
    expected_security_preflight_sha256: str = EXPECTED_SECURITY_PREFLIGHT_SHA256,
) -> dict[str, Any]:
    require(base == LOOPBACK_BASE, "runtime probe refuses non-loopback URLs")
    snapshot = commercial_snapshot(base, health_getter=health_getter)
    _require_digest(x402_http_path, expected_x402_http_sha256, "x402_http.py")
    _require_digest(payment_gate_path, expected_payment_gate_sha256, "payment_gate.py")
    _require_digest(state_store_path, expected_state_store_sha256, "state_store.py")
    _require_digest(gateway_path, expected_gateway_sha256, "gateway")
    _require_digest(
        security_preflight_path,
        expected_security_preflight_sha256,
        "Security Preflight core",
    )

    runtime = x402_http_module or _runtime_module(x402_http_path, "x402_http")
    rail = x402_rail_module or _runtime_module(x402_rail_path, "x402_rail")
    seat = runtime.seat_option("regulatory-radar", PUBLIC_BASE)
    require(seat == EXPECTED_SEAT, "Regulatory Radar seat object changed")
    success = runtime._with_commerce_metadata(
        {"status": "ok"},
        "regulatory-radar",
        "scan_regulations",
        PUBLIC_BASE,
    )
    commerce = success.get("viridis_commerce", {})
    require(
        commerce.get("seat_option") == EXPECTED_SEAT,
        "successful Regulatory Radar result omits the exact seat offer",
    )
    require(
        commerce.get("auto_execute") is False
        and commerce.get("payment_required") is True
        and commerce.get("buyer_authorization_required") is True,
        "commerce envelope weakened the fresh authorization boundary",
    )
    failed = runtime._with_commerce_metadata(
        {"status": "error", "error": "probe fixture"},
        "regulatory-radar",
        "scan_regulations",
        PUBLIC_BASE,
    )
    require(
        "viridis_commerce" not in failed,
        "failed paid result received commerce metadata",
    )
    for agent, tool in (
        ("hive", "solve"),
        ("security-preflight", "security_preflight"),
    ):
        uncovered = runtime._with_commerce_metadata(
            {"status": "ok"}, agent, tool, PUBLIC_BASE
        )
        require(
            "seat_option" not in uncovered.get("viridis_commerce", {}),
            f"uncovered {agent} route received a Compliance Seat offer",
        )

    require(rail.is_enabled() is True, "runtime x402 rail is not enabled")
    requirements = rail.build_accepts(
        "regulatory-radar",
        25,
        f"{PUBLIC_BASE}/x402/regulatory-radar/scan_regulations",
    )
    require(isinstance(requirements, dict), "payment requirements are missing")
    require(
        requirements.get("maxAmountRequired") == "250000",
        "runtime payment requirement price changed",
    )
    transport_called = False

    def blocked_transport(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal transport_called
        transport_called = True
        raise AssertionError("facilitator transport must not be called")

    refusal = rail.verify_and_settle(
        {},
        requirements,
        _transport=blocked_transport,
    )
    require(
        refusal
        == {"settled": False, "reason": "missing_or_malformed_payment"},
        "empty payment did not fail closed",
    )
    require(transport_called is False, "payment refusal contacted facilitator")

    return {
        "status": "ok",
        "mode": "production_runtime",
        "agent_count": snapshot["agent_count"],
        "x402_http_sha256": expected_x402_http_sha256,
        "payment_gate_sha256": expected_payment_gate_sha256,
        "state_store_sha256": expected_state_store_sha256,
        "gateway_sha256": expected_gateway_sha256,
        "security_preflight_sha256": expected_security_preflight_sha256,
        "seat_option": seat,
        "empty_payment_refusal": refusal,
        "facilitator_contacted": False,
        "paid_route_called": False,
        "payment_signed": False,
        "payment_settled": False,
        "checkout_opened": False,
        "subscription_mutated": False,
    }


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), "baseline is not an object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)
    capture = subparsers.add_parser("public-capture")
    capture.add_argument("--base", default=PUBLIC_BASE)
    verify = subparsers.add_parser("public-verify")
    verify.add_argument("--base", default=PUBLIC_BASE)
    verify.add_argument("--baseline", type=Path, required=True)
    runtime = subparsers.add_parser("runtime")
    runtime.add_argument("--base", default=LOOPBACK_BASE)
    args = parser.parse_args(argv)
    try:
        if args.mode == "public-capture":
            result = commercial_snapshot(args.base.rstrip("/"))
        elif args.mode == "public-verify":
            result = verify_public(
                args.base.rstrip("/"),
                _read_json(args.baseline),
            )
        else:
            result = verify_runtime(args.base.rstrip("/"))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "mode": args.mode,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
