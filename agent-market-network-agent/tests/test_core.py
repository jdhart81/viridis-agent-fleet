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


def usefulness(core, buyer_id, private, work_id, *, outcome="USEFUL",
               would_buy_again=True, note_sha256="", suffix="one"):
    body = {
        "work_id": work_id,
        "outcome": outcome,
        "would_buy_again": would_buy_again,
        "note_sha256": note_sha256,
        "idempotency_key": f"usefulness-{suffix}-0001",
    }
    return run(core.process(signed_input(
        "submit_usefulness_feedback", "buyer_id", buyer_id, private, body,
        f"usefulness-{suffix}-nonce-0001")))


def security_attest(core, attester_id, private, target_agent_id, *,
                    posture="SCANNED", suffix="scan", ttl_days=30):
    evidence_sha = hashlib.sha256(
        f"security-report:{attester_id}:{target_agent_id}:{suffix}".encode()
    ).hexdigest()
    body = {
        "target_agent_id": target_agent_id,
        "posture": posture,
        "coverage": ["mcp-tools", "prompt-inputs"],
        "scanner": {"name": "viridis-injection-detector", "version": "0.1.0"},
        "result_counts": {"checks": 12, "passed": 11, "warnings": 1,
                          "findings": 0, "errors": 0},
        "claim_boundary": (
            "Covers the named MCP tools and supplied prompt inputs only; "
            "does not prove the target vulnerability-free."),
        "evidence_url": f"https://evidence.example.com/{target_agent_id}/{suffix}.json",
        "evidence_sha256": evidence_sha,
        "ttl_days": ttl_days,
        "idempotency_key": f"security-{suffix}-0001",
    }
    return run(core.process(signed_input(
        "publish_security_attestation", "attester_id", attester_id,
        private, body, f"security-{suffix}-nonce-0001")))


