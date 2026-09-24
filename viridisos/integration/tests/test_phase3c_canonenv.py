"""Phase 3c canon-index relocation acceptance.

Run from the ViridisOS package root:
    python3 integration/tests/test_phase3c_canonenv.py

Pure stdlib. Proves the default index remains backward-compatible and the
VIRIDISOS_CANON_INDEX override controls resolver construction with no args.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import runtime.canon_resolver as canon_resolver
from viridis_platform import catalog_status


ENV_NAME = "VIRIDISOS_CANON_INDEX"
REAL_INDEX = ROOT.parent / "RESEARCH_PIPELINE_v2" / "canon_fingerprint_index.json"
EXPECTED = {
    "mutualist": "BLOCKED",
    "restoration": "READY",
    "afforestation": "READY",
    "harmonization": "READY",
}

_PASS = 0
_FAIL = 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {name}")


def _states_for(index_path: str | None) -> dict[str, str]:
    had_original = ENV_NAME in os.environ
    original = os.environ.get(ENV_NAME)
    try:
        if index_path is None:
            os.environ.pop(ENV_NAME, None)
        else:
            os.environ[ENV_NAME] = index_path
        importlib.reload(canon_resolver)
        resolver = canon_resolver.CanonResolver()
        return {row["id"]: row["state"] for row in catalog_status(resolver)}
    finally:
        if had_original:
            os.environ[ENV_NAME] = original or ""
        else:
            os.environ.pop(ENV_NAME, None)
        importlib.reload(canon_resolver)


def c_default_path_unchanged():
    check("default index keeps 3 READY + mutualist BLOCKED",
          _states_for(None) == EXPECTED)


def c_real_index_override_matches_default():
    check("real-index override keeps 3 READY + mutualist BLOCKED",
          _states_for(str(REAL_INDEX)) == EXPECTED)


def c_missing_index_override_blocks_all():
    missing = ROOT / "_missing_canon" / "canon_fingerprint_index.json"
    states = _states_for(str(missing))
    check("missing-index override makes every module BLOCKED",
          set(states) == set(EXPECTED)
          and all(state == "BLOCKED" for state in states.values()))


TESTS = [
    c_default_path_unchanged,
    c_real_index_override_matches_default,
    c_missing_index_override_blocks_all,
]


if __name__ == "__main__":
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            _FAIL += 1
            print(f"  FAIL: {test.__name__} ({type(exc).__name__}: {exc})")
    print(f"{_PASS} passed, {_FAIL} failed")
    raise SystemExit(1 if _FAIL else 0)
