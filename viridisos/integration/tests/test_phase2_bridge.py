"""Phase 2 acceptance — ViridisOS-side unification + fleet toll conformance (read-only).

House style: pure stdlib, self-contained runner. Run from the ViridisOS package root:
    python3 integration/tests/test_phase2_bridge.py
Green ("N passed, 0 failed") == Phase 2 done. DO NOT EDIT — implement certifier_bridge.py instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime.module import Module, Backing
from runtime.canon_resolver import CanonResolver
from certification.certifier import Certifier
from integration.trust_root import TrustRoot
from integration.mark import MARK, verify_mark, Envelope
from integration.toll import compute_toll, _ceil_bps
from integration.certifier_bridge import (
    unified_certifier, certificate_to_envelope, agent_attestation, conservation_validator,
)

# --- fixtures (mirror tests/test_certification.py) -------------------------
GOOD = "10.5281/zenodo.CERTGOOD"
RESOLVER = CanonResolver(entries={GOOD: {"verified": True, "lean_module": "Good"}})

class _Demo(Module):
    id = "demo"; name = "Demo"; line = "Test"; version = "1.0.0"
    backing = Backing(doi=GOOD, lean_module="Good", aristotle_id="a", verified=True)
    def compute(self, inputs):
        return {"score": round(inputs["x"] * 2.0, 6)}

# Fleet published protocol-margin schedule (esc-fee-v1, 2026-07-19). Source of truth for the take.
FLEET_MARGIN_BPS = {"new": 200, "connect_onboarded": 150, "connect_verified": 100}

# --- harness ---------------------------------------------------------------
_PASS = 0; _FAIL = 0
def check(name, cond):
    global _PASS, _FAIL
    if cond: _PASS += 1
    else: _FAIL += 1; print(f"  FAIL: {name}")


# --- P2-1 : Certifier signs under the shared root, behavior intact ---------
def p2_certifier_uses_shared_root():
    root = TrustRoot()
    c = unified_certifier(root, resolver=RESOLVER)
    m = _Demo(resolver=RESOLVER)
    inputs = {"x": 3.0}
    cert = c.issue(m, subject="parcel-42", inputs=inputs)
    check("P2-1 values intact", cert.claim.values == {"score": 6.0})
    check("P2-1 verify still True", c.verify(cert, m, inputs) is True)
    check("P2-1 signed by shared root key", cert.key_id == root.key_id)


# --- P2-2 : conservation Certificate -> unified Envelope, mark verifies ----
def p2_certificate_to_envelope():
    root = TrustRoot()
    c = unified_certifier(root, resolver=RESOLVER)
    m = _Demo(resolver=RESOLVER)
    cert = c.issue(m, subject="parcel-7", inputs={"x": 2.0})
    env = certificate_to_envelope(cert)
    check("P2-2 is Envelope", isinstance(env, Envelope))
    check("P2-2 profile conservation-claim", env.profile == "conservation-claim")
    check("P2-2 mark stamped", env.mark == MARK)
    check("P2-2 root_id shared", env.root_id == root.root_id)
    check("P2-2 verify_mark True", verify_mark(root, env, conservation_validator) is True)


# --- P2-3 : agent attestation under the same root, one root_id -------------
def p2_agent_attestation_same_root():
    root = TrustRoot()
    c = unified_certifier(root, resolver=RESOLVER)
    cert = c.issue(_Demo(resolver=RESOLVER), subject="p", inputs={"x": 1.0})
    cons_env = certificate_to_envelope(cert)
    agent_env = agent_attestation(root, {"did": "did:viridis:abc", "event": "delivered"})
    check("P2-3 agent mark verifies", verify_mark(root, agent_env, lambda _p: True) is True)
    check("P2-3 one root across profiles", cons_env.root_id == agent_env.root_id == root.root_id)


# --- P2-4 : tamper rejected -----------------------------------------------
def p2_tamper_rejected():
    root = TrustRoot()
    c = unified_certifier(root, resolver=RESOLVER)
    cert = c.issue(_Demo(resolver=RESOLVER), subject="p", inputs={"x": 1.0})
    env = certificate_to_envelope(cert)
    bad_payload = dict(env.payload); bad_payload["values"] = {"score": 999.0}
    tampered = Envelope(bad_payload, env.profile, env.root_id, env.key_id, env.signature, MARK)
    check("P2-4 tamper rejected", verify_mark(root, tampered, conservation_validator) is False)


# --- P2-5 : conservation_validator enforces standard fields ---------------
def p2_validator_enforces_fields():
    check("P2-5 empty payload invalid", conservation_validator({}) is False)
    full = {"subject": "p", "module_id": "demo", "values": {}, "backing_doi": "d",
            "lean_module": "L", "input_hashes": {}, "timestamp": "t"}
    check("P2-5 full payload valid", conservation_validator(full) is True)


# --- P2-6 : fleet toll conformance (read-only, protocol margin) ------------
def p2_toll_conformance():
    ok = True
    for tier, bps in FLEET_MARGIN_BPS.items():
        t = compute_toll(10_000, tier)
        if t["protocol_margin_bps"] != bps:
            ok = False
        # protocol margin (the Viridis take) matches ceil-bps of the schedule for sample amounts
        for amt in (1, 733, 10_000, 250_000):
            if compute_toll(amt, tier)["protocol_margin_minor"] != _ceil_bps(amt, bps):
                ok = False
    check("P2-6 protocol margin == fleet esc-fee-v1 schedule (all tiers)", ok)


TESTS = [
    p2_certifier_uses_shared_root, p2_certificate_to_envelope, p2_agent_attestation_same_root,
    p2_tamper_rejected, p2_validator_enforces_fields, p2_toll_conformance,
]

if __name__ == "__main__":
    for t in TESTS:
        try:
            t()
        except NotImplementedError:
            _FAIL += 1; print(f"  FAIL: {t.__name__} (NotImplementedError — stub not yet implemented)")
        except Exception as e:  # noqa: BLE001
            _FAIL += 1; print(f"  FAIL: {t.__name__} ({type(e).__name__}: {e})")
    print(f"{_PASS} passed, {_FAIL} failed")
    sys.exit(0 if _FAIL == 0 else 1)
