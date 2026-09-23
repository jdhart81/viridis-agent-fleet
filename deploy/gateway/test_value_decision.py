"""VD1-VD6: the free agent-to-agent value-decision contract."""
import asyncio
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import a2a_commerce  # noqa: E402
import value_decision  # noqa: E402
import x402_http  # noqa: E402


class FakeRequest:
    def __init__(self, *, method="POST", body=None, query=None):
        self.method = method
        self._body = body
        self.query_params = query or {}

    async def json(self):
        return self._body


def call(handler, request):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(handler(request))
    finally:
        loop.close()


def payload(response):
    return json.loads(response.body.decode("utf-8"))


def qualifying_workflow(**overrides):
    workflow = {
        "delivery_shape": "INTEGRATED_WORKFLOW",
        "runs_per_month": 40,
        "minutes_per_run": 30,
        "loaded_hourly_cost_minor": 6000,
        "monthly_error_cost_minor": 40000,
        "implementation_budget_minor": 99500,
        "monthly_operating_cost_minor": 14900,
        "target_payback_months": 3,
        "systems": ["CRM", "email"],
        "data_access_ready": True,
        "acceptance_criteria_ready": True,
        "irreversible_actions": ["customer_message"],
        "human_approval_available": True,
    }
    workflow.update(overrides)
    return workflow


def test_value_profiles_cover_exactly_the_shipped_paid_routes():
    assert set(value_decision.VALUE_PROFILES) == set(x402_http.X402_HTTP_TOOLS)
    for agent, tool in x402_http.X402_HTTP_TOOLS:
        contract = value_decision.route_value_contract(agent, tool)
        assert contract["spec_version"] == value_decision.SPEC_VERSION
        assert contract["job_to_be_done"]
        assert contract["expected_outcome"]
        assert contract["not_for"]
        assert contract["proof_contract"] == {
            "quote_authority": "live_unpaid_http_402",
            "paid_transport_receipt": "viridis-paid-delivery-v1",
            "buyer_acceptance": "not_proven_by_seller_receipt",
            "usefulness": "not_proven_by_seller_receipt",
        }


def test_regulatory_deadline_objective_selects_the_repeat_value_route():
    decision = value_decision.build_value_decision(
        "https://mcp.test",
        "Monitor regulatory changes and compliance deadlines",
        inputs={
            "jurisdiction": "US",
            "topics": ["emissions", "climate"],
            "lookback_days": 90,
        },
        max_price_minor=25,
    )
    assert decision["decision"] == "REQUEST_QUOTE"
    assert decision["selected"]["route"] == (
        "regulatory-radar/monitor_changes")
    assert decision["selected"]["input_shape_ready"] is True
    assert decision["selected"]["fresh_quote"] == {
        "endpoint": (
            "https://mcp.test/x402/regulatory-radar/monitor_changes"),
        "method": "POST",
        "authoritative_for_payment": True,
        "payment_header_required_for_preflight": False,
        "payment_authorized_by_this_decision": False,
    }
    assert decision["money_moved"] is False
    assert decision["payment_authorized"] is False
    assert decision["tool_executed"] is False


def test_initial_regulatory_scan_names_the_missing_buyer_input():
    decision = value_decision.build_value_decision(
        "https://mcp.test",
        "Find applicable climate compliance requirements",
        inputs={},
        max_price_minor=25,
    )
    assert decision["decision"] == "NEEDS_INPUT"
    assert decision["selected"]["route"] == (
        "regulatory-radar/scan_regulations")
    assert decision["selected"]["missing_buyer_inputs"] == ["jurisdiction"]
    assert decision["selected"]["input_shape_ready"] is False


def test_invalid_input_shape_never_advances_to_quote():
    decision = value_decision.build_value_decision(
        "https://mcp.test",
        "Scan climate regulations",
        inputs={"jurisdiction": "MARS"},
        max_price_minor=25,
    )
    assert decision["decision"] == "NEEDS_INPUT"
    assert decision["selected"]["missing_buyer_inputs"] == []
    assert decision["selected"]["input_shape_ready"] is False


def test_budget_does_not_substitute_a_cheaper_irrelevant_route():
    decision = value_decision.build_value_decision(
        "https://mcp.test",
        "Run an MCP security preflight on this manifest",
        inputs={"agent_id": "example-agent", "manifest": {"tools": []}},
        max_price_minor=25,
    )
    assert decision["decision"] == "BUDGET_TOO_LOW"
    assert decision["selected"]["route"] == (
        "security-preflight/security_preflight")
    assert decision["selected"]["list_price_minor"] == 100
    assert "No cheaper unrelated route was substituted" in decision["reason"]


