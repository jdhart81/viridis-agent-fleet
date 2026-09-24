"""Invariant tests for agent-provenance-agent (V1-V8) + fleet contract."""
import pytest
from src.core import (build, FOUNDING_COHORT_SIZE, _ARTIFACT_CONTENT_FIELDS,
                      _cert_hash, _epoch)

ARTIFACT_HASH = "a" * 64
FACTOR_HASH = "b" * 64
METADATA_HASH = "c" * 64


@pytest.fixture
def core():
    return build()


async def _born(core, aid, parent=None, artifact="sha256:abc"):
    return await core.process({"action": "register_genesis", "agent_id": aid,
                               "parent_id": parent, "artifact_hash": artifact})


async def _artifact(core, artifact_id, artifact_hash=ARTIFACT_HASH,
                    producer="ghg-ledger-agent", parents=None, **over):
    payload = {"action": "register_artifact", "artifact_id": artifact_id,
               "artifact_hash": artifact_hash,
               "producer_agent_id": producer,
               "parent_hashes": parents if parents is not None else [FACTOR_HASH],
               "relation": "calculated_from",
               "metadata_digest": METADATA_HASH}
    payload.update(over)
    return await core.process(payload)


# --- V1 content-addressed certificates -------------------------------------- #
async def test_V1_certificate_content_addressed(core):
    r = await _born(core, "alpha")
    cert = {k: r["data"][k] for k in ("agent_id", "genesis_index", "epoch",
                                      "parent_id", "artifact_hash", "born_at")}
    assert _cert_hash(cert) == r["data"]["cert_hash"]


# --- V2 strictly monotone sequence + founding cohort -------------------------- #
async def test_V2_monotone_sequence_and_epochs(core):
    for i in range(5):
        r = await _born(core, f"a{i}")
        assert r["data"]["genesis_index"] == i
        assert r["data"]["epoch"] == 0 and r["data"]["founding_cohort"] is True
    assert _epoch(FOUNDING_COHORT_SIZE - 1) == 0
    assert _epoch(FOUNDING_COHORT_SIZE) == 1  # the door closes exactly once


# --- V3 acyclic lineage --------------------------------------------------------- #
async def test_V3_lineage_acyclic(core):
    self_parent = await core.process({"action": "register_genesis",
                                      "agent_id": "x", "parent_id": "x"})
    assert self_parent["status"] == "error"
    orphan = await _born(core, "child", parent="never-registered")
    assert orphan["status"] == "error" and orphan["field"] == "parent_id"
    await _born(core, "parent")
    ok = await _born(core, "child", parent="parent")
    assert ok["status"] == "ok"
    lin = await core.process({"action": "lineage", "agent_id": "child"})
    assert lin["data"]["ancestors"] == ["parent"] and lin["data"]["generation"] == 1


# --- V4 recall cascades ------------------------------------------------------------ #
async def test_V4_recall_cascades_transitively(core):
    await _born(core, "gen0")
    await _born(core, "gen1", parent="gen0")
    await _born(core, "gen2a", parent="gen1")
    await _born(core, "gen2b", parent="gen1")
    await _born(core, "bystander")
    r = await core.process({"action": "recall", "agent_id": "gen0",
                            "reason": "compromised weights"})
    assert set(r["data"]["descendants_quarantined"]) == {"gen1", "gen2a", "gen2b"}
    by = await core.process({"action": "get_certificate", "agent_id": "bystander"})
    assert by["data"]["quarantined"] is False


# --- V5 recalled lineage sticky ------------------------------------------------------ #
async def test_V5_quarantined_at_birth(core):
    await _born(core, "bad")
    await core.process({"action": "recall", "agent_id": "bad", "reason": "evil"})
    r = await _born(core, "bad-child", parent="bad")
    assert r["status"] == "ok" and r["data"]["quarantined"] is True
    r2 = await _born(core, "bad-grandchild", parent="bad-child")
    assert r2["data"]["quarantined"] is True  # sticky through the flagged line


