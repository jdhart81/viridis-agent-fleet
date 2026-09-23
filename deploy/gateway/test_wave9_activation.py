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
        "security-preflight": "1000000",
        "hive": "5000000",
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
            "security-preflight": {
                "verdict": "pass",
                "receipt": {"receipt_id": "vsr_demo"},
            },
            "hive": {
                "job_id": "job-hive-demo",
                "audit_sha256": "hive-audit",
                "synthesis": {"recommendation": "prioritize controls"},
            },
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


def test_demo_client_returning_radar_is_one_list_price_bounded_purchase():
    demo = _load_demo()
    buyer = FakeBuyer()
    result = demo.run_workflow(
        "https://mcp.test",
        buyer,
        steps=demo.select_steps("regulatory-radar"),
        max_payment_atomic=250_000,
    )
    assert [agent for agent, _ in buyer.challenges] == ["regulatory-radar"]
    assert [agent for agent, _ in buyer.payments] == ["regulatory-radar"]
    assert result["selected_routes"] == ["regulatory-radar"]
    assert result["quoted_total_atomic_usdc"] == 250_000
    assert result["list_total_atomic_usdc"] == 250_000


def test_demo_client_hive_route_is_one_fixed_price_bounded_purchase():
    demo = _load_demo()
    buyer = FakeBuyer()
    result = demo.run_workflow(
        "https://mcp.test",
        buyer,
        steps=demo.select_steps("hive"),
        max_payment_atomic=5_000_000,
    )
    assert [agent for agent, _ in buyer.challenges] == ["hive"]
    assert [agent for agent, _ in buyer.payments] == ["hive"]
    payload = buyer.payments[0][1]
    assert payload["budget_minor"] == 500
    assert payload["depth"] == 0
    assert payload["fee_bps"] == 0
    assert payload["redundancy"] == 2
    assert 1 <= len(payload["subtasks"]) <= 4
    assert result["workflow"] == "orchestrate"
    assert result["selected_routes"] == ["hive"]
    assert result["quoted_total_atomic_usdc"] == 5_000_000
    assert result["list_total_atomic_usdc"] == 5_000_000


def test_demo_client_hive_refuses_quote_above_fixed_price_ceiling():
    demo = _load_demo()

    class OverpricedHiveBuyer(FakeBuyer):
        AMOUNTS = {**FakeBuyer.AMOUNTS, "hive": "5000001"}

    buyer = OverpricedHiveBuyer()
    with pytest.raises(RuntimeError, match="no payment attempted"):
        demo.run_workflow(
            "https://mcp.test",
            buyer,
            steps=demo.select_steps("hive"),
            max_payment_atomic=5_000_000,
        )
    assert [agent for agent, _ in buyer.challenges] == ["hive"]
    assert buyer.payments == []


def test_demo_client_advertised_watch_route_is_selectable_and_bounded():
    demo = _load_demo()
    buyer = FakeBuyer()
    result = demo.run_workflow(
        "https://mcp.test",
        buyer,
        steps=demo.select_steps("regulatory-watch"),
        max_payment_atomic=250_000,
    )
    assert [agent for agent, _ in buyer.payments] == ["regulatory-radar"]
    payload = buyer.payments[0][1]
    assert payload == {
        "jurisdiction": "US",
        "topics": ["emissions", "climate"],
        "lookback_days": 90,
    }
    assert result["workflow"] == "watch"
    assert result["list_total_atomic_usdc"] == 250_000


def test_demo_client_security_preflight_dry_run_is_complete_and_never_pays():
    demo = _load_demo()
    buyer = FakeBuyer()
    result = demo.run_workflow(
        "https://mcp.test",
        buyer,
        dry_run=True,
        steps=demo.select_steps("security-preflight"),
    )
    assert [agent for agent, _ in buyer.challenges] == ["security-preflight"]
    assert buyer.payments == []
    payload = buyer.challenges[0][1]
    assert "action" not in payload
    assert payload["agent_id"] == "buyer-security-demo"
    assert payload["manifest"]["tools"][0]["input_schema"][
        "additionalProperties"] is False
    assert payload["policy"]["allowed_tools"] == ["read_status"]
    assert result["workflow"] == "secure"
    assert result["list_total_atomic_usdc"] == 1_000_000


