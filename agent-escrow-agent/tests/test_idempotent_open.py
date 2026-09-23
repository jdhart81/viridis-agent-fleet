"""E10 — idempotent open (client-retry dedup). One test per claim."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core import EscrowAgentCore, AgentConfig, build, OPEN


@pytest.fixture
def agent():
    return build(AgentConfig(name="agent-escrow-agent", debug=True, fee_bps=100))


async def _open(agent, **kw):
    base = {"action": "open", "payer": "agentA", "payee": "agentB",
            "amount_minor": 10_000}
    base.update(kw)
    return await agent.process(base)


async def test_E10_same_ref_returns_original_escrow(agent):
    first = await _open(agent, open_ref="job-42")
    retry = await _open(agent, open_ref="job-42")
    assert first["status"] == retry["status"] == "ok"
    assert retry["data"]["escrow_id"] == first["data"]["escrow_id"]
    assert retry["data"]["duplicate"] is True
    assert "duplicate" not in first["data"]
    listing = await agent.process({"action": "list"})
    assert listing["data"]["count"] == 1            # exactly one escrow


async def test_E10_replay_wins_even_with_argument_drift(agent):
    first = await _open(agent, open_ref="job-42", amount_minor=270)
    drift = await _open(agent, open_ref="job-42", amount_minor=999,
                        payee="someone-else")
    assert drift["data"]["escrow_id"] == first["data"]["escrow_id"]
    assert drift["data"]["amount_minor"] == 270     # original record wins
    assert drift["data"]["payee"] == "agentB"


async def test_E10_distinct_refs_distinct_escrows(agent):
    a = await _open(agent, open_ref="job-1")
    b = await _open(agent, open_ref="job-2")
    assert a["data"]["escrow_id"] != b["data"]["escrow_id"]


async def test_E10_no_ref_preserves_pre_E10_behavior(agent):
    a = await _open(agent)
    b = await _open(agent)
    assert a["data"]["escrow_id"] != b["data"]["escrow_id"]
    assert "duplicate" not in a["data"] and "duplicate" not in b["data"]
    assert a["data"]["state"] == OPEN


async def test_E10_blank_or_nonstring_ref_ignored(agent):
    a = await _open(agent, open_ref="   ")
    b = await _open(agent, open_ref=7)
    c = await _open(agent, open_ref=None)
    assert len({a["data"]["escrow_id"], b["data"]["escrow_id"],
                c["data"]["escrow_id"]}) == 3


async def test_E10_replay_after_lifecycle_returns_current_state(agent):
    first = await _open(agent, open_ref="job-42")
    eid = first["data"]["escrow_id"]
    await agent.process({"action": "fund", "escrow_id": eid,
                         "payment_ref": "t"})
    retry = await _open(agent, open_ref="job-42")
    assert retry["data"]["escrow_id"] == eid
    assert retry["data"]["state"] == "FUNDED"       # truth, not a stale echo
    assert retry["data"]["duplicate"] is True
