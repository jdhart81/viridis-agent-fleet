#!/usr/bin/env python3
"""Fail-closed probe for a non-serving, copied-state gateway candidate.

The probe uses only the gateway's loopback HTTP/MCP surfaces.  It never calls
Hive ``solve``, a payment/checkout tool, or any production URL.  Hive and the
production-baseline modes are read-only.  The Subscriptions and Wavefunction
initial phases mutate only the candidate's scratch database so persistence can
be proven across a restart.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.request
from typing import Any


EXPECTED_TOOLS = {
    "hive": {
        "solve", "job_status", "audit_job", "verify_audit",
        "list_solvers", "describe_agent",
    },
    "subscriptions": {
        "list_plans", "get_plan", "create_account",
        "create_checkout_link", "record_subscription",
        "subscription_status", "customer_portal_link", "usage_summary",
        "mrr_summary", "describe_agent",
    },
    "wavefunction": {
        "intake", "collapse", "find_matches", "register_collective",
        "describe_agent",
    },
}

EXPECTED_VERSIONS = {
    "production-baseline": {
        "hive": "0.1.2",
        "subscriptions": "0.1.0",
        "wavefunction": "0.1.1",
    },
    "hive": {
        "hive": "0.1.4",
        "subscriptions": "0.1.0",
        "wavefunction": "0.1.1",
    },
    "subscriptions": {
        "hive": "0.1.2",
        "subscriptions": "0.1.1",
        "wavefunction": "0.1.1",
    },
    "wavefunction": {
        "hive": "0.1.2",
        "subscriptions": "0.1.0",
        "wavefunction": "0.2.0",
    },
}

WAVE_COLLECTIVE = "candidate-climate-20260726"
WAVE_USER = "candidate-buyer-20260726"
PRIVACY_MARKER = "candidate-secret-20260726"


class ProbeFailure(RuntimeError):
    """A release invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeFailure(message)