def test_unknown_objective_fails_closed_without_a_paid_recommendation():
    decision = value_decision.build_value_decision(
        "https://mcp.test",
        "Book a flight and reserve a hotel",
        inputs={},
        max_price_minor=10_000,
    )
    assert decision["decision"] == "NO_MATCH"
    assert "selected" not in decision
    assert decision["money_moved"] is False


def test_integrated_workflow_builds_existing_reliability_sprint_only():
    decision = value_decision.build_workflow_value_decision(
        "https://mcp.test",
        "Qualify inbound leads and prepare a reviewed CRM follow-up",
        workflow=qualifying_workflow(),
    )
    assert decision["decision"] == "BUILD"
    assert decision["sprint"] == {
        "existing_profile_id": "viridis-mcp-delivery",
        "name": "Viridis Agent Reliability Sprint",
        "list_price_minor": 99500,
        "delivery_business_days": 5,
        "scope": "one workflow and up to two existing systems or APIs",
        "funding_required_before_work": True,
        "funding_evidence": "independently_verified_live_cash_escrow",
        "offer_submitted_by_this_decision": False,
    }
    assert decision["economics"]["gross_monthly_value_minor"] == 160000
    assert decision["economics"]["conservative_monthly_value_minor"] == 80000
    assert decision["economics"]["sprint_payback_months"] == "1.53"
    assert decision["optional_follow_on"]["list_price_minor_per_month"] == 14900
    assert decision["new_agent_created"] is False
    assert decision["offer_submitted"] is False
    assert decision["money_moved"] is False


def test_single_result_buys_existing_route_instead_of_selling_a_sprint():
    decision = value_decision.build_workflow_value_decision(
        "https://mcp.test",
        "Monitor regulatory changes and compliance deadlines",
        workflow=qualifying_workflow(
            delivery_shape="SINGLE_RESULT",
            runs_per_month=10,
            minutes_per_run=15,
            loaded_hourly_cost_minor=6000,
            monthly_error_cost_minor=0,
            implementation_budget_minor=0,
            monthly_operating_cost_minor=0,
            systems=[],
            irreversible_actions=[],
        ),
        inputs={
            "jurisdiction": "US",
            "topics": ["emissions", "climate"],
            "lookback_days": 90,
        },
        max_price_minor=25,
    )
    assert decision["decision"] == "BUY"
    assert decision["sprint_required"] is False
    assert decision["existing_route_decision"]["decision"] == "REQUEST_QUOTE"
    assert decision["existing_route_decision"]["selected"]["route"] == (
        "regulatory-radar/monitor_changes")
    assert decision["economics"]["existing_route_monthly_list_cost_minor"] == 250
    assert decision["payment_authorized"] is False


def test_weak_workflow_economics_fail_closed_without_a_build_recommendation():
    decision = value_decision.build_workflow_value_decision(
        "https://mcp.test",
        "Automate a rare internal summary",
        workflow=qualifying_workflow(
            runs_per_month=1,
            minutes_per_run=10,
            loaded_hourly_cost_minor=3000,
            monthly_error_cost_minor=0,
            monthly_operating_cost_minor=0,
            target_payback_months=6,
            systems=["notes"],
            irreversible_actions=[],
        ),
    )
    assert decision["decision"] == "DO_NOT_AUTOMATE"
    assert decision["blocking_reasons"] == [
        "payback_exceeds_buyer_target"]
    assert decision["work_started"] is False


def test_missing_access_or_approval_returns_needs_input():
    no_access = value_decision.build_workflow_value_decision(
        "https://mcp.test",
        "Automate a recurring CRM workflow",
        workflow=qualifying_workflow(data_access_ready=False),
    )
    assert no_access["decision"] == "NEEDS_INPUT"
    assert no_access["blocking_reasons"] == [
        "data_or_system_access_not_ready"]

    no_approval = value_decision.build_workflow_value_decision(
        "https://mcp.test",
        "Automate a recurring CRM workflow",
        workflow=qualifying_workflow(human_approval_available=False),
    )
    assert no_approval["decision"] == "NEEDS_INPUT"
    assert no_approval["blocking_reasons"] == [
        "irreversible_actions_require_human_approval"]


def test_free_http_handler_supports_post_and_rejects_unknown_fields():
    handler = value_decision.make_value_decision_route("https://mcp.test")
    ok = call(handler, FakeRequest(body={
        "objective": "Calculate a Scope 1 greenhouse gas inventory",
        "inputs": {"activities": []},
        "max_price_minor": 100,
    }))
    assert ok.status_code == 200
    assert payload(ok)["decision"] == "REQUEST_QUOTE"
    assert payload(ok)["selected"]["route"] == (
        "ghg-ledger/calculate_inventory")

    bad = call(handler, FakeRequest(body={
        "objective": "Calculate a Scope 1 greenhouse gas inventory",
        "auto_pay": True,
    }))
    assert bad.status_code == 400
    assert payload(bad)["decision"] == "INVALID_REQUEST"
    assert payload(bad)["payment_authorized"] is False