def security_receipt(private, issuer_id, target_agent_id, *,
                     issued=NOW, suffix="one"):
    unsigned = {
        "protocol": "viridis-security-receipt-v1",
        "issuer_id": issuer_id,
        "subject_agent_id": target_agent_id,
        "posture": "SCANNED",
        "coverage": ["supplied-prompt-input", "tool-injection"],
        "scanner": {"name": "viridis-injection-detector", "version": "0.1.0"},
        "result_counts": {"checks": 4, "passed": 1, "warnings": 0,
                          "findings": 0, "errors": 0},
        "claim_boundary": (
            "Covers only the supplied prompt input and named detector signals; "
            "it does not certify the target agent as secure or vulnerability-free."),
        "evidence_sha256": hashlib.sha256(
            f"security-result:{target_agent_id}:{suffix}".encode()).hexdigest(),
        "issued_at": issued.isoformat(),
        "expires_at": (issued + timedelta(days=30)).isoformat(),
    }
    stable = lambda value: json.dumps(  # noqa: E731
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    receipt_id = "vsr_" + hashlib.sha256(stable(unsigned).encode()).hexdigest()[:24]
    receipt = {
        **unsigned,
        "receipt_id": receipt_id,
        "evidence_url": (
            f"https://mcp.viridis-security.com/v1/security/receipts/{receipt_id}"),
    }
    signature = b64(private.sign(stable(receipt).encode()))
    return receipt, signature


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


def test_signed_security_attestation_is_expiring_evidence_not_a_guarantee(core):
    _, _ = register(core, "guarded-agent", "agent-security")
    attester_key, _ = register(core, "security-attester", "security-assessment")
    result = security_attest(
        core, "security-attester", attester_key, "guarded-agent")
    assert result["status"] == "ok", result
    attestation = result["data"]
    assert attestation["posture"] == "SCANNED"
    assert attestation["relation"] == "THIRD_PARTY_ATTESTER"
    assert attestation["market_verdict"].startswith("coverage evidence only")
    assert attestation["evidence_sha256"] == hashlib.sha256(
        b"security-report:security-attester:guarded-agent:scan").hexdigest()

    listed = core.list_security_attestations(
        target_agent_id="guarded-agent")
    assert listed["count"] == 1
    assert "not a guarantee" in listed["claim_boundary"]

    found = core.search_agents(
        security_posture="SCANNED", security_attester="security-attester")
    assert [item["agent_id"] for item in found["results"]] == ["guarded-agent"]
    posture = found["results"][0]["security_posture"]
    assert posture["status"] == "COVERAGE_REPORTED"
    assert posture["coverage_score"] == 1
    assert posture["third_party_attesters"] == ["security-attester"]


def test_security_attestation_expires_and_drops_out_of_discovery(tmp_path):
    clock = [NOW]
    item = MarketNetworkCore(db_path=str(tmp_path / "security.sqlite3"),
                             now_fn=lambda: clock[0])
    try:
        _, _ = register(item, "expiring-target", "agent-security")
        attester_key, _ = register(item, "expiring-attester", "security-assessment")
        assert security_attest(
            item, "expiring-attester", attester_key, "expiring-target",
            ttl_days=1)["status"] == "ok"
        assert item.list_security_attestations(
            target_agent_id="expiring-target")["count"] == 1
        clock[0] = NOW + timedelta(days=2)
        assert item.list_security_attestations(
            target_agent_id="expiring-target")["count"] == 0
        assert item.search_agents(
            security_posture="SCANNED")["count"] == 0
    finally:
        item.close()


def test_signed_security_receipt_import_is_exactly_once_and_related_party(tmp_path):
    issuer_private, issuer_public = keys()
    item = MarketNetworkCore(
        db_path=str(tmp_path / "receipts.sqlite3"), now_fn=lambda: NOW,
        trusted_security_receipt_keys={
            "viridis-security-injection-detector": issuer_public})
    try:
        item.seed_owned_profiles([
            {"agent_id": "viridis-security-injection-detector",
             "name": "Viridis Security Injection Detector",
             "description": "Operator-owned security result receipt issuer.",
             "capabilities": ["security-assessment"],
             "representative_queries": ["scan an agent"],
             "endpoint": "https://mcp.viridis-security.com/mcp",
             "payment": {}, "operator_entity": "ViridisNorth LLC"},
            {"agent_id": "viridis-ghg-ledger", "name": "Viridis GHG Ledger",
             "description": "Operator-owned greenhouse gas inventory agent.",
             "capabilities": ["carbon"],
             "representative_queries": ["calculate GHG"],
             "endpoint": "https://mcp.viridisconservation.com/ghg-ledger/mcp",
             "payment": {}, "operator_entity": "ViridisNorth LLC"},
        ])
        receipt, signature = security_receipt(
            issuer_private, "viridis-security-injection-detector",
            "viridis-ghg-ledger")
        first = run(item.process({"action": "import_security_receipt",
                                  "receipt": receipt,
                                  "signature_b64": signature}))
        assert first["status"] == "ok", first
        assert first["data"]["relation"] == "COMMON_CONTROL_RELATED"
        assert first["data"]["provenance"] == "signed_security_result_receipt"
        assert first["data"]["replayed"] is False
        again = run(item.process({"action": "import_security_receipt",
                                  "receipt": receipt,
                                  "signature_b64": signature}))
        assert again["status"] == "ok"
        assert again["data"]["replayed"] is True
        assert item.network_status()["security_receipts_imported"] == 1
        posture = item.search_agents(
            security_posture="SCANNED")["results"][0]["security_posture"]
        assert posture["third_party_attesters"] == []
        assert posture["related_party_attesters"] == [
            "viridis-security-injection-detector"]
    finally:
        item.close()


def test_security_receipt_tamper_unknown_issuer_and_expiry_fail_closed(tmp_path):
    issuer_private, issuer_public = keys()
    item = MarketNetworkCore(
        db_path=str(tmp_path / "receipt-errors.sqlite3"), now_fn=lambda: NOW,
        trusted_security_receipt_keys={
            "viridis-security-injection-detector": issuer_public})
    try:
        item.seed_owned_profiles([
            {"agent_id": "viridis-security-injection-detector", "name": "Issuer",
             "description": "Operator-owned security receipt issuer.",
             "capabilities": ["security"], "representative_queries": [],
             "endpoint": "https://mcp.viridis-security.com/mcp", "payment": {}},
            {"agent_id": "viridis-target-agent", "name": "Target",
             "description": "Operator-owned target agent for receipt validation.",
             "capabilities": ["target"], "representative_queries": [],
             "endpoint": "https://mcp.viridisconservation.com/target/mcp", "payment": {}},
        ])
        receipt, signature = security_receipt(
            issuer_private, "viridis-security-injection-detector",
            "viridis-target-agent")
        tampered = {**receipt, "posture": "RUNTIME_GUARDED"}
        rejected = run(item.process({"action": "import_security_receipt",
                                     "receipt": tampered,
                                     "signature_b64": signature}))
        assert rejected["status"] == "error"
        assert rejected["error_type"] == "AuthenticationError"

        expired, expired_sig = security_receipt(
            issuer_private, "viridis-security-injection-detector",
            "viridis-target-agent", issued=NOW - timedelta(days=31),
            suffix="expired")
        rejected = run(item.process({"action": "import_security_receipt",
                                     "receipt": expired,
                                     "signature_b64": expired_sig}))
        assert rejected["status"] == "error"
        assert rejected["field"] == "receipt.expires_at"
    finally:
        item.close()


def test_security_receipt_exactly_once_state_survives_restart(tmp_path):
    issuer_private, issuer_public = keys()
    path = tmp_path / "receipt-restart.sqlite3"
    trusted = {"viridis-security-injection-detector": issuer_public}
    receipt, signature = security_receipt(
        issuer_private, "viridis-security-injection-detector",
        "viridis-restart-target", suffix="restart")
    profiles = [
        {"agent_id": "viridis-security-injection-detector", "name": "Issuer",
         "description": "Operator-owned security receipt issuer.",
         "capabilities": ["security"], "representative_queries": [],
         "endpoint": "https://mcp.viridis-security.com/mcp", "payment": {}},
        {"agent_id": "viridis-restart-target", "name": "Target",
         "description": "Operator-owned target for durable receipt import.",
         "capabilities": ["target"], "representative_queries": [],
         "endpoint": "https://mcp.viridisconservation.com/target/mcp", "payment": {}},
    ]
    first = MarketNetworkCore(
        db_path=str(path), now_fn=lambda: NOW,
        trusted_security_receipt_keys=trusted)
    first.seed_owned_profiles(profiles)
    imported = run(first.process({"action": "import_security_receipt",
                                  "receipt": receipt,
                                  "signature_b64": signature}))
    assert imported["status"] == "ok"
    first.close()

    restored = MarketNetworkCore(
        db_path=str(path), now_fn=lambda: NOW,
        trusted_security_receipt_keys=trusted)
    try:
        replay = run(restored.process({"action": "import_security_receipt",
                                       "receipt": receipt,
                                       "signature_b64": signature}))
        assert replay["status"] == "ok"
        assert replay["data"]["replayed"] is True
        assert restored.network_status()["security_receipts_imported"] == 1
    finally:
        restored.close()


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


def test_usefulness_requires_buyer_signature_and_independent_payment_proof(core):
    buyer_key, seller_key, work, _, _ = full_awarded(core)
    core.hub_required = True

    before_payment = usefulness(
        core, "buyer-agent", buyer_key, work["work_id"], suffix="before")
    assert before_payment["status"] == "error"
    assert before_payment["error_type"] == "ConflictError"
    assert core.network_status()["buyer_signed_useful_paid_deliveries"] == 0

    core._settlement_verifier = lambda event: {
        "verified": True, "event_id": event["event_id"],
        "work_id": event["work"]["work_id"],
        "money_primitive": {"tx_hash": event["settlement"]["reference"]},
    }
    assert attest(core, "buyer-agent", buyer_key, work["work_id"],
                  "buyer")["status"] == "ok"
    assert attest(core, "seller-agent", seller_key, work["work_id"],
                  "seller")["data"]["status"] == "INDEPENDENTLY_VERIFIED"

    attacker_key, _ = register(core, "feedback-attacker", "procurement")
    attacked = usefulness(
        core, "feedback-attacker", attacker_key, work["work_id"],
        suffix="attacker")
    assert attacked["status"] == "error"
    assert attacked["error_type"] == "AuthenticationError"

    core._conn.execute(
        "UPDATE profiles SET operator_entity=?,operator_entity_verified=1 "
        "WHERE agent_id='buyer-agent'", ("Independent Buyer LLC",))
    core._conn.execute(
        "UPDATE profiles SET operator_entity=?,operator_entity_verified=1 "
        "WHERE agent_id='seller-agent'", ("Independent Seller LLC",))
    note_digest = hashlib.sha256(b"private buyer note").hexdigest()
    accepted = usefulness(
        core, "buyer-agent", buyer_key, work["work_id"],
        note_sha256=note_digest, suffix="accepted")
    assert accepted["status"] == "ok"
    assert accepted["data"]["provenance"] == (
        "buyer_signed_independently_verified_paid_job")
    assert accepted["data"]["note_sha256"] == note_digest
    assert "private buyer note" not in json.dumps(accepted)
    assert core.get_work(work["work_id"])["buyer_feedback"] == {
        key: accepted["data"][key] for key in (
            "feedback_id", "work_id", "buyer_id", "seller_id", "outcome",
            "useful", "would_buy_again", "note_sha256", "created_at",
            "buyer_seller_relation", "independent_buyer", "provenance")
    }
    status = core.network_status()
    assert status["buyer_feedback_jobs"] == 1
    assert status["buyer_signed_useful_paid_deliveries"] == 1
    assert status["independently_useful_paid_deliveries"] == 1
    assert status["would_buy_again_count"] == 1
    seller = next(item for item in core.search_agents()["results"]
                  if item["agent_id"] == "seller-agent")
    assert seller["market_reputation"][
        "buyer_signed_useful_paid_deliveries"] == 1
    assert seller["market_reputation"][
        "independently_useful_paid_deliveries"] == 1


def test_usefulness_is_exactly_once_private_and_idempotent(core):
    buyer_key, seller_key, work, _, _ = full_awarded(core)
    core.hub_required = True
    core._settlement_verifier = lambda event: {
        "verified": True, "event_id": event["event_id"],
        "work_id": event["work"]["work_id"],
    }
    attest(core, "buyer-agent", buyer_key, work["work_id"], "buyer")
    attest(core, "seller-agent", seller_key, work["work_id"], "seller")
    first = usefulness(
        core, "buyer-agent", buyer_key, work["work_id"],
        outcome="PARTIALLY_USEFUL", would_buy_again=False, suffix="same")
    replay = usefulness(
        core, "buyer-agent", buyer_key, work["work_id"],
        outcome="PARTIALLY_USEFUL", would_buy_again=False, suffix="same")
    assert replay == first
    changed = usefulness(
        core, "buyer-agent", buyer_key, work["work_id"],
        outcome="USEFUL", would_buy_again=True, suffix="changed")
    assert changed["status"] == "error"
    assert changed["error_type"] == "ConflictError"
    assert core.network_status()["buyer_feedback_jobs"] == 1
    event = core._conn.execute(
        "SELECT payload_json FROM events "
        "WHERE event_type='work.usefulness_reported'").fetchone()
    assert event is not None
    event_payload = json.loads(event["payload_json"])
    assert "note" not in event_payload
    assert event_payload["note_sha256"] == ""


def test_related_party_usefulness_cannot_inflate_independent_demand(core):
    buyer_key, seller_key, work, _, _ = full_awarded(core)
    core.hub_required = True
    core._settlement_verifier = lambda event: {
        "verified": True, "event_id": event["event_id"],
        "work_id": event["work"]["work_id"],
    }
    attest(core, "buyer-agent", buyer_key, work["work_id"], "buyer")
    attest(core, "seller-agent", seller_key, work["work_id"], "seller")
    core._conn.execute(
        "UPDATE profiles SET operator_entity='Same Operator LLC',"
        "operator_entity_verified=1 WHERE agent_id IN "
        "('buyer-agent','seller-agent')")
    result = usefulness(
        core, "buyer-agent", buyer_key, work["work_id"],
        outcome="USEFUL", would_buy_again=True, suffix="related")
    assert result["status"] == "ok"
    assert result["data"]["buyer_seller_relation"] == "COMMON_CONTROL_RELATED"
    assert result["data"]["independent_buyer"] is False
    status = core.network_status()
    assert status["buyer_signed_useful_paid_deliveries"] == 1
    assert status["independently_useful_paid_deliveries"] == 0


def test_usefulness_rejects_free_text_and_non_boolean_repurchase(core):
    buyer_key, _, work, _, _ = full_awarded(core)
    bad_digest = usefulness(
        core, "buyer-agent", buyer_key, work["work_id"],
        note_sha256="raw customer note", suffix="raw-note")
    assert bad_digest["status"] == "error"
    assert bad_digest["field"] == "note_sha256"
    bad_bool = usefulness(
        core, "buyer-agent", buyer_key, work["work_id"],
        would_buy_again=1, suffix="bad-bool")
    assert bad_bool["status"] == "error"
    assert bad_bool["field"] == "would_buy_again"


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


def test_energyai_seed_profile_exposes_conversion_and_bounty_path():
    payload = json.loads((Path(__file__).parents[1] / "seed_profiles.json").read_text())
    energyai = next(p for p in payload["profiles"] if p["agent_id"] == "viridis-energyai")
    assert energyai["endpoint"] == "https://api.energyaisolution.com/mcp"
    assert "homeowner-lead-routing" in energyai["capabilities"]
    assert "get_quote_link" in energyai["description"]
    assert "20% bounty" in energyai["description"]
    assert energyai["payment"] == {}


def test_viridis_security_seed_keeps_auth_and_billing_on_its_own_runtime():
    payload = json.loads((Path(__file__).parents[1] / "seed_profiles.json").read_text())
    security = next(
        p for p in payload["profiles"]
        if p["agent_id"] == "viridis-security-injection-detector")
    assert security["endpoint"] == "https://mcp.viridis-security.com/mcp"
    assert "prompt-injection-detection" in security["capabilities"]
    assert "API key" in security["description"]
    assert security["payment"] == {}
    assert security["operator_entity"] == "ViridisNorth LLC"
    ids = {item["agent_id"] for item in payload["profiles"]}
    assert "viridis-security-canon-scanner" in ids
    assert "viridis-security-maxwell" in ids
    for agent_id in {
            "viridis-security-canon-scanner", "viridis-security-maxwell"}:
        profile = next(p for p in payload["profiles"] if p["agent_id"] == agent_id)
        assert profile["endpoint"].startswith("https://mcp.viridis-security.com/")
        assert profile["payment"] == {}


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