def _decode_sse(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8")
    payloads = [
        line[5:].strip() for line in text.splitlines()
        if line.startswith("data:")
    ]
    require(bool(payloads), "MCP response contained no data event")
    result = json.loads(payloads[-1])
    require("error" not in result, f"MCP protocol error: {result.get('error')}")
    require("result" in result, "MCP response contained no result")
    return result["result"]


def _request(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> bytes:
    request = urllib.request.Request(
        url, data=data, headers=headers or {}, method="POST" if data else "GET")
    with urllib.request.urlopen(request, timeout=20) as response:
        require(response.status == 200, f"{url} returned HTTP {response.status}")
        return response.read()


def get_json(base: str, path: str = "/healthz") -> dict[str, Any]:
    return json.loads(_request(base + path))


def mcp(base: str, mount: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }).encode("utf-8")
    return _decode_sse(_request(
        f"{base}/{mount}/mcp",
        data=body,
        headers={
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
        },
    ))


def tools(base: str, mount: str) -> set[str]:
    result = mcp(base, mount, "tools/list", {})
    return {tool["name"] for tool in result.get("tools", [])}


def call(base: str, mount: str, name: str, arguments: dict[str, Any]) -> Any:
    result = mcp(base, mount, "tools/call", {
        "name": name,
        "arguments": arguments,
    })
    content = result.get("content", [])
    require(
        content and content[0].get("type") == "text",
        f"{mount}.{name} returned no text content",
    )
    return json.loads(content[0]["text"])


def health_gate(base: str, release: str) -> dict[str, Any]:
    health = get_json(base)
    require(health.get("status") == "ok", "gateway health is not ok")
    require(health.get("mount_errors") == {}, "gateway has mount errors")
    persistence = health.get("persistence", {})
    require(persistence.get("available") is True, "persistence is unavailable")
    require(persistence.get("errors") == {}, "persistence has errors")

    agents = health.get("agents", {})
    require(len(agents) == 27, f"expected 27 agents, found {len(agents)}")
    expected = EXPECTED_VERSIONS[release]
    actual = {
        "hive": agents.get("hive", {}).get("version"),
        "subscriptions": health.get("subscriptions", {}).get("version"),
        "wavefunction": agents.get("wavefunction", {}).get("version"),
    }
    require(actual == expected, f"release isolation mismatch: {actual}")
    return health


def tool_gate(base: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for mount, expected in EXPECTED_TOOLS.items():
        actual = tools(base, mount)
        require(actual == expected, f"{mount} tools mismatch: {sorted(actual)}")
        found[mount] = sorted(actual)
    return found


def probe_hive(base: str, health: dict[str, Any]) -> dict[str, Any]:
    hive = health["agents"]["hive"]
    checks = hive.get("checks", {})
    require(checks.get("rails_mode") == "wired", "Hive rails are not wired")
    require(
        checks.get("wired_dependencies_ready") is True,
        "Hive wired dependencies are not ready",
    )
    require(
        checks.get("solver_provider_ready") is True,
        "Hive provider is not ready",
    )
    require(checks.get("solvers_registered") == 3, "Hive does not have 3 solvers")
    require(checks.get("jobs") == 0, "Hive candidate contains job state")

    described = call(base, "hive", "describe_agent", {})
    pricing = described.get("pricing", {})
    limits = described.get("public_limits", {})
    require(pricing.get("service_price_minor") == 500, "Hive price is not $5")
    require(pricing.get("free_per_day") == 0, "Hive execution free tier is not zero")
    require(
        pricing.get("provider_service_tier") == "default",
        "Hive provider tier is not Standard/default",
    )
    require(
        pricing.get("max_solver_settlement_minor") == 300,
        "Hive solver settlement cap is not $3",
    )
    require(
        pricing.get("max_provider_api_cost_usd") <= 0.175296,
        "Hive provider cost cap increased",
    )
    require(
        pricing.get("minimum_contribution_margin_minor") >= 182,
        "Hive contribution margin fell below $1.82",
    )
    require(
        pricing.get("contribution_margin_bps") >= 3500,
        "Hive contribution margin fell below 35%",
    )
    require(limits.get("max_model_calls") == 24, "Hive model-call cap changed")

    solver_result = call(base, "hive", "list_solvers", {})
    solvers = solver_result.get("data", {}).get("solvers", [])
    require(len(solvers) == 3, "Hive solver listing does not contain 3 workers")
    require(
        all(item.get("kind") == "worker" for item in solvers),
        "Hive public solver pool contains a non-worker",
    )
    return {
        "version": hive["version"],
        "provider_ready": True,
        "solvers": [item["solver_id"] for item in solvers],
        "jobs": 0,
        "price_minor": pricing["service_price_minor"],
        "minimum_margin_minor": pricing["minimum_contribution_margin_minor"],
    }


def _page(base: str, path: str, *, referer: str | None = None) -> None:
    headers = {"referer": referer} if referer else {}
    _request(base + path, headers=headers)


def probe_subscriptions(
    base: str,
    health: dict[str, Any],
    phase: str,
) -> dict[str, Any]:
    before = health["subscriptions"]["frontdoor_funnel"]
    if phase == "initial":
        _page(base, "/agents?source=awesome-x402")
        _page(
            base,
            "/quickstart",
            referer="https://github.com/jdhart81/viridis-agent-fleet",
        )
        _page(
            base,
            f"/agents?source=unknown&private={PRIVACY_MARKER}",
            referer=f"https://untrusted.invalid/{PRIVACY_MARKER}",
        )
    after = get_json(base)["subscriptions"]["frontdoor_funnel"]

    surfaces = after.get("acquisition_surface_views", {})
    sources = after.get("acquisition_source_views", {})
    require(
        after.get("acquisition_classification")
        == "seller_reported_aggregate_telemetry_not_revenue",
        "Subscriptions acquisition classification changed",
    )
    require(
        set(surfaces) == {"agents", "quickstart"},
        "Subscriptions acquisition surfaces changed",
    )
    require(
        set(sources) == {
            "awesome_x402", "meshmcp", "github", "internal",
            "search", "direct", "other",
        },
        "Subscriptions acquisition sources changed",
    )
    if phase != "promotion":
        require(surfaces.get("agents", 0) >= 2, "agents attribution was not recorded")
        require(
            surfaces.get("quickstart", 0) >= 1,
            "quickstart attribution was not recorded",
        )
        require(
            sources.get("awesome_x402", 0) >= 1,
            "awesome_x402 attribution was not recorded",
        )
        require(sources.get("github", 0) >= 1, "GitHub attribution was not recorded")
        require(sources.get("other", 0) >= 1, "unknown source did not map to other")
    if phase == "initial":
        require(
            after.get("landing_page_views", 0)
            == before.get("landing_page_views", 0) + 3,
            "initial attribution probe did not add exactly 3 views",
        )
    else:
        require(after == before, "restart read-only probe mutated attribution")

    plans = call(base, "subscriptions", "list_plans", {})
    require(plans.get("status") == "ok", "Subscriptions list_plans failed")
    return {
        "version": health["subscriptions"]["version"],
        "landing_page_views": after["landing_page_views"],
        "surfaces": surfaces,
        "sources": sources,
        "mrr_minor": after["mrr_minor"],
    }


def probe_wavefunction(
    base: str,
    health: dict[str, Any],
    phase: str,
) -> dict[str, Any]:
    if phase == "promotion":
        described = call(base, "wavefunction", "describe_agent", {})
        require(
            described.get("version") == "0.2.0",
            "Wavefunction describe version is not 0.2.0",
        )
        return {
            "version": described["version"],
            "production_mutation": False,
        }
    if phase == "initial":
        registered = call(base, "wavefunction", "register_collective", {
            "collective_id": WAVE_COLLECTIVE,
            "name": "Candidate Climate Collective",
            "mission": "Execute verified climate action",
            "domain_profile": {"climate": 1.0},
            "constitutional_scores": {
                "c1_biosphere": 0.9,
                "c2_governance": 0.9,
                "c3_transparency": 0.9,
                "c4_long_term": 0.9,
            },
            "capacity": 10,
        })
        require(
            registered == {"status": "ok", "collective_id": WAVE_COLLECTIVE},
            f"Wavefunction registration failed: {registered}",
        )
        intake = call(base, "wavefunction", "intake", {
            "user_id": WAVE_USER,
            "dialogue": [{
                "role": "user",
                "content": "I need verified climate action",
            }],
        })
        require(intake.get("status") == "ok", f"Wavefunction intake failed: {intake}")

    routed = call(base, "wavefunction", "find_matches", {"user_id": WAVE_USER})
    require(routed.get("status") == "ok", f"Wavefunction match failed: {routed}")
    matches = routed.get("matches", [])
    require(
        [item.get("collective_id") for item in matches] == [WAVE_COLLECTIVE],
        f"Wavefunction route was not isolated: {matches}",
    )
    match = matches[0]
    require(
        0.0 <= match.get("alignment_score", -1) <= 1.0,
        "Wavefunction alignment score is outside [0,1]",
    )
    require(
        math.isclose(match.get("constitutional_score", 0), 0.9),
        "Wavefunction constitutional score changed",
    )
    require(
        math.isclose(match.get("routing_probability", 0), 1.0),
        "Wavefunction routing probability is not 1",
    )
    current = get_json(base)["agents"]["wavefunction"]
    require(
        current.get("checks") == {"wavefunctions": 1, "collectives": 1},
        "Wavefunction scratch state counts are wrong",
    )
    return {
        "version": current["version"],
        "collective_id": match["collective_id"],
        "alignment_score": match["alignment_score"],
        "constitutional_score": match["constitutional_score"],
        "combined_score": match["combined_score"],
        "routing_probability": match["routing_probability"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", default="http://127.0.0.1:18402",
        help="loopback-only candidate base URL",
    )
    parser.add_argument(
        "--release", required=True, choices=sorted(EXPECTED_VERSIONS),
    )
    parser.add_argument(
        "--phase", choices=("initial", "restart", "promotion"),
        default="initial",
    )
    args = parser.parse_args()
    base = args.base.rstrip("/")
    if not (
        base.startswith("http://127.0.0.1:")
        or base.startswith("http://localhost:")
    ):
        print(json.dumps({
            "status": "error",
            "message": "probe refuses non-loopback base URLs",
        }))
        return 2

    try:
        health = health_gate(base, args.release)
        found_tools = tool_gate(base)
        if args.release == "hive":
            release_evidence = probe_hive(base, health)
        elif args.release == "subscriptions":
            release_evidence = probe_subscriptions(base, health, args.phase)
        elif args.release == "wavefunction":
            release_evidence = probe_wavefunction(base, health, args.phase)
        else:
            release_evidence = {
                "versions": EXPECTED_VERSIONS["production-baseline"],
            }
        result = {
            "status": "ok",
            "release": args.release,
            "phase": args.phase,
            "base": base,
            "agent_count": len(health["agents"]),
            "versions": EXPECTED_VERSIONS[args.release],
            "tools": found_tools,
            "release_evidence": release_evidence,
        }
    except Exception as exc:
        result = {
            "status": "error",
            "release": args.release,
            "phase": args.phase,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
