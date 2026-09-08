import asyncio
import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MARKET_STATE_DB", ":memory:")

import adapters.mcp_server as market_mcp  # noqa: E402
from client import AgentMarketSigner  # noqa: E402
from src.core import MarketNetworkCore  # noqa: E402


mcp = market_mcp.mcp


def call_tool(name, arguments):
    _content, structured = asyncio.run(mcp.call_tool(name, arguments))
    schema = next(
        tool.outputSchema for tool in asyncio.run(mcp.list_tools())
        if tool.name == name)
    Draft202012Validator(schema).validate(structured)
    return structured


def signed_args(action, actor_field, actor_id, signer, body):
    return {
        actor_field: actor_id,
        **body,
        "auth": signer.auth(action, actor_id, body),
    }


def publish_profile(agent_id, signer, capability):
    body = {
        "name": agent_id.replace("-", " ").title(),
        "description": f"Deterministic {capability} service for agent buyers.",
        "capabilities": [capability, "agent-service"],
        "representative_queries": [f"find a {capability} service"],
        "endpoint": f"https://agents.example.com/{agent_id}/mcp",
        "public_key_b64": signer.public_key_b64,
        "payment": {
            "x402_endpoint": f"https://agents.example.com/{agent_id}/x402/run",
            "network": "eip155:8453",
            "asset": "USDC",
            "price_minor": 50,
            "currency": "USD",
        },
        "idempotency_key": f"{agent_id}-profile",
        "ttl_days": 90,
    }
    result = call_tool(
        "publish_agent_profile",
        signed_args("publish_profile", "agent_id", agent_id, signer, body),
    )
    assert result["status"] == "ok", result
    return result["data"]


def test_mcp_exposes_complete_market_loop():
    tools = {tool.name for tool in asyncio.run(mcp.list_tools())}
    required = {
        "prepare_signature", "publish_agent_profile", "search_agents",
        "publish_security_attestation", "list_security_attestations",
        "import_security_receipt",
        "import_operator_verification_receipt",
        "list_operator_verifications",
        "subscribe_to_work", "post_work", "search_work", "get_work",
        "submit_offer", "award_offer", "submit_delivery", "accept_delivery",
        "attest_settlement", "submit_usefulness_feedback",
        "send_agent_message", "read_agent_inbox",
        "network_status", "describe_network",
    }
    assert required == tools


def test_mcp_transport_has_dns_rebinding_protection():
    settings = mcp.settings.transport_security
    assert settings.enable_dns_rebinding_protection is True
    assert "mcp.viridisconservation.com" in settings.allowed_hosts
    assert "127.0.0.1:*" in settings.allowed_hosts
    assert "https://mcp.viridisconservation.com" in settings.allowed_origins


def test_mcp_tools_advertise_structured_results_and_safety_hints():
    tools = asyncio.run(mcp.list_tools())
    assert len(tools) == 22
    for tool in tools:
        assert tool.outputSchema is not None, tool.name
        assert tool.outputSchema["properties"]["status"]["type"] == "string"
        assert tool.annotations is not None, tool.name
        assert tool.annotations.destructiveHint is False, tool.name
        assert tool.annotations.idempotentHint is True, tool.name
        assert tool.annotations.openWorldHint is False, tool.name

    by_name = {tool.name: tool for tool in tools}
    for name in {
        "prepare_signature", "search_agents", "list_security_attestations",
        "list_operator_verifications",
        "search_work", "get_work",
        "network_status", "describe_network",
    }:
        assert by_name[name].annotations.readOnlyHint is True
    assert by_name["post_work"].annotations.readOnlyHint is False


def test_mcp_result_schema_accepts_success_and_error_envelopes():
    success = call_tool("network_status", {})
    assert success["status"] == "ok"

    error = call_tool("get_work", {"work_id": "missing-work"})
    assert error["status"] == "error"
    assert error["error_type"] == "ValidationError"


