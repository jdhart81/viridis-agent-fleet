import asyncio
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.core import MarketNetworkCore, canonical_action


NOW = datetime(2026, 7, 20, 20, 0, tzinfo=timezone.utc)


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def keys():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return private, b64(public)


def auth(private, action, actor, body, nonce="nonce-00000001", when=NOW):
    signed_at = when.isoformat()
    message = canonical_action(action, actor, nonce, signed_at, body).encode()
    return {"nonce": nonce, "signed_at": signed_at,
            "signature": b64(private.sign(message))}


def run(call):
    return asyncio.run(call)


@pytest.fixture
def core(tmp_path):
    item = MarketNetworkCore(db_path=str(tmp_path / "market.sqlite3"),
                             now_fn=lambda: NOW)
    yield item
    item.close()


def profile_payload(agent_id, private, public, *, capability="carbon",
                    idem="profile-0001", nonce="profile-nonce-0001"):
    body = {
        "name": agent_id.replace("-", " ").title(),
        "description": f"Deterministic {capability} agent for autonomous buyers.",
        "capabilities": [capability, "agent-service"],
        "representative_queries": [f"find a {capability} agent"],
        "endpoint": f"https://agents.example.com/{agent_id}/mcp",
        "public_key_b64": public,
        "payment": {
            "x402_endpoint": f"https://agents.example.com/{agent_id}/x402/run",
            "network": "eip155:8453", "asset": "USDC",
            "price_minor": 50, "currency": "USD",
        },
        "ttl_days": 90,
        "idempotency_key": idem,
    }
    return {"action": "publish_profile", "agent_id": agent_id, **body,
            "auth": auth(private, "publish_profile", agent_id, body, nonce)}


def register(core, agent_id, capability="carbon"):
    private, public = keys()
    result = run(core.process(profile_payload(
        agent_id, private, public, capability=capability,
        idem=f"{agent_id}-profile", nonce=f"{agent_id}-profile-nonce")))
    assert result["status"] == "ok", result
    return private, result["data"]


def signed_input(action, actor_field, actor, private, body, nonce):
    return {"action": action, actor_field: actor, **body,
            "auth": auth(private, action, actor, body, nonce)}


def post_work(core, buyer, private, *, idem="work-post-0001",
              nonce="work-post-nonce-0001"):
    body = {
        "title": "Compile a carbon disclosure",
        "description": "Turn supplied GHG activities into an auditable CSRD draft.",
        "required_capabilities": ["carbon", "disclosure"],
        "budget_minor": 500,
        "currency": "USD",
        "allowed_rails": ["x402", "viridis_cash_escrow"],
        "delivery_deadline": (NOW + timedelta(days=5)).isoformat(),
        "idempotency_key": idem,
    }
    result = run(core.process(signed_input(
        "post_work", "buyer_id", buyer, private, body, nonce)))
    assert result["status"] == "ok", result
    return result["data"]


def offer(core, seller, private, work_id, *, idem="offer-submit-0001",
          nonce="offer-submit-nonce-0001"):
    body = {
        "work_id": work_id, "amount_minor": 400, "currency": "USD",
        "proposal": "I will return an HTTPS artifact and immutable digest.",
        "delivery_seconds": 3600,
        "settlement": {
            "rail": "x402",
            "payment_endpoint": f"https://agents.example.com/{seller}/x402/run",
            "network": "eip155:8453", "asset": "USDC",
        },
        "idempotency_key": idem,
    }
    result = run(core.process(signed_input(
        "submit_offer", "seller_id", seller, private, body, nonce)))
    assert result["status"] == "ok", result
    return result["data"]


def award(core, buyer, private, work_id, offer_id):
    body = {"work_id": work_id, "offer_id": offer_id,
            "idempotency_key": "award-offer-0001"}
    result = run(core.process(signed_input(
        "award_offer", "buyer_id", buyer, private, body,
        "award-offer-nonce-0001")))
    assert result["status"] == "ok", result
    return result["data"]


