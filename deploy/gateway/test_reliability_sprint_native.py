from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

import viridis_mcp_gateway as gateway


HERE = Path(__file__).resolve().parent


def test_gateway_natively_serves_the_flagship_conversion_path(
        tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DB", str(tmp_path / "gateway.db"))
    old_members = gateway.EXTERNAL_MEMBERS
    gateway.EXTERNAL_MEMBERS = []
    try:
        with TestClient(gateway.build_app()) as client:
            page = client.get("/reliability-sprint")
            health = client.get("/healthz")
            directory = client.get("/")
            llms = client.get("/llms.txt")
            sitemap = client.get("/sitemap.xml")
    finally:
        gateway.EXTERNAL_MEMBERS = old_members

    assert page.status_code == 200
    assert "Bring one fragile workflow" in page.text
    assert (
        'href="https://mcp.viridisconservation.com/reliability-sprint"'
        in page.text)
    assert page.headers["x-frame-options"] == "DENY"
    assert (
        "https://mcp.viridisconservation.com/reliability-sprint"
        in llms.text)
    assert (
        "<loc>https://mcp.viridisconservation.com/reliability-sprint</loc>"
        in sitemap.text)
    assert health.json()["human_surfaces"]["reliability_sprint"].endswith(
        "/reliability-sprint")
    assert directory.json()["human_surfaces"]["reliability_sprint"] == {
        "endpoint": "/reliability-sprint",
        "description": (
            "Fixed-scope production-readiness service for one existing "
            "AI-agent or automation workflow"),
        "money_movement": False,
    }
    assert (
        "COPY deploy/gateway/reliability_sprint.html deploy/gateway/"
        in (HERE / "Dockerfile").read_text())
