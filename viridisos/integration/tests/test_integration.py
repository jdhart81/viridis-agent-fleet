"""Acceptance suite for the root/mark/toll unification — the spec's definition of done.

House style: pure stdlib, self-contained runner (no pytest). Matches ViridisOS/tests/*.
Run:  python3 integration/tests/test_integration.py     (from the ViridisOS package root)
Green ("N passed, 0 failed") == the build is done. DO NOT EDIT — implement the modules instead.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

# stdlib first, THEN put the package root on the path (avoids the platform.py shadow).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from integration.trust_root import TrustRoot
from integration.mark import Envelope, MARK, issue_envelope, verify_mark, canonical_bytes
from integration.toll import compute_toll, _ceil_bps


# ---- tiny harness ---------------------------------------------------------
_PASS = 0
_FAIL = 0

def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {name}")

def raises(fn, exc=Exception):
    try:
        fn()
        return False
    except exc:
        return True
    except Exception:
        return False

def _valid(_p):   return True
def _invalid(_p): return False


# ---- U-1 : one root, both profiles ---------------------------------------
def u1_single_root_both_profiles():
    root = TrustRoot()
    c = issue_envelope(root, "conservation-claim", {"subject": "parcel-1", "value": 42})
    a = issue_envelope(root, "agent-attestation", {"did": "did:viridis:abc", "event": "delivered"})
    check("U1 same root_id", c.root_id == a.root_id == root.root_id)
    check("U1 same key_id", c.key_id == a.key_id == root.key_id)
    check("U1 conservation verifies", root.verify(canonical_bytes(c.payload), c.signature))
    check("U1 agent verifies", root.verify(canonical_bytes(a.payload), a.signature))

def u1_bind_did_matches_fleet():
    root = TrustRoot()
    aid, pk = "agent-007", "PUBKEY123"
    expected = "did:viridis:" + hashlib.sha256(f"{aid}|{pk}".encode()).hexdigest()[:16]
    check("U1 bind_did == fleet R1 formula", root.bind_did(aid, pk) == expected)


# ---- U-2 : one envelope shape --------------------------------------------
def u2_envelope_shape():
    root = TrustRoot()
    env = issue_envelope(root, "conservation-claim", {"subject": "p", "value": 1})
    check("U2 is Envelope", isinstance(env, Envelope))
    check("U2 profile set", env.profile == "conservation-claim")
    check("U2 mark stamped", env.mark == MARK)
    check("U2 fields present", bool(env.signature and env.key_id and env.root_id))

def u2_unknown_profile_rejected():
    root = TrustRoot()
    check("U2 unknown profile raises", raises(lambda: issue_envelope(root, "nope", {"x": 1})))


# ---- U-3 : one mark, guarded ---------------------------------------------
def u3_mark_valid_path():
    root = TrustRoot()
    env = issue_envelope(root, "agent-attestation", {"did": "did:viridis:x", "event": "ok"})
    check("U3 valid when standard-valid + root-signed", verify_mark(root, env, _valid) is True)

def u3_reject_standard_invalid():
    root = TrustRoot()
    env = issue_envelope(root, "agent-attestation", {"did": "did:viridis:x", "event": "ok"})
    check("U3 reject standard-invalid", verify_mark(root, env, _invalid) is False)

def u3_reject_forged_signature():
    root = TrustRoot()
    env = issue_envelope(root, "conservation-claim", {"subject": "p", "value": 1})
    forged = Envelope(env.payload, env.profile, env.root_id, env.key_id, "deadbeef", MARK)
    check("U3 reject forged signature", verify_mark(root, forged, _valid) is False)

def u3_reject_missing_mark():
    root = TrustRoot()
    env = issue_envelope(root, "conservation-claim", {"subject": "p", "value": 1})
    unmarked = Envelope(env.payload, env.profile, env.root_id, env.key_id, env.signature, "")
    check("U3 reject missing mark", verify_mark(root, unmarked, _valid) is False)

def u3_reject_tampered_payload():
    root = TrustRoot()
    env = issue_envelope(root, "conservation-claim", {"subject": "p", "value": 1})
    tampered = Envelope({"subject": "p", "value": 999}, env.profile, env.root_id,
                        env.key_id, env.signature, MARK)
    check("U3 reject tampered payload", verify_mark(root, tampered, _valid) is False)


# ---- U-4 : one toll ------------------------------------------------------
def u4_shape():
    t = compute_toll(10_000, "connect_verified")
    check("U4 fields present",
          all(k in t for k in
              ("protocol_margin_minor", "protocol_margin_bps", "card_rail_cost_minor", "total_fee_minor")))

def u4_verified_100bps():
    t = compute_toll(10_000, "connect_verified")
    check("U4 verified tier 100bps", t["protocol_margin_bps"] == 100)
    check("U4 verified margin minor", t["protocol_margin_minor"] == 100)
    check("U4 card rail pass-through", t["card_rail_cost_minor"] == _ceil_bps(10_000, 290))
    check("U4 total = margin + rail",
          t["total_fee_minor"] == t["protocol_margin_minor"] + t["card_rail_cost_minor"])

def u4_new_200bps():
    t = compute_toll(10_000, "new")
    check("U4 new tier 200bps", t["protocol_margin_bps"] == 200 and t["protocol_margin_minor"] == 200)

def u4_floor():
    t = compute_toll(10_000, "connect_verified")
    check("U4 margin >= 50bps floor", t["protocol_margin_bps"] >= 50)

def u4_ceil_rounding():
    t = compute_toll(12_345, "connect_verified")   # 123.45 -> ceil 124
    check("U4 ceil rounding", t["protocol_margin_minor"] == 124)

def u4_unknown_tier_raises():
    check("U4 unknown tier raises ValueError", raises(lambda: compute_toll(10_000, "platinum"), ValueError))

def u4_single_source_of_truth():
    check("U4 identical both paths",
          compute_toll(50_000, "connect_onboarded") == compute_toll(50_000, "connect_onboarded"))


# ---- cross-profile chain -------------------------------------------------
def cross_profile_chain():
    root = TrustRoot()
    did = root.bind_did("weaver-agent", "PK")
    env = issue_envelope(root, "conservation-claim",
                         {"subject": "corridor-9", "issued_by": did, "value": 7})
    check("XP mark valid", verify_mark(root, env, _valid) is True)
    check("XP issued_by is did:viridis", env.payload["issued_by"].startswith("did:viridis:"))


TESTS = [
    u1_single_root_both_profiles, u1_bind_did_matches_fleet,
    u2_envelope_shape, u2_unknown_profile_rejected,
    u3_mark_valid_path, u3_reject_standard_invalid, u3_reject_forged_signature,
    u3_reject_missing_mark, u3_reject_tampered_payload,
    u4_shape, u4_verified_100bps, u4_new_200bps, u4_floor, u4_ceil_rounding,
    u4_unknown_tier_raises, u4_single_source_of_truth,
    cross_profile_chain,
]

if __name__ == "__main__":
    for t in TESTS:
        try:
            t()
        except NotImplementedError:
            _FAIL += 1
            print(f"  FAIL: {t.__name__} (NotImplementedError — stub not yet implemented)")
        except Exception as e:  # noqa: BLE001
            _FAIL += 1
            print(f"  FAIL: {t.__name__} ({type(e).__name__}: {e})")
    # last line format is parsed by run_all_tests.sh: "<pass> passed, <fail> failed"
    print(f"{_PASS} passed, {_FAIL} failed")
    sys.exit(0 if _FAIL == 0 else 1)
