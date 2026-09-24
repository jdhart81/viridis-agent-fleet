"""agent-notary-agent — invariant tests (N1–N8) + fleet contract."""
import asyncio
import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from src.core import build


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


FUTURE = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
SALT = "s3cr3t-salt"
DIGEST = hashlib.sha256(b"the actual deliverable bytes").hexdigest()
COMMIT = hashlib.sha256((SALT + DIGEST).encode()).hexdigest()


def _commit(a, nonce="job-1", commit_hash=COMMIT, deadline=FUTURE):
    return run(a.process({"action": "commit", "committer": "agent-seller",
                          "nonce": nonce, "commit_hash": commit_hash,
                          "context": "esc_000123", "deadline": deadline}))


def _reveal(a, cid, salt=SALT, digest=DIGEST, now=None):
    p = {"action": "reveal", "commitment_id": cid, "salt": salt,
         "content_digest": digest}
    if now:
        p["_now"] = now
    return run(a.process(p))


# N1/N8 — a commitment binds; (committer, nonce) is unique + deterministic
def test_n1_n8_commitment_binds():
    a = build()
    r1 = _commit(a)
    assert r1["status"] == "ok"
    r_same = _commit(a)                                 # same hash: idempotent
    assert r_same["data"]["idempotent"] is True
    assert r_same["data"]["commitment_id"] == r1["data"]["commitment_id"]
    other = hashlib.sha256(b"different").hexdigest()
    r_diff = _commit(a, commit_hash=other)              # same key, new hash
    assert r_diff["status"] == "error"                  # binding holds


# N2 — reveal verifies iff hash matches exactly
def test_n2_reveal_must_match():
    a = build()
    cid = _commit(a)["data"]["commitment_id"]
    bad = _reveal(a, cid, digest=hashlib.sha256(b"swapped goods").hexdigest())
    assert bad["status"] == "error"
    assert bad["error_type"] == "CommitmentMismatch"
    good = _reveal(a, cid)
    assert good["status"] == "ok"
    assert good["data"]["state"] == "REVEALED"
    assert good["data"]["delivery_proof"].startswith("notary:")


# N3 — exactly-once reveal
def test_n3_second_reveal_is_idempotent():
    a = build()
    cid = _commit(a)["data"]["commitment_id"]
    _reveal(a, cid)
    again = _reveal(a, cid)
    assert again["data"]["idempotent"] is True
    assert again["data"]["state"] == "REVEALED"


# N4 — late reveal is refused and machine-detectable
def test_n4_late_reveal_expires():
    a = build()
    cid = _commit(a)["data"]["commitment_id"]
    late = (datetime.now(timezone.utc) + timedelta(days=8)).isoformat()
    r = _reveal(a, cid, now=late)
    assert r["status"] == "error" and r["error_type"] == "Expired"
    st = run(a.process({"action": "status", "commitment_id": cid}))
    assert st["data"]["state"] == "EXPIRED"


# N5 — receipts independently verifiable
def test_n5_verify_recomputes():
    a = build()
    cid = _commit(a)["data"]["commitment_id"]
    _reveal(a, cid)
    ok = run(a.process({"action": "verify", "commitment_id": cid,
                        "content_digest": DIGEST}))
    assert ok["data"]["valid"] is True
    wrong = run(a.process({"action": "verify", "commitment_id": cid,
                           "content_digest": hashlib.sha256(b"x").hexdigest()}))
    assert wrong["data"]["valid"] is False


# N6 — never raises / fleet contract
def test_n6_never_raises_and_contract():
    a = build()
    for bad in (None, [], "x", {"action": "nope"},
                {"action": "commit", "committer": "a", "nonce": "n",
                 "commit_hash": "not-hex", "deadline": FUTURE},
                {"action": "reveal", "commitment_id": "none"}):
        r = run(a.process(bad))
        assert r["status"] == "error"
    h = run(a.health())
    d = a.describe()
    assert d["name"] == h["agent"] == "agent-notary-agent"
    assert d["capabilities"]


# N7 — the notary never stores raw content; pre-reveal salt/digest are hidden
def test_n7_privacy_by_construction():
    a = build()
    cid = _commit(a)["data"]["commitment_id"]
    st = run(a.process({"action": "status", "commitment_id": cid}))["data"]
    assert st["content_digest"] == "" and st["salt"] == ""   # hidden pre-reveal
    raw = run(a.process({"action": "commit", "committer": "x", "nonce": "y",
                         "commit_hash": "raw content here",
                         "deadline": FUTURE}))
    assert raw["status"] == "error"                          # digests only


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
