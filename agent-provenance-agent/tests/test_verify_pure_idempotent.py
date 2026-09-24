"""Idempotency/purity pin for verify_certificate + verify_artifact (strengthens V6/A5).

V6 and A5's existing tests cover tamper-detection but not that these verify_*
reads are PURE and repeatable -- the "idempotency on verify_audit-style actions"
signal queued in N63/N64, closed across the A2A verify_* family tonight (mirrors
metering's verify_chain pin). Both take the full record as input and recompute
from it, so identical calls must be byte-identical, and neither read may mutate
the ledger it checks against. Additive; V1-V8/A1-A7 untouched.
"""
import pytest
from src.core import build

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


async def test_V6_verify_certificate_is_idempotent_and_pure(core):
    r = await _born(core, "alpha")
    cert = r["data"]

    before = await core.process({"action": "get_certificate", "agent_id": "alpha"})
    v1 = await core.process({"action": "verify_certificate", "certificate": cert})
    v2 = await core.process({"action": "verify_certificate", "certificate": cert})
    after = await core.process({"action": "get_certificate", "agent_id": "alpha"})

    assert v1["data"]["valid"] is True
    assert v1["data"] == v2["data"]
    assert before["data"] == after["data"]  # verifying does not touch the ledger


async def test_A5_verify_artifact_is_idempotent_and_pure(core):
    result = await _artifact(core, "inventory-1")
    artifact = result["data"]

    before = await core.process({"action": "get_artifact", "artifact_id": "inventory-1"})
    v1 = await core.process({"action": "verify_artifact", "artifact": artifact})
    v2 = await core.process({"action": "verify_artifact", "artifact": artifact})
    after = await core.process({"action": "get_artifact", "artifact_id": "inventory-1"})

    assert v1["data"]["valid"] is True
    assert v1["data"] == v2["data"]
    assert before["data"] == after["data"]  # verifying does not touch the ledger