# --- V6 verification detects tampering ------------------------------------------------- #
async def test_V6_verify_detects_tampering(core):
    r = await _born(core, "honest")
    cert = r["data"]
    v = await core.process({"action": "verify_certificate", "certificate": cert})
    assert v["data"]["valid"] is True
    forged = {**cert, "genesis_index": 0, "agent_id": "impostor"}
    v2 = await core.process({"action": "verify_certificate", "certificate": forged})
    assert v2["data"]["valid"] is False


# --- V7 born once ------------------------------------------------------------------------ #
async def test_V7_registration_idempotent(core):
    r1 = await _born(core, "once")
    r2 = await _born(core, "once", artifact="sha256:different")
    assert r2["data"]["created"] is False
    assert r2["data"]["cert_hash"] == r1["data"]["cert_hash"]
    assert r2["data"]["genesis_index"] == r1["data"]["genesis_index"]


# --- V8 unknown agent ---------------------------------------------------------------------- #
async def test_V8_unknown_agent_error_envelope(core):
    for action in ("get_certificate", "lineage", "recall"):
        r = await core.process({"action": action, "agent_id": "ghost"})
        assert r["status"] == "error" and r["field"] == "agent_id"
        for key in ("error_type", "field", "value", "constraint", "message", "timestamp"):
            assert key in r


# --- A1 separate from genesis ---------------------------------------------- #
async def test_A1_artifacts_do_not_consume_genesis_or_enter_lineage(core):
    await _born(core, "founder")
    genesis_before = list(core._order)
    artifact = await _artifact(core, "inventory-1")
    assert artifact["status"] == "ok"
    assert core._order == genesis_before
    records = await core.process({"action": "list"})
    assert records["data"]["count"] == 1
    assert core._records["founder"].children == []


# --- A2 content-addressed records ------------------------------------------ #
async def test_A2_artifact_record_is_content_addressed(core):
    result = await _artifact(core, "inventory-1")
    data = result["data"]
    content = {key: data[key] for key in _ARTIFACT_CONTENT_FIELDS}
    assert _cert_hash(content) == data["record_hash"]
    assert data["artifact_hash"] == ARTIFACT_HASH


# --- A3 acyclic parent-hash DAG -------------------------------------------- #
async def test_A3_artifact_dag_rejects_self_and_transitive_cycles(core):
    self_parent = await _artifact(core, "self", parents=[ARTIFACT_HASH])
    assert self_parent["status"] == "error"
    assert self_parent["field"] == "parent_hashes"

    hash_a, hash_b = "d" * 64, "e" * 64
    first = await _artifact(core, "a", artifact_hash=hash_a,
                            parents=[hash_b])
    assert first["status"] == "ok"  # hash_b is an external root for now
    cycle = await _artifact(core, "b", artifact_hash=hash_b,
                            parents=[hash_a])
    assert cycle["status"] == "error" and cycle["field"] == "parent_hashes"


# --- A4 exact idempotency; conflicting reuse fails closed ------------------ #
async def test_A4_exact_artifact_replay_is_idempotent_and_hash_unique(core):
    first = await _artifact(core, "same")
    replay = await _artifact(core, "same")
    assert replay["status"] == "ok"
    assert replay["data"]["created"] is False
    assert replay["data"]["record_hash"] == first["data"]["record_hash"]
    collision = await _artifact(core, "other", artifact_hash=ARTIFACT_HASH)
    assert collision["status"] == "error"
    assert collision["field"] == "artifact_hash"