def deliver(core, seller, private, work_id):
    digest = hashlib.sha256(b"delivery").hexdigest()
    body = {"work_id": work_id,
            "artifact_url": "https://artifacts.example.com/delivery.json",
            "content_sha256": digest, "summary": "Completed auditable disclosure.",
            "idempotency_key": "delivery-submit-0001"}
    result = run(core.process(signed_input(
        "submit_delivery", "seller_id", seller, private, body,
        "delivery-submit-nonce-0001")))
    assert result["status"] == "ok", result
    return result["data"]


def accept(core, buyer, private, work_id, digest):
    body = {"work_id": work_id, "content_sha256": digest,
            "idempotency_key": "delivery-accept-0001"}
    result = run(core.process(signed_input(
        "accept_delivery", "buyer_id", buyer, private, body,
        "delivery-accept-nonce-0001")))
    assert result["status"] == "ok", result
    return result["data"]


def attest(core, agent_id, private, work_id, suffix):
    body = {"work_id": work_id, "rail": "x402", "amount_minor": 400,
            "currency": "USD", "reference": "0x" + "ab" * 32,
            "evidence_url": "https://basescan.org/tx/0x" + "ab" * 32,
            "idempotency_key": f"settlement-{suffix}-0001"}
    return run(core.process(signed_input(
        "attest_settlement", "agent_id", agent_id, private, body,
        f"settlement-{suffix}-nonce-0001")))


def full_awarded(core):
    buyer_key, _ = register(core, "buyer-agent", "procurement")
    seller_key, _ = register(core, "seller-agent", "carbon")
    work = post_work(core, "buyer-agent", buyer_key)
    bid = offer(core, "seller-agent", seller_key, work["work_id"])
    award(core, "buyer-agent", buyer_key, work["work_id"], bid["offer_id"])
    delivery = deliver(core, "seller-agent", seller_key, work["work_id"])
    accept(core, "buyer-agent", buyer_key, work["work_id"],
           delivery["content_sha256"])
    return buyer_key, seller_key, work, bid, delivery


def test_signed_profile_binds_key_and_is_searchable(core):
    private, public = keys()
    payload = profile_payload("carbon-seller", private, public)
    result = run(core.process(payload))
    assert result["status"] == "ok"
    assert result["data"]["did"].startswith("did:viridis:")
    found = core.search_agents("autonomous carbon", ["carbon"])
    assert found["count"] == 1
    assert found["results"][0]["agent_id"] == "carbon-seller"
    assert found["results"][0]["payment"]["price_minor"] == 50


def test_bad_signature_and_stale_signature_fail_closed(core):
    private, public = keys()
    payload = profile_payload("bad-signer", private, public)
    payload["description"] = "tampered after signing"
    bad = run(core.process(payload))
    assert bad["status"] == "error"
    assert bad["error_type"] == "AuthenticationError"
    stale = profile_payload("stale-signer", private, public)
    body = {key: value for key, value in stale.items()
            if key not in {"action", "agent_id", "auth"}}
    stale["auth"] = auth(private, "publish_profile", "stale-signer", body,
                         "stale-profile-nonce", NOW - timedelta(hours=1))
    rejected = run(core.process(stale))
    assert rejected["status"] == "error"
    assert rejected["error_type"] == "AuthenticationError"


def test_nonce_replay_refused_but_idempotent_retry_returns_same_result(core):
    key, _ = register(core, "buyer-replay", "procurement")
    body = {
        "title": "Carbon model", "description": "Build a deterministic model.",
        "required_capabilities": ["carbon"], "budget_minor": 100,
        "currency": "USD", "allowed_rails": ["x402"],
        "delivery_deadline": (NOW + timedelta(days=1)).isoformat(),
        "idempotency_key": "work-replay-idem",
    }
    first = run(core.process(signed_input(
        "post_work", "buyer_id", "buyer-replay", key, body,
        "work-replay-nonce-1")))
    second = run(core.process(signed_input(
        "post_work", "buyer_id", "buyer-replay", key, body,
        "work-replay-nonce-2")))
    assert first == second
    changed = dict(body, idempotency_key="work-replay-idem-2")
    replay = run(core.process(signed_input(
        "post_work", "buyer_id", "buyer-replay", key, changed,
        "work-replay-nonce-1")))
    assert replay["error_type"] == "ReplayError"
    assert core.network_status()["work_open"] == 1


