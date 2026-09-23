"""Invariant tests for agent-covenant-agent (C1-C8) + fleet contract."""
import pytest
from src.core import build


@pytest.fixture
def core():
    return build()


async def _grant(core, **over):
    payload = {"action": "grant", "principal": "justin", "agent_id": "worker-1",
               "scopes": ["payments.*", "files.read"], "budget_minor": 10000,
               "expires_at": "2099-01-01T00:00:00+00:00", **over}
    r = await core.process(payload)
    assert r["status"] == "ok"
    return r["data"]["covenant_id"]


async def _act(core, cid, act_id, scope="payments.refund", amount=100, **over):
    return await core.process({"action": "check_act", "covenant_id": cid,
                               "act_id": act_id, "scope": scope,
                               "amount_minor": amount, **over})


# --- C1 deny-by-default ----------------------------------------------------- #
async def test_C1_deny_by_default(core):
    cid = await _grant(core)
    ok = await _act(core, cid, "a1", scope="payments.refund", amount=100)
    assert ok["data"]["allowed"] is True
    bad_scope = await _act(core, cid, "a2", scope="accounts.delete", amount=0)
    assert bad_scope["data"]["allowed"] is False and "scope" in bad_scope["data"]["reason"]
    too_much = await _act(core, cid, "a3", scope="payments.send", amount=999999)
    assert too_much["data"]["allowed"] is False and "budget" in too_much["data"]["reason"]


# --- C2 budget monotone, never negative -------------------------------------- #
async def test_C2_budget_monotone_never_negative(core):
    cid = await _grant(core, budget_minor=250)
    await _act(core, cid, "a1", amount=100)
    await _act(core, cid, "a2", amount=100)
    denied = await _act(core, cid, "a3", amount=100)  # would exceed
    assert denied["data"]["allowed"] is False
    st = await core.process({"action": "status", "covenant_id": cid})
    assert st["data"]["consumed_minor"] == 200
    assert st["data"]["remaining_minor"] == 50  # denied act consumed nothing


# --- C3 audit chain records allows AND denies --------------------------------- #
async def test_C3_audit_chain_tamper_evident(core):
    cid = await _grant(core)
    await _act(core, cid, "a1", amount=10)                       # allow
    await _act(core, cid, "a2", scope="nope.x", amount=0)        # deny
    v = await core.process({"action": "verify_audit", "covenant_id": cid})
    assert v["data"]["valid"] is True and v["data"]["checks"] == 2
    core._covenants[cid].audit[0]["amount_minor"] = 999999  # tamper
    v2 = await core.process({"action": "verify_audit", "covenant_id": cid})
    assert v2["data"]["valid"] is False and v2["data"]["broken_at_index"] == 0


# --- C4 revocation immediate + terminal ---------------------------------------- #
async def test_C4_revoke_immediate_terminal(core):
    cid = await _grant(core)
    await core.process({"action": "revoke", "covenant_id": cid, "reason": "compromised"})
    r = await _act(core, cid, "a1", amount=1)
    assert r["data"]["allowed"] is False and "revoked" in r["data"]["reason"]
    again = await core.process({"action": "revoke", "covenant_id": cid})
    assert again["data"]["state"] == "REVOKED"  # idempotent, still terminal


# --- C5 deterministic scope matching --------------------------------------------- #
async def test_C5_scope_wildcards(core):
    cid = await _grant(core, scopes=["payments.*"])
    assert (await _act(core, cid, "a1", scope="payments.refund"))["data"]["allowed"]
    assert (await _act(core, cid, "a2", scope="payments"))["data"]["allowed"] is False
    assert (await _act(core, cid, "a3", scope="files.read"))["data"]["allowed"] is False
    cid2 = await _grant(core, scopes=["*"])
    assert (await _act(core, cid2, "b1", scope="anything.at.all"))["data"]["allowed"]


# --- C6 expiry enforced ------------------------------------------------------------ #
async def test_C6_expiry_enforced(core):
    cid = await _grant(core, expires_at="2020-01-01T00:00:00+00:00")
    r = await _act(core, cid, "a1", amount=1,
                   now="2026-07-09T00:00:00+00:00")
    assert r["data"]["allowed"] is False and "expired" in r["data"]["reason"]
    st = await core.process({"action": "status", "covenant_id": cid})
    assert st["data"]["state"] == "EXPIRED"


# --- C7 idempotent on act_id ---------------------------------------------------------- #
async def test_C7_act_id_idempotent(core):
    cid = await _grant(core, budget_minor=1000)
    r1 = await _act(core, cid, "retry-me", amount=400)
    r2 = await _act(core, cid, "retry-me", amount=400)  # network retry
    assert r2["data"]["duplicate"] is True
    st = await core.process({"action": "status", "covenant_id": cid})
    assert st["data"]["consumed_minor"] == 400  # consumed once


# --- C8 unknown covenant ----------------------------------------------------------------- #
async def test_C8_unknown_covenant_error_envelope(core):
    for action in ("check_act", "revoke", "status", "verify_audit"):
        r = await core.process({"action": action, "covenant_id": "nope",
                                "act_id": "x", "scope": "s"})
        assert r["status"] == "error" and r["field"] == "covenant_id"
        for key in ("error_type", "field", "value", "constraint", "message", "timestamp"):
            assert key in r


# --- domain: zero-budget covenant allows zero-amount scoped acts --------------------------- #
async def test_zero_budget_read_only_covenant(core):
    cid = await _grant(core, scopes=["files.read"], budget_minor=0)
    r = await _act(core, cid, "a1", scope="files.read", amount=0)
    assert r["data"]["allowed"] is True
    r2 = await _act(core, cid, "a2", scope="files.read", amount=1)
    assert r2["data"]["allowed"] is False


# --- fleet contract -------------------------------------------------------------------------- #
async def test_contract_never_raises_and_unknown_action(core):
    for payload in [{}, {"action": None}, {"action": "nope"}, "not-a-dict", 42]:
        r = await core.process(payload)
        assert isinstance(r, dict) and r["status"] == "error"


async def test_contract_describe_health_consistent(core):
    d = core.describe()
    h = await core.health()
    assert d["name"] == h["agent"]
    assert d["capabilities"] and d["a2a_role"] == "authority"
    assert set(h) >= {"status", "agent", "version", "timestamp", "checks"}
