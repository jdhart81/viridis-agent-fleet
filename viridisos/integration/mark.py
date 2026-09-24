"""U-2/U-3 One envelope, one mark. "Certified by ViridisOS" spans both profiles.

The mark is the only enforceable claim: valid iff the payload passes its profile's standard
validator AND the signature verifies under the shared root. Guard it accordingly.

IMPLEMENT ME — see BUILD_SPEC.md §"integration/mark.py".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from runtime.provenance import canonical
from .trust_root import TrustRoot

MARK = "Certified by ViridisOS"
PROFILES = ("conservation-claim", "agent-attestation")


@dataclass(frozen=True)
class Envelope:
    payload: dict
    profile: str
    root_id: str
    key_id: str
    signature: str
    mark: str = ""


def canonical_bytes(payload: dict) -> bytes:
    """Canonical, signature-stable bytes. Reuse runtime.provenance.canonical."""
    return canonical(payload).encode("utf-8")


def issue_envelope(root: TrustRoot, profile: str, payload: dict) -> Envelope:
    """Sign canonical_bytes(payload) under `root`, stamp MARK, fill root_id/key_id.
    Raise on unknown profile."""
    if profile not in PROFILES:
        raise ValueError(f"unknown profile: {profile}")

    return Envelope(
        payload=payload,
        profile=profile,
        root_id=root.root_id,
        key_id=root.key_id,
        signature=root.sign(canonical_bytes(payload)),
        mark=MARK,
    )


def verify_mark(root: TrustRoot, env: Envelope, validator: Callable[[dict], bool]) -> bool:
    """True iff env.mark == MARK AND env.root_id == root.root_id AND validator(env.payload)
    AND root.verify(canonical_bytes(env.payload), env.signature). Never raises — return False
    on any failure."""
    try:
        return bool(
            env.mark == MARK
            and env.root_id == root.root_id
            and env.key_id == root.key_id          # key-rotation guard (hardening)
            and validator(env.payload)
            and root.verify(canonical_bytes(env.payload), env.signature)
        )
    except Exception:
        return False
