"""Small agent-side signer helper for Viridis Agent Market writes.

This module belongs with the caller, not the server. It never sends a request
or writes a key to disk; the calling agent decides how its private key is held.
"""
from __future__ import annotations

import base64
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.core import canonical_action


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


class AgentMarketSigner:
    """Signs canonical marketplace actions with a caller-owned Ed25519 key."""

    def __init__(self, private_key: Ed25519PrivateKey):
        self._private_key = private_key

    @classmethod
    def generate_ephemeral(cls) -> "AgentMarketSigner":
        """Create an in-memory key. Production callers should use their vault."""
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_private_bytes(cls, value: bytes) -> "AgentMarketSigner":
        return cls(Ed25519PrivateKey.from_private_bytes(value))

    def private_bytes(self) -> bytes:
        """Export only when the caller intentionally stores the key securely."""
        return self._private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption())

    @property
    def public_key_b64(self) -> str:
        value = self._private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return _b64(value)

    def auth(self, action: str, actor_id: str, body: dict, *,
             nonce: Optional[str] = None,
             signed_at: Optional[str] = None) -> dict:
        nonce = nonce or "nonce-" + uuid.uuid4().hex
        signed_at = signed_at or datetime.now(timezone.utc).isoformat()
        message = canonical_action(
            action, actor_id, nonce, signed_at, body).encode()
        return {"nonce": nonce, "signed_at": signed_at,
                "signature": _b64(self._private_key.sign(message))}


def signer_from_env(name: str = "VIRIDIS_AGENT_MARKET_PRIVATE_KEY_B64") -> AgentMarketSigner:
    """Optional caller helper. The market server itself never reads this env."""
    raw = os.environ.get(name, "")
    if not raw:
        raise RuntimeError(f"{name} is not set")
    value = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    return AgentMarketSigner.from_private_bytes(value)

