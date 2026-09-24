"""
Invariant tests for fleet_utils.error_envelope (Nightkeeper N56, C4 helper).

Maps 1:1 to the I1–I6 invariants documented in errors.py.
Runnable under real pytest OR standalone (python test_errors.py).
"""

import pytest

from fleet_utils.errors import error_envelope, ERROR_ENVELOPE_KEYS


def test_I1_canonical_key_order_and_set():
    env = error_envelope("ValidationError", "bad input")
    assert tuple(env.keys()) == ERROR_ENVELOPE_KEYS


def test_I2_status_is_error():
    assert error_envelope("X", "m")["status"] == "error"


def test_I3_timestamp_default_is_iso_string():
    env = error_envelope("X", "m")
    assert isinstance(env["timestamp"], str) and "T" in env["timestamp"]


def test_I3_timestamp_preserved_when_supplied():
    env = error_envelope("X", "m", timestamp="2026-06-15T00:00:00")
    assert env["timestamp"] == "2026-06-15T00:00:00"


def test_I4_empty_error_type_raises():
    with pytest.raises(ValueError):
        error_envelope("", "m")


def test_I4_empty_message_raises():
    with pytest.raises(ValueError):
        error_envelope("X", "   ")


def test_I4_non_string_message_raises():
    with pytest.raises(ValueError):
        error_envelope("X", 123)


def test_I5_legacy_error_absent_by_default():
    assert "error" not in error_envelope("X", "m")


def test_I5_legacy_error_defaults_to_message():
    env = error_envelope("X", "boom", include_legacy_error=True)
    assert env["error"] == "boom"


def test_I5_legacy_error_explicit_value():
    env = error_envelope("X", "boom", include_legacy_error=True, legacy_error="legacy text")
    assert env["error"] == "legacy text"


def test_I6_does_not_mutate_inputs_and_returns_fresh_dict():
    a = error_envelope("X", "m")
    b = error_envelope("X", "m")
    a["field"] = "mutated"
    assert b["field"] is None  # independent objects


def test_guard_path_shape_matches_legacy_guard():
    # Reproduces the regulatory-radar/POC guard envelope exactly (sans legacy key).
    env = error_envelope(
        "ValidationError", "input_data must be a dict, got str",
        field="input_data", value="str", constraint="input_data must be a dict",
    )
    assert env["error_type"] == "ValidationError"
    assert env["field"] == "input_data"
    assert env["constraint"] == "input_data must be a dict"
    assert "error" not in env


def test_unknown_action_path_includes_legacy_key():
    env = error_envelope(
        "UnknownOperation", "Unknown action: bogus", include_legacy_error=True,
    )
    assert env["error"] == "Unknown action: bogus"
    assert env["error_type"] == "UnknownOperation"


if __name__ == "__main__":
    import sys, types
    # standalone shim
    class _R:
        def __init__(s,e): s.e=e
        def __enter__(s): return s
        def __exit__(s,et,ev,tb):
            if et is None: raise AssertionError("DID NOT RAISE")
            return issubclass(et,s.e)
    pytest.raises = lambda e:_R(e)
    p=f=0
    g=dict(globals())
    for n,fn in g.items():
        if n.startswith("test_") and callable(fn):
            try: fn(); p+=1
            except Exception as e: f+=1; print("FAIL",n,e)
    print(f"{p} passed, {f} failed"); sys.exit(1 if f else 0)