def test_demo_client_security_preflight_ceiling_refuses_before_payment():
    demo = _load_demo()
    buyer = FakeBuyer()
    with pytest.raises(RuntimeError, match="no payment attempted"):
        demo.run_workflow(
            "https://mcp.test",
            buyer,
            steps=demo.select_steps("security-preflight"),
            max_payment_atomic=10_000,
        )
    assert [agent for agent, _ in buyer.challenges] == ["security-preflight"]
    assert buyer.payments == []


def test_demo_client_payment_limit_is_exact_usdc():
    demo = _load_demo()
    assert demo._usdc_to_atomic("0.01") == 10_000
    assert demo._usdc_to_atomic("0.25") == 250_000
    assert demo._usdc_to_atomic("0.000001") == 1
    with pytest.raises(demo.argparse.ArgumentTypeError):
        demo._usdc_to_atomic("0.0000001")


@pytest.mark.parametrize(("query", "referer", "expected"), [
    ("", "", "direct"),
    ("", "https://mcp.viridisconservation.com/agents", "internal"),
    ("", "https://github.com/xpaysh/awesome-x402", "github"),
    ("", "https://www.google.com/search?q=viridis", "search"),
    ("", "https://partner.example/private?buyer=secret", "other"),
    ("source=awesome-x402", "", "awesome_x402"),
    ("source=meshmcp", "https://attacker.example/private", "meshmcp"),
    ("source=x402-success", "https://attacker.example/private", "x402_success"),
    ("source=openclaw", "https://attacker.example/private", "openclaw"),
    ("source=untrusted", "https://github.com/x/y", "github"),
])
def test_public_acquisition_source_is_finite_and_discards_raw_context(
        query, referer, expected):
    from starlette.requests import Request
    import viridis_mcp_gateway as gateway

    headers = []
    if referer:
        headers.append((b"referer", referer.encode()))
    request = Request({
        "type": "http",
        "method": "GET",
        "scheme": "https",
        "server": ("mcp.viridisconservation.com", 443),
        "path": "/agents",
        "query_string": query.encode(),
        "headers": headers,
    })
    observed = gateway._public_acquisition_source(request)
    assert observed == expected
    assert observed in {
        "awesome_x402", "meshmcp", "x402_success", "openclaw", "github",
        "internal", "search", "direct", "other",
    }


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
    old_members = gateway.EXTERNAL_MEMBERS
    gateway.EXTERNAL_MEMBERS = []
    try:
        with TestClient(gateway.build_app()) as client:
            agents = client.get("/agents")
            quickstart = client.get("/quickstart")
            agents_github = client.get(
                "/agents",
                headers={"referer":
                         "https://github.com/xpaysh/awesome-x402"})
            quickstart_mesh = client.get(
                "/quickstart?source=meshmcp",
                headers={"referer": "https://attacker.example/private?id=1"})
            seats_mesh = client.get(
                "/seats?source=meshmcp",
                headers={"referer": "https://attacker.example/private?id=2"})
            snapshot = client.get("/compliance-snapshot")
            snapshot_example = client.get("/compliance-snapshot/example")
            llms = client.get("/llms.txt")
            brand_mark = client.get("/brand/viridis-mark.svg")
            x402_catalog = client.get("/x402/catalog")
            x402_well_known = client.get("/.well-known/x402")
            x402_manifest = client.get("/.well-known/x402.json")
            openapi_well_known = client.get("/.well-known/openapi.json")
            openapi_root = client.get("/openapi.json")
            robots = client.get("/robots.txt")
            sitemap = client.get("/sitemap.xml")
            skills_index = client.get("/.well-known/skills/index.json")
            buyer_skill = client.get(
                "/.well-known/skills/viridis-paid-tools/SKILL.md")
            health = client.get("/healthz")
            catalog = client.get("/.well-known/ai-catalog.json")
    finally:
        gateway.EXTERNAL_MEMBERS = old_members

    assert agents.status_code == 200
    assert quickstart.status_code == 200
    assert agents_github.status_code == 200
    assert quickstart_mesh.status_code == 200
    assert seats_mesh.status_code == 200
    assert snapshot.status_code == 200
    assert snapshot_example.status_code == 200
    assert llms.status_code == 200
    assert brand_mark.status_code == 200
    assert brand_mark.headers["content-type"].startswith("image/svg+xml")
    assert "Viridis connected land mark" in brand_mark.text
    assert x402_catalog.status_code == 200
    assert x402_well_known.status_code == 200
    assert x402_manifest.status_code == 200
    assert openapi_well_known.status_code == 200
    assert openapi_root.status_code == 200
    assert robots.status_code == 200
    assert robots.headers["content-type"].startswith("text/plain")
    assert sitemap.status_code == 200
    assert sitemap.headers["content-type"].startswith("application/xml")
    assert skills_index.status_code == 200
    assert buyer_skill.status_code == 200
    assert buyer_skill.headers["content-type"].startswith("text/markdown")
    assert skills_index.json() == {"skills": [{
        "name": "viridis-paid-tools",
        "description": (
            "Discover and buy Viridis MCP Security Preflight, carbon and "
            "compliance tools through x402 v2, or inspect signed Agent "
            "Market work listings."),
        "files": ["SKILL.md"],
    }]}
    assert "name: viridis-paid-tools" in buyer_skill.text
    assert "viridis_commerce.next_paid_routes" in buyer_skill.text
    assert "viridis_commerce.repeat_purchase" in buyer_skill.text
    assert "`input_schema`, `input_example`" in buyer_skill.text
    assert "`required_buyer_inputs`, and `quote`" in buyer_skill.text
    assert "quote.authoritative_source" in buyer_skill.text
    assert "quote.payer_hint_required_for_exact_quote" in buyer_skill.text
    assert "caller's public signing address" in buyer_skill.text
    assert "funding_status: UNVERIFIED" in buyer_skill.text
    # The September 17 Security discovery release intentionally made /agents
    # a focused Security buyer front door.  The wider paid-route inventory and
    # Regulatory Radar purchase instructions remain on /quickstart and the
    # machine-readable surfaces below.
    assert "Start with an MCP manifest preflight" in agents.text
    assert "https://mcp.viridis-security.com/security-preflight/mcp" \
        in agents.text
    assert "Connecting and listing tools do not authorize payment" \
        in agents.text
    assert "https://mcp.viridisconservation.com/x402/catalog" \
        in agents.text
    assert "Maxwell Defense Rehearsal" in agents.text
    assert "https://mcp.viridisconservation.com/reliability-sprint" \
        in agents.text
    assert "quantity-takeoff" in quickstart.text
    assert "x402_demo_client.py" in quickstart.text
    assert "--dry-run" in quickstart.text
    assert "--route regulatory-radar --max-payment-usdc 0.01" in quickstart.text
    assert "--route regulatory-radar --max-payment-usdc 0.25" in quickstart.text
    assert "--route regulatory-watch --max-payment-usdc 0.25" \
        in quickstart.text
    assert "/x402/security-preflight/security_preflight" in quickstart.text
    assert 'id="security-first-call"' in quickstart.text
    assert "--dry-run --route security-preflight" in quickstart.text
    assert "--route security-preflight --max-payment-usdc 0.01" \
        in quickstart.text
    assert "does not fetch or certify the live runtime" in quickstart.text
    assert "The live unpaid 402 is authoritative" in quickstart.text
    assert "--route hive --max-payment-usdc 5.00" in quickstart.text
    assert "max_amount(10_000)" in quickstart.text
    assert "PAYMENT-REQUIRED" in quickstart.text
    assert "PAYMENT-SIGNATURE" in quickstart.text
    assert "PAYMENT-RESPONSE" in quickstart.text
    assert "45V clean energy tax credit emissions disclosure" in quickstart.text
    assert "legacy v1 header names" in quickstart.text
    assert "New and returning buyers should put their public signing address" \
        in quickstart.text
    assert "first 402 reflects that wallet's exact price eligibility" \
        in quickstart.text
    assert "Never send a private key." in quickstart.text
    assert "Hermes Agent" in quickstart.text
    assert "/compliance-snapshot" in quickstart.text
    assert "/seats" in quickstart.text
    assert "$49 reviewed Compliance Snapshot" in quickstart.text
    assert "Continue to Stripe — $49" in snapshot.text
    assert "hermes mcp add viridis-market" in quickstart.text
    assert "Viridis does not install or operate it" in quickstart.text
    assert ".well-known/skills/viridis-paid-tools" in quickstart.text
    assert "--source well-known" in quickstart.text
    assert "--yes" in quickstart.text
    assert "--now" not in quickstart.text
    assert "First paid call from every new wallet on eligible" in quickstart.text
    assert "What an agent can verify before paying" in quickstart.text
    assert "seller-reported pricing state" in quickstart.text
    assert "settled Regulatory Radar" in quickstart.text
    assert "Recommended first purchase" in quickstart.text
    assert "Viridis never treats a prior purchase as permission" \
        in quickstart.text
    assert 'id="radar-repeat-call"' in quickstart.text
    assert 'id="radar-watch-call"' in quickstart.text
    assert "This is exactly one new paid attempt." in quickstart.text
    assert "authorize any later purchase" in quickstart.text
    assert 'id="official-client"' in quickstart.text
    assert ".card code{display:block;overflow-wrap:anywhere;" in quickstart.text
    assert "unpaid GHG Ledger" in quickstart.text
    assert "seller-published pointer index" in quickstart.text
    assert "immutable merge commit and SHA-256" in quickstart.text
    assert "unpaid preflight" in quickstart.text
    assert "older paid-settlement capture" in quickstart.text
    assert "a seller-reported count is not" in quickstart.text
    assert "Payable HTTP routes" in llms.text
    assert "--route security-preflight --max-payment-usdc 0.01" in llms.text
    assert "Coinbase's Bazaar MCP server" in llms.text
    assert "Coinbase Payments MCP" in llms.text
    assert "--route regulatory-radar --max-payment-usdc 0.25" in llms.text
    assert "--route regulatory-watch --max-payment-usdc 0.25" in llms.text
    assert "exactly one new paid attempt" in llms.text
    assert "authorize any later purchase" in llms.text
    assert "10000-atomic ceiling" in llms.text
    assert "Hermes Agent buyer guide" in llms.text
    assert "https://mcp.viridisconservation.com/network/mcp" in llms.text
    assert (
        "https://mcp.viridisconservation.com/.well-known/skills/index.json"
        in llms.text)
    assert "First paid call from every new wallet on eligible" in llms.text
    assert "--route regulatory-radar --max-payment-usdc 0.25" \
        in buyer_skill.text
    assert "--route regulatory-watch --max-payment-usdc 0.25" \
        in buyer_skill.text
    assert "regulatory-radar/monitor_changes" in buyer_skill.text
    assert "not a scheduled monitor" in buyer_skill.text
    assert "exactly one new paid attempt" in buyer_skill.text
    assert "authorize any later purchase" in buyer_skill.text
    machine = x402_catalog.json()
    assert x402_well_known.json() == machine
    assert machine["spec_version"] == "viridis-x402-catalog-v1"
    assert machine["manifest"].endswith("/.well-known/x402.json")
    assert machine["openapi"].endswith("/.well-known/openapi.json")
    assert machine["robots_txt"].endswith("/robots.txt")
    assert machine["sitemap"].endswith("/sitemap.xml")
    assert machine["intro_pricing"]["enabled"] is True
    assert machine["intro_pricing"]["seen_payers_evidence"] == {
        "classification": "seller_reported_pricing_eligibility_state",
        "independently_verifiable": False,
        "authoritative_for_payment": False,
        "revenue_signal": False,
    }
    evidence = machine["independent_evidence"]
    assert evidence["classification"] == "external_fixture_pointer_index"
    assert evidence["index_posture"] == "seller_published_pointer_only"
    assert evidence["authoritative_for_payment"] is False
    assert evidence["revenue_signal"] is False
    assert evidence["verification_required"] is True
    assert {item["route"] for item in evidence["fixtures"]} == {
        "regulatory-radar/scan_regulations",
        "ghg-ledger/calculate_inventory",
    }
    fixtures = {item["route"]: item for item in evidence["fixtures"]}
    assert fixtures["regulatory-radar/scan_regulations"][
        "fixture_state"] == "matched_on_last_comparison"
    assert fixtures["regulatory-radar/scan_regulations"][
        "matched_on_last_comparison"] is True
    assert fixtures["regulatory-radar/scan_regulations"][
        "payment_terms_changed"] is False
    assert fixtures["regulatory-radar/scan_regulations"][
        "capture_method"] == "unpaid_preflight"
    assert fixtures["regulatory-radar/scan_regulations"][
        "settled_flow_provenance"][
            "current_fixture_is_settlement_receipt"] is False
    assert fixtures["ghg-ledger/calculate_inventory"][
        "matched_on_last_comparison"] is True
    assert all(
        len(item["merge_commit"]) == 40
        and len(item["sha256"]) == 64
        and "/blob/" + item["merge_commit"] + "/" in item["immutable_url"]
        for item in evidence["fixtures"])
    assert "not independent buyer or revenue proof" in (
        machine["intro_pricing"]["note"])
    assert len(machine["routes"]) == 11
    assert machine["buyer_skill"].endswith(
        "/.well-known/skills/viridis-paid-tools/SKILL.md")
    assert {route["agent"] for route in machine["routes"]} == {
        "quantity-takeoff", "ghg-ledger", "disclosure-compiler",
        "taxcredit-engine", "regulatory-radar", "hive",
        "security-preflight"}
    manifest = x402_manifest.json()
    assert manifest["x402Version"] == 2
    assert manifest["name"] == "Viridis Agent Fleet"
    assert isinstance(manifest["accepts_payment"], bool)
    assert manifest["default_network"] == "eip155:8453"
    assert manifest["default_asset"].lower() == (
        "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913")
    assert manifest["services"] == manifest["resources"]
    assert manifest["services"] == manifest["accepts"]
    assert len(manifest["services"]) == 11
    # Validators must be able to construct a valid POST body from every
    # top-level paid-route entry.  Keeping schemas only in follow-on offers
    # makes a first-party discovery pass incorrectly classify a valid x402
    # endpoint as untestable.
    for service in manifest["services"]:
        schema = service["input_schema"]
        example = service["input_example"]
        assert schema["type"] == "object", service["id"]
        assert isinstance(example, dict), service["id"]
        assert set(schema.get("required", [])).issubset(example), service["id"]
    radar_service = next(
        service for service in manifest["services"]
        if service["id"] == "viridis.regulatory-radar.scan_regulations")
    assert radar_service["method"] == "POST"
    assert radar_service["price_atomic"] == 250000
    assert radar_service["price_usdc"] == "0.25"
    assert radar_service["owner_contact"] == (
        "viridissecurity1@gmail.com")
    assert radar_service["input_schema"]["required"] == ["jurisdiction"]
    assert radar_service["input_example"]["jurisdiction"] == "US"
    assert radar_service["quote_authority"] == "live_unpaid_http_402"
    assert radar_service["fresh_quote_required"] is True
    assert radar_service["list_price_only"] is True
    assert radar_service["auto_payment"] is False
    watch_service = next(
        service for service in manifest["services"]
        if service["id"] == "viridis.regulatory-radar.monitor_changes")
    assert watch_service["name"] == "Viridis Regulatory Radar Watch"
    assert watch_service["price_atomic"] == 250000
    assert watch_service["input_schema"]["properties"][
        "lookback_days"]["maximum"] == 365
    assert watch_service["tags"] == [
        "climate-compliance",
        "regulatory-calendar",
        "compliance-deadlines",
        "effective-dates",
        "change-monitoring",
    ]
    assert "monitor regulatory changes" in watch_service[
        "description"].lower()
    assert "not a live external regulatory feed" in watch_service[
        "description"].lower()
    security_service = next(
        service for service in manifest["services"]
        if service["id"] == "viridis.security-preflight.security_preflight")
    assert security_service["name"] == "Viridis Security Preflight"
    assert security_service["price_atomic"] == 1000000
    assert security_service["input_schema"]["required"] == [
        "agent_id", "manifest"]
    assert security_service["input_example"]["agent_id"] == (
        "example-research-agent")
    assert "does not fetch or certify" in security_service[
        "description"].lower()
    serialized_manifest = json.dumps(manifest, sort_keys=True).lower()
    assert "private_key" not in serialized_manifest
    assert "facilitator" not in serialized_manifest
    assert "stripe_secret" not in serialized_manifest
    openapi = openapi_well_known.json()
    assert openapi_root.json() == openapi
    assert openapi["openapi"] == "3.1.0"
    assert openapi["servers"] == [{
        "url": "https://mcp.viridisconservation.com"}]
    assert len(openapi["paths"]) == 15
    assert set(openapi["paths"]) == {
        "/x402/regulatory-radar/scan_regulations",
        "/x402/regulatory-radar/monitor_changes",
        "/x402/taxcredit-engine/calculate_tax_credit",
        "/x402/taxcredit-engine/signed_cliff_check",
        "/x402/ghg-ledger/calculate_inventory",
        "/x402/quantity-takeoff/calculate_takeoff",
        "/x402/disclosure-compiler/compile_disclosure",
        "/x402/hive/solve",
        "/x402/security-preflight/security_preflight",
        "/x402/security-preflight/scan_source",
        "/x402/security-preflight/screen_injection",
        "/adopt",
        "/x402/feedback",
        "/security-preflight/watch",
        "/security-preflight/receipts/{receipt_id}",
    }
    assert all(set(path_item) == ({"get"} if "{receipt_id}" in path else {"post"})
               for path, path_item in openapi["paths"].items())
    assert openapi["paths"]["/adopt"]["post"][
        "x-viridis-state-changing"] is False
    assert openapi["paths"]["/adopt"]["post"][
        "x-viridis-auto-payment"] is False
    feedback_post = openapi["paths"]["/x402/feedback"]["post"]
    assert feedback_post["x-viridis-feedback-classification"] == (
        "buyer_possession_feedback")
    assert feedback_post["x-viridis-independently-verified"] is False
    assert feedback_post["x-viridis-revenue-signal"] is False
    radar_post = openapi["paths"][
        "/x402/regulatory-radar/scan_regulations"]["post"]
    radar_json = radar_post["requestBody"]["content"]["application/json"]
    assert radar_json["schema"]["required"] == ["jurisdiction"]
    assert radar_json["example"]["jurisdiction"] == "US"
    assert radar_post["responses"]["402"]["headers"][
        "PAYMENT-REQUIRED"]["required"] is True
    assert radar_post["x-viridis-x402"] == {
        "advertised_list_price_minor_usd": 25,
        "advertised_list_amount_atomic_usdc": "250000",
        "paid_execution_method": "POST",
        "quote_authority": "live_unpaid_http_402",
        "fresh_quote_required": True,
        "auto_payment": False,
        "buyer_authorization_required": True,
        "request_payment_header": "PAYMENT-SIGNATURE",
        "quote_header": "PAYMENT-REQUIRED",
        "receipt_header": "PAYMENT-RESPONSE",
        "service_name": "Viridis Regulatory Radar",
        "category": "climate-compliance",
        "owner_url": "https://mcp.viridisconservation.com/agents",
        "owner_contact": "viridissecurity1@gmail.com",
    }
    watch_post = openapi["paths"][
        "/x402/regulatory-radar/monitor_changes"]["post"]
    assert watch_post["x-viridis-x402"]["service_name"] == (
        "Viridis Regulatory Radar Watch")
    assert watch_post["x-viridis-x402"]["quote_authority"] == (
        "live_unpaid_http_402")
    assert watch_post["tags"] == watch_service["tags"]
    assert "compliance deadlines" in watch_post["summary"].lower()
    assert watch_post["requestBody"]["content"]["application/json"][
        "schema"]["properties"]["lookback_days"]["maximum"] == 365
    security_post = openapi["paths"][
        "/x402/security-preflight/security_preflight"]["post"]
    assert security_post["x-viridis-x402"]["service_name"] == (
        "Viridis Security Preflight")
    assert security_post["requestBody"]["content"]["application/json"][
        "schema"]["required"] == ["agent_id", "manifest"]
    serialized_openapi = json.dumps(openapi, sort_keys=True).lower()
    assert "private_key" not in serialized_openapi
    assert "x402_facilitator_url" not in serialized_openapi
    assert "stripe_secret" not in serialized_openapi
    assert robots.text == (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /internal/\n"
        "Disallow: /seats/checkout\n"
        "Disallow: /seats/success\n"
        "Disallow: /seats/manage\n"
        "Disallow: /compliance-snapshot/checkout\n"
        "Disallow: /compliance-snapshot/success\n"
        "Sitemap: https://mcp.viridisconservation.com/sitemap.xml\n")
    assert sitemap.text.startswith("<?xml version=\"1.0\"")
    assert sitemap.text.count("<url><loc>") == 6
    for path in (
            "/agents",
            "/reliability-sprint",
            "/quickstart",
            "/seats",
            "/compliance-snapshot",
            "/compliance-snapshot/example"):
        assert (
            f"<loc>https://mcp.viridisconservation.com{path}</loc>"
            in sitemap.text)
    assert "/checkout" not in sitemap.text
    assert "/success" not in sitemap.text
    assert "/manage" not in sitemap.text
    assert (
        '<link rel="canonical" '
        'href="https://mcp.viridisconservation.com/agents">'
        in agents.text)
    assert (
        '<meta name="description" content="Security checks agents can call: '
        'MCP manifest preflight'
        in agents.text)
    assert (
        '<link rel="canonical" '
        'href="https://mcp.viridisconservation.com/quickstart">'
        in quickstart.text)
    assert (
        '<meta name="description" content="Use the Viridis x402 quickstart'
        in quickstart.text)
    assert (
        '<link rel="canonical" '
        'href="https://mcp.viridisconservation.com/seats">'
        in seats_mesh.text)
    assert (
        '<link rel="canonical" '
        'href="https://mcp.viridisconservation.com/compliance-snapshot">'
        in snapshot.text)
    assert (
        '<link rel="canonical" href="https://mcp.viridisconservation.com/'
        'compliance-snapshot/example">'
        in snapshot_example.text)
    assert agents.headers["x-frame-options"] == "DENY"
    assert "x-robots-tag" not in agents.headers
    assert health.status_code == 200
    assert health.json()["human_surfaces"]["agents"].endswith("/agents")
    assert health.json()["human_surfaces"]["quickstart"].endswith(
        "/quickstart")
    assert health.json()["human_surfaces"]["compliance_snapshot"].endswith(
        "/compliance-snapshot")
    assert health.json()["human_surfaces"]["llms_txt"].endswith(
        "/llms.txt")
    assert health.json()["human_surfaces"]["x402_catalog"].endswith(
        "/x402/catalog")
    assert health.json()["human_surfaces"]["x402_manifest"].endswith(
        "/.well-known/x402.json")
    assert health.json()["human_surfaces"]["openapi"].endswith(
        "/.well-known/openapi.json")
    assert health.json()["human_surfaces"]["robots_txt"].endswith(
        "/robots.txt")
    assert health.json()["human_surfaces"]["sitemap"].endswith(
        "/sitemap.xml")
    assert health.json()["human_surfaces"]["agent_skills_index"].endswith(
        "/.well-known/skills/index.json")
    assert health.json()["human_surfaces"]["buyer_skill"].endswith(
        "/.well-known/skills/viridis-paid-tools/SKILL.md")
    funnel = health.json()["subscriptions"]["frontdoor_funnel"]
    assert funnel["landing_page_views"] == 4
    assert funnel["acquisition_surface_views"] == {
        "agents": 2, "quickstart": 2}
    assert funnel["acquisition_source_views"]["direct"] == 2
    assert funnel["acquisition_source_views"]["github"] == 1
    assert funnel["acquisition_source_views"]["meshmcp"] == 1
    assert funnel["page_views"] == 1
    assert funnel["seat_source_views"]["meshmcp"] == 1
    assert funnel["seat_attributed_views"] == 1
    assert funnel["seat_unattributed_views"] == 0
    assert funnel["seat_acquisition_classification"] == (
        "seller_reported_aggregate_telemetry_not_unique_buyers_"
        "and_not_revenue")
    assert "attacker.example" not in json.dumps(funnel, sort_keys=True)
    assert funnel["acquisition_classification"] == (
        "seller_reported_aggregate_telemetry_not_revenue")
    surfaces = {item["url"] for item in catalog.json()["humanSurfaces"]}
    assert "https://mcp.viridisconservation.com/agents" in surfaces
    assert "https://mcp.viridisconservation.com/quickstart" in surfaces
    assert (
        "https://mcp.viridisconservation.com/compliance-snapshot"
        in surfaces)
    assert "https://mcp.viridisconservation.com/llms.txt" in surfaces
    assert "https://mcp.viridisconservation.com/x402/catalog" in surfaces
    assert catalog.json()["host"]["metadata"]["x402ManifestUrl"].endswith(
        "/.well-known/x402.json")
    assert catalog.json()["host"]["metadata"]["openapiUrl"].endswith(
        "/.well-known/openapi.json")
    radar_ard = next(
        entry for entry in catalog.json()["entries"]
        if entry["identifier"] == "urn:air:viridis:regulatory-radar")
    assert radar_ard["metadata"]["x402"]["tool"] == "scan_regulations"
    assert radar_ard["metadata"]["pricing"]["paymentRoutes"]["x402"].endswith(
        "/x402/regulatory-radar/scan_regulations")
    dockerfile = (HERE / "Dockerfile").read_text()
    assert "COPY deploy/gateway/agents.html deploy/gateway/" in dockerfile
    assert "COPY deploy/gateway/quickstart.html deploy/gateway/" in dockerfile
    assert (
        "COPY deploy/gateway/compliance_snapshot.html deploy/gateway/"
        in dockerfile)
    assert "COPY deploy/gateway/llms.txt deploy/gateway/" in dockerfile
    assert "COPY deploy/gateway/viridis-mark.svg deploy/gateway/" in dockerfile
    assert (
        "COPY integrations/viridis-paid-tools/SKILL.md "
        "integrations/viridis-paid-tools/" in dockerfile)


