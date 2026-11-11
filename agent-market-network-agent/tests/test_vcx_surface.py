"""VCX local tool boundary and complete demonstration checks."""
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys

import pytest

AGENT = Path(__file__).resolve().parents[1]
FLEET = AGENT.parent
for directory in (FLEET, AGENT):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from mcp.server.fastmcp import FastMCP
from src.core import MarketNetworkCore
from vcx.demo import run_demo
from vcx.exchange import ComputeExchange
from vcx.providers import TAKEOFF_SERVICE


def load_adapter():
    spec = importlib.util.spec_from_file_location(
        "_vcx_surface_adapter", AGENT / "adapters" / "vcx_mcp_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecordingExchange:
    def __init__(self):
        self.calls = []

    def process(self, request):
        self.calls.append(request)
        return {"status": "ok", "data": {"mode": "simulation", "forwarded": True}}


def test_import_performs_no_server_startup_or_database_creation(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("adapter import performed startup")
    monkeypatch.setattr(FastMCP, "run", forbidden)
    monkeypatch.setattr(MarketNetworkCore, "__init__", forbidden)
    monkeypatch.setattr(ComputeExchange, "__init__", forbidden)
    assert callable(load_adapter().build_server)


def test_tool_catalog_is_explicit_local_and_has_no_financial_admin_surface():
    exchange = RecordingExchange()
    server = load_adapter().build_server(exchange)
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert names == {
        "list_capacity", "register_capacity", "request_compute", "get_compute_quotes",
        "reserve_compute", "authorize_compute", "execute_compute_job", "get_compute_job",
        "verify_compute_result", "settle_compute", "get_compute_budget", "get_compute_earnings",
        "cancel_compute", "dispute_compute", "refund_compute", "reinvest_compute",
        "recover_compute_jobs",
    }
    assert not names & {"seed_account", "top_up", "set_policy", "confirm_simulated_payment",
                        "create_payment", "create_payout", "execute_transfer", "onboard_seller"}
    annotations = {tool.name: tool.annotations for tool in tools}
    assert annotations["list_capacity"].readOnlyHint is True
    assert annotations["get_compute_quotes"].readOnlyHint is False
    assert all(tool.annotations.openWorldHint is False for tool in tools)
    assert exchange.calls == []


def test_signed_tool_forwards_exact_body_and_auth_without_adding_authority():
    exchange = RecordingExchange()
    server = load_adapter().build_server(exchange)
    body = {"idempotency_key": "request-one", "request_id": "request-one", "max_price_minor": 250}
    auth = {"nonce": "request-nonce", "signed_at": "2026-11-10T20:00:00+00:00", "signature": "placeholder"}
    asyncio.run(server.call_tool("request_compute", {"actor_id": "buyer-one", "body": body, "auth": auth}))
    assert exchange.calls == [{"action": "request_compute", "actor_id": "buyer-one",
                               "body": body, "auth": auth}]
    asyncio.run(server.call_tool("list_capacity", {}))
    assert exchange.calls[-1] == {"action": "list_capacity"}


def test_demo_runs_existing_fleet_service_and_earnings_funded_job(tmp_path):
    report = run_demo(tmp_path)
    assert report["mode"] == "simulation"
    assert report["actual_revenue_minor"] == report["live_charges"] == report["live_payouts"] == 0
    assert report["redeemable"] is False
    assert report["participants"]["sellers"] == 3
    assert report["participants"]["buyers"] == 2
    assert report["discovery_count"] == 4
    first = report["first_job"]
    assert first["state"] == "SETTLED" and first["seller_id"] == "seller-accurate"
    assert first["price_minor"] == 200
    assert report["reinvestment"]["amount_minor"] == 150
    followup = report["earnings_funded_job"]
    assert followup["buyer_id"] == first["seller_id"]
    assert followup["seller_id"] == "seller-economy"
    assert followup["state"] == "SETTLED" and followup["price_minor"] == 100
    takeoff = report["fleet_takeoff_job"]
    assert takeoff["state"] == "SETTLED" and takeoff["service_id"] == TAKEOFF_SERVICE
    assert takeoff["output"]["line_items"][0]["net_qty"] == "7.407"
    assert report["budgets"]["buyer-beta"]["available_budget_minor"] == 50
    assert report["failure_simulations"]["cancelled"]["state"] == "CANCELLED"
    expired = report["failure_simulations"]["expired_authorization"]["recovered"]
    assert len(expired) == 1 and expired[0]["state"] == "EXPIRED"
    reconciliation = report["reconciliation"]
    assert reconciliation["conserved"] is True
    assert reconciliation["journal_net_minor"] == 0
    assert reconciliation["errors"] == []
    assert reconciliation["held_minor"] == 0
    assert reconciliation["available_minor"] + reconciliation["pending_earnings_minor"] + reconciliation["marketplace_fees_minor"] == reconciliation["external_simulated_funding_minor"]
    assert type(reconciliation["marketplace_fees_minor"]) is int
    assert "private_key" not in json.dumps(report).lower()


def test_demo_refuses_to_overwrite_existing_identity_state(tmp_path):
    protected = tmp_path / "existing.db"
    protected.write_text("existing state")
    with pytest.raises(ValueError, match="must be empty"):
        run_demo(tmp_path)
    assert protected.read_text() == "existing state"