def test_free_http_handler_supports_workflow_value_decisions():
    handler = value_decision.make_value_decision_route("https://mcp.test")
    response = call(handler, FakeRequest(body={
        "decision_type": "WORKFLOW",
        "objective": "Qualify inbound leads and prepare a reviewed follow-up",
        "workflow": qualifying_workflow(),
    }))
    assert response.status_code == 200
    assert payload(response)["decision"] == "BUILD"
    assert payload(response)["decision_type"] == "WORKFLOW"
    assert payload(response)["offer_submitted"] is False

    discovery = value_decision.decision_discovery("https://mcp.test")
    assert discovery["route_decisions"] == [
        "REQUEST_QUOTE", "NEEDS_INPUT", "BUDGET_TOO_LOW", "NO_MATCH"]
    assert discovery["workflow_decisions"] == [
        "BUY", "BUILD", "DO_NOT_AUTOMATE", "NEEDS_INPUT"]
    assert discovery["reliability_sprint"] == {
        "existing_profile_id": "viridis-mcp-delivery",
        "list_price_minor": 99500,
        "delivery_business_days": 5,
        "new_agent_created": False,
    }


def test_free_http_handler_accepts_json_inputs_on_get():
    handler = value_decision.make_value_decision_route("https://mcp.test")
    response = call(handler, FakeRequest(method="GET", query={
        "objective": "Estimate a 45V tax credit",
        "inputs": json.dumps({"credit": "45V", "facts": {"tax_year": 2026}}),
        "max_price_minor": "200",
    }))
    assert response.status_code == 200
    assert payload(response)["decision"] == "REQUEST_QUOTE"
    assert payload(response)["selected"]["route"] == (
        "taxcredit-engine/calculate_tax_credit")


def test_a2a_card_exposes_value_decision_before_any_paid_task():
    card = a2a_commerce.agent_card("https://mcp.test")
    discovery = card["metadata"]["viridis.valueDecision"]
    assert discovery["endpoint"] == "https://mcp.test/x402/decide"
    assert discovery["price_minor"] == 0
    assert discovery["state_changing"] is False
    assert discovery["payment_signed"] is False
    assert discovery["tool_executed"] is False
    assert len(card["skills"]) == 11
    assert all("valueDecision" in skill["metadata"]
               for skill in card["skills"])


def test_gateway_exposes_decision_across_machine_buyer_surfaces(
        tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    import viridis_mcp_gateway as gateway

    monkeypatch.setenv("STATE_DB", str(tmp_path / "gateway.db"))
    old_members = gateway.EXTERNAL_MEMBERS
    gateway.EXTERNAL_MEMBERS = []
    try:
        with TestClient(gateway.build_app()) as client:
            response = client.post("/x402/decide", json={
                "objective": (
                    "monitor regulatory changes and compliance deadlines"),
                "inputs": {
                    "jurisdiction": "US",
                    "topics": ["emissions", "climate"],
                    "lookback_days": 90,
                },
                "max_price_minor": 25,
            })
            catalog = client.get("/x402/catalog").json()
            manifest = client.get("/.well-known/x402.json").json()
            health = client.get("/healthz").json()
            card = client.get("/.well-known/agent-card.json").json()
            llms = client.get("/llms.txt").text
            buyer_skill = client.get(
                "/.well-known/skills/viridis-paid-tools/SKILL.md").text
    finally:
        gateway.EXTERNAL_MEMBERS = old_members

    assert response.status_code == 200
    assert response.json()["decision"] == "REQUEST_QUOTE"
    assert response.json()["selected"]["route"] == (
        "regulatory-radar/monitor_changes")
    assert response.json()["money_moved"] is False
    assert catalog["value_decision"]["spec_version"] == (
        "viridis-agent-value-decision-v2")
    assert catalog["value_decision"]["endpoint"].endswith("/x402/decide")
    assert all(route["value_decision"]["expected_outcome"]
               for route in catalog["routes"])
    assert manifest["decision_support"]["endpoint"].endswith(
        "/x402/decide")
    assert manifest["decision_support"]["payment_signed"] is False
    assert all(service["value_decision"]["proof_contract"][
        "quote_authority"] == "live_unpaid_http_402"
        for service in manifest["services"])
    assert health["human_surfaces"]["value_decision"].endswith(
        "/x402/decide")
    assert card["metadata"]["viridis.valueDecision"]["endpoint"].endswith(
        "/x402/decide")
    assert "Free value decision before payment" in llms
    assert "https://mcp.viridisconservation.com/x402/decide" in buyer_skill
    dockerfile = (HERE / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY deploy/gateway/value_decision.py deploy/gateway/" in dockerfile
