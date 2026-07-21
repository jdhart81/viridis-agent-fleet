from client import AgentMarketSigner
from src.core import MarketNetworkCore


def test_client_signer_interoperates_without_server_private_key(tmp_path):
    signer = AgentMarketSigner.generate_ephemeral()
    body = {
        "name": "Example Seller", "description": "Signed carbon service.",
        "capabilities": ["carbon"],
        "representative_queries": ["find carbon service"],
        "endpoint": "https://seller.example.com/mcp",
        "public_key_b64": signer.public_key_b64,
        "payment": {"x402_endpoint": "https://seller.example.com/x402/run"},
        "ttl_days": 90, "idempotency_key": "client-profile-0001",
    }
    core = MarketNetworkCore(db_path=str(tmp_path / "client.sqlite3"))
    try:
        auth = signer.auth("publish_profile", "example-seller", body)
        import asyncio
        result = asyncio.run(core.process({
            "action": "publish_profile", "agent_id": "example-seller",
            **body, "auth": auth,
        }))
        assert result["status"] == "ok"
        assert result["data"]["agent_id"] == "example-seller"
    finally:
        core.close()