@pytest.mark.parametrize(("changed", "conflict_field"), [
    ({"artifact_hash": "d" * 64}, "artifact_hash"),
    ({"producer": "different-agent"}, "producer_agent_id"),
    ({"parents": ["d" * 64]}, "parent_hashes"),
    ({"relation": "unrelated_to"}, "relation"),
    ({"metadata_digest": "d" * 64}, "metadata_digest"),
])
async def test_A4_conflicting_artifact_replay_fails_closed(
        core, changed, conflict_field):
    first = await _artifact(core, "same")
    conflict = await _artifact(core, "same", **changed)
    assert conflict["status"] == "error"
    assert conflict["error_type"] == "ConflictError"
    assert conflict["field"] == "artifact_id"
    assert conflict["value"] == "same"
    assert conflict_field in conflict["message"]
    assert "data" not in conflict
    assert len(core._artifacts) == 1
    assert core._artifacts["same"]["record_hash"] \
        == first["data"]["record_hash"]


# --- A5 verification detects tampering ------------------------------------ #
async def test_A5_verify_artifact_detects_tampering(core):
    result = await _artifact(core, "inventory-1")
    artifact = result["data"]
    verified = await core.process({"action": "verify_artifact",
                                   "artifact": artifact})
    assert verified["data"] == {"artifact_id": "inventory-1", "valid": True,
                                 "hash_ok": True, "on_ledger": True,
                                 "dag_ok": True}
    forged = {**artifact, "relation": "unrelated"}
    invalid = await core.process({"action": "verify_artifact",
                                  "artifact": forged})
    assert invalid["data"]["valid"] is False
    assert invalid["data"]["hash_ok"] is False


# --- A6 canonical built-in state + list filter ----------------------------- #
async def test_A6_artifact_state_is_builtin_and_canonical(core):
    result = await _artifact(core, "inventory-1",
                             parents=[FACTOR_HASH, "d" * 64, FACTOR_HASH])
    assert result["data"]["parent_hashes"] == [FACTOR_HASH, "d" * 64]
    assert isinstance(core._artifacts, dict)
    assert isinstance(core._artifact_order, list)
    assert all(isinstance(item, dict) for item in core._artifacts.values())
    await _artifact(core, "inventory-2", artifact_hash="e" * 64,
                    producer="another-agent", parents=[])
    filtered = await core.process({"action": "list_artifacts",
                                   "producer_agent_id": "ghg-ledger-agent"})
    assert filtered["data"]["count"] == 1
    assert filtered["data"]["artifacts"][0]["artifact_id"] == "inventory-1"


# --- A7 fail-loud validation and unknowns ---------------------------------- #
async def test_A7_artifact_unknowns_and_digests_fail_loud(core):
    for payload, field in (
            ({"action": "get_artifact", "artifact_id": "ghost"},
             "artifact_id"),
            ({"action": "verify_artifact", "artifact": {}}, "artifact"),
            ({"action": "register_artifact", "artifact_id": "bad",
              "artifact_hash": "abc", "producer_agent_id": "producer"},
             "artifact_hash"),
            ({"action": "register_artifact", "artifact_id": "bad-parent",
              "artifact_hash": "f" * 64, "producer_agent_id": "producer",
              "parent_hashes": ["not-a-digest"]}, "parent_hashes")):
        error = await core.process(payload)
        assert error["status"] == "error" and error["field"] == field


# --- fleet contract --------------------------------------------------------------------------- #
async def test_contract_never_raises_and_unknown_action(core):
    for payload in [{}, {"action": None}, {"action": "nope"}, "not-a-dict", 42]:
        r = await core.process(payload)
        assert isinstance(r, dict) and r["status"] == "error"


async def test_contract_describe_health_consistent(core):
    d = core.describe()
    h = await core.health()
    assert d["name"] == h["agent"]
    assert d["capabilities"] and d["a2a_role"] == "provenance"
    assert d["version"] == h["version"] == "0.2.0"
    assert set(("register_artifact", "get_artifact", "verify_artifact",
                "list_artifacts")) <= set(d["capabilities"])
    assert set(h) >= {"status", "agent", "version", "timestamp", "checks"}
