"""Tests for agent-identity-registry-agent — invariants R1–R8."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core import IdentityRegistryCore, AgentConfig, build, ACTIVE, REVOKED


@pytest.fixture
def agent():
    return build(AgentConfig(name="agent-identity-registry-agent", debug=True))


async def _reg(agent, agent_id="agentA", caps=None, **kw):
    payload = {"action": "register", "agent_id": agent_id,
               "capabilities": caps or ["cad", "measurement"], "pubkey": "pk_" + agent_id}
    payload.update(kw)
    return await agent.process(payload)


class TestFleetInterface:
    @pytest.mark.asyncio
    async def test_health(self, agent):
        h = await agent.health()
        for k in ("status", "agent", "version", "timestamp"):
            assert k in h

    def test_describe(self, agent):
        d = agent.describe()
        for k in ("name", "version", "capabilities", "inputs", "outputs"):
            assert k in d
        assert d["a2a_role"] == "identity"

    @pytest.mark.asyncio
    async def test_unknown_action(self, agent):
        assert (await agent.process({"action": "zzz"}))["status"] == "error"

    @pytest.mark.asyncio
    async def test_non_dict(self, agent):
        for bad in (None, [], "s", 9):
            assert (await agent.process(bad))["status"] == "error"


class TestRegister:
    @pytest.mark.asyncio
    async def test_register_ok(self, agent):
        r = await _reg(agent)
        assert r["status"] == "ok"
        assert r["data"]["did"].startswith("did:viridis:")
        assert r["data"]["created"] is True

    @pytest.mark.asyncio
    async def test_did_deterministic(self, agent):  # R1
        r1 = await _reg(agent, agent_id="x", pubkey="pkX")
        did1 = r1["data"]["did"]
        # re-register same id+pubkey -> same did
        r2 = await _reg(agent, agent_id="x", pubkey="pkX")
        assert r2["data"]["did"] == did1

    @pytest.mark.asyncio
    async def test_register_idempotent_updates(self, agent):  # R2
        await _reg(agent, agent_id="y", caps=["a"])
        r = await _reg(agent, agent_id="y", caps=["a", "b"])
        assert r["data"]["created"] is False
        assert r["data"]["version"] == 2
        assert len(agent._by_id) == 1

    @pytest.mark.asyncio
    async def test_capabilities_required_nonempty(self, agent):  # R7
        assert (await agent.process({"action": "register", "agent_id": "z", "capabilities": []}))["status"] == "error"
        assert (await agent.process({"action": "register", "agent_id": "z", "capabilities": "cad"}))["status"] == "error"


class TestResolve:
    @pytest.mark.asyncio
    async def test_resolve_by_id_and_did(self, agent):
        did = (await _reg(agent, agent_id="m"))["data"]["did"]
        by_id = await agent.process({"action": "resolve", "agent_id": "m"})
        by_did = await agent.process({"action": "resolve", "did": did})
        assert by_id["data"]["agent_id"] == "m"
        assert by_did["data"]["agent_id"] == "m"

    @pytest.mark.asyncio
    async def test_resolve_unknown(self, agent):  # R5
        assert (await agent.process({"action": "resolve", "agent_id": "ghost"}))["status"] == "error"


class TestDiscover:
    @pytest.mark.asyncio
    async def test_and_semantics(self, agent):  # R3
        await _reg(agent, agent_id="a1", caps=["cad", "measurement"])
        await _reg(agent, agent_id="a2", caps=["cad"])
        await _reg(agent, agent_id="a3", caps=["security"])
        r = await agent.process({"action": "discover", "capabilities": ["cad", "measurement"]})
        ids = [x["agent_id"] for x in r["data"]["results"]]
        assert ids == ["a1"]  # only a1 has BOTH

    @pytest.mark.asyncio
    async def test_revoked_excluded(self, agent):  # R3/R6
        await _reg(agent, agent_id="b1", caps=["cad"])
        await agent.process({"action": "revoke", "agent_id": "b1"})
        r = await agent.process({"action": "discover", "capabilities": ["cad"]})
        assert r["data"]["count"] == 0

    @pytest.mark.asyncio
    async def test_ranking_stable(self, agent):  # R4
        await _reg(agent, agent_id="c1", caps=["cad"], reputation_hint=0.4)
        await _reg(agent, agent_id="c2", caps=["cad"], reputation_hint=0.9)
        r = await agent.process({"action": "discover", "capabilities": ["cad"]})
        ids = [x["agent_id"] for x in r["data"]["results"]]
        assert ids[0] == "c2"  # higher reputation ranks first


class TestRevoke:
    @pytest.mark.asyncio
    async def test_revoke_retains_record(self, agent):  # R6
        await _reg(agent, agent_id="d1")
        await agent.process({"action": "revoke", "agent_id": "d1"})
        r = await agent.process({"action": "resolve", "agent_id": "d1"})
        assert r["data"]["status"] == REVOKED  # still resolvable

    @pytest.mark.asyncio
    async def test_revoke_unknown(self, agent):
        assert (await agent.process({"action": "revoke", "agent_id": "nope"}))["status"] == "error"


class TestList:
    @pytest.mark.asyncio
    async def test_list_filter_status(self, agent):
        await _reg(agent, agent_id="e1")
        await _reg(agent, agent_id="e2")
        await agent.process({"action": "revoke", "agent_id": "e2"})
        allr = await agent.process({"action": "list"})
        activer = await agent.process({"action": "list", "status": ACTIVE})
        assert allr["data"]["count"] == 2
        assert activer["data"]["count"] == 1
