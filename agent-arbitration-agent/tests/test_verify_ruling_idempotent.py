"""Idempotency/purity pin for verify_ruling (strengthens A6).

A6's existing test (test_core.py) covers tamper-detection but not that
verify_ruling is a PURE, repeatable audit read -- the "idempotency on
verify_audit-style actions" signal queued in N63/N64 and closed across the
A2A verify_* family tonight (mirrors metering's verify_chain pin). verify_ruling
must (a) return identical results across repeated calls on an unchanged ruling
and (b) never mutate the case it inspects. Additive; A1-A9 untouched.
"""
import pytest
from src.core import build


@pytest.fixture
def core():
    return build()


async def _case(core, **over):
    payload = {"action": "file_case", "escrow_id": "esc-1", "claimant": "buyer",
               "respondent": "seller", "amount_minor": 10000, **over}
    r = await core.process(payload)
    assert r["status"] == "ok"
    return r["data"]["case_id"]


async def _ev(core, cid, party, kind="statement", content="x"):
    return await core.process({"action": "submit_evidence", "case_id": cid,
                               "party": party, "kind": kind, "content": content})


async def test_A6_verify_ruling_is_idempotent_and_pure(core):
    cid = await _case(core)
    await _ev(core, cid, "buyer", kind="log")
    await _ev(core, cid, "seller", kind="delivery_proof")
    await core.process({"action": "set_trust_scores", "case_id": cid,
                        "scores": {"seller": 0.9}})
    await core.process({"action": "rule", "case_id": cid})

    before = await core.process({"action": "get_case", "case_id": cid})
    v1 = await core.process({"action": "verify_ruling", "case_id": cid})
    v2 = await core.process({"action": "verify_ruling", "case_id": cid})
    after = await core.process({"action": "get_case", "case_id": cid})

    # (a) repeatable: two audits of an unchanged ruling return identical verdicts
    assert v1["data"]["valid"] is True
    assert v1["data"] == v2["data"]
    # (b) pure: auditing the ruling does not alter the case's stored ruling/state
    assert before["data"] == after["data"]


async def test_A6_verify_ruling_idempotent_after_tamper(core):
    cid = await _case(core)
    await _ev(core, cid, "buyer", kind="log")
    await _ev(core, cid, "seller", kind="delivery_proof")
    await core.process({"action": "rule", "case_id": cid})
    core._cases[cid].ruling["claimant_pct"] = 99  # tamper

    v1 = await core.process({"action": "verify_ruling", "case_id": cid})
    v2 = await core.process({"action": "verify_ruling", "case_id": cid})
    # a tampered ruling reports the SAME verdict deterministically on every audit
    assert v1["data"]["valid"] is False
    assert v1["data"] == v2["data"]
