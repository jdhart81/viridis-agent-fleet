"""agent-erc8004-bridge-agent — invariant tests (B1–B8) + fleet contract."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.core import build, AgentConfig


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


REG = {"action": "import_registration", "chain_id": 1, "token_id": 4242,
       "agent_uri": "https://agents.example/4242.json",
       "owner": "0xAbC0000000000000000000000000000000000001"}


def _import(agent, **over):
    return run(agent.process({**REG, **over}))


# --------------------------------------------------------------------- #
# B1 — deterministic, distinct bridge DIDs; content-addressed records
# --------------------------------------------------------------------- #
def test_b1_deterministic_and_distinct_dids():
    a = build()
    r1 = _import(a)
    r2 = _import(a)                                   # same identity
    assert r1["data"]["bridge_did"] == r2["data"]["bridge_did"] \
        == "did:viridis:erc8004:1:4242"
    r3 = _import(a, token_id=4243)
    r4 = _import(a, chain_id=8453)                    # Base, same token id
    assert len({r1["data"]["bridge_did"], r3["data"]["bridge_did"],
                r4["data"]["bridge_did"]}) == 3
    assert r1["data"]["record_hash"]


# --------------------------------------------------------------------- #
# B2 — idempotent import
# --------------------------------------------------------------------- #
def test_b2_reimport_updates_never_duplicates():
    a = build()
    _import(a)
    r = _import(a, agent_uri="https://agents.example/4242-v2.json")
    assert r["data"]["idempotent_update"] is True
    assert r["data"]["agent_uri"].endswith("v2.json")
    listing = run(a.process({"action": "list"}))
    assert listing["data"]["count"] == 1


# --------------------------------------------------------------------- #
# B3 — scoring: bounds, neutral prior, monotonicity, decay
# --------------------------------------------------------------------- #
def test_b3_neutral_prior_and_bounds():
    a = build()
    _import(a)
    s = run(a.process({"action": "score", "chain_id": 1, "token_id": 4242}))
    assert s["data"]["score"] == 0.5                  # no feedback -> prior
    assert s["data"]["tier"] == "NEUTRAL"


def test_b3_positive_never_lowers_negative_never_raises():
    a = build()
    _import(a)
    now = datetime.now(timezone.utc).isoformat()

    def score():
        return run(a.process({"action": "score", "chain_id": 1,
                              "token_id": 4242}))["data"]["score"]

    base = score()
    run(a.process({"action": "import_feedback", "chain_id": 1, "token_id": 4242,
                   "feedback": [{"value": True, "at": now}]}))
    up = score()
    assert up >= base
    run(a.process({"action": "import_feedback", "chain_id": 1, "token_id": 4242,
                   "feedback": [{"value": False, "at": now}]}))
    assert score() <= up
    assert 0.0 <= score() <= 1.0


def test_b3_newer_feedback_outweighs_older():
    cfg = AgentConfig(name="agent-erc8004-bridge-agent", half_life_days=10.0)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=100)).isoformat()

    a1 = build(cfg)                                    # old praise, new blame
    _import(a1)
    run(a1.process({"action": "import_feedback", "chain_id": 1, "token_id": 4242,
                    "feedback": [{"value": True, "at": old},
                                 {"value": False, "at": now.isoformat()}]}))
    s1 = run(a1.process({"action": "score", "chain_id": 1,
                         "token_id": 4242}))["data"]["score"]

    a2 = build(cfg)                                    # new praise, old blame
    r = run(a2.process({**REG}))
    assert r["status"] == "ok"
    run(a2.process({"action": "import_feedback", "chain_id": 1, "token_id": 4242,
                    "feedback": [{"value": False, "at": old},
                                 {"value": True, "at": now.isoformat()}]}))
    s2 = run(a2.process({"action": "score", "chain_id": 1,
                         "token_id": 4242}))["data"]["score"]
    assert s2 > s1                                     # recency dominates


def test_b3_duplicate_feedback_ids_are_skipped():
    a = build()
    _import(a)
    fb = {"value": True, "at": datetime.now(timezone.utc).isoformat(),
          "feedback_id": "fb-1"}
    r1 = run(a.process({"action": "import_feedback", "chain_id": 1,
                        "token_id": 4242, "feedback": [fb]}))
    r2 = run(a.process({"action": "import_feedback", "chain_id": 1,
                        "token_id": 4242, "feedback": [fb]}))
    assert r1["data"]["imported"] == 1
    assert r2["data"]["skipped_duplicates"] == 1
    assert r2["data"]["feedback_count"] == 1


# --------------------------------------------------------------------- #
# B4 — content-addressed export; tamper detection
# --------------------------------------------------------------------- #
def test_b4_export_verifies_and_tamper_is_detected():
    a = build()
    _import(a)
    exp = run(a.process({"action": "export_attestation", "chain_id": 1,
                         "token_id": 4242}))["data"]
    ok = run(a.process({"action": "verify", "payload": exp}))
    assert ok["data"]["valid"] is True
    tampered = dict(exp, score=0.999999)
    bad = run(a.process({"action": "verify", "payload": tampered}))
    assert bad["data"]["valid"] is False


# --------------------------------------------------------------------- #
# B5 — no key custody, ever; exports are explicitly unsigned
# --------------------------------------------------------------------- #
def test_b5_key_material_is_refused():
    a = build()
    r = run(a.process({**REG, "private_key": "0xdeadbeef"}))
    assert r["status"] == "error"
    assert r["error_type"] == "KeyMaterialRefused"
    nested = run(a.process({**REG, "metadata": {"wallet": {"mnemonic": "a b c"}}}))
    assert nested["error_type"] == "KeyMaterialRefused"
    listing = run(a.process({"action": "list"}))
    assert listing["data"]["count"] == 0               # nothing was stored


def test_b5_exports_and_bindings_are_unsigned():
    a = build()
    _import(a)
    exp = run(a.process({"action": "export_attestation", "chain_id": 1,
                         "token_id": 4242}))["data"]
    assert exp["signed"] is False
    assert "YOUR OWN signer" in exp["anchoring"]
    b = run(a.process({"action": "bind", "fleet_did": "did:viridis:abc",
                       "chain_id": 1, "token_id": 4242}))["data"]
    assert b["signed"] is False


# --------------------------------------------------------------------- #
# B6 — crash-safety / fleet contract
# --------------------------------------------------------------------- #
def test_b6_never_raises():
    a = build()
    for bad in (None, [], "x", 42):
        r = run(a.process(bad))
        assert r["status"] == "error"
    r = run(a.process({"action": "no_such_action"}))
    assert r["status"] == "error" and "unknown action" in r["message"]
    r = run(a.process({"action": "resolve", "bridge_did": "did:none"}))
    assert r["status"] == "error"


def test_fleet_contract_describe_matches_health():
    a = build()
    h = run(a.health())
    d = a.describe()
    assert d["name"] == h["agent"] == "agent-erc8004-bridge-agent"
    assert d["capabilities"]
    assert h["status"] == "ok"


# --------------------------------------------------------------------- #
# B7 — resolution is total over imports
# --------------------------------------------------------------------- #
def test_b7_resolve_by_did_and_by_pair():
    a = build()
    imported = _import(a)["data"]
    by_pair = run(a.process({"action": "resolve", "chain_id": 1,
                             "token_id": 4242}))["data"]
    by_did = run(a.process({"action": "resolve",
                            "bridge_did": imported["bridge_did"]}))["data"]
    assert by_pair["bridge_did"] == by_did["bridge_did"] == imported["bridge_did"]
    assert by_pair["agent_uri"] == by_did["agent_uri"]


# --------------------------------------------------------------------- #
# B8 — binding is order-independent (canonically sorted parties)
# --------------------------------------------------------------------- #
def test_b8_binding_symmetry():
    a = build()
    _import(a)
    b1 = run(a.process({"action": "bind", "fleet_did": "did:viridis:zzz",
                        "chain_id": 1, "token_id": 4242}))["data"]
    b2 = run(a.process({"action": "bind", "fleet_did": "did:viridis:zzz",
                        "chain_id": 1, "token_id": 4242}))["data"]
    assert b1["parties"] == sorted(b1["parties"])       # canonical order
    assert b1["content_hash"] == b2["content_hash"]     # content-identical
    ok = run(a.process({"action": "verify", "payload": b1}))
    assert ok["data"]["valid"] is True


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
