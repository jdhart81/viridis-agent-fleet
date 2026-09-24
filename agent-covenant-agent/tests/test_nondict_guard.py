"""Pin the fleet-standard non-dict input guard (N54 idiom) — Night 63.

process() must never raise on non-dict input; it must return the canonical
A2A structured error envelope. The existing suite asserted only
status=="error" (shallow pin); this pins the full envelope shape
(field/value/constraint/message/timestamp) so a dialect regression cannot
land silently. Envelope captured by runtime probe before writing this test.
Covenant agent (deny-by-default authority leases) — closes the N61/N62 pin-sweep queue (22/22 stable agents pinned).
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
