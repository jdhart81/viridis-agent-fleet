"""Tests for agent-trust-oracle-agent — invariants T1–T8."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import timedelta
from src.core import TrustOracleCore, AgentConfig, build, _utcnow


@pytest.fixture
def agent():
    return build(AgentConfig(name="agent-trust-oracle-agent", debug=True, half_life_days=30))


class TestFleetInterface:
    @pytest.mark.asyncio
    async def test_health_keys(self, agent):
        h = await agent.health()
        for k in ("status", "agent", "version", "timestamp"):
            assert k in h

    def test_describe(self, agent):
        d = agent.describe()
        for k in ("name", "version", "capabilities", "inputs", "outputs"):
            assert k in d
        assert d["capabilities"] and d["a2a_role"] == "trust"

    @pytest.mark.asyncio
    async def test_unknown_action(self, agent):
        assert (await agent.process({"action": "x"}))["status"] == "error"

    @pytest.mark.asyncio
    async def test_non_dict(self, agent):
        for bad in (None, [], "s", 3):
            assert (await agent.process(bad))["status"] == "error"


class TestScoring:
    @pytest.mark.asyncio
    async def test_unknown_agent_neutral_prior(self, agent):  # T2
        r = await agent.process({"action": "score", "agent_id": "ghost"})
        assert r["data"]["score"] == 0.5
        assert r["data"]["tier"] == "NEUTRAL"
        assert r["data"]["prior"] is True

    @pytest.mark.asyncio
    async def test_score_bounds(self, agent):  # T1
        for _ in range(20):
            await agent.process({"action": "record_outcome", "agent_id": "a", "kind": "success"})
        r = await agent.process({"action": "score", "agent_id": "a"})
        assert 0.0 <= r["data"]["score"] <= 1.0
        assert r["data"]["score"] > 0.5

    @pytest.mark.asyncio
    async def test_success_raises_failure_lowers(self, agent):  # T3
        await agent.process({"action": "record_outcome", "agent_id": "b", "kind": "success"})
        up = (await agent.process({"action": "score", "agent_id": "b"}))["data"]["score"]
        await agent.process({"action": "record_outcome", "agent_id": "b", "kind": "failure"})
        await agent.process({"action": "record_outcome", "agent_id": "b", "kind": "failure"})
        down = (await agent.process({"action": "score", "agent_id": "b"}))["data"]["score"]
        assert down < up

    @pytest.mark.asyncio
    async def test_security_incident_heavier(self, agent):
        await agent.process({"action": "record_outcome", "agent_id": "c", "kind": "success"})
        await agent.process({"action": "record_outcome", "agent_id": "d", "kind": "success"})
        await agent.process({"action": "record_outcome", "agent_id": "c", "kind": "failure"})
        await agent.process({"action": "record_outcome", "agent_id": "d", "kind": "security_incident"})
        c = (await agent.process({"action": "score", "agent_id": "c"}))["data"]["score"]
        d = (await agent.process({"action": "score", "agent_id": "d"}))["data"]["score"]
        assert d < c  # security incident penalizes harder

    @pytest.mark.asyncio
    async def test_tiers(self, agent):  # T7
        assert agent._tier(0.9) == "TRUSTED"
        assert agent._tier(0.7) == "RELIABLE"
        assert agent._tier(0.5) == "NEUTRAL"
        assert agent._tier(0.3) == "CAUTION"
        assert agent._tier(0.1) == "UNTRUSTED"

    @pytest.mark.asyncio
    async def test_time_decay(self, agent):  # T4
        subj = agent._subject("e", create=True)
        # inject an old success directly
        from src.core import Outcome
        subj.outcomes.append(Outcome(kind="success", at=_utcnow() - timedelta(days=365), weight=1.0))
        old = agent._score(subj)
        subj.outcomes.append(Outcome(kind="success", at=_utcnow(), weight=1.0))
        fresh = agent._score(subj)
        assert fresh > old  # recent evidence moves score more

    @pytest.mark.asyncio
    async def test_bad_kind_and_weight(self, agent):
        assert (await agent.process({"action": "record_outcome", "agent_id": "a", "kind": "bogus"}))["status"] == "error"
        assert (await agent.process({"action": "record_outcome", "agent_id": "a", "kind": "success", "weight": -1}))["status"] == "error"


class TestAttestation:
    @pytest.mark.asyncio
    async def test_attest_and_verify(self, agent):  # T5, T6
        await agent.process({"action": "record_outcome", "agent_id": "f", "kind": "success"})
        att = (await agent.process({"action": "attest", "agent_id": "f", "claim": "kyc"}))["data"]
        v = await agent.process({"action": "verify_attestation", "agent_id": "f",
                                 "attestation_id": att["attestation_id"]})
        assert v["data"]["valid"] is True

    @pytest.mark.asyncio
    async def test_verify_unknown(self, agent):
        v = await agent.process({"action": "verify_attestation", "agent_id": "f",
                                 "attestation_id": "deadbeef"})
        assert v["data"]["valid"] is False

    @pytest.mark.asyncio
    async def test_attestation_chain_links(self, agent):
        await agent.process({"action": "record_outcome", "agent_id": "g", "kind": "success"})
        a1 = (await agent.process({"action": "attest", "agent_id": "g"}))["data"]
        a2 = (await agent.process({"action": "attest", "agent_id": "g"}))["data"]
        assert a2["prev"] == a1["attestation_id"]  # chained


class TestHistory:
    @pytest.mark.asyncio
    async def test_history(self, agent):
        await agent.process({"action": "record_outcome", "agent_id": "h", "kind": "success"})
        await agent.process({"action": "record_outcome", "agent_id": "h", "kind": "failure"})
        r = await agent.process({"action": "history", "agent_id": "h"})
        assert len(r["data"]["outcomes"]) == 2
        assert "tier" in r["data"]