def test_mcp_full_signed_work_funnel_validates_every_result(tmp_path, monkeypatch):
    def verify_settlement(event):
        return {
            "verified": True,
            "event_id": event["event_id"],
            "work_id": event["work"]["work_id"],
            "money_primitive": {"tx_hash": event["settlement"]["reference"]},
        }

    isolated = MarketNetworkCore(
        db_path=str(tmp_path / "market-mcp-funnel.sqlite3"),
        settlement_verifier=verify_settlement,
        hub_required=True,
    )
    monkeypatch.setattr(market_mcp, "agent", isolated)
    try:
        buyer = AgentMarketSigner.generate_ephemeral()
        seller = AgentMarketSigner.generate_ephemeral()
        publish_profile("transport-buyer", buyer, "procurement")
        publish_profile("transport-seller", seller, "typescript")

        deadline = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        work_body = {
            "title": "Build a TypeScript MCP client",
            "description": "Deliver a tested TypeScript client and documentation.",
            "required_capabilities": ["typescript", "mcp"],
            "budget_minor": 50,
            "currency": "USD",
            "allowed_rails": ["x402"],
            "delivery_deadline": deadline,
            "idempotency_key": "transport-work-0001",
        }
        posted = call_tool(
            "post_work",
            signed_args(
                "post_work", "buyer_id", "transport-buyer", buyer, work_body),
        )
        assert posted["status"] == "ok", posted
        work_id = posted["data"]["work_id"]

        search = call_tool(
            "search_work", {"query": "typescript mcp", "limit": 10})
        assert search["data"]["results"][0]["work_id"] == work_id
        inspected = call_tool("get_work", {"work_id": work_id})
        assert inspected["data"]["offers"] == []

        offer_body = {
            "work_id": work_id,
            "amount_minor": 50,
            "currency": "USD",
            "proposal": "Deliver a tested client with an immutable artifact digest.",
            "delivery_seconds": 3600,
            "settlement": {
                "rail": "x402",
                "payment_endpoint": (
                    "https://agents.example.com/transport-seller/x402/run"),
                "network": "eip155:8453",
                "asset": "USDC",
            },
            "idempotency_key": "transport-offer-0001",
        }
        offered = call_tool(
            "submit_offer",
            signed_args(
                "submit_offer", "seller_id", "transport-seller", seller,
                offer_body),
        )
        assert offered["status"] == "ok", offered

        award_body = {
            "work_id": work_id,
            "offer_id": offered["data"]["offer_id"],
            "idempotency_key": "transport-award-0001",
        }
        awarded = call_tool(
            "award_offer",
            signed_args(
                "award_offer", "buyer_id", "transport-buyer", buyer,
                award_body),
        )
        assert awarded["data"]["payment_plan"]["executed"] is False
        assert awarded["data"]["payment_plan"]["marketplace_money_movement"] == "none"

        digest = hashlib.sha256(b"transport-level delivery").hexdigest()
        delivery_body = {
            "work_id": work_id,
            "artifact_url": "https://artifacts.example.com/typescript-client.tgz",
            "content_sha256": digest,
            "summary": "Tested TypeScript client delivered.",
            "idempotency_key": "transport-delivery-0001",
        }
        delivered = call_tool(
            "submit_delivery",
            signed_args(
                "submit_delivery", "seller_id", "transport-seller", seller,
                delivery_body),
        )
        assert delivered["status"] == "ok", delivered

        accept_body = {
            "work_id": work_id,
            "content_sha256": digest,
            "idempotency_key": "transport-accept-0001",
        }
        accepted = call_tool(
            "accept_delivery",
            signed_args(
                "accept_delivery", "buyer_id", "transport-buyer", buyer,
                accept_body),
        )
        assert accepted["data"]["status"] == "ACCEPTED_PAYMENT_DUE"

        for actor_id, signer, suffix in (
                ("transport-buyer", buyer, "buyer"),
                ("transport-seller", seller, "seller")):
            settlement_body = {
                "work_id": work_id,
                "rail": "x402",
                "amount_minor": 50,
                "currency": "USD",
                "reference": "0x" + "12" * 32,
                "evidence_url": "https://basescan.org/tx/0x" + "12" * 32,
                "idempotency_key": f"transport-settlement-{suffix}",
            }
            settled = call_tool(
                "attest_settlement",
                signed_args(
                    "attest_settlement", "agent_id", actor_id, signer,
                    settlement_body),
            )
            assert settled["status"] == "ok", settled

        final = call_tool("get_work", {"work_id": work_id})
        assert final["data"]["status"] == "COMPLETED"
        assert final["data"]["settlement"]["independently_verified"] is True
        feedback_body = {
            "work_id": work_id,
            "outcome": "USEFUL",
            "would_buy_again": True,
            "note_sha256": hashlib.sha256(
                b"kept on the buyer side").hexdigest(),
            "idempotency_key": "transport-usefulness-0001",
        }
        feedback = call_tool(
            "submit_usefulness_feedback",
            signed_args(
                "submit_usefulness_feedback", "buyer_id",
                "transport-buyer", buyer, feedback_body),
        )
        assert feedback["status"] == "ok", feedback
        assert feedback["data"]["useful"] is True
        network = call_tool("network_status", {})
        assert network["data"]["independently_verified_jobs"] == 1
        assert network["data"]["buyer_signed_useful_paid_deliveries"] == 1
        assert network["data"]["independently_useful_paid_deliveries"] == 0
    finally:
        isolated.close()
