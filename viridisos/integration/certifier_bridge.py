"""Phase 2 (ViridisOS-side unification) — adopt the shared TrustRoot and emit mark envelopes.

Wires the existing L3 Certifier to the one root, and adapts both a conservation Certificate and
an agent event into the single mark-stamped Envelope format. NO fleet code is touched in Phase 2;
toll equivalence is proven read-only in the acceptance suite. Additive only, stdlib only.

IMPLEMENT ME — see PHASE2_SPEC.md.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from certification.certifier import Certifier
from certification.claim import Certificate
from certification.standard import STANDARD
from runtime.canon_resolver import CanonResolver
from .trust_root import TrustRoot
from .mark import Envelope, MARK, issue_envelope

# Required claim.* fields per the Certification Standard (strip the "claim." prefix).
_REQUIRED_CLAIM_FIELDS = tuple(
    f.split("claim.", 1)[1] for f in STANDARD["required_certificate_fields"] if f.startswith("claim.")
)


def unified_certifier(root: Optional[TrustRoot] = None,
                      resolver: Optional[CanonResolver] = None) -> Certifier:
    """Return a Certifier whose signer IS the shared TrustRoot (conservation certs sign under the
    one root). Existing Certifier behavior is unchanged (U-5). Pass `resolver` through if given."""
    shared_root = root if root is not None else TrustRoot()
    return Certifier(resolver=resolver, signer=shared_root)


def certificate_to_envelope(cert: Certificate) -> Envelope:
    """Adapt a conservation Certificate into the unified Envelope (profile 'conservation-claim').

    payload = asdict(cert.claim); signature/key_id come from the cert; root_id = TrustRoot.root_id;
    mark = MARK. Because the Certifier signed canonical(asdict(claim)) under the shared root, the
    resulting envelope verifies under verify_mark with the same root. Do NOT re-sign."""
    return Envelope(
        payload=asdict(cert.claim),
        profile="conservation-claim",
        root_id=TrustRoot.root_id,
        key_id=cert.key_id,
        signature=cert.signature,
        mark=MARK,
    )


def agent_attestation(root: TrustRoot, event: dict) -> Envelope:
    """Issue an agent-attestation envelope under the same root (thin wrapper over issue_envelope)."""
    return issue_envelope(root, "agent-attestation", event)


def conservation_validator(payload: dict) -> bool:
    """Standard-field validator for verify_mark: True iff every required claim.* field is present.
    (Deep recompute stays in Certifier.verify; the mark attests 'was certified under the standard'.)"""
    return isinstance(payload, dict) and all(field in payload for field in _REQUIRED_CLAIM_FIELDS)
