"""Tests for underwriting_bridge.py — one per BW invariant, real cores."""
import asyncio
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import underwriting_bridge   # noqa: E402


def _load_pkg(agent_dir: str):
    for m in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
        del sys.modules[m]
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


VERIFIED = _load_pkg("agent-verified-relay-agent")
SURETY = _load_pkg("agent-surety-agent")


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def ok_transport(url, body, timeout_s):
    import json
    return (200, "application/json", json.dumps(
        {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}))


def err_transport(url, body, timeout_s):
    raise ConnectionError("down")


def _rig():
    return VERIFIED.build(transport=ok_transport), SURETY.build()


def _register(v, provider="acme", url="https://api.example.com/mcp"):
    r = run(v.process({"action": "register_service", "url": url, "provider": provider}))
    return r["data"]["service_id"]


def _relay_ok(v, sid, n):
    for i in range(n):
        run(v.process({"action": "call_verified", "service_id": sid,
                       "tool": "t", "call_id": f"{sid}-ok-{i}"}))


def quote(v, s, sid, coverage=100_000, days=30):
    return run(underwriting_bridge.quote_bond_for_service(v, s, sid, coverage, days))


def test_bw2_unknown_service_errors_cleanly():
    v, s = _rig()
    r = quote(v, s, "vsvc-nope")
    assert r["status"] == "error" and r["field"] == "service_id"
    r2 = run(underwriting_bridge.quote_bond_for_service(v, s, "", 100, 30))
    assert r2["status"] == "error"


def test_bw3_monotonic_more_deliveries_never_costs_more():
    v, s = _rig()
    thin = _register(v, provider="thin")
    _relay_ok(v, thin, 2)
    thick = _register(v, provider="thick")
    _relay_ok(v, thick, 40)
    q_thin = quote(v, s, thin)["quote"]
    q_thick = quote(v, s, thick)["quote"]
    assert q_thick["premium_minor"] <= q_thin["premium_minor"]   # BW3
    # A brand-new provider (no deliveries) prices at unknown rate or declines.
    fresh = _register(v, provider="fresh")
    q_fresh = quote(v, s, fresh)["quote"]
    assert q_fresh["decision"] in ("quote", "declined")
    if q_fresh["decision"] == "quote":
        assert q_fresh["premium_minor"] >= q_thick["premium_minor"]


def test_bw4_traceability_hash_and_disclosed_inputs():
    v, s = _rig()
    sid = _register(v)
    _relay_ok(v, sid, 5)
    r = quote(v, s, sid)
    assert r["quote"]["quote_hash"]                              # recomputable
    assert r["underwriting_inputs"]["successful_deliveries"] == 5
    # Re-derive: feeding the disclosed inputs to surety reproduces the hash.
    direct = run(s.process({"action": "price_bond", "coverage_minor": 100_000,
                            "duration_days": 30,
                            "history": r["underwriting_inputs"]}))["data"]
    assert direct["quote_hash"] == r["quote"]["quote_hash"]      # BW4


def test_bw5_honest_mapping_only_calls_ok():
    v, s = _rig()
    # A service with only failed relays: calls_ok stays 0 -> unknown risk.
    vbad = VERIFIED.build(transport=err_transport)
    sid = run(vbad.process({"action": "register_service",
                            "url": "https://bad.example.com/mcp",
                            "provider": "bad"}))["data"]["service_id"]
    for i in range(6):
        run(vbad.process({"action": "call_verified", "service_id": sid,
                          "tool": "t", "call_id": f"e{i}"}))
    r = run(underwriting_bridge.quote_bond_for_service(vbad, s, sid, 100_000, 30))
    assert r["service"]["calls_error"] == 6 and r["service"]["calls_ok"] == 0
    assert r["underwriting_inputs"]["successful_deliveries"] == 0
    assert r["underwriting_inputs"]["slashes"] == 0              # never invented
    # errors don't lower the premium below a proven provider's
    v2, s2 = _rig()
    good = _register(v2, provider="good")
    _relay_ok(v2, good, 6)
    r_good = quote(v2, s2, good)["quote"]
    assert r["quote"].get("premium_minor", 10**9) >= r_good.get("premium_minor", 0)


def test_bw6_validation_delegated_to_surety():
    v, s = _rig()
    sid = _register(v)
    _relay_ok(v, sid, 3)
    bad_cov = run(underwriting_bridge.quote_bond_for_service(v, s, sid, 0, 30))
    assert bad_cov["status"] == "error" and bad_cov["field"] == "coverage_minor"
    bad_dur = run(underwriting_bridge.quote_bond_for_service(v, s, sid, 100, 999))
    assert bad_dur["status"] == "error" and bad_dur["field"] == "duration_days"


def test_bw1_read_only_no_state_mutation():
    import copy
    v, s = _rig()
    sid = _register(v)
    _relay_ok(v, sid, 4)
    v_before = copy.deepcopy(run(v.process({"action": "list_services"}))["data"])
    for _ in range(3):
        quote(v, s, sid)
    v_after = run(v.process({"action": "list_services"}))["data"]
    assert v_before == v_after                                  # BW1
    # surety made no bonds
    assert run(s.process({"action": "list"}))["data"]["count"] == 0
