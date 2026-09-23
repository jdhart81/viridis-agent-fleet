#!/usr/bin/env python3
"""Verify the Reliability Sprint overlay without authorizing payment or work."""
from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


EXPECTED_ROUTES = [
    ("disclosure-compiler", "compile_disclosure", 200),
    ("ghg-ledger", "calculate_inventory", 100),
    ("hive", "solve", 500),
    ("quantity-takeoff", "calculate_takeoff", 50),
    ("regulatory-radar", "monitor_changes", 25),
    ("regulatory-radar", "scan_regulations", 25),
    ("security-preflight", "security_preflight", 100),
    ("taxcredit-engine", "calculate_tax_credit", 200),
]


def fetch(base: str, path: str) -> tuple[int, str]:
    request = Request(base.rstrip("/") + path, method="GET")
    try:
        with urlopen(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as error:
        return error.code, error.read().decode("utf-8")


def post(base: str, path: str, payload: dict) -> dict:
    request = Request(
        base.rstrip("/") + path,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )
    with urlopen(request, timeout=20) as response:
        assert response.status == 200
        return json.loads(response.read())


def workflow(**updates) -> dict:
    result = {
        "delivery_shape": "INTEGRATED_WORKFLOW",
        "runs_per_month": 40,
        "minutes_per_run": 30,
        "loaded_hourly_cost_minor": 8000,
        "monthly_error_cost_minor": 40000,
        "implementation_budget_minor": 99500,
        "monthly_operating_cost_minor": 14900,
        "target_payback_months": 6,
        "systems": ["HubSpot", "Gmail"],
        "data_access_ready": True,
        "acceptance_criteria_ready": True,
        "irreversible_actions": ["customer_message"],
        "human_approval_available": True,
    }
    result.update(updates)
    return result


def verify(base: str, *, sanitized: bool) -> dict:
    health_code, health_text = fetch(base, "/healthz")
    health = json.loads(health_text)
    assert health_code == (503 if sanitized else 200)
    assert health["status"] in ({"degraded"} if sanitized else {"ok"})
    assert health["mount_errors"] == {}
    assert health["persistence"]["available"] is True
    assert len(health["agents"]) == 28
    if sanitized:
        assert {
            name for name, item in health["agents"].items()
            if item.get("status") != "ok"
        } <= {"hive"}
    else:
        assert all(item.get("status") == "ok" for item in health["agents"].values())

    _, agents = fetch(base, "/agents")
    assert "Make one existing AI workflow reliable enough to ship" in agents
    assert "The fleet is the delivery engine" in agents
    assert "href=\"/reliability-sprint#fit-check\"" in agents
    assert "no buyer order" in agents

    _, offer = fetch(base, "/reliability-sprint?source=release-probe")
    assert "Bring one fragile workflow" in offer
    assert "$995 introductory fixed price" in offer
    assert "five-business-day delivery target" in offer
    assert "Do not enter credentials" in offer

    _, robots = fetch(base, "/robots.txt")
    assert "Sitemap: https://mcp.viridisconservation.com/sitemap.xml" in robots
    _, sitemap = fetch(base, "/sitemap.xml")
    assert "https://mcp.viridisconservation.com/reliability-sprint" in sitemap
    _, llms = fetch(base, "/llms.txt")
    assert llms.startswith("# Viridis Agent Reliability Sprint")
    assert "# Viridis autonomous carbon and compliance agents" in llms
    assert "{{INTRO_STATUS}}" not in llms

    _, catalog_text = fetch(base, "/x402/catalog")
    catalog = json.loads(catalog_text)
    signature = sorted(
        (item["agent"], item["tool"], item["price_minor"])
        for item in catalog["routes"]
    )
    assert signature == EXPECTED_ROUTES

    objective = "Qualify inbound leads and prepare a reviewed CRM follow-up"
    build = post(base, "/x402/decide", {
        "decision_type": "WORKFLOW", "objective": objective,
        "workflow": workflow(),
    })
    assert build["decision"] == "BUILD"
    assert build["sprint"]["list_price_minor"] == 99500

    decline = post(base, "/x402/decide", {
        "decision_type": "WORKFLOW", "objective": objective,
        "workflow": workflow(implementation_budget_minor=50000),
    })
    assert decline["decision"] == "DO_NOT_AUTOMATE"

    needs_input = post(base, "/x402/decide", {
        "decision_type": "WORKFLOW", "objective": objective,
        "workflow": workflow(data_access_ready=False),
    })
    assert needs_input["decision"] == "NEEDS_INPUT"

    buy = post(base, "/x402/decide", {
        "decision_type": "WORKFLOW",
        "objective": "Find applicable climate compliance requirements",
        "inputs": {"jurisdiction": "US"},
        "max_price_minor": 25,
        "workflow": workflow(
            delivery_shape="SINGLE_RESULT", systems=["API"],
        ),
    })
    assert buy["decision"] == "BUY"

    for result in (build, decline, needs_input, buy):
        assert result["money_moved"] is False
        assert result["payment_authorized"] is False
        assert result["tool_executed"] is False

    return {
        "status": "pass",
        "base": base,
        "health": health["status"],
        "agents": len(health["agents"]),
        "route_price_signature": signature,
        "workflow_decisions": [
            build["decision"], decline["decision"],
            needs_input["decision"], buy["decision"],
        ],
        "money_moved": False,
        "payment_authorized": False,
        "tool_executed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("--sanitized", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(args.base, sanitized=args.sanitized), indent=2))


if __name__ == "__main__":
    main()
