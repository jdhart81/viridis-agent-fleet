"""Tests for agent-escrow-agent — state machine + invariants E1–E8."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core import (
    EscrowAgentCore, AgentConfig, build,
    OPEN, FUNDED, RELEASED, REFUNDED, DISPUTED,
)


@pytest.fixture
def agent():
    return build(AgentConfig(name="agent-escrow-agent", debug=True, fee_bps=100))


async def _open(agent, **kw):
    base = {"action": "open", "payer": "agentA", "payee": "agentB", "amount_minor": 10_000}
    base.update(kw)
    r = await agent.process(base)
    return r


# --- fleet-standard interface ------------------------------------------------
class TestFleetInterface:
    @pytest.mark.asyncio
    async def test_health_keys(self, agent):
        h = await agent.health()
        for k in ("status", "agent", "version", "timestamp"):
            assert k in h
        assert h["status"] == "ok"

    def test_describe_contract(self, agent):
        d = agent.describe()
        for k in ("name", "version", "capabilities", "inputs", "outputs"):
            assert k in d
        assert d["capabilities"]
        assert d["name"] == agent.config.name
        assert d["a2a_role"] == "settlement"

    @pytest.mark.asyncio
    async def test_unknown_action_no_raise(self, agent):
        r = await agent.process({"action": "nope"})
        assert r["status"] == "error"
        assert r["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_non_dict_no_raise(self, agent):
        for bad in (None, [], "x", 7):
            r = await agent.process(bad)
            assert r["status"] == "error"


# --- open (E2, E3) -----------------------------------------------------------
class TestOpen:
    @pytest.mark.asyncio
    async def test_open_ok(self, agent):
        r = await _open(agent)
        assert r["status"] == "ok"
        assert r["data"]["state"] == OPEN
        assert r["data"]["escrow_id"]

    @pytest.mark.asyncio
    async def test_fee_computed_ceil(self, agent):
        r = await _open(agent, amount_minor=10_001, fee_bps=100)  # 1% of 10001 = 100.01 -> 101
        assert r["data"]["fee_minor"] == 101
        assert r["data"]["net_to_payee_minor"] == 10_001 - 101

    @pytest.mark.asyncio
    async def test_amount_must_be_positive_int(self, agent):
        for bad in (0, -5, 3.5, True, "100"):
            r = await _open(agent, amount_minor=bad)
            assert r["status"] == "error"
            assert r["field"] == "amount_minor"

    @pytest.mark.asyncio
    async def test_payer_payee_differ(self, agent):
        r = await _open(agent, payer="x", payee="x")
        assert r["status"] == "error"
        assert r["field"] == "payee"

    @pytest.mark.asyncio
    async def test_missing_field(self, agent):
        r = await agent.process({"action": "open", "payer": "a"})
        assert r["status"] == "error"


# --- state machine (E1, E4, E5, E6) -----------------------------------------
class TestStateMachine:
    @pytest.mark.asyncio
    async def test_happy_path_release(self, agent):
        eid = (await _open(agent))["data"]["escrow_id"]
        assert (await agent.process({"action": "fund", "escrow_id": eid}))["data"]["state"] == FUNDED
        r = await agent.process({"action": "release", "escrow_id": eid, "delivery_proof": "sig"})
        assert r["data"]["state"] == RELEASED

    @pytest.mark.asyncio
    async def test_cannot_release_before_funding(self, agent):
        eid = (await _open(agent))["data"]["escrow_id"]
        r = await agent.process({"action": "release", "escrow_id": eid})
        assert r["status"] == "error"  # E4: OPEN -> RELEASED illegal

    @pytest.mark.asyncio
    async def test_open_refund_is_cancel(self, agent):
        eid = (await _open(agent))["data"]["escrow_id"]
        r = await agent.process({"action": "refund", "escrow_id": eid, "reason": "cancel"})
        assert r["data"]["state"] == REFUNDED  # E5

    @pytest.mark.asyncio
    async def test_release_idempotent(self, agent):
        eid = (await _open(agent))["data"]["escrow_id"]
        await agent.process({"action": "fund", "escrow_id": eid})
        r1 = await agent.process({"action": "release", "escrow_id": eid})
        r2 = await agent.process({"action": "release", "escrow_id": eid})
        assert r1["data"]["state"] == RELEASED and r2["data"]["state"] == RELEASED  # E6

    @pytest.mark.asyncio
    async def test_no_refund_after_release(self, agent):
        eid = (await _open(agent))["data"]["escrow_id"]
        await agent.process({"action": "fund", "escrow_id": eid})
        await agent.process({"action": "release", "escrow_id": eid})
        r = await agent.process({"action": "refund", "escrow_id": eid})
        assert r["status"] == "error"  # E6 no double payout

    @pytest.mark.asyncio
    async def test_no_release_after_refund(self, agent):
        eid = (await _open(agent))["data"]["escrow_id"]
        await agent.process({"action": "fund", "escrow_id": eid})
        await agent.process({"action": "refund", "escrow_id": eid})
        r = await agent.process({"action": "release", "escrow_id": eid})
        assert r["status"] == "error"

    @pytest.mark.asyncio
    async def test_dispute_then_release(self, agent):
        eid = (await _open(agent))["data"]["escrow_id"]
        await agent.process({"action": "fund", "escrow_id": eid})
        await agent.process({"action": "dispute", "escrow_id": eid, "reason": "late"})
        r = await agent.process({"action": "release", "escrow_id": eid})
        assert r["data"]["state"] == RELEASED  # DISPUTED -> RELEASED allowed

    @pytest.mark.asyncio
    async def test_unknown_escrow(self, agent):
        r = await agent.process({"action": "status", "escrow_id": "ghost"})
        assert r["status"] == "error" and r["field"] == "escrow_id"  # E8


# --- audit chain (E7) --------------------------------------------------------
class TestAudit:
    @pytest.mark.asyncio
    async def test_audit_chain_valid(self, agent):
        eid = (await _open(agent))["data"]["escrow_id"]
        await agent.process({"action": "fund", "escrow_id": eid})
        await agent.process({"action": "release", "escrow_id": eid})
        r = await agent.process({"action": "verify_audit", "escrow_id": eid})
        assert r["data"]["valid"] is True
        assert r["data"]["entries"] == 3  # open, fund, release

    @pytest.mark.asyncio
    async def test_tamper_detected(self, agent):
        eid = (await _open(agent))["data"]["escrow_id"]
        await agent.process({"action": "fund", "escrow_id": eid})
        agent._escrows[eid].audit[1]["detail"]["ref"] = "TAMPERED"
        r = await agent.process({"action": "verify_audit", "escrow_id": eid})
        assert r["data"]["valid"] is False
        assert r["data"]["broken_at"] == 1


# --- list --------------------------------------------------------------------
class TestList:
    @pytest.mark.asyncio
    async def test_list_and_filter(self, agent):
        for _ in range(3):
            await _open(agent)
        e = (await _open(agent))["data"]["escrow_id"]
        await agent.process({"action": "fund", "escrow_id": e})
        allr = await agent.process({"action": "list"})
        fundedr = await agent.process({"action": "list", "state": FUNDED})
        assert allr["data"]["count"] == 4
        assert fundedr["data"]["count"] == 1


# --- E9: sync dispatch surface ------------------------------------------------
class TestProcessSyncE9:
    """E9: process_sync(x) is semantically identical to await process(x)."""

    def test_e9_full_lifecycle_sync(self, agent):
        opened = agent.process_sync({"action": "open", "payer": "agentA",
                                     "payee": "viridis:protogen",
                                     "amount_minor": 500})
        assert opened["status"] == "ok"
        eid = opened["data"]["escrow_id"]
        funded = agent.process_sync({"action": "fund", "escrow_id": eid,
                                     "payment_ref": "tx-1"})
        assert funded["data"]["state"] == FUNDED
        released = agent.process_sync({"action": "release", "escrow_id": eid})
        assert released["data"]["state"] == RELEASED
        audit = agent.process_sync({"action": "verify_audit", "escrow_id": eid})
        assert audit["data"]["valid"] is True

    def test_e9_error_envelopes_never_raise(self, agent):
        bad = agent.process_sync({"action": "release", "escrow_id": "nope"})
        assert bad["status"] == "error"
        assert bad["error_type"] == "ValidationError"
        notdict = agent.process_sync("not a dict")
        assert notdict["status"] == "error"
        unknown = agent.process_sync({"action": "warp"})
        assert unknown["status"] == "error"

    @pytest.mark.asyncio
    async def test_e9_equivalence_with_async_process(self, agent):
        """Same action sequence through both entries lands in identical state,
        and envelopes carry the same shape/keys."""
        r_sync = agent.process_sync({"action": "open", "payer": "a",
                                     "payee": "b", "amount_minor": 100})
        r_async = await agent.process({"action": "open", "payer": "a",
                                       "payee": "b", "amount_minor": 100})
        assert set(r_sync.keys()) == set(r_async.keys())
        assert r_sync["status"] == r_async["status"] == "ok"
        e1, e2 = r_sync["data"]["escrow_id"], r_async["data"]["escrow_id"]
        s1 = agent.process_sync({"action": "status", "escrow_id": e1})
        s2 = await agent.process({"action": "status", "escrow_id": e2})
        assert s1["data"]["state"] == s2["data"]["state"] == OPEN
        assert s1["data"]["fee_minor"] == s2["data"]["fee_minor"]

    def test_e9_exactly_once_preserved_through_sync(self, agent):
        """E6 via the sync surface: double release is an idempotent no-op."""
        eid = agent.process_sync({"action": "open", "payer": "a", "payee": "b",
                                  "amount_minor": 100})["data"]["escrow_id"]
        agent.process_sync({"action": "fund", "escrow_id": eid})
        first = agent.process_sync({"action": "release", "escrow_id": eid})
        second = agent.process_sync({"action": "release", "escrow_id": eid})
        assert first["data"]["state"] == second["data"]["state"] == RELEASED
        assert first["data"]["audit_len"] == second["data"]["audit_len"]
