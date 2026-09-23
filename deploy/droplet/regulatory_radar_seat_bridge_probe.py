#!/usr/bin/env python3
"""Fail-closed, no-payment probe for the Regulatory Radar seat bridge.

Run this inside the isolated candidate container. It reads only the loopback
health surface and imports the already-loaded gateway module. It never calls a
paid route, signs a payment, opens checkout, mutates a subscription, or uses a
provider.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


X402_HTTP_PATH = Path("/fleet/deploy/gateway/x402_http.py")
PAYMENT_GATE_PATH = Path("/fleet/deploy/gateway/payment_gate.py")
EXPECTED_X402_HTTP_SHA256 = (
    "8feb4ec0762b734e4258335d48046c3325c1f6af8b8dc12e14b555bab317b1b6"
)
EXPECTED_PAYMENT_GATE_SHA256 = (
    "5bc12a1f78337216665b9a5eb83f2411fec12608559b4c622178afd98c67b269"
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


class ProbeFailure(RuntimeError):
    """A candidate invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeFailure(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _loopback(base: str) -> bool:
    return (
        base.startswith("http://127.0.0.1:")
        or base.startswith("http://localhost:")
    )


def get_health(base: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        base.rstrip("/") + "/healthz",
        headers={
            "accept": "application/json",
            "user-agent": "viridis-regulatory-radar-seat-bridge-probe/1.0",
        },
    )
    try:
        response = urllib.request.urlopen(request, timeout=20)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        payload = json.load(response)
        status = int(response.status)
    require(isinstance(payload, dict), "health did not return an object")
    return status, payload


def _runtime_module(path: Path) -> Any:
    require(path.is_file(), "candidate x402_http.py is missing")
    sys.path.insert(0, str(path.parent))
    module = importlib.import_module("x402_http")
    require(
        Path(module.__file__).resolve() == path.resolve(),
        "runtime imported x402_http from an unexpected path",
    )
    return module


def _require_health(base: str) -> dict[str, Any]:
    require(_loopback(base), "seat-bridge probe refuses non-loopback URLs")
    http_status, health = get_health(base)
    require(
        http_status in {200, 503},
        f"health returned unexpected HTTP {http_status}",
    )
    require(health.get("mount_errors") == {}, "gateway has mount errors")
    persistence = health.get("persistence", {})
    require(persistence.get("available") is True, "persistence unavailable")
    require(persistence.get("errors") == {}, "persistence has errors")
    agents = health.get("agents", {})
    require(isinstance(agents, dict), "health agents is not an object")
    require(len(agents) == 27, f"expected 27 agents, found {len(agents)}")

    x402 = health.get("payment_gate", {}).get("x402", {})
    require(x402.get("enabled") is False, "candidate payment rail is enabled")
    require(x402.get("errors") == {}, "candidate payment rail has errors")
    radar = [
        route
        for route in x402.get("http_front_door", [])
        if route.get("agent") == "regulatory-radar"
        and route.get("tool") == "scan_regulations"
    ]
    require(len(radar) == 1, "Regulatory Radar route is missing or duplicated")
    require(
        str(radar[0].get("amount_atomic_usdc")) == "250000",
        "Regulatory Radar list price is not $0.25",
    )

    status = health.get("status")
    if status == "ok":
        require(http_status == 200, "healthy gateway did not return HTTP 200")
        health_mode = "fully_healthy"
    else:
        require(status == "degraded", "gateway health is neither ok nor degraded")
        require(http_status == 503, "degraded gateway did not return HTTP 503")
        unhealthy = {
            name: details
            for name, details in agents.items()
            if isinstance(details, dict)
            and details.get("status") not in {"ok", "healthy"}
        }
        require(
            set(unhealthy) == {"hive"},
            "credential-free candidate has unexpected degraded agents",
        )
        hive = unhealthy["hive"]
        checks = hive.get("checks", {})
        require(
            hive.get("status") == "degraded"
            and checks.get("solver_provider_ready") is False
            and checks.get("wired_dependencies_ready") is True,
            "Hive degradation is not the exact missing-provider condition",
        )
        health_mode = "expected_missing_hive_provider"

    return {
        "http_status": http_status,
        "gateway_status": status,
        "health_mode": health_mode,
        "agent_count": len(agents),
        "payment_enabled": False,
        "radar_amount_atomic_usdc": 250000,
    }


def probe(
    base: str,
    *,
    module: Any | None = None,
    x402_http_path: Path = X402_HTTP_PATH,
    payment_gate_path: Path = PAYMENT_GATE_PATH,
    expected_x402_http_sha256: str = EXPECTED_X402_HTTP_SHA256,
    expected_payment_gate_sha256: str = EXPECTED_PAYMENT_GATE_SHA256,
) -> dict[str, Any]:
    health = _require_health(base)
    require(x402_http_path.is_file(), "candidate x402_http.py is missing")
    require(payment_gate_path.is_file(), "candidate payment_gate.py is missing")
    require(
        _sha256(x402_http_path) == expected_x402_http_sha256,
        "candidate x402_http.py digest mismatch",
    )
    require(
        _sha256(payment_gate_path) == expected_payment_gate_sha256,
        "candidate payment_gate.py digest mismatch",
    )
    runtime = module or _runtime_module(x402_http_path)

    seat = runtime.seat_option(
        "regulatory-radar", "https://mcp.viridisconservation.com"
    )
    require(seat == EXPECTED_SEAT, "Regulatory Radar seat object changed")

    success = runtime._with_commerce_metadata(
        {"status": "ok"},
        "regulatory-radar",
        "scan_regulations",
        "https://mcp.viridisconservation.com",
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
        "commerce envelope weakened the fresh buyer-authorization boundary",
    )

    failed = runtime._with_commerce_metadata(
        {"status": "error", "error": "probe fixture"},
        "regulatory-radar",
        "scan_regulations",
        "https://mcp.viridisconservation.com",
    )
    require(
        "viridis_commerce" not in failed,
        "failed paid result received commerce metadata",
    )

    hive = runtime._with_commerce_metadata(
        {"status": "ok"},
        "hive",
        "solve",
        "https://mcp.viridisconservation.com",
    )
    require(
        "seat_option" not in hive.get("viridis_commerce", {}),
        "uncovered Hive route received a Compliance Seat offer",
    )

    return {
        "status": "ok",
        "mode": "regulatory_radar_seat_bridge",
        **health,
        "x402_http_sha256": expected_x402_http_sha256,
        "payment_gate_sha256": expected_payment_gate_sha256,
        "seat_option": seat,
        "failed_result_enriched": False,
        "uncovered_agent_seat_option": False,
        "paid_route_called": False,
        "payment_signed": False,
        "checkout_opened": False,
        "subscription_mutated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8402")
    args = parser.parse_args()
    try:
        result = probe(args.base)
    except Exception as exc:
        print(json.dumps({
            "status": "failed",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