def test_x402_manifest_exposes_public_receiver_but_never_facilitator(
        monkeypatch):
    import viridis_mcp_gateway as gateway

    receiver = "0x" + "ab" * 20
    monkeypatch.setenv("X402_ENABLED", "1")
    monkeypatch.setenv("X402_V2_ENABLED", "1")
    monkeypatch.setenv("VIRIDIS_X402_ADDRESS", receiver)
    monkeypatch.setenv("X402_FACILITATOR_URL", "https://secret.fac.example")

    manifest = gateway._x402_manifest_document("https://mcp.test/")

    assert manifest["accepts_payment"] is True
    assert manifest["pay_to"] == receiver
    assert all(service["pay_to"] == receiver
               for service in manifest["services"])
    assert "secret.fac.example" not in json.dumps(manifest, sort_keys=True)


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

    # /agents is now a static Security-first page and deliberately does not
    # advertise the fleet-wide introductory-price switch.  The authoritative
    # buyer instructions continue to render the switch on /quickstart and
    # /llms.txt.
    assert "First paid call from every new wallet is $0.01" not in agents.text
    for response in (quickstart, llms):
        assert response.status_code == 200
        assert "Intro pricing is currently disabled" in response.text
        assert "First paid call from every new wallet is $0.01" \
            not in response.text
