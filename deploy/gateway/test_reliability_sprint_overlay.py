from __future__ import annotations

import sys
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import reliability_sprint_overlay as overlay  # noqa: E402


async def base_health(request):
    return JSONResponse({"status": "exact-base", "state": "unchanged"})


def app():
    base = Starlette(routes=[Route("/healthz", base_health)])
    page = (HERE / "reliability_sprint.html").read_text(encoding="utf-8")
    llms = (HERE / "reliability_sprint_llms_intro.txt").read_text(
        encoding="utf-8") + "\n\n# Exact live base catalog\n"
    return overlay.ReliabilitySprintOverlay(
        base, page_html=page, llms_text=llms,
        public_base="https://mcp.test")


def qualifying_workflow():
    return {
        "decision_type": "WORKFLOW",
        "objective": (
            "Qualify inbound leads and prepare a reviewed CRM follow-up"
        ),
        "workflow": {
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
        },
    }


def test_human_offer_is_outcome_first_and_claim_bounded():
    with TestClient(app()) as client:
        response = client.get("/reliability-sprint?source=discord")
    assert response.status_code == 200
    assert "Bring one fragile workflow" in response.text
    assert "$995 introductory fixed price" in response.text
    assert "no buyer order" in response.text
    assert "Do not enter credentials" in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"


def test_free_fit_check_returns_build_without_side_effect_claims():
    with TestClient(app()) as client:
        response = client.post("/x402/decide", json=qualifying_workflow())
    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "BUILD"
    assert payload["sprint"]["existing_profile_id"] == "viridis-mcp-delivery"
    assert payload["money_moved"] is False
    assert payload["payment_authorized"] is False
    assert payload["offer_submitted"] is False
    assert payload["work_started"] is False
    assert response.headers["cache-control"] == "no-store"


def test_new_routes_do_not_replace_exact_base_routes():
    with TestClient(app()) as client:
        health = client.get("/healthz")
        wrong_page_method = client.post("/reliability-sprint")
        wrong_decision_method = client.put("/x402/decide")
    assert health.json() == {"status": "exact-base", "state": "unchanged"}
    assert wrong_page_method.status_code == 405
    assert wrong_decision_method.status_code == 405
    assert wrong_decision_method.json()["money_moved"] is False


def test_crawl_surfaces_name_the_buyer_offer():
    with TestClient(app()) as client:
        robots = client.get("/robots.txt")
        sitemap = client.get("/sitemap.xml")
        llms = client.get("/llms.txt")
    assert robots.status_code == 200
    assert "Sitemap: https://mcp.test/sitemap.xml" in robots.text
    assert "https://mcp.test/reliability-sprint" in sitemap.text
    assert "https://mcp.test/agents" in sitemap.text
    assert "Viridis Agent Reliability Sprint" in llms.text
    assert "Exact live base catalog" in llms.text


def test_supporting_surfaces_point_to_one_primary_offer():
    agents = (HERE / "agents_reliability_sprint.html").read_text(
        encoding="utf-8")
    llms = (HERE / "reliability_sprint_llms_intro.txt").read_text(
        encoding="utf-8")
    dockerfile = (HERE /
                  "Dockerfile.reliability-sprint-conversion-20260821").read_text(
                      encoding="utf-8")
    assert "href=\"/reliability-sprint#fit-check\"" in agents
    assert "The fleet is the delivery engine" in agents
    assert "Primary buyer outcome" in llms
    assert "https://mcp.viridisconservation.com/reliability-sprint" in llms
    assert "viridis_mcp_gateway.py" not in dockerfile
    assert "reliability_sprint_overlay.py" in dockerfile
    assert "value_decision.py" in dockerfile
