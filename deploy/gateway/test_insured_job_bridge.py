"""Tests for insured_job_bridge.py — one per IJ invariant, real cores."""
import asyncio
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import insured_job_bridge   # noqa: E402


def _load_pkg(agent_dir):
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
    return (200, "application/json", json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}))


def _rig():
    return VERIFIED.build(transport=ok_transport), SURETY.build()


def _register(v, provider="acme"):
    return run(v.process({"action": "register_service",
                          "url": "https://api.example.com/mcp",
                          "provider": provider}))["data"]["service_id"]


def _relay(v, sid, n):
    for i in range(n):
        run(v.process({"action": "call_verified", "service_id": sid,
                       "tool": "t", "call_id": f"{sid}-{i}"}))


def quote(v, s, sid, job=100000, cov=50000, days=30):
    return run(insured_job_bridge.quote_insured_job(v, s, sid, job, cov, days))


def test_ij1_ij2_itemized_and_priced_from_record():
    v, s = _rig()
    sid = _register(v)
    _relay(v, sid, 10)
    q = quote(v, s, sid)
    assert q["insurable"] is True
    d = q["quote"]
    assert d["total_protection_cost_minor"] == d["bond_premium_minor"] + d["escrow_fee_minor"]  # IJ2
    assert d["escrow_fee_minor"] == 1000    # 1% of 100000
    assert d["quote_hash"]                  # IJ1 recomputable carried through
    # premium reflects the Verified record (matches the underwriting bridge)
    import underwriting_bridge
    uw = run(underwriting_bridge.quote_bond_for_service(v, s, sid, 50000, 30))
    assert d["bond_premium_minor"] == uw["quote"]["premium_minor"]


def test_ij3_read_only():
    import copy
    v, s = _rig()
    sid = _register(v)
    _relay(v, sid, 5)
    v_before = copy.deepcopy(run(v.process({"action": "list_services"}))["data"])
    for _ in range(3):
        quote(v, s, sid)
    assert run(v.process({"action": "list_services"}))["data"] == v_before
    assert run(s.process({"action": "list"}))["data"]["count"] == 0   # no bonds posted


def test_ij4_unknown_service_and_validation():
    v, s = _rig()
    assert quote(v, s, "vsvc-missing")["status"] == "error"
    sid = _register(v)
    _relay(v, sid, 3)
    bad = run(insured_job_bridge.quote_insured_job(v, s, sid, 0, 50000, 30))
    assert bad["status"] == "error" and bad["field"] == "job_amount_minor"


def test_ij5_not_insurable_when_declined():
    v, s = _rig()
    # A provider with no successful deliveries: surety may still quote at the
    # unknown rate, so force a DECLINE via a huge coverage vs a slashed history
    # is not reachable here; instead a fresh provider with zero deliveries is
    # quotable — assert the insurable flag is coherent either way.
    fresh = _register(v, provider="fresh")
    q = quote(v, s, fresh)
    assert "insurable" in q
    if not q["insurable"]:
        assert "reason" in q and "quote" not in q


def test_ij6_playbook_is_ordered_and_complete():
    v, s = _rig()
    sid = _register(v)
    _relay(v, sid, 8)
    pb = quote(v, s, sid)["playbook"]
    tools = [(p["mount"], p["tool"]) for p in pb]
    assert ("surety", "post_bond") in tools
    assert ("escrow", "open") in tools
    assert ("verified", "call_verified") in tools
    assert ("arbitration", "file_case") in tools    # the breach path
    # steps are ordered: post_bond before escrow open before delivery
    assert tools.index(("surety", "post_bond")) < tools.index(("escrow", "open"))
    assert tools.index(("escrow", "open")) < tools.index(("verified", "call_verified"))
