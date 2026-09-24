"""Candidate-level smoke for the public Wavefunction MCP shim."""

import pytest

from adapters.mcp_server import FleetShim


CONSTITUTION = {
    "c1_biosphere": 0.9,
    "c2_governance": 0.9,
    "c3_transparency": 0.9,
    "c4_long_term": 0.9,
}


@pytest.mark.asyncio
async def test_mcp_shim_routes_dialogue_to_a_real_candidate():
    shim = FleetShim()
    registered = await shim.process({
        "action": "register_collective",
        "collective_id": "climate-agent",
        "name": "Climate Agent",
        "mission": "Execute climate action",
        "domain_profile": {"climate": 1.0},
        "constitutional_scores": CONSTITUTION,
        "capacity": 10,
    })
    assert registered == {
        "status": "ok",
        "collective_id": "climate-agent",
    }

    intake = await shim.process({
        "stage": "intake",
        "user_id": "buyer-1",
        "dialogue": [{"role": "user", "content": "I need climate action"}],
    })
    assert intake["status"] == "ok"

    routed = await shim.process({
        "stage": "find_matches",
        "user_id": "buyer-1",
    })
    assert routed["status"] == "ok"
    assert [item["collective_id"] for item in routed["matches"]] == [
        "climate-agent"]
    assert routed["matches"][0]["routing_probability"] == pytest.approx(1.0)

    health = await shim.health()
    assert health["status"] == "ok"
    assert health["version"] == "0.2.0"
    assert health["checks"]["wavefunctions"] == 1
    assert health["checks"]["collectives"] == 1


@pytest.mark.asyncio
async def test_mcp_shim_fails_closed_on_incomplete_constitution():
    shim = FleetShim()
    await shim.process({
        "action": "register_collective",
        "collective_id": "incomplete-agent",
        "name": "Incomplete Agent",
        "mission": "Missing constitutional evidence",
        "domain_profile": {"climate": 1.0},
        "constitutional_scores": {"c1_biosphere": 1.0},
        "capacity": 10,
    })
    await shim.process({
        "stage": "intake",
        "user_id": "buyer-2",
        "dialogue": [{"role": "user", "content": "climate"}],
    })
    routed = await shim.process({
        "stage": "find_matches",
        "user_id": "buyer-2",
    })
    assert routed["status"] == "ok"
    assert routed["matches"] == []
