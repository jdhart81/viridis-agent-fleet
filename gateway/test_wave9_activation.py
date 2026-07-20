#!/usr/bin/env python3
"""Wave 9 activation pages, manifest links, and offline buyer chain."""
import base64
import importlib.util
import json
import os
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))


def _load_demo():
    path = ROOT / "scripts" / "x402_demo_client.py"
    spec = importlib.util.spec_from_file_location("x402_demo_client", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeBuyer:
    AMOUNTS = {
        "quantity-takeoff": "500000",
        "ghg-ledger": "1000000",
        "disclosure-compiler": "2000000",
        "taxcredit-engine": "2000000",
        "regulatory-radar": "250000",
    }

    def __init__(self):
        self.challenges = []
        self.payments = []

    def _agent(self, url):
        return url.split("/x402/", 1)[1].split("/", 1)[0]

    def challenge(self, url, payload):
        agent = self._agent(url)
        self.challenges.append((agent, payload))
        required = {"x402Version": 2, "accepts": [{
            "scheme": "exact", "network": "eip155:8453",
            "asset": "0xUSDC", "amount": self.AMOUNTS[agent],
            "payTo": "0xViridis",
        }]}
        encoded = base64.b64encode(json.dumps(required).encode()).decode()
        return {"status": 402, "headers": {"PAYMENT-REQUIRED": encoded},
                "body": {"error": "PAYMENT-SIGNATURE required"}}

    def pay(self, url, payload):
        agent = self._agent(url)
        self.payments.append((agent, payload))
        data = {
            "quantity-takeoff": {"audit_sha256": "qt-audit"},
            "ghg-ledger": {"audit_sha256": "ghg-audit",
                           "total_kg_co2e": "123"},
            "disclosure-compiler": {"audit_sha256": "disclosure-audit"},
            "taxcredit-engine": {"credit": "45V",
                                 "audit_sha256": "tax-audit"},
            "regulatory-radar": {"total_regulations": 4},
        }[agent]
        return {"status": 200, "headers": {"PAYMENT-RESPONSE": "receipt"},
                "body": {"status": "ok", "data": data}}


def test_demo_client_offline_fake_gets_five_402s_and_composes_chain(capsys):
    demo = _load_demo()
    buyer = FakeBuyer()
    result = demo.run_workflow("https://mcp.test", buyer, dry_run=False)
    assert len(buyer.challenges) == 5 and len(buyer.payments) == 5
    assert result["quoted_total_atomic_usdc"] == 5750000
    assert result["list_total_atomic_usdc"] == 5750000
    assert result["same_wallet_expected_total_atomic_usdc"] == 5750000
    paid = dict(buyer.payments)
    assert paid["ghg-ledger"]["options"][
        "source_takeoff_audit_sha256"] == "qt-audit"
    assert paid["disclosure-compiler"]["ghg_result"][
        "audit_sha256"] == "ghg-audit"
    assert paid["taxcredit-engine"]["facts"][
        "source_disclosure_audit_sha256"] == "disclosure-audit"
    assert "45V" in paid["regulatory-radar"]["query"]
    assert "HTTP 402" in capsys.readouterr().out


def test_demo_client_dry_run_never_pays():
    demo = _load_demo()
    buyer = FakeBuyer()
    result = demo.run_workflow("https://mcp.test", buyer, dry_run=True)
    assert len(buyer.challenges) == 5 and buyer.payments == []
    assert result["dry_run"] is True
    assert "independent" in result["preflight_note"]


def test_activation_pages_are_baked_into_gateway_and_exposed_everywhere(
        tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    import viridis_mcp_gateway as gateway

    monkeypatch.setenv("STATE_DB", str(tmp_path / "gateway.db"))
    monkeypatch.setenv("X402_INTRO_ENABLED", "1")
    old_members = gateway.EXTERNAL_MEMBERS
    gateway.EXTERNAL_MEMBERS = []
    try:
        with TestClient(gateway.build_app()) as client:
            agents = client.get("/agents")
            quickstart = client.get("/quickstart")
            llms = client.get("/llms.txt")
            x402_catalog = client.get("/x402/catalog")
            health = client.get("/healthz")
            catalog = client.get("/.well-known/ai-catalog.json")
    finally:
        gateway.EXTERNAL_MEMBERS = old_members

    assert agents.status_code == 200
    assert quickstart.status_code == 200
    assert llms.status_code == 200
    assert x402_catalog.status_code == 200
    assert "5 live paid routes" in agents.text
    assert "CDP Bazaar" in agents.text
    assert "First paid call from every new wallet is $0.01" in agents.text
    assert "quantity-takeoff" in quickstart.text
    assert "x402_demo_client.py" in quickstart.text
    assert "--dry-run" in quickstart.text
    assert "First paid call from every new wallet is $0.01" in quickstart.text
    assert "Payable HTTP routes" in llms.text
    assert "First paid call from every new wallet is $0.01" in llms.text
    machine = x402_catalog.json()
    assert machine["spec_version"] == "viridis-x402-catalog-v1"
    assert machine["intro_pricing"]["enabled"] is True
    assert len(machine["routes"]) == 5
    assert {route["agent"] for route in machine["routes"]} == {
        "quantity-takeoff", "ghg-ledger", "disclosure-compiler",
        "taxcredit-engine", "regulatory-radar"}
    assert agents.headers["x-frame-options"] == "DENY"
    assert "x-robots-tag" not in agents.headers
    assert health.status_code == 200
    assert health.json()["human_surfaces"]["agents"].endswith("/agents")
    assert health.json()["human_surfaces"]["quickstart"].endswith(
        "/quickstart")
    assert health.json()["human_surfaces"]["llms_txt"].endswith(
        "/llms.txt")
    assert health.json()["human_surfaces"]["x402_catalog"].endswith(
        "/x402/catalog")
    surfaces = {item["url"] for item in catalog.json()["humanSurfaces"]}
    assert "https://mcp.viridisconservation.com/agents" in surfaces
    assert "https://mcp.viridisconservation.com/quickstart" in surfaces
    assert "https://mcp.viridisconservation.com/llms.txt" in surfaces
    assert "https://mcp.viridisconservation.com/x402/catalog" in surfaces
    dockerfile = (HERE / "Dockerfile").read_text()
    assert "COPY deploy/gateway/agents.html deploy/gateway/" in dockerfile
    assert "COPY deploy/gateway/quickstart.html deploy/gateway/" in dockerfile
    assert "COPY deploy/gateway/llms.txt deploy/gateway/" in dockerfile


def test_activation_copy_tracks_intro_kill_switch(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    import viridis_mcp_gateway as gateway

    monkeypatch.setenv("STATE_DB", str(tmp_path / "gateway-off.db"))
    monkeypatch.setenv("X402_INTRO_ENABLED", "0")
    old_members = gateway.EXTERNAL_MEMBERS
    gateway.EXTERNAL_MEMBERS = []
    try:
        with TestClient(gateway.build_app()) as client:
            agents = client.get("/agents")
            quickstart = client.get("/quickstart")
            llms = client.get("/llms.txt")
    finally:
        gateway.EXTERNAL_MEMBERS = old_members

    for response in (agents, quickstart, llms):
        assert response.status_code == 200
        assert "Intro pricing is currently disabled" in response.text
        assert "First paid call from every new wallet is $0.01" \
            not in response.text
