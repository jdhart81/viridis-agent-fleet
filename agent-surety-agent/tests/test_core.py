"""agent-surety-agent — invariant tests (SB1–SB8) + fleet contract."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.core import build


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


FUTURE = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
PAST = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def _bond(a, principal=10_000, expires=FUTURE, activate=True):
    r = run(a.process({"action": "post_bond", "principal_agent": "agent-x",
                       "principal": principal, "coverage": "cad jobs",
                       "expires_at": expires}))
    bid = r["data"]["bond_id"]
    if activate:
        run(a.process({"action": "activate", "bond_id": bid,
                       "funding_ref": "x402:test"}))
    return bid


def _claim(a, bid, amount=4_000):
    return run(a.process({"action": "file_claim", "bond_id": bid,
                          "claimant": "agent-y", "amount_minor": amount,
                          "reason": "undelivered"}))["data"]["claim_id"]


def _slash(a, bid, cid, case="case-1", h="abc123", upheld=True):
    return run(a.process({"action": "slash", "bond_id": bid, "claim_id": cid,
                          "ruling_case_id": case, "ruling_hash": h,
                          "upheld": upheld}))


# SB1 — forward-only state machine
def test_sb1_forward_only():
    a = build()
    bid = _bond(a)
    r = run(a.process({"action": "release", "bond_id": bid, "_now": PAST}))
    assert r["status"] == "error"                       # window not elapsed
    ok = run(a.process({"action": "release", "bond_id": bid,
                        "_now": (datetime.now(timezone.utc)
                                 + timedelta(days=31)).isoformat()}))
    assert ok["data"]["state"] == "RELEASED"
    # terminal: further claims refused
    again = run(a.process({"action": "file_claim", "bond_id": bid,
                           "claimant": "z", "amount_minor": 1}))
    assert again["status"] == "error"


# SB2 — positive integers only
def test_sb2_no_floats_no_nonpositive():
    a = build()
    for bad in (0, -5, 1.5, "100", None, True):
        r = run(a.process({"action": "post_bond", "principal_agent": "x",
                           "principal": bad, "expires_at": FUTURE}))
        assert r["status"] == "error", bad


# SB3 — conservation after every mutation
def test_sb3_conservation_holds():
    a = build()
    bid = _bond(a, principal=10_000)
    cid = _claim(a, bid, 3_000)
    _slash(a, bid, cid)
    st = run(a.process({"action": "status", "bond_id": bid}))["data"]
    assert st["available"] + st["slashed_total"] + st["released"] == 10_000


# SB4 — no ruling, no slash; ruling pays exactly once
def test_sb4_ruling_gated_and_exactly_once():
    a = build()
    bid = _bond(a)
    cid = _claim(a, bid)
    naked = run(a.process({"action": "slash", "bond_id": bid, "claim_id": cid}))
    assert naked["status"] == "error"                   # no authority
    first = _slash(a, bid, cid)
    assert first["data"]["state"] == "PAID"
    second = _slash(a, bid, cid)                        # same ruling again
    assert second["data"].get("idempotent") is True
    st = run(a.process({"action": "status", "bond_id": bid}))["data"]
    assert st["slashed_total"] == 4_000                 # paid once


def test_sb4_denied_ruling_pays_nothing():
    a = build()
    bid = _bond(a)
    cid = _claim(a, bid)
    r = _slash(a, bid, cid, upheld=False)
    assert r["data"]["state"] == "DENIED"
    st = run(a.process({"action": "status", "bond_id": bid}))["data"]
    assert st["slashed_total"] == 0 and st["available"] == 10_000


# SB5 — slash caps at available; over-claim exhausts
def test_sb5_overclaim_caps_and_exhausts():
    a = build()
    bid = _bond(a, principal=5_000)
    cid = _claim(a, bid, 9_999)
    r = _slash(a, bid, cid)
    assert r["data"]["paid_minor"] == 5_000             # capped
    assert r["data"]["bond_state"] == "EXHAUSTED"
    st = run(a.process({"action": "status", "bond_id": bid}))["data"]
    assert st["available"] == 0
    assert st["available"] + st["slashed_total"] + st["released"] == 5_000


# SB6 — release needs elapsed window AND no open claims
def test_sb6_release_blocked_by_open_claim():
    a = build()
    bid = _bond(a)
    _claim(a, bid)
    r = run(a.process({"action": "release", "bond_id": bid,
                       "_now": (datetime.now(timezone.utc)
                                + timedelta(days=31)).isoformat()}))
    assert r["status"] == "error" and "open claims" in r["message"]


def test_sb6_release_returns_exact_available():
    a = build()
    bid = _bond(a, principal=10_000)
    cid = _claim(a, bid, 2_500)
    _slash(a, bid, cid)
    r = run(a.process({"action": "release", "bond_id": bid,
                       "_now": (datetime.now(timezone.utc)
                                + timedelta(days=31)).isoformat()}))
    assert r["data"]["released_now"] == 7_500
    assert r["data"]["released"] == 7_500


# SB7 — tamper-evident audit chain
def test_sb7_audit_chain_verifies_and_detects_tampering():
    a = build()
    bid = _bond(a)
    cid = _claim(a, bid)
    _slash(a, bid, cid)
    ok = run(a.process({"action": "verify_audit", "bond_id": bid}))
    assert ok["data"]["valid"] is True and ok["data"]["length"] >= 4
    a._bonds[bid].audit[1]["detail"]["amount"] = 999_999   # tamper
    bad = run(a.process({"action": "verify_audit", "bond_id": bid}))
    assert bad["data"]["valid"] is False


# SB8 — never raises / fleet contract
def test_sb8_never_raises_and_contract():
    a = build()
    for bad in (None, [], "x", 42, {"action": "nope"},
                {"action": "status", "bond_id": "none"}):
        r = run(a.process(bad))
        assert r["status"] == "error"
    h = run(a.health())
    d = a.describe()
    assert d["name"] == h["agent"] == "agent-surety-agent"
    assert d["capabilities"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
