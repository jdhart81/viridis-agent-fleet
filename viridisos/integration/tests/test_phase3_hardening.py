"""Phase 3 pre-deploy hardening — key-rotation guard + toll input validation.

Run from the ViridisOS package root:
    python3 integration/tests/test_phase3_hardening.py
Pure stdlib. Locks the two hardening fixes without weakening any prior suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from certification.attestation import HmacSigner
from integration.trust_root import TrustRoot
from integration.mark import MARK, Envelope, issue_envelope, verify_mark
from integration.toll import compute_toll

_PASS = 0; _FAIL = 0
def check(name, cond):
    global _PASS, _FAIL
    if cond: _PASS += 1
    else: _FAIL += 1; print(f"  FAIL: {name}")

def raises(fn, exc=Exception):
    try: fn(); return False
    except exc: return True
    except Exception: return False


# ---- H-1 : key-rotation guard --------------------------------------------
def h1_key_id_mismatch_rejected():
    root = TrustRoot()
    env = issue_envelope(root, "agent-attestation", {"did": "did:viridis:x", "event": "ok"})
    # an envelope claiming a different key_id must fail even if everything else lines up
    forged_kid = Envelope(env.payload, env.profile, env.root_id, "some-other-key", env.signature, MARK)
    check("H-1 key_id mismatch rejected", verify_mark(root, forged_kid, lambda _p: True) is False)

def h1_matching_key_id_still_valid():
    root = TrustRoot()
    env = issue_envelope(root, "conservation-claim", {"subject": "p", "value": 1})
    check("H-1 matching key_id still valid", verify_mark(root, env, lambda _p: True) is True)

def h1_second_root_different_key_rejected():
    root_a = TrustRoot(signer=HmacSigner(secret=b"A", key_id="key-A"))
    root_b = TrustRoot(signer=HmacSigner(secret=b"B", key_id="key-B"))
    env = issue_envelope(root_a, "agent-attestation", {"event": "x"})
    check("H-1 cross-root verify rejected", verify_mark(root_b, env, lambda _p: True) is False)


# ---- H-2 : toll input validation -----------------------------------------
def h2_negative_amount_raises():
    check("H-2 negative amount raises", raises(lambda: compute_toll(-1, "new"), ValueError))

def h2_non_int_amount_raises():
    check("H-2 non-int amount raises", raises(lambda: compute_toll(10.5, "new"), ValueError))

def h2_zero_amount_zero_fee():
    t = compute_toll(0, "connect_verified")
    check("H-2 zero amount -> zero fees",
          t["protocol_margin_minor"] == 0 and t["card_rail_cost_minor"] == 0 and t["total_fee_minor"] == 0)


TESTS = [
    h1_key_id_mismatch_rejected, h1_matching_key_id_still_valid, h1_second_root_different_key_rejected,
    h2_negative_amount_raises, h2_non_int_amount_raises, h2_zero_amount_zero_fee,
]

if __name__ == "__main__":
    for t in TESTS:
        try: t()
        except Exception as e:  # noqa: BLE001
            _FAIL += 1; print(f"  FAIL: {t.__name__} ({type(e).__name__}: {e})")
    print(f"{_PASS} passed, {_FAIL} failed")
    sys.exit(0 if _FAIL == 0 else 1)
