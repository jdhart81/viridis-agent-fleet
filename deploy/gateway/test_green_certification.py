#!/usr/bin/env python3
"""
GR3 gateway composition — a green-router certificate is REAL clearinghouse
retirement or nothing. Real green-router + offsets cores, real StateStore.

Run:  pytest deploy/gateway/test_green_certification.py -q
"""
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import viridis_mcp_gateway as gateway                      # noqa: E402
from state_store import StateStore                         # noqa: E402


def _load(agent_dir):
    for m in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
        del sys.modules[m]
    root = str(ROOT / agent_dir)
    while root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)
    ps = importlib.util.spec_from_file_location(
        "src", ROOT / agent_dir / "src" / "__init__.py",
        submodule_search_locations=[str(ROOT / agent_dir / "src")])
    pkg = importlib.util.module_from_spec(ps)
    sys.modules["src"] = pkg
    ps.loader.exec_module(pkg)
    cs = importlib.util.spec_from_file_location(
        "src.core", ROOT / agent_dir / "src" / "core.py")
    mod = importlib.util.module_from_spec(cs)
    sys.modules["src.core"] = mod
    cs.loader.exec_module(mod)
    return mod


GREEN = _load("green-router-agent")
OFFSETS = _load("agent-offset-clearinghouse-agent")

WORKLOAD = {"backend_id": "frontier_cloud", "total_tokens": 3000,
            "output_tokens": 800, "calls": 100}


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def build_pair(db, seed_book=True):
    store = StateStore(db)
    green = GREEN.build()
    offsets = OFFSETS.build()
    if seed_book:
        r = run(offsets.process({
            "action": "list_credit", "issuer": "test-issuer",
            "project_id": "test-forest",
            "mass_g": 1_000_000, "price_minor_per_kg": 100,
            "verification_ref": "dscore:gateway-green-certification-test",
            "registry": "verra", "vcs_project_id": "VCS0001",
            "serial_number": "VCS-0001-11111-22222", "vintage": "2025"}))
        assert r["status"] == "ok", r
    gateway._attach_green_certification(green, offsets, store)
    return store, green, offsets


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "state.db")


def test_GR3_certify_retires_real_mass_with_provenance(db):
    _, green, offsets = build_pair(db)
    r = run(green.process({"action": "certify", "workload": WORKLOAD}))
    assert r["status"] == "ok", r
    cert = r["data"]
    assert cert["status"] == "certified"
    ret = cert["retirement"]
    assert ret["status"] == "retired"
    assert ret["retired_g"] == cert["footprint"]["retirement_required_g"]
    assert ret["purchase_id"] == cert["certificate_id"]
    assert ret["fills"] and ret["fills"][0]["registry"] == "verra"
    # the clearinghouse really moved
    verify = run(offsets.process({"action": "verify_retirement",
                                  "purchase_id": cert["certificate_id"]}))
    assert verify["status"] == "ok"


def test_GR3_empty_book_fails_closed_no_certificate(db):
    _, green, offsets = build_pair(db, seed_book=False)
    r = run(green.process({"action": "certify", "workload": WORKLOAD}))
    assert r["status"] == "error"
    assert r["error_type"] == "retirement_refused"
    led = run(green.process({"action": "list_certificates"}))
    assert led["data"]["count"] == 0                      # voided, honest


def test_GR3_quote_and_reads_bypass_composition(db):
    _, green, offsets = build_pair(db, seed_book=False)
    q = run(green.process({"action": "quote_footprint",
                           "workload": WORKLOAD}))
    assert q["status"] == "ok"                            # quotes need no book
    rt = run(green.process({"action": "green_route", "workload": WORKLOAD}))
    assert rt["status"] == "ok"


def test_GR3_retirement_idempotent_on_certificate_id(db):
    """The clearinghouse's O2 idempotency protects a replayed finalize."""
    _, green, offsets = build_pair(db)
    r = run(green.process({"action": "certify", "workload": WORKLOAD}))
    cert_id = r["data"]["certificate_id"]
    replay = run(offsets.process({
        "action": "buy_offset", "buyer": "green-router",
        "purchase_id": cert_id,
        "mass_g": r["data"]["retirement"]["retired_g"]}))
    assert replay["data"]["duplicate"] is True            # never double-retires


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
