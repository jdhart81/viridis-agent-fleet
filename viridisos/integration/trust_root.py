"""U-1 One root. A single signing authority for BOTH certificate profiles.

TrustRoot satisfies the existing `certification.attestation.Signer` Protocol, so it drops
straight into `Certifier(signer=TrustRoot())`. Dev signing uses HmacSigner; production swaps
to the K3 signer without touching callers.

IMPLEMENT ME — see BUILD_SPEC.md §"integration/trust_root.py".
"""

from __future__ import annotations

import hashlib
from typing import Optional

from certification.attestation import Signer, HmacSigner


class TrustRoot:
    root_id: str = "viridis-root-v1"

    def __init__(self, signer: Optional[Signer] = None):
        self._signer: Signer = signer if signer is not None else HmacSigner()

    @property
    def key_id(self) -> str:
        return self._signer.key_id

    def sign(self, payload: bytes) -> str:
        return self._signer.sign(payload)

    def verify(self, payload: bytes, signature: str) -> bool:
        return self._signer.verify(payload, signature)

    def bind_did(self, agent_id: str, pubkey: str) -> str:
        """Reproduce the fleet DID exactly (identity core R1):
        did:viridis:<first16 hex of sha256("<agent_id>|<pubkey>")>."""
        digest = hashlib.sha256(f"{agent_id}|{pubkey}".encode()).hexdigest()
        return f"did:viridis:{digest[:16]}"
