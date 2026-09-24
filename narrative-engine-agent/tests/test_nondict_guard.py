"""Pin the fleet-standard non-dict input guard (N54 idiom).

process() must never raise on non-dict input; it must return the canonical
structured error envelope. Added Night 60 — the guard existed in core.py but
no test pinned it, so a regression would have gone undetected.
"""
import pytest

from src.core import NarrativeEngineCore


@pytest.fixture
def core():
    return NarrativeEngineCore()


@pytest.mark.parametrize("bad_input", [None, [], "not-a-dict", 5])
async def test_nondict_input_returns_canonical_envelope(core, bad_input):
    r = await core.process(bad_input)
    assert isinstance(r, dict)
    assert r["status"] == "error"
    assert r["error_type"] == "ValidationError"
    assert r["field"] == "input_data"
    assert r["value"] == type(bad_input).__name__
    assert r["constraint"] == "input_data must be a dict"
    assert "timestamp" in r
