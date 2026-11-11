"""VCX authorization reuses actual signed Market Network identities."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

AGENT = Path(__file__).resolve().parents[1]
if str(AGENT) not in sys.path:
    sys.path.insert(0, str(AGENT))

from client import AgentMarketSigner
from src.core import MarketNetworkCore
from vcx.identity import MarketIdentity


@pytest.fixture
def identity_market(tmp_path):
    clock = [datetime(2026, 11, 10, 20, tzinfo=timezone.utc)]
    market = MarketNetworkCore(db_path=str(tmp_path / "market.sqlite3"),
                               now_fn=lambda: clock[0])
    signer = AgentMarketSigner.generate_ephemeral()
    body = {
        "name": "Synthetic VCX participant",
        "description": "Synthetic profile for local authorization tests.",
        "capabilities": ["integer-sum"],
        "representative_queries": [],
        "endpoint": "https://vcx-example.test/identity/mcp",
        "public_key_b64": signer.public_key_b64,
        "payment": {},
        "operator_entity": "Self-declared Example Operator",
        "ttl_days": 1,
        "idempotency_key": "identity-profile-0001",
    }
    auth = signer.auth("publish_profile", "identity-test", body,
                       signed_at=clock[0].isoformat())
    response = asyncio.run(market.process({
        "action": "publish_profile", "agent_id": "identity-test",
        **body, "auth": auth,
    }))
    assert response["status"] == "ok", response
    yield MarketIdentity(market), market, signer, clock, response["data"]
    market.close()


def signed_request(signer, clock, *, action="vcx.authorize_compute", actor="identity-test"):
    body = {"job_id": "vcx-example", "idempotency_key": "authorization-0001"}
    auth = signer.auth(action, actor, body, signed_at=clock[0].isoformat())
    return action, actor, body, auth


def test_actual_signed_profile_authorization_and_public_field_boundary(identity_market):
    identity, _, signer, clock, _ = identity_market
    public = identity.verify(*signed_request(signer, clock), clock[0])
    assert public == identity.profile("identity-test")
    assert set(public) == {
        "agent_id", "did", "profile_sha256", "capabilities",
        "expires_at", "public_key_b64",
    }
    assert public["public_key_b64"] == signer.public_key_b64
    assert public["capabilities"] == ["integer-sum"]
    assert public["did"].startswith("did:viridis:")
    assert len(public["profile_sha256"]) == 64


def test_signed_profile_is_not_verified_legal_identity(identity_market):
    identity, _, _, _, raw_profile = identity_market
    assert raw_profile["operator_entity"] == "Self-declared Example Operator"
    assert raw_profile["operator_entity_verified"] is False
    public = identity.profile("identity-test")
    assert "operator_entity_verified" not in public
    assert "operator_entity" not in public
    assert "legal_identity_verified" not in public


@pytest.mark.parametrize("change", ["actor", "action", "body", "signer", "signature"])
def test_wrong_authorization_rejected_without_echo(identity_market, change):
    identity, _, signer, clock, _ = identity_market
    action, actor, body, auth = signed_request(signer, clock)
    if change == "actor":
        actor = "unknown-actor"
    elif change == "action":
        action = "vcx.cancel_compute"
    elif change == "body":
        body["private_key"] = "secret-identity-canary"
    elif change == "signer":
        auth = AgentMarketSigner.generate_ephemeral().auth(
            action, actor, body, signed_at=clock[0].isoformat())
    else:
        auth["signature"] = "secret-identity-canary"
    with pytest.raises(ValueError) as error:
        identity.verify(action, actor, body, auth, clock[0])
    assert "secret-identity-canary" not in str(error.value)
    assert "private_key" not in str(error.value)


@pytest.mark.parametrize("delta", [-301, 301])
def test_stale_or_future_timestamp_rejected(identity_market, delta):
    identity, _, signer, clock, _ = identity_market
    action, actor, body, _ = signed_request(signer, clock)
    auth = signer.auth(action, actor, body,
                       signed_at=(clock[0] + timedelta(seconds=delta)).isoformat())
    with pytest.raises(ValueError):
        identity.verify(action, actor, body, auth, clock[0])


def test_passed_exchange_clock_and_profile_expiry_are_enforced(identity_market):
    identity, _, signer, clock, _ = identity_market
    request = signed_request(signer, clock)
    with pytest.raises(ValueError):
        identity.verify(*request, clock[0] + timedelta(seconds=301))
    clock[0] += timedelta(days=1, seconds=1)
    with pytest.raises(ValueError):
        identity.profile("identity-test")
    with pytest.raises(ValueError):
        identity.verify(*signed_request(signer, clock), clock[0])


@pytest.mark.parametrize("auth_mode", ["operator_managed", "unknown"])
def test_unsigned_or_unknown_profile_mode_cannot_authorize(identity_market, auth_mode):
    identity, market, signer, clock, _ = identity_market
    market._conn.execute("UPDATE profiles SET auth_mode=? WHERE agent_id=?",
                         (auth_mode, "identity-test"))
    with pytest.raises(ValueError):
        identity.profile("identity-test")
    with pytest.raises(ValueError):
        identity.verify(*signed_request(signer, clock), clock[0])


def test_revoked_market_profile_cannot_authorize(identity_market):
    identity, market, signer, clock, _ = identity_market
    market._conn.execute("UPDATE profiles SET status='REVOKED' WHERE agent_id=?",
                         ("identity-test",))
    with pytest.raises(ValueError):
        identity.verify(*signed_request(signer, clock), clock[0])


def test_identity_adapter_does_not_consume_exchange_nonces(identity_market):
    identity, market, signer, clock, _ = identity_market
    request = signed_request(signer, clock)
    before = market._conn.execute("SELECT count(*) FROM nonces").fetchone()[0]
    first = identity.verify(*request, clock[0].timestamp())
    assert identity.verify(*request, clock[0]) == first
    assert market._conn.execute("SELECT count(*) FROM nonces").fetchone()[0] == before
