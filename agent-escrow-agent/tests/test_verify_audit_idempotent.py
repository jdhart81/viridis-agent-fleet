"""verify_audit purity/idempotency pin — strengthens E7 (tamper-evident audit
hash chain). Mirrors the fleet-wide verify_* idiom (metering verify_chain N64,
arbitration/surety/provenance/erc8004/covenant N65): auditing must be a PURE,
repeatable read that never mutates the record it inspects, and tamper
detection must be deterministic across repeats. Escrow settles live cash, so
this is the highest-priority target named in the N65 cross-pollination queue.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core import AgentConfig, build


@pytest.fixture
def agent():
    return build(AgentConfig(name="agent-escrow-agent", debug=True, fee_bps=100))


async def _open_funded(agent, **kw):
    base = {"action": "open", "payer": "agentA", "payee": "agentB",
            "amount_minor": 10_000}
    base.update(kw)
    opened = await agent.process(base)
    eid = opened["data"]["escrow_id"]
    await agent.process({"action": "fund", "escrow_id": eid, "payment_ref": "t1"})
    await agent.process({"action": "dispute", "escrow_id": eid, "reason": "qc"})
    return eid


async def test_verify_audit_is_pure_and_repeatable(agent):
    eid = await _open_funded(agent)

    before = await agent.process({"action": "status", "escrow_id": eid})
    first = await agent.process({"action": "verify_audit", "escrow_id": eid})
    second = await agent.process({"action": "verify_audit", "escrow_id": eid})
    after = await agent.process({"action": "status", "escrow_id": eid})

    assert first["status"] == second["status"] == "ok"
    assert first["data"] == second["data"] == {"valid": True, "entries": 3}
    # auditing never mutates the escrow it inspects (state, not just contents)
    assert before["data"] == after["data"]


async def test_verify_audit_tamper_detection_is_deterministic(agent):
    eid = await _open_funded(agent)
    esc = agent._escrows[eid]
    pristine_len = len(esc.audit)

    # tamper with the middle entry's detail payload (breaks its own hash)
    esc.audit[1]["detail"] = {"reason": "forged"}

    first = await agent.process({"action": "verify_audit", "escrow_id": eid})
    second = await agent.process({"action": "verify_audit", "escrow_id": eid})

    assert first["data"] == second["data"] == {"valid": False, "broken_at": 1}
    # the audit list itself is untouched in length by the *read* (only the
    # test harness tampered it directly) — verify_audit does not truncate,
    # append, or otherwise repair on read
    assert len(esc.audit) == pristine_len
