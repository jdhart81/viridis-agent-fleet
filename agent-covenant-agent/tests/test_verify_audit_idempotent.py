"""Idempotency/purity pin for verify_audit (strengthens C3).

C3's existing test covers tamper-detection but not that verify_audit is a PURE,
repeatable audit read -- the "idempotency on verify_audit-style actions" signal
queued in N63/N64, closed across the A2A verify_* family tonight (mirrors
metering's verify_chain pin). verify_audit must (a) return identical results
across repeated calls on an unchanged covenant and (b) never mutate the budget,
audit chain, or state it inspects. Additive; C1-C8 untouched.
"""
import pytest
from src.core import build


@pytest.fixture
def core():
    return build()


async def _grant(core, **over):
    payload = {"action": "grant", "principal": "justin", "agent_id": "worker-1",
               "scopes": ["payments.*", "files.read"], "budget_minor": 10000,
               "expires_at": "2099-01-01T00:00:00+00:00", **over}
    r = await core.process(payload)
    assert r["status"] == "ok"
    return r["data"]["covenant_id"]


async def _act(core, cid, act_id, scope="payments.refund", amount=100, **over):
    return await core.process({"action": "check_act", "covenant_id": cid,
                               "act_id": act_id, "scope": scope,
                               "amount_minor": amount, **over})


async def test_C3_verify_audit_is_idempotent_and_pure(core):
    cid = await _grant(core)
    await _act(core, cid, "a1", amount=100)
    await _act(core, cid, "a2", amount=200)

    before = await core.process({"action": "status", "covenant_id": cid})
    v1 = await core.process({"action": "verify_audit", "covenant_id": cid})
    v2 = await core.process({"action": "verify_audit", "covenant_id": cid})
    after = await core.process({"action": "status", "covenant_id": cid})

    # (a) repeatable: two audits of an unchanged covenant return identical verdicts
    assert v1["data"]["valid"] is True
    assert v1["data"] == v2["data"]
    # (b) pure: auditing does not spend budget, append acts, or change state
    assert before["data"] == after["data"]


async def test_C3_verify_audit_idempotent_after_tamper(core):
    cid = await _grant(core)
    await _act(core, cid, "a1", amount=100)
    core._covenants[cid].audit[0]["prev_hash"] = "tampered"

    v1 = await core.process({"action": "verify_audit", "covenant_id": cid})
    v2 = await core.process({"action": "verify_audit", "covenant_id": cid})
    assert v1["data"]["valid"] is False
    assert v1["data"] == v2["data"]
