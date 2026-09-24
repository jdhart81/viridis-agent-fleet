"""A9 — default judgment (burden of proof, policy DJ-14).

One test per claim. rule() WITHOUT the flag must remain byte-identical
(pinned against the A4 evidence-weighted path).
"""
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


async def test_A9_default_judgment_rules_for_respondent(core):
    """Zero claimant evidence -> 0/100, release, policy stamped."""
    cid = await _case(core)
    r = await core.process({"action": "rule", "case_id": cid,
                            "default_judgment": True})
    assert r["status"] == "ok"
    d = r["data"]
    assert d["claimant_pct"] == 0 and d["respondent_pct"] == 100   # A5
    assert d["claimant_amount_minor"] == 0
    assert d["respondent_amount_minor"] == 10000
    assert d["escrow_instruction"] == "release"
    assert d["default_judgment"] is True
    assert d["policy"] == "DJ-14"
    assert d["ruling_hash"]


async def test_A9_refused_when_claimant_has_evidence(core):
    """An evidenced claim always forces the A4 merits path."""
    cid = await _case(core)
    assert (await _ev(core, cid, "buyer"))["status"] == "ok"
    r = await core.process({"action": "rule", "case_id": cid,
                            "default_judgment": True})
    assert r["status"] == "error"
    assert r["field"] == "default_judgment"
    g = await core.process({"action": "get_case", "case_id": cid})
    assert g["data"]["state"] == "EVIDENCE_OPEN"        # case untouched


async def test_A9_respondent_evidence_does_not_block_default(core):
    """Only the CLAIMANT's silence matters; respondent evidence is cited."""
    cid = await _case(core)
    assert (await _ev(core, cid, "seller", kind="delivery_proof"))["status"] == "ok"
    r = await core.process({"action": "rule", "case_id": cid,
                            "default_judgment": True})
    assert r["status"] == "ok"
    assert r["data"]["respondent_pct"] == 100
    assert len(r["data"]["cited_evidence"]) == 1


async def test_A9_idempotent_via_A7(core):
    cid = await _case(core)
    first = await core.process({"action": "rule", "case_id": cid,
                                "default_judgment": True})
    again = await core.process({"action": "rule", "case_id": cid,
                                "default_judgment": True})
    assert again["data"]["duplicate"] is True
    assert again["data"]["ruling_hash"] == first["data"]["ruling_hash"]
    merits_retry = await core.process({"action": "rule", "case_id": cid})
    assert merits_retry["data"]["duplicate"] is True    # ruling immutable (A1)


async def test_A9_verify_ruling_validates_default_judgment(core):
    cid = await _case(core)
    await _ev(core, cid, "seller")
    await core.process({"action": "rule", "case_id": cid,
                        "default_judgment": True})
    v = await core.process({"action": "verify_ruling", "case_id": cid})
    assert v["status"] == "ok"
    assert v["data"]["valid"] is True
    assert v["data"]["recomputed"]["policy"] == "DJ-14"


async def test_A9_ordinary_rule_path_unchanged(core):
    """No flag -> exact pre-A9 behavior: empty record ties 50/50 -> refund."""
    cid = await _case(core)
    r = await core.process({"action": "rule", "case_id": cid})
    assert r["status"] == "ok"
    d = r["data"]
    assert d["claimant_pct"] == 50 and d["respondent_pct"] == 50
    assert d["escrow_instruction"] == "refund"
    assert "default_judgment" not in d
    v = await core.process({"action": "verify_ruling", "case_id": cid})
    assert v["data"]["valid"] is True                   # A6 path intact
