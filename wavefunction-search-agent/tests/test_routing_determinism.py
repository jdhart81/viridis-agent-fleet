"""Routing determinism pin (N64 idiom propagated to the demand side, N68).

Wavefunction-search ROUTES demand between agents/collectives; a router that
ranks differently on identical input silently redistributes real traffic.
The core is stdlib-deterministic (no random, no clock in the match path) but
nothing pinned that. These tests make it mechanical:

- identical intake -> find_matches output byte-identical across FRESH engines
- repeat find_matches on one engine is pure (read-only, no drift)
- scoring functions and end-to-end routing diverge with dialogue
- equal combined scores tie-break by REGISTRATION ORDER (dict insertion) —
  documented as the rule, so an accidental re-keying shows up as a red test.
"""

import asyncio
import json
import re
from pathlib import Path

import pytest

from adapters.mcp_server import FleetShim
from src.core import VERSION as CORE_VERSION, WavefunctionSearchCore


DIALOGUE = [
    {"role": "user", "content": "I want to help regenerate watershed forests"},
    {"role": "user", "content": "community governance matters to me"},
]

DIVERGENT_DIALOGUE = [
    {"role": "user", "content": "I want to build industrial mining automation"},
]


def test_local_manifest_and_adapter_versions_match():
    manifest = (Path(__file__).resolve().parents[1] / "agent.yaml").read_text()
    version = re.search(r'^version:\s*"([^"]+)"', manifest, re.MULTILINE)
    assert version is not None
    assert CORE_VERSION == FleetShim.VERSION == version.group(1)


def _seed(engine: WavefunctionSearchCore) -> None:
    engine.register_collective(
        "alpha", "Alpha Regen", "watershed regeneration",
        {"water": 0.9, "governance": 0.8},
        {"c1_biosphere": 0.95, "c2_governance": 0.9,
         "c3_transparency": 0.9, "c4_long_term": 0.9}, capacity=10)
    engine.register_collective(
        "beta", "Beta Commons", "community forest commons",
        {"forest": 0.85, "governance": 0.9},
        {"c1_biosphere": 0.9, "c2_governance": 0.92,
         "c3_transparency": 0.9, "c4_long_term": 0.9}, capacity=10)


async def _pipeline(dialogue) -> str:
    engine = WavefunctionSearchCore()
    _seed(engine)
    await engine.process({"stage": "intake", "user_id": "u1", "dialogue": dialogue})
    out = await engine.process({"stage": "find_matches", "user_id": "u1"})
    assert out["status"] == "ok", out
    return json.dumps(out, sort_keys=True, default=str)


@pytest.mark.asyncio
async def test_matches_byte_identical_across_fresh_engines():
    runs = [await _pipeline(DIALOGUE) for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]


@pytest.mark.asyncio
async def test_find_matches_is_pure_on_repeat():
    engine = WavefunctionSearchCore()
    _seed(engine)
    await engine.process({"stage": "intake", "user_id": "u1", "dialogue": DIALOGUE})
    a = json.dumps(await engine.process({"stage": "find_matches", "user_id": "u1"}),
                   sort_keys=True, default=str)
    b = json.dumps(await engine.process({"stage": "find_matches", "user_id": "u1"}),
                   sort_keys=True, default=str)
    assert a == b


@pytest.mark.asyncio
async def test_non_triviality_scoring_diverges_on_divergent_profiles():
    """The score is non-trivial and the flagship path returns real matches."""
    engine = WavefunctionSearchCore()
    _seed(engine)
    await engine.process({"stage": "intake", "user_id": "u1", "dialogue": DIALOGUE})
    wf = engine.user_wavefunctions["u1"]

    rich = engine.collectives["alpha"]
    a = engine.compute_alignment_score(wf, rich)

    engine.register_collective("gamma", "Gamma", "m", {"heart": 0.01},
                               {"c1_biosphere": 0.4, "c2_governance": 0.4,
                                "c3_transparency": 0.4,
                                "c4_long_term": 0.4}, capacity=10)
    poor = engine.collectives["gamma"]
    b = engine.compute_alignment_score(wf, poor)
    assert a != b, "alignment scoring is input-insensitive"

    ca = engine.compute_constitutional_score(rich)
    cb = engine.compute_constitutional_score(poor)
    assert ca != cb, "constitutional scoring is input-insensitive"
    matches = await engine.find_matches("u1")
    assert [match["collective_id"] for match in matches] == ["alpha", "beta"]
    assert sum(match["routing_probability"] for match in matches) == (
        pytest.approx(1.0))


@pytest.mark.asyncio
async def test_dialogue_conditions_which_collective_is_routed():
    engine = WavefunctionSearchCore()
    constitution = {
        "c1_biosphere": 0.9,
        "c2_governance": 0.9,
        "c3_transparency": 0.9,
        "c4_long_term": 0.9,
    }
    engine.register_collective(
        "climate", "Climate", "climate action", {"climate": 1.0},
        constitution, capacity=10)
    engine.register_collective(
        "community", "Community", "community governance",
        {"community": 1.0}, constitution, capacity=10)

    await engine.process({
        "stage": "intake", "user_id": "climate-user",
        "dialogue": [{"role": "user", "content": "climate action"}]})
    await engine.process({
        "stage": "intake", "user_id": "community-user",
        "dialogue": [{"role": "user", "content": "community"}]})

    climate = await engine.find_matches("climate-user")
    community = await engine.find_matches("community-user")
    assert [match["collective_id"] for match in climate] == ["climate"]
    assert [match["collective_id"] for match in community] == ["community"]


@pytest.mark.asyncio
async def test_equal_scores_tie_break_by_registration_order():
    """Two collectives with IDENTICAL profiles must rank in registration
    order (stable sort over dict insertion). Pins today's rule so silent
    re-keying of self.collectives becomes visible."""
    engine = WavefunctionSearchCore()
    profile = (
        {"water": 0.9, "forest": 0.9, "community": 0.9,
         "governance": 0.9},
        {"c1_biosphere": 0.95, "c2_governance": 0.9,
         "c3_transparency": 0.9, "c4_long_term": 0.9})
    engine.register_collective("first", "First", "m", profile[0], profile[1], 10)
    engine.register_collective("second", "Second", "m", profile[0], profile[1], 10)
    await engine.process({"stage": "intake", "user_id": "u1", "dialogue": DIALOGUE})
    out = await engine.process({"stage": "find_matches", "user_id": "u1"})
    ids = [m["collective_id"] for m in out["matches"]]
    assert ids == ["first", "second"]
    assert out["matches"][0]["combined_score"] == (
        out["matches"][1]["combined_score"])
