"""Idempotency/purity pin for verify_audit (strengthens SB7).

SB7's existing test covers tamper-detection but not that verify_audit is a PURE,
repeatable audit read -- the "idempotency on verify_audit-style actions" signal
queued in N63/N64, closed across the A2A verify_* family tonight (mirrors
metering's verify_chain pin). verify_audit must (a) return identical results
across repeated calls on an unchanged bond audit chain and (b) never mutate the
bond it inspects. Additive; SB1-SB8 untouched.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from src.core import build


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


FUTURE = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()


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


def test_sb7_verify_audit_is_idempotent_and_pure():
    a = build()
    bid = _bond(a)
    cid = _claim(a, bid)
    _slash(a, bid, cid)

    before_len = len(a._bonds[bid].audit)
    v1 = run(a.process({"action": "verify_audit", "bond_id": bid}))
    v2 = run(a.process({"action": "verify_audit", "bond_id": bid}))
    after_len = len(a._bonds[bid].audit)

    # (a) repeatable: two audits of an unchanged chain return identical verdicts
    assert v1["data"]["valid"] is True
    assert v1["data"] == v2["data"]
    # (b) pure: auditing the bond does not append to or mutate its audit chain
    assert before_len == after_len


def test_sb7_verify_audit_idempotent_after_tamper():
    a = build()
    bid = _bond(a)
    cid = _claim(a, bid)
    _slash(a, bid, cid)
    a._bonds[bid].audit[1]["detail"]["amount"] = 999_999  # tamper

    v1 = run(a.process({"action": "verify_audit", "bond_id": bid}))
    v2 = run(a.process({"action": "verify_audit", "bond_id": bid}))
    # a broken chain reports the SAME break deterministically on every audit
    assert v1["data"]["valid"] is False
    assert v1["data"] == v2["data"]
