"""Invariant tests for agent-arbitration-agent (A1-A8) + fleet contract."""
import pytest
from src.core import build


@pytest.fixture
def core():
    return build()


async def _case(core, **over):
    payload = {"action": "file_case", "escrow_id": "esc-1", "claimant": "buyer",
               "respondent": "seller", "amount_minor": 10000, **over}
    r = await core.process(payload)
    assert r["status"] == "ok"
    return r["data"]["case_id"]


async def _ev(core, cid, party, kind="statement", content="x"):
    return await core.process({"action": "submit_evidence", "case_id": cid,
                               "party": party, "kind": kind, "content": content})


# --- A1 forward-only lifecycle -------------------------------------------- #
async def test_A1_lifecycle_forward_only_ruled_terminal(core):
    cid = await _case(core)
    g = await core.process({"action": "get_case", "case_id": cid})
    assert g["data"]["state"] == "EVIDENCE_OPEN"
    r = await core.process({"action": "rule", "case_id": cid})
    assert r["status"] == "ok"
    g2 = await core.process({"action": "get_case", "case_id": cid})
    assert g2["data"]["state"] == "RULED"
    ev = await _ev(core, cid, "buyer")  # A1/A3: nothing moves a RULED case
    assert ev["status"] == "error"


# --- A2 distinct parties --------------------------------------------------- #
async def test_A2_requires_distinct_parties_and_escrow(core):
    r = await core.process({"action": "file_case", "escrow_id": "esc-1",
                            "claimant": "same", "respondent": "same",
                            "amount_minor": 100})
    assert r["status"] == "error" and r["field"] == "respondent"
    r2 = await core.process({"action": "file_case", "claimant": "a",
                             "respondent": "b", "amount_minor": 100})
    assert r2["status"] == "error" and r2["field"] == "escrow_id"


# --- A3 evidence gating ----------------------------------------------------- #
async def test_A3_only_parties_only_while_open(core):
    cid = await _case(core)
    stranger = await _ev(core, cid, "random-agent")
    assert stranger["status"] == "error" and stranger["field"] == "party"
    ok = await _ev(core, cid, "buyer", kind="log")
    assert ok["status"] == "ok"
    await core.process({"action": "rule", "case_id": cid})
    late = await _ev(core, cid, "seller", kind="delivery_proof")
    assert late["status"] == "error"


# --- A4 deterministic rulings ----------------------------------------------- #
async def test_A4_same_inputs_same_ruling(core):
    core2 = build()
    for c in (core, core2):
        cid = await _case(c)
        await _ev(c, cid, "buyer", kind="log", content="latency logs")
        await _ev(c, cid, "seller", kind="delivery_proof", content="hash")
        await c.process({"action": "set_trust_scores", "case_id": cid,
                         "scores": {"buyer": 0.6, "seller": 0.8}})
    r1 = await core.process({"action": "rule", "case_id": "case-000001"})
    r2 = await core2.process({"action": "rule", "case_id": "case-000001"})
    assert r1["data"]["claimant_pct"] == r2["data"]["claimant_pct"]
    assert r1["data"]["ruling_hash"] == r2["data"]["ruling_hash"]


# --- A5 allocation sums to 100 ---------------------------------------------- #
async def test_A5_allocation_complete(core):
    cid = await _case(core, amount_minor=9999)
    await _ev(core, cid, "buyer", kind="statement")
    await _ev(core, cid, "seller", kind="delivery_proof")
    r = await core.process({"action": "rule", "case_id": cid})
    d = r["data"]
    assert d["claimant_pct"] + d["respondent_pct"] == 100
    assert d["claimant_amount_minor"] + d["respondent_amount_minor"] == 9999


# --- A6 machine-checkable rulings ------------------------------------------- #
async def test_A6_verify_ruling_recomputes(core):
    cid = await _case(core)
    await _ev(core, cid, "buyer", kind="log")
    await _ev(core, cid, "seller", kind="delivery_proof")
    await core.process({"action": "set_trust_scores", "case_id": cid,
                        "scores": {"seller": 0.9}})
    await core.process({"action": "rule", "case_id": cid})
    v = await core.process({"action": "verify_ruling", "case_id": cid})
    assert v["data"]["valid"] is True
    # tamper with the stored ruling -> verification fails
    core._cases[cid].ruling["claimant_pct"] = 99
    v2 = await core.process({"action": "verify_ruling", "case_id": cid})
    assert v2["data"]["valid"] is False


# --- A7 exactly-once -------------------------------------------------------- #
async def test_A7_rule_idempotent(core):
    cid = await _case(core)
    r1 = await core.process({"action": "rule", "case_id": cid})
    r2 = await core.process({"action": "rule", "case_id": cid})
    assert r2["data"]["duplicate"] is True
    assert r2["data"]["ruling_hash"] == r1["data"]["ruling_hash"]


# --- A8 unknown case --------------------------------------------------------- #
async def test_A8_unknown_case_error_envelope(core):
    for action in ("submit_evidence", "rule", "verify_ruling", "get_case",
                   "set_trust_scores"):
        r = await core.process({"action": action, "case_id": "nope"})
        assert r["status"] == "error" and r["field"] == "case_id"
        for key in ("error_type", "field", "value", "constraint", "message", "timestamp"):
            assert key in r


# --- domain: evidence weights + escrow instruction --------------------------- #
async def test_evidence_outweighs_neutral_trust(core):
    cid = await _case(core)
    await _ev(core, cid, "seller", kind="delivery_proof")  # weight 3
    r = await core.process({"action": "rule", "case_id": cid})
    assert r["data"]["respondent_pct"] > r["data"]["claimant_pct"]
    assert r["data"]["escrow_instruction"] == "release"


async def test_trust_score_bounds_enforced(core):
    cid = await _case(core)
    r = await core.process({"action": "set_trust_scores", "case_id": cid,
                            "scores": {"buyer": 1.5}})
    assert r["status"] == "error"


# --- fleet contract ----------------------------------------------------------- #
async def test_contract_never_raises_and_unknown_action(core):
    for payload in [{}, {"action": None}, {"action": "nope"}, "not-a-dict", 42]:
        r = await core.process(payload)
        assert isinstance(r, dict) and r["status"] == "error"


async def test_contract_describe_health_consistent(core):
    d = core.describe()
    h = await core.health()
    assert d["name"] == h["agent"]
    assert d["capabilities"] and d["a2a_role"] == "arbitration"
    assert set(h) >= {"status", "agent", "version", "timestamp", "checks"}
