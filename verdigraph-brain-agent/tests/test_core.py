"""Invariant tests for verdigraph-brain-agent (VB1-VB6) + fleet contract."""
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core import build

FIXTURE = os.path.join(os.path.dirname(__file__), "fixture_genome.json")


@pytest.fixture
def core():
    return build()


def genome_text() -> str:
    with open(FIXTURE, "r", encoding="utf-8") as f:
        return f.read()


async def _build(core, **kw):
    payload = {"action": "build", "content": genome_text(),
               "format": "verdigraph_genome", **kw}
    return await core.process(payload)


# --- VB1 determinism ------------------------------------------------------- #
async def test_VB1_identical_bytes_identical_brain(core):
    a = await _build(core)
    b = await _build(core)
    assert a["status"] == b["status"] == "ok"
    assert a["data"]["brain_id"] == b["data"]["brain_id"]
    assert a["data"]["content_hash"] == b["data"]["content_hash"]
    assert a["data"]["node_count"] == b["data"]["node_count"] == 14
    assert a["data"]["edge_count"] == b["data"]["edge_count"] == 33


async def test_VB1_one_byte_of_drift_changes_the_brain(core):
    a = await _build(core)
    drifted = await core.process({"action": "build",
                                  "content": genome_text() + " ",
                                  "format": "verdigraph_genome"})
    assert drifted["status"] == "ok"
    assert drifted["data"]["brain_id"] != a["data"]["brain_id"]


# --- VB2 honest invariant report ------------------------------------------- #
async def test_VB2_build_carries_full_invariant_report(core):
    r = await _build(core)
    report = r["data"]["invariant_report"]
    checks = report.get("checks") or report.get("invariants") or []
    assert len(checks) >= 9
    # honest: report includes pass/fail detail, not just a boolean
    assert any("passed" in json.dumps(c) for c in checks) or "passed" in report


# --- VB3 machine-checkable verification ------------------------------------ #
async def test_VB3_verify_matches_and_catches_mismatch(core):
    built = await _build(core)
    good = await core.process({"action": "verify", "content": genome_text(),
                               "format": "verdigraph_genome",
                               "brain_id": built["data"]["brain_id"]})
    assert good["data"]["valid"] is True
    bad = await core.process({"action": "verify", "content": genome_text(),
                              "format": "verdigraph_genome",
                              "brain_id": "FAKE_ID_123"})
    assert bad["data"]["valid"] is False
    assert bad["data"]["matches"]["brain_id"] is False


# --- VB4 unsupported format teaches ---------------------------------------- #
async def test_VB4_unknown_format_names_supported_formats(core):
    r = await core.process({"action": "build", "content": genome_text(),
                            "format": "carrier_pigeon"})
    assert r["status"] == "error"
    assert "verdigraph_genome" in r["constraint"]


# --- VB5 provenance --------------------------------------------------------- #
async def test_VB5_build_carries_provenance(core):
    r = await _build(core)
    p = r["data"]["provenance"]
    assert p["input_bytes"] == len(genome_text().encode())
    assert len(p["input_sha256"]) == 64
    assert p["format"] == "verdigraph_genome"


# --- VB6 / fleet C1 contract ------------------------------------------------ #
@pytest.mark.parametrize("bad", [None, [], "x", 5])
async def test_VB6_nondict_input_never_raises(core, bad):
    r = await core.process(bad)
    assert r["status"] == "error"
    assert r["field"] == "input_data"


async def test_VB6_missing_content_is_structured_error(core):
    r = await core.process({"action": "build"})
    assert r["status"] == "error"
    assert r["field"] == "content"


async def test_unknown_action_lists_actions(core):
    r = await core.process({"action": "meditate"})
    assert r["status"] == "error"
    assert "build" in r["constraint"]


async def test_detect_format_and_health(core):
    d = await core.process({"action": "detect_format",
                            "content": genome_text()})
    assert d["data"]["format"] == "verdigraph_genome"
    h = await core.health()
    assert h["status"] == "ok"
    assert h["checks"]["builds"] >= 0
