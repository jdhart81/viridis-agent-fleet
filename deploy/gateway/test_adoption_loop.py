"""ADOPT-1..5: one-entry agent adoption contract."""
import asyncio
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import adoption_loop  # noqa: E402


class Request:
    def __init__(self, body=None, *, method="POST", query=None):
        self._body = body
        self.method = method
        self.query_params = query or {}

    async def json(self):
        return self._body


def run(handler, request):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(handler(request))
    finally:
        loop.close()


def body(response):
    return json.loads(response.body.decode("utf-8"))


def test_ready_plan_returns_one_complete_integration_contract():
    plan = adoption_loop.build_adoption_plan(
        "https://mcp.test",
        "Monitor regulatory changes and compliance deadlines",
        inputs={
            "jurisdiction": "US",
            "topics": ["emissions"],
            "lookback_days": 90,
        },
        max_price_minor=25,
    )
    assert plan["decision"] == "READY_FOR_QUOTE"
    assert plan["money_moved"] is False
    assert plan["payment_authorized"] is False
    assert plan["tool_executed"] is False
    assert plan["state_persisted"] is False
    integration = plan["integration"]
    assert integration["route"] == "regulatory-radar/monitor_changes"
    assert integration["quote_request"] == {
        "method": "POST",
        "url": (
            "https://mcp.test/x402/regulatory-radar/monitor_changes"),
        "headers": {
            "content-type": "application/json",
            "x-viridis-acquisition-source": (
                "one finite caller-declared integration label"),
        },
        "body": {
            "jurisdiction": "US",
            "topics": ["emissions"],
            "lookback_days": 90,
        },
        "expected_unpaid_status": 402,
        "authoritative_price_source": "PAYMENT-REQUIRED response",
    }
    assert integration["delivery_contract"]["version"] == (
        "viridis-paid-delivery-v1")
    assert integration["feedback_contract"]["endpoint"] == (
        "https://mcp.test/x402/feedback")
    assert integration["feedback_contract"]["exactly_once"] is True
    assert integration["feedback_contract"]["independently_verified"] is False
    assert plan["next_action"]["action"] == "fetch_unpaid_quote"


def test_missing_input_plan_names_only_the_buyer_gap():
    plan = adoption_loop.build_adoption_plan(
        "https://mcp.test",
        "Scan climate compliance regulations",
        inputs={},
        max_price_minor=25,
    )
    assert plan["decision"] == "NEEDS_INPUT"
    assert plan["integration"]["route"] == (
        "regulatory-radar/scan_regulations")
    assert plan["next_action"] == {
        "action": "supply_missing_inputs_or_change_budget",
        "missing_buyer_inputs": ["jurisdiction"],
        "payment_authorized": False,
    }


def test_no_match_never_manufactures_an_integration():
    plan = adoption_loop.build_adoption_plan(
        "https://mcp.test", "Book a flight and hotel", inputs={})
    assert plan["decision"] == "NO_MATCH"
    assert "integration" not in plan
    assert plan["next_action"]["catalog"].endswith("/x402/catalog")


def test_http_and_discovery_contracts_are_stable_and_read_only():
    handler = adoption_loop.make_adoption_route("https://mcp.test")
    response = run(handler, Request({
        "objective": "Calculate a Scope 1 greenhouse gas inventory",
        "inputs": {"activities": []},
        "max_price_minor": 100,
    }))
    assert response.status_code == 200
    assert body(response)["decision"] == "READY_FOR_QUOTE"
    assert body(response)["integration"]["route"] == (
        "ghg-ledger/calculate_inventory")

    rejected = run(handler, Request({
        "objective": "Calculate an inventory",
        "inputs": {"activities": []},
        "auto_pay": True,
    }))
    assert rejected.status_code == 400
    assert body(rejected)["decision"] == "INVALID_REQUEST"
    assert body(rejected)["payment_authorized"] is False

    discovery = adoption_loop.adoption_discovery("https://mcp.test")
    assert discovery["endpoint"] == "https://mcp.test/adopt"
    assert discovery["price_minor"] == 0
    assert discovery["state_changing"] is False
    assert discovery["decisions"] == [
        "READY_FOR_QUOTE", "NEEDS_INPUT", "BUDGET_TOO_LOW", "NO_MATCH",
    ]


def test_gateway_exposes_adoption_across_machine_surfaces(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    import viridis_mcp_gateway as gateway

    monkeypatch.setenv("STATE_DB", str(tmp_path / "gateway.db"))
    old_members = gateway.EXTERNAL_MEMBERS
    gateway.EXTERNAL_MEMBERS = []
    try:
        with TestClient(gateway.build_app()) as client:
            plan = client.post("/adopt", json={
                "objective": "Monitor regulatory changes and deadlines",
                "inputs": {
                    "jurisdiction": "US",
                    "topics": ["emissions"],
                    "lookback_days": 90,
                },
                "max_price_minor": 25,
            })
            discovery = client.get(
                "/.well-known/agent-adoption.json").json()
            catalog = client.get("/x402/catalog").json()
            manifest = client.get("/.well-known/x402.json").json()
            health = client.get("/healthz").json()
            card = client.get("/.well-known/agent-card.json").json()
            openapi = client.get("/openapi.json").json()
    finally:
        gateway.EXTERNAL_MEMBERS = old_members

    assert plan.status_code == 200
    assert plan.json()["decision"] == "READY_FOR_QUOTE"
    assert discovery["spec_version"] == "viridis-adoption-v1"
    assert catalog["adoption"] == discovery
    assert manifest["adoption_support"] == discovery
    assert health["human_surfaces"]["adoption"].endswith("/adopt")
    assert health["human_surfaces"]["buyer_feedback"].endswith(
        "/x402/feedback")
    assert card["metadata"]["viridis.adoption"] == discovery
    assert "/adopt" in openapi["paths"]
    assert "/x402/feedback" in openapi["paths"]
    dockerfile = (HERE / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY deploy/gateway/adoption_loop.py deploy/gateway/" in dockerfile
