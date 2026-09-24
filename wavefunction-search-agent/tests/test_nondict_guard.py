"""Pin the non-dict input contract (Night 61).

wavefunction-search satisfies the fleet-wide "process() never raises"
contract through its validation gate (src/validation.py), not the inline
isinstance idiom used elsewhere in the stable. The envelope is the
validation-gate dialect: a structured `errors` list whose entries carry
field / message / error_type / timestamp. This test pins that shape so a
regression in either core.process() or validate_process_input() is caught.

NOTE (supersedes the N60 queue entry): the gate's envelope is NOT the thin
raw-str variant — it is field-rich. No inline guard should be added; doing so
would change the established response shape that this suite now pins.
"""
import pytest

from src.core import WavefunctionSearchCore


@pytest.fixture
def core():
    return WavefunctionSearchCore()


@pytest.mark.parametrize("bad_input", [None, [], "not-a-dict", 5])
async def test_nondict_input_returns_validation_gate_envelope(core, bad_input):
    r = await core.process(bad_input)
    assert isinstance(r, dict)
    assert r["status"] == "error"
    assert r["reason"] == "Validation failed"
    assert isinstance(r["errors"], list) and len(r["errors"]) == 1
    err = r["errors"][0]
    assert err["field"] == "input"
    assert err["message"] == "input_data must be a dict"
    assert err["error_type"] == "validation_error"
    assert "timestamp" in err
    assert r["warnings"] == []


async def test_valid_dict_input_still_routes(core):
    """Regression guard: a well-formed request must not hit the gate."""
    r = await core.process({"stage": "intake", "user_id": "u-guard-test",
                            "dialogue": []})
    assert r["status"] == "ok"
    assert r["stage"] == "intake"