def test_subscription_match_arrives_in_signed_inbox(core):
    seller_key, _ = register(core, "subscriber-agent", "carbon")
    buyer_key, _ = register(core, "work-buyer", "procurement")
    sub_body = {"query": "carbon disclosure", "capabilities": ["carbon"],
                "ttl_days": 14, "idempotency_key": "subscribe-carbon"}
    sub = run(core.process(signed_input(
        "subscribe_work", "agent_id", "subscriber-agent", seller_key,
        sub_body, "subscribe-carbon-nonce")))
    assert sub["status"] == "ok"
    work = post_work(core, "work-buyer", buyer_key)
    assert work["matched_subscriptions"] == 1
    inbox_body = {"limit": 25, "after": "",
                  "idempotency_key": "read-inbox-0001"}
    inbox = run(core.process(signed_input(
        "read_inbox", "agent_id", "subscriber-agent", seller_key,
        inbox_body, "read-inbox-nonce-0001")))
    assert inbox["status"] == "ok"
    assert inbox["data"]["messages"][0]["kind"] == "match"
    assert inbox["data"]["messages"][0]["work_id"] == work["work_id"]


def test_direct_message_is_private_pull_and_audited(core):
    sender_key, _ = register(core, "sender-agent", "coordination")
    recipient_key, _ = register(core, "recipient-agent", "carbon")
    body = {"recipient_id": "recipient-agent", "subject": "Work question",
            "body": "Can you deliver a pinned-factor inventory?", "work_id": "",
            "idempotency_key": "message-send-0001"}
    sent = run(core.process(signed_input(
        "send_message", "sender_id", "sender-agent", sender_key,
        body, "message-send-nonce-0001")))
    assert sent["status"] == "ok"
    assert len(sent["data"]["content_sha256"]) == 64
    inbox_body = {"limit": 25, "after": "", "idempotency_key": "inbox-read-0002"}
    inbox = run(core.process(signed_input(
        "read_inbox", "agent_id", "recipient-agent", recipient_key,
        inbox_body, "inbox-read-nonce-0002")))
    assert inbox["data"]["messages"][0]["body"].startswith("Can you")
    events = core._conn.execute(
        "SELECT event_type,payload_json FROM events WHERE event_type='message.sent'").fetchall()
    assert len(events) == 1
    assert "pinned-factor" not in events[0]["payload_json"]


def test_full_workflow_routes_payment_but_never_moves_it(core):
    buyer_key, seller_key, work, bid, delivery = full_awarded(core)
    state = core.get_work(work["work_id"])
    assert state["status"] == "ACCEPTED_PAYMENT_DUE"
    assert bid["settlement"]["rail"] == "x402"
    assert state["settlement"] is None
    assert core.network_status()["counterparty_attested_jobs"] == 0
    accepted = state["status"]
    assert accepted == "ACCEPTED_PAYMENT_DUE"
    # The only executable action is described for the buyer's own x402 client.
    awarded = core._payment_plan(
        core._conn.execute("SELECT * FROM work_orders WHERE work_id=?",
                           (work["work_id"],)).fetchone(),
        core._conn.execute("SELECT * FROM offers WHERE offer_id=?",
                           (bid["offer_id"],)).fetchone())
    assert awarded["executed"] is False
    assert awarded["marketplace_money_movement"] == "none"


def test_only_both_matching_attestations_record_earnings(core):
    buyer_key, seller_key, work, _, _ = full_awarded(core)
    first = attest(core, "buyer-agent", buyer_key, work["work_id"], "buyer")
    assert first["status"] == "ok"
    assert first["data"]["status"] == "PARTIALLY_ATTESTED"
    assert core.network_status()["counterparty_attested_jobs"] == 0
    second = attest(core, "seller-agent", seller_key, work["work_id"], "seller")
    assert second["data"]["status"] == "COUNTERPARTY_ATTESTED"
    assert second["data"]["independently_verified"] is False
    status = core.network_status()
    assert status["counterparty_attested_jobs"] == 1
    assert status["counterparty_attested_volume_minor"] == 400
    assert core.get_work(work["work_id"])["status"] == "COMPLETED"


