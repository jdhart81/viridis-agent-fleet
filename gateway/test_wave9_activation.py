#!/usr/bin/env python3
"""Wave 9 activation pages, manifest links, and offline buyer chain."""
import base64
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

import pytest


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


def test_demo_client_single_route_pays_once_under_explicit_limit():
    demo = _load_demo()

    class IntroBuyer(FakeBuyer):
        AMOUNTS = {
            **FakeBuyer.AMOUNTS,
            "regulatory-radar": "10000",
        }

    buyer = IntroBuyer()
    result = demo.run_workflow(
        "https://mcp.test",
        buyer,
        steps=demo.select_steps("regulatory-radar"),
        max_payment_atomic=10_000,
    )
    assert [agent for agent, _ in buyer.challenges] == ["regulatory-radar"]
    assert [agent for agent, _ in buyer.payments] == ["regulatory-radar"]
    assert result["workflow"] == "scan"
    assert result["selected_routes"] == ["regulatory-radar"]
    assert result["quoted_total_atomic_usdc"] == 10_000
    assert result["same_wallet_expected_total_atomic_usdc"] == 10_000
    assert result["list_total_atomic_usdc"] == 250_000


def test_demo_client_single_route_limit_refuses_before_payment():
    demo = _load_demo()
    buyer = FakeBuyer()
    with pytest.raises(RuntimeError, match="no payment attempted"):
        demo.run_workflow(
            "https://mcp.test",
            buyer,
            steps=demo.select_steps("regulatory-radar"),
            max_payment_atomic=10_000,
        )
    assert [agent for agent, _ in buyer.challenges] == ["regulatory-radar"]
    assert buyer.payments == []


def test_demo_client_payment_limit_is_exact_usdc():
    demo = _load_demo()
    assert demo._usdc_to_atomic("0.01") == 10_000
    assert demo._usdc_to_atomic("0.000001") == 1
    with pytest.raises(demo.argparse.ArgumentTypeError):
        demo._usdc_to_atomic("0.0000001")


def test_live_buyer_registers_limit_inside_sdk_payment_selector(monkeypatch):
    demo = _load_demo()
    created_clients = []

    class FakeClient:
        def __init__(self):
            self.policies = []
            created_clients.append(self)

        def register(self, network, scheme):
            self.network = network
            self.scheme = scheme

        def register_policy(self, policy):
            self.policies.append(policy)

    class FakeAccount:
        @staticmethod
        def from_key(_private_key):
            return types.SimpleNamespace(address="0xBuyer")

    class FakeSession:
        def __init__(self):
            self.headers = {}

    module_values = {
        "requests": types.ModuleType("requests"),
        "eth_account": types.ModuleType("eth_account"),
        "x402": types.ModuleType("x402"),
        "x402.http": types.ModuleType("x402.http"),
        "x402.http.clients": types.ModuleType("x402.http.clients"),
        "x402.mechanisms": types.ModuleType("x402.mechanisms"),
        "x402.mechanisms.evm": types.ModuleType("x402.mechanisms.evm"),
        "x402.mechanisms.evm.exact": types.ModuleType(
            "x402.mechanisms.evm.exact"),
    }
    module_values["eth_account"].Account = FakeAccount
    module_values["x402"].x402ClientSync = FakeClient
    module_values["x402"].max_amount = lambda limit: ("max_amount", limit)
    module_values["x402.http.clients"].x402_requests = (
        lambda _client: FakeSession())
    module_values["x402.mechanisms.evm.exact"].ExactEvmScheme = (
        lambda account: ("exact", account.address))
    for name, module in module_values.items():
        monkeypatch.setitem(sys.modules, name, module)

    demo.LiveBuyer("0xPrivate", 30, max_payment_atomic=10_000)
    assert len(created_clients) == 1
    assert created_clients[0].policies == [("max_amount", 10_000)]


