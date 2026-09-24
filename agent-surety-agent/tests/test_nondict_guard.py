"""Pin the fleet-standard non-dict input guard (N54 idiom) — Night 61.

process() must never raise on non-dict input; it must return the canonical
structured error envelope. The guard existed in core.py but no test pinned
it, so a regression would have gone undetected (same gap N60 closed for the
revenue services).
"""
import asyncio

import pytest

from src.core import build


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


@pytest.mark.parametrize("bad_input", [None, [], "not-a-dict", 5])
def test_nondict_input_returns_canonical_envelope(bad_input):
    a = build()
    r = run(a.process(bad_input))
    assert isinstance(r, dict)
    assert r["status"] == "error"
    assert r["error_type"] == "ValidationError"
    assert r["field"] == "input"
    assert r["value"] == type(bad_input).__name__
    assert r["constraint"] == "dict"
    assert r["message"] == "input must be an object"
    assert "timestamp" in r