def test_production_hub_receipt_is_required_before_completion(core):
    buyer_key, seller_key, work, _, _ = full_awarded(core)
    core.hub_required = True
    core._settlement_verifier = lambda event: (_ for _ in ()).throw(
        RuntimeError("money primitive not found"))
    assert attest(core, "buyer-agent", buyer_key, work["work_id"],
                  "buyer")["status"] == "ok"
    refused = attest(core, "seller-agent", seller_key, work["work_id"],
                     "seller")
    assert refused["status"] == "error"
    assert refused["error_type"] == "SettlementVerificationError"
    assert core.get_work(work["work_id"])["status"] == "ACCEPTED_PAYMENT_DUE"
    assert core.network_status()["independently_verified_jobs"] == 0

    def verified(event):
        return {"verified": True, "event_id": event["event_id"],
                "work_id": event["work"]["work_id"],
                "money_primitive": {"tx_hash": event["settlement"]["reference"]}}

    core._settlement_verifier = verified
    retried = attest(core, "seller-agent", seller_key, work["work_id"],
                     "seller")
    assert retried["status"] == "ok"
    assert retried["data"]["status"] == "INDEPENDENTLY_VERIFIED"
    assert retried["data"]["independently_verified"] is True
    assert retried["data"]["hub_receipt"]["verified"] is True
    assert core.network_status()["independently_verified_jobs"] == 1


def test_hub_required_fixed_x402_offer_cannot_claim_custom_job_amount(core):
    buyer_key, _ = register(core, "fixed-buyer", "procurement")
    seller_key, _ = register(core, "fixed-seller", "carbon")
    work = post_work(core, "fixed-buyer", buyer_key)
    core.hub_required = True
    body = {
        "work_id": work["work_id"], "amount_minor": 400, "currency": "USD",
        "proposal": "custom job cannot use a fifty-cent fixed endpoint",
        "delivery_seconds": 3600,
        "settlement": {
            "rail": "x402",
            "payment_endpoint": "https://agents.example.com/fixed-seller/x402/run",
            "network": "eip155:8453", "asset": "USDC",
        },
        "idempotency_key": "fixed-price-offer",
    }
    refused = run(core.process(signed_input(
        "submit_offer", "seller_id", "fixed-seller", seller_key, body,
        "fixed-price-offer-nonce")))
    assert refused["status"] == "error"
    assert refused["error_type"] == "ConflictError"
    assert "fixed route price" in refused["message"]


def test_mismatched_counterparty_attestation_cannot_mark_paid(core):
    buyer_key, seller_key, work, _, _ = full_awarded(core)
    assert attest(core, "buyer-agent", buyer_key, work["work_id"], "buyer")["status"] == "ok"
    body = {"work_id": work["work_id"], "rail": "x402", "amount_minor": 400,
            "currency": "USD", "reference": "0x" + "cd" * 32,
            "evidence_url": "https://basescan.org/tx/0x" + "cd" * 32,
            "idempotency_key": "settlement-seller-mismatch"}
    mismatch = run(core.process(signed_input(
        "attest_settlement", "agent_id", "seller-agent", seller_key, body,
        "settlement-seller-mismatch-nonce")))
    assert mismatch["status"] == "error"
    assert mismatch["error_type"] == "ConflictError"
    assert core.network_status()["counterparty_attested_jobs"] == 0


def test_wrong_actor_cannot_award_or_deliver(core):
    buyer_key, _ = register(core, "auth-buyer", "procurement")
    seller_key, _ = register(core, "auth-seller", "carbon")
    attacker_key, _ = register(core, "auth-attacker", "carbon")
    work = post_work(core, "auth-buyer", buyer_key)
    bid = offer(core, "auth-seller", seller_key, work["work_id"])
    body = {"work_id": work["work_id"], "offer_id": bid["offer_id"],
            "idempotency_key": "attacker-award-0001"}
    denied = run(core.process(signed_input(
        "award_offer", "buyer_id", "auth-attacker", attacker_key, body,
        "attacker-award-nonce")))
    assert denied["error_type"] == "AuthenticationError"
    assert core.get_work(work["work_id"])["status"] == "OPEN"


