#!/usr/bin/env python3
"""Fail-closed loopback probe for the Wu Wei Router v2 release.

Initial mode performs bounded writes only against a copied candidate database.
Restart mode is read-only and proves that v2 receipts survived a restart.
The probe refuses non-loopback URLs and has no payment-signing capability.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from typing import Any


EXPECTED_TOOLS = {
    "create_agent", "submit_evaluation", "get_agent", "list_agents",
    "best_next_steps", "get_ledger", "export_state", "import_state",
    "delete_agent", "register_compute_profile", "route_task",
    "record_route_outcome", "compute_efficiency_report", "describe_agent",
}
POLICY = "wu-wei-router-v2"


class ProbeFailure(RuntimeError):
    """A release invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeFailure(message)


def _loopback(base: str) -> bool:
    return (
        base.startswith("http://127.0.0.1:")
        or base.startswith("http://localhost:")
    )


def _decode_sse(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8")
    if text.lstrip().startswith("{"):
        document = json.loads(text)
        require("error" not in document, f"MCP protocol error: {document}")
        require("result" in document, "MCP response contained no result")
        return document["result"]
    payloads = [
        line[5:].strip() for line in text.splitlines()
        if line.startswith("data:")
    ]
    require(bool(payloads), "MCP response contained no data event")
    document = json.loads(payloads[-1])
    require("error" not in document, f"MCP protocol error: {document}")
    require("result" in document, "MCP response contained no result")
    return document["result"]


def _request(url: str, *, data: bytes | None = None) -> bytes:
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
            "user-agent": "viridis-wu-wei-router-v2-probe/1.0",
        },
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        require(response.status == 200, f"{url} returned {response.status}")
        return response.read()


def get_json(base: str, path: str) -> dict[str, Any]:
    document = json.loads(_request(base + path))
    require(isinstance(document, dict), f"{path} did not return an object")
    return document


def mcp(base: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
    }).encode("utf-8")
    return _decode_sse(_request(base + "/neurogenesis/mcp", data=body))


def tools(base: str) -> set[str]:
    result = mcp(base, "tools/list", {})
    return {tool["name"] for tool in result.get("tools", [])}


