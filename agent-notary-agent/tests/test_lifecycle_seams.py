"""Lifecycle-seam pins for the commit-reveal state machine (N68).

N1-N8 each had a single-shot pin; the SEAMS between them did not:
- a MISMATCHED reveal must leave the commitment PENDING (retry with the
  right salt is legitimate commit-reveal semantics, N2+N3 interplay);
- once EXPIRED, nothing resurrects the commitment (N3 terminality after
  an N4 transition), and verify() reports it honestly (N5);
- N8's "deterministic per (committer, nonce)" holds ACROSS fresh core
  instances — the id is content-addressed, not instance-local.
"""

import asyncio
import hashlib

from src.core import NotaryAgentCore, AgentConfig


SALT = "s3cr3t-salt"
DIGEST = hashlib.sha256(b"the deliverable").hexdigest()
COMMIT_HASH = hashlib.sha256((SALT + DIGEST).encode()).hexdigest()


def _core():
    return NotaryAgentCore(AgentConfig(name="agent-notary-agent"))


def _run(core, payload):
    return asyncio.run(core.process(payload))


def _commit(core, deadline="2099-01-01T00:00:00+00:00"):
    out = _run(core, {"action": "commit", "committer": "seller-1",
                      "nonce": "job-42", "commit_hash": COMMIT_HASH,
                      "deadline": deadline})
    assert out["status"] == "ok", out
    return out["data"]["commitment_id"]


def test_mismatched_reveal_leaves_pending_and_retry_succeeds():
    core = _core()
    cid = _commit(core)
    bad = _run(core, {"action": "reveal", "commitment_id": cid,
                      "salt": "wrong-salt", "content_digest": DIGEST})
    assert bad["status"] == "error"
    assert bad["error_type"] == "CommitmentMismatch"
    st = _run(core, {"action": "status", "commitment_id": cid})
    assert st["data"]["state"] == "PENDING", (
        "mismatch must not consume or expire the commitment")
    good = _run(core, {"action": "reveal", "commitment_id": cid,
                       "salt": SALT, "content_digest": DIGEST})
    assert good["status"] == "ok"
    assert good["data"]["state"] == "REVEALED"


def test_expired_commitment_is_terminal_and_verify_is_honest():
    core = _core()
    cid = _commit(core, deadline="2020-01-01T00:00:00+00:00")
    late = _run(core, {"action": "reveal", "commitment_id": cid,
                       "salt": SALT, "content_digest": DIGEST,
                       "_now": "2021-01-01T00:00:00+00:00"})
    assert late["status"] == "error" and late["error_type"] == "Expired"
    # No resurrection: a subsequent reveal (even a "correct" one) returns
    # the terminal record idempotently rather than flipping state.
    again = _run(core, {"action": "reveal", "commitment_id": cid,
                        "salt": SALT, "content_digest": DIGEST})
    assert again["status"] == "ok"
    assert again["data"]["state"] == "EXPIRED"
    ver = _run(core, {"action": "verify", "commitment_id": cid})
    assert ver["data"]["valid"] is False
    assert ver["data"]["state"] == "EXPIRED"


def test_n8_commitment_id_deterministic_across_fresh_cores():
    ids = set()
    for _ in range(3):
        ids.add(_commit(_core()))
    assert len(ids) == 1, "commitment_id must be content-addressed (N8)"