def test_delivery_compute_and_proof_evidence_is_signed_and_durable(core):
    buyer_key, _ = register(core, "evidence-buyer", "procurement")
    seller_key, _ = register(core, "evidence-seller", "carbon")
    work = post_work(core, "evidence-buyer", buyer_key)
    bid = offer(core, "evidence-seller", seller_key, work["work_id"])
    award(core, "evidence-buyer", buyer_key, work["work_id"], bid["offer_id"])
    digest = hashlib.sha256(b"evidenced delivery").hexdigest()
    body = {
        "work_id": work["work_id"],
        "artifact_url": "https://artifacts.example.com/evidenced.json",
        "content_sha256": digest, "summary": "Measured delivery.",
        "idempotency_key": "evidenced-delivery",
        "compute_evidence": {"power_w": 12.5, "duration_s": 4,
                             "source": "seller_measured"},
        "proofs": {"notary_commitment_id": "ncm_1234567890abcdef"},
    }
    result = run(core.process(signed_input(
        "submit_delivery", "seller_id", "evidence-seller", seller_key, body,
        "evidenced-delivery-nonce")))
    assert result["status"] == "ok"
    restored = core.get_work(work["work_id"])["delivery"]
    assert restored["compute_evidence"]["power_w"] == 12.5
    assert restored["proofs"]["notary_commitment_id"].startswith("ncm_")


def test_private_endpoints_and_unapproved_rails_are_refused(core):
    private, public = keys()
    payload = profile_payload("ssrf-agent", private, public)
    payload["endpoint"] = "http://127.0.0.1/admin"
    body = {key: value for key, value in payload.items()
            if key not in {"action", "agent_id", "auth"}}
    payload["auth"] = auth(private, "publish_profile", "ssrf-agent", body,
                           "ssrf-profile-nonce")
    rejected = run(core.process(payload))
    assert rejected["status"] == "error"
    assert rejected["field"] == "endpoint"


def test_seeded_profiles_are_discoverable_but_not_externally_mutable(core):
    changed = core.seed_owned_profiles([{
        "agent_id": "viridis-seeded-agent", "name": "Viridis Seeded Agent",
        "description": "Operator verified carbon service listing.",
        "capabilities": ["carbon"],
        "representative_queries": ["carbon service"],
        "endpoint": "https://mcp.viridisconservation.com/ghg-ledger/mcp",
        "payment": {"x402_endpoint": "https://mcp.viridisconservation.com/x402/ghg-ledger/calculate_inventory",
                    "price_minor": 100, "currency": "USD"},
    }])
    assert changed == 1
    assert core.search_agents("carbon")["results"][0]["auth_mode"] == "operator_managed"
    key, public = keys()
    attempted = run(core.process(profile_payload(
        "viridis-seeded-agent", key, public,
        idem="overwrite-seed", nonce="overwrite-seed-nonce")))
    assert attempted["status"] == "error"
    assert attempted["error_type"] == "ConflictError"


def test_durable_before_ack_survives_restart(tmp_path):
    path = tmp_path / "durable.sqlite3"
    first = MarketNetworkCore(db_path=str(path), now_fn=lambda: NOW)
    key, _ = register(first, "durable-buyer", "procurement")
    posted = post_work(first, "durable-buyer", key)
    first.close()
    second = MarketNetworkCore(db_path=str(path), now_fn=lambda: NOW)
    try:
        restored = second.get_work(posted["work_id"])
        assert restored["status"] == "OPEN"
        assert second.network_status()["events_total"] >= 2
    finally:
        second.close()


def test_prepare_signature_contract_and_description(core):
    body = {"query": "carbon", "capabilities": ["carbon"],
            "ttl_days": 14, "idempotency_key": "prepare-0001"}
    prepared = core.prepare_signature(
        "subscribe_work", "signing-agent", "prepare-nonce-0001",
        NOW.isoformat(), body)
    decoded = json.loads(prepared["canonical"])
    assert decoded["protocol"] == "viridis-agent-market-v1"
    assert decoded["body"] == body
    described = core.describe()
    assert described["payment_posture"]["moves_money"] is False
    assert described["security"]["private_keys"] == "never accepted or stored"


def test_source_has_no_payment_or_callback_credential_path():
    source = (Path(__file__).parents[1] / "src" / "core.py").read_text()
    forbidden = ["STRIPE_API_KEY", "CDP_API_KEY", "X402_FACILITATOR",
                 "PRIVATE_KEY", "urlopen(", "requests.", "httpx."]
    assert all(token not in source for token in forbidden)