def test_activation_pages_are_baked_into_gateway_and_exposed_everywhere(
        tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    import viridis_mcp_gateway as gateway

    monkeypatch.setenv("STATE_DB", str(tmp_path / "gateway.db"))
    monkeypatch.setenv("X402_INTRO_ENABLED", "1")
    monkeypatch.setenv("X402_ENABLED", "1")
    monkeypatch.setenv("X402_V2_ENABLED", "1")
    monkeypatch.setenv("VIRIDIS_X402_ADDRESS", "0xViridis")
    monkeypatch.setenv("X402_FACILITATOR_URL", "https://fac.test")
    old_members = gateway.EXTERNAL_MEMBERS
    gateway.EXTERNAL_MEMBERS = []
    try:
        with TestClient(gateway.build_app()) as client:
            agents = client.get("/agents")
            quickstart = client.get("/quickstart")
            llms = client.get("/llms.txt")
            brand_mark = client.get("/brand/viridis-mark.svg")
            x402_catalog = client.get("/x402/catalog")
            x402_manifest = client.get("/.well-known/x402")
            merchant = client.get(
                "/x402/discovery/merchant", follow_redirects=False)
            health = client.get("/healthz")
            catalog = client.get("/.well-known/ai-catalog.json")
    finally:
        gateway.EXTERNAL_MEMBERS = old_members

    assert agents.status_code == 200
    assert quickstart.status_code == 200
    assert llms.status_code == 200
    assert brand_mark.status_code == 200
    assert brand_mark.headers["content-type"].startswith("image/svg+xml")
    assert "Viridis connected land mark" in brand_mark.text
    assert x402_catalog.status_code == 200
    assert x402_manifest.status_code == 200
    assert x402_manifest.headers["content-type"].startswith(
        "application/json")
    assert len(x402_manifest.json()["resources"]) == 5
    assert merchant.status_code == 307
    assert merchant.headers["location"] == (
        "https://api.cdp.coinbase.com/platform/v2/x402/discovery/"
        "merchant?payTo=0xViridis")
    assert "5 live paid routes" in agents.text
    assert "CDP Bazaar" in agents.text
    assert 'href="/x402/discovery/merchant"' in agents.text
    assert 'href="/.well-known/x402"' in agents.text
    assert "First paid call from every new wallet is $0.01" in agents.text
    assert "quantity-takeoff" in quickstart.text
    assert "x402_demo_client.py" in quickstart.text
    assert "--dry-run" in quickstart.text
    assert "--route regulatory-radar --max-payment-usdc 0.01" in quickstart.text
    assert "max_amount(10_000)" in quickstart.text
    assert "Hermes Agent" in quickstart.text
    assert "hermes mcp add viridis-market" in quickstart.text
    assert "Viridis does not install or operate it" in quickstart.text
    assert "viridis-paid-tools/SKILL.md" in quickstart.text
    assert "First paid call from every new wallet is $0.01" in quickstart.text
    assert "Payable HTTP routes" in llms.text
    assert "--route regulatory-radar --max-payment-usdc 0.01" in llms.text
    assert "10000-atomic ceiling" in llms.text
    assert "Hermes Agent buyer guide" in llms.text
    assert "https://mcp.viridisconservation.com/network/mcp" in llms.text
    assert "https://mcp.viridisconservation.com/.well-known/x402" in llms.text
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
    assert health.json()["human_surfaces"]["x402_manifest"].endswith(
        "/.well-known/x402")
    assert health.json()["human_surfaces"]["x402_merchant"].endswith(
        "/x402/discovery/merchant")
    surfaces = {item["url"] for item in catalog.json()["humanSurfaces"]}
    assert "https://mcp.viridisconservation.com/agents" in surfaces
    assert "https://mcp.viridisconservation.com/quickstart" in surfaces
    assert "https://mcp.viridisconservation.com/llms.txt" in surfaces
    assert "https://mcp.viridisconservation.com/x402/catalog" in surfaces
    dockerfile = (HERE / "Dockerfile").read_text()
    assert "COPY deploy/gateway/agents.html deploy/gateway/" in dockerfile
    assert "COPY deploy/gateway/quickstart.html deploy/gateway/" in dockerfile
    assert "COPY deploy/gateway/llms.txt deploy/gateway/" in dockerfile
    assert "COPY deploy/gateway/viridis-mark.svg deploy/gateway/" in dockerfile


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