def call(base: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = mcp(base, "tools/call", {
        "name": name, "arguments": arguments,
    })
    content = result.get("content", [])
    require(content and content[0].get("type") == "text",
            f"{name} returned no text content")
    document = json.loads(content[0]["text"])
    require(document.get("status") == "ok", f"{name} failed: {document}")
    return document["data"]


def health_gate(base: str) -> dict[str, Any]:
    health = get_json(base, "/healthz")
    require(health.get("status") == "ok", "gateway health is not ok")
    require(health.get("mount_errors") == {}, "gateway has mount errors")
    persistence = health.get("persistence", {})
    require(persistence.get("available") is True, "persistence unavailable")
    require(persistence.get("errors") == {}, "persistence has errors")
    agents = health.get("agents", {})
    require(len(agents) == 28, f"expected 28 hosted agents, got {len(agents)}")
    neuro = agents.get("neurogenesis", {})
    require(neuro.get("status") == "ok", "Neurogenesis is not healthy")
    require(neuro.get("version") == "0.2.0",
            f"Neurogenesis version is {neuro.get('version')}")
    require(neuro.get("checks", {}).get("wu_wei_policy") == POLICY,
            "Wu Wei v2 policy is absent from health")
    return health


def initial_probe(base: str) -> dict[str, Any]:
    health_gate(base)
    found = tools(base)
    require(found == EXPECTED_TOOLS,
            f"Neurogenesis tool mismatch: {sorted(found)}")
    request_prefix = "wu-wei-candidate-20260809"
    profiles = [
        {
            "id": "candidate-local", "execution_mode": "local",
            "quality_score": 0.85, "reliability_score": 0.96,
            "cost_per_1k_input_tokens": 0.002,
            "cost_per_1k_output_tokens": 0.004,
            "latency_ms": 300, "max_context_tokens": 128000,
            "local": True, "capabilities": ["analysis"],
            "energy_wh_per_1k_input_tokens": 0.02,
            "energy_wh_per_1k_output_tokens": 0.04,
            "carbon_intensity_g_per_kwh": 40,
        },
        {
            "id": "candidate-cloud", "execution_mode": "cloud",
            "quality_score": 0.9, "reliability_score": 0.99,
            "cost_per_1k_input_tokens": 0.001,
            "cost_per_1k_output_tokens": 0.002,
            "latency_ms": 500, "max_context_tokens": 128000,
            "capabilities": ["analysis"],
            "energy_wh_per_1k_input_tokens": 3.0,
            "energy_wh_per_1k_output_tokens": 5.0,
            "carbon_intensity_g_per_kwh": 400,
        },
    ]
    for index, profile in enumerate(profiles, start=1):
        call(base, "register_compute_profile", {
            "profile": profile,
            "request_id": f"{request_prefix}-profile-{index}",
        })
    route = call(base, "route_task", {
        "task": {
            "id": "candidate-energy-route", "task_type": "analysis",
            "expected_input_tokens": 2000,
            "expected_output_tokens": 500,
            "min_quality": 0.7, "min_reliability": 0.9,
            "required_capabilities": ["analysis"],
            "require_energy_estimate": True, "energy_weight": 10.0,
            "baseline_cost_usd": 0.02,
            "baseline_energy_wh": 10.0,
            "baseline_latency_ms": 1000,
        },
        "request_id": f"{request_prefix}-route-energy",
    })
    require(route.get("policy_version") == POLICY, "wrong route policy")
    require(route.get("profile_id") == "candidate-local",
            f"energy route chose {route.get('profile_id')}")
    require(route.get("execution_mode") == "local", "route is not local")
    require(route.get("quality_floor_honored") is True,
            "quality floor was not honored")
    require(len(str(route.get("decision_sha256") or "")) == 64,
            "decision receipt is not hash-bound")
    deferred = call(base, "route_task", {
        "task": {
            "id": "candidate-defer-route", "task_type": "maintenance",
            "min_quality": 0.7, "allow_defer": True,
            "value_score": 0.01, "defer_below_value": 0.1,
            "urgency": 0.1, "risk": 0.2,
            "baseline_cost_usd": 0.04, "baseline_energy_wh": 4.0,
        },
        "request_id": f"{request_prefix}-route-defer",
    })
    require(deferred.get("execution_mode") == "defer", "defer did not win")
    require(deferred.get("no_result_claimed") is True,
            "defer incorrectly claims a result")
    outcome = call(base, "record_route_outcome", {
        "decision_id": route["decision_id"], "success_score": 0.9,
        "actual_cost_usd": 0.006, "actual_latency_ms": 320,
        "actual_energy_wh": 0.065,
        "notes": "isolated copied-state candidate observation",
        "request_id": f"{request_prefix}-outcome",
    })
    require(outcome.get("decision_sha256") == route["decision_sha256"],
            "outcome is not bound to the decision")
    require(len(str(outcome.get("outcome_sha256") or "")) == 64,
            "outcome receipt is not hash-bound")
    report = call(base, "compute_efficiency_report", {"limit": 50})
    require(report.get("policy_version") == POLICY, "wrong report policy")
    require(report.get("by_mode", {}).get("local", 0) >= 1,
            "report omits local route")
    require(report.get("by_mode", {}).get("defer", 0) >= 1,
            "report omits deferred route")
    require(report.get("observed_outcomes", {}).get("count", 0) >= 1,
            "report omits observed outcome")
    return {
        "status": "ok", "phase": "initial", "policy_version": POLICY,
        "decision_id": route["decision_id"],
        "decision_sha256": route["decision_sha256"],
        "outcome_id": outcome["outcome_id"],
        "outcome_sha256": outcome["outcome_sha256"],
        "selected_profile": route["profile_id"],
        "estimated_energy_wh": route["estimated_energy_wh"],
        "deferred_decision_id": deferred["decision_id"],
    }


def restart_probe(base: str, decision_id: str,
                  outcome_sha256: str) -> dict[str, Any]:
    health_gate(base)
    require(tools(base) == EXPECTED_TOOLS, "tool surface changed on restart")
    report = call(base, "compute_efficiency_report", {"limit": 200})
    decisions = {item["decision_id"]: item
                 for item in report.get("decisions", [])}
    require(decision_id in decisions, "decision did not survive restart")
    outcomes = {item["outcome_sha256"]: item
                for item in report.get("outcomes", [])}
    require(outcome_sha256 in outcomes, "outcome did not survive restart")
    require(outcomes[outcome_sha256]["decision_id"] == decision_id,
            "restored outcome points to the wrong decision")
    return {
        "status": "ok", "phase": "restart", "policy_version": POLICY,
        "decision_id": decision_id, "outcome_sha256": outcome_sha256,
        "persistence_verified": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--phase", choices=("initial", "restart"),
                        required=True)
    parser.add_argument("--decision-id")
    parser.add_argument("--outcome-sha256")
    args = parser.parse_args(argv)
    require(_loopback(args.base), "probe refuses non-loopback URLs")
    if args.phase == "initial":
        result = initial_probe(args.base)
    else:
        require(bool(args.decision_id), "restart requires --decision-id")
        require(bool(args.outcome_sha256),
                "restart requires --outcome-sha256")
        result = restart_probe(
            args.base, args.decision_id, args.outcome_sha256)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProbeFailure as exc:
        print(json.dumps({"status": "error", "message": str(exc)},
                         sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
