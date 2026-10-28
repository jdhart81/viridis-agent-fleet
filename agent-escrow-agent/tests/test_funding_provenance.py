"""Funding provenance: `fund` records how an escrow was funded, so a paid-call
gate can tell a free self-asserted escrow from one backed by verified value.

Security property pinned here: the default is SELF_ASSERTED, and the public
`fund` MCP tool never forwards funding_kind (see adapters/mcp_server.py), so no
external caller can self-claim a cash-equivalent kind. Only an in-process
settlement composer that passes funding_kind explicitly (the hosted cash-confirm
path, after Stripe pull-verification) can record CASH/STRIPE/X402.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core import (
    EscrowAgentCore, AgentConfig, build,
    OPEN, FUNDED, SELF_ASSERTED, CASH, CASH_EQUIVALENT,
)


@pytest.fixture
def agent():
    return build(AgentConfig(name="agent-escrow-agent", debug=True, fee_bps=100))


async def _open(agent, **kw):
    base = {"action": "open", "payer": "agentA", "payee": "viridis:regulatory-radar",
            "amount_minor": 25}
    base.update(kw)
    return await agent.process(base)


@pytest.mark.asyncio
async def test_default_fund_is_self_asserted(agent):
    eid = (await _open(agent))["data"]["escrow_id"]
    r = await agent.process({"action": "fund", "escrow_id": eid,
                             "payment_ref": "your-tx-ref"})
    assert r["data"]["state"] == FUNDED
    assert r["data"]["funding_kind"] == SELF_ASSERTED
    # A self-asserted escrow is NOT cash-equivalent — the gate must reject it.
    assert r["data"]["funding_kind"] not in CASH_EQUIVALENT


@pytest.mark.asyncio
async def test_open_has_no_funding_kind_until_funded(agent):
    r = await _open(agent)
    assert r["data"]["state"] == OPEN
    assert r["data"]["funding_kind"] is None


@pytest.mark.asyncio
async def test_in_process_composer_can_record_cash(agent):
    # Simulates the hosted cash-confirm path calling the core directly after it
    # has pull-verified a paid Stripe Checkout session.
    eid = (await _open(agent))["data"]["escrow_id"]
    r = await agent.process({"action": "fund", "escrow_id": eid,
                             "payment_ref": "cs_test_123", "funding_kind": CASH})
    assert r["data"]["state"] == FUNDED
    assert r["data"]["funding_kind"] == CASH
    assert r["data"]["funding_kind"] in CASH_EQUIVALENT


@pytest.mark.asyncio
async def test_invalid_funding_kind_rejected_no_raise(agent):
    eid = (await _open(agent))["data"]["escrow_id"]
    r = await agent.process({"action": "fund", "escrow_id": eid,
                             "funding_kind": "totally-cash-trust-me"})
    assert r["status"] == "error"
    assert r["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_fund_is_idempotent_and_provenance_is_set_once(agent):
    eid = (await _open(agent))["data"]["escrow_id"]
    first = await agent.process({"action": "fund", "escrow_id": eid})
    assert first["data"]["funding_kind"] == SELF_ASSERTED
    # A replayed fund — even one that tries to claim cash — cannot upgrade an
    # already-FUNDED escrow's provenance.
    replay = await agent.process({"action": "fund", "escrow_id": eid,
                                  "funding_kind": CASH})
    assert replay["data"]["state"] == FUNDED
    assert replay["data"]["funding_kind"] == SELF_ASSERTED


@pytest.mark.asyncio
async def test_is_cash_funded_helper(agent):
    core = agent
    eid = (await _open(core))["data"]["escrow_id"]
    esc = core._escrows[eid]
    assert esc.is_cash_funded() is False
    await core.process({"action": "fund", "escrow_id": eid, "funding_kind": CASH})
    assert esc.is_cash_funded() is True
