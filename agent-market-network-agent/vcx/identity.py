"""Narrow bridge to the existing signed Agent Market identity contract.

VCX does not mint identities or accept private keys. The caller owns replay
protection in its durable transaction: this adapter verifies a signature but
deliberately does not consume a Market Network nonce in a separate database.
It uses only the Market core's public extension-auth interface
(``extension_profile``, ``verify_extension_action``,
``extension_security_posture``), covered by a contract test.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class MarketIdentity:
    def __init__(self, market: Any):
        self.market = market

    @staticmethod
    def _time(value: Any) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError("an aware clock is required")
            return value.astimezone(timezone.utc)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value, timezone.utc)
        raise ValueError("an aware clock is required")

    def profile(self, actor_id: str) -> dict:
        # Payment destinations, signing configuration, private annotations and
        # operator evidence are never returned by the public interface.
        try:
            return self.market.extension_profile(actor_id)
        except Exception:
            raise ValueError("an active signed market profile is required") from None

    def security_posture(self, actor_id: str) -> dict:
        """Targeted current evidence; discovery pagination cannot affect eligibility."""
        return self.market.extension_security_posture(actor_id)

    def verify(self, action: str, actor_id: str, body: dict, auth: dict,
               now: Any) -> dict:
        """Verify existing canonical Ed25519 authorization without moving state.

        The exchange must consume ``auth.nonce`` and bind request idempotency
        in the same transaction as the authorized mutation. Public-key control
        does not assert independently verified operator identity.
        """
        try:
            return self.market.verify_extension_action(
                action, actor_id, body, auth, now=self._time(now))
        except Exception:
            # Market errors may include caller-controlled field names. Keep
            # the exchange error independent of secret-bearing caller input.
            raise ValueError("valid authorization from an active signed profile is required") from None
