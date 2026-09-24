"""Purity/idempotency pin for compute-ledger's three verify_* actions —
strengthens L1 (verify_chain), L5 (verify_attestation), and I4
(verify_inventory_chain). Mirrors the fleet-wide verify_* idiom (metering
verify_chain N64; arbitration/surety/provenance/erc8004/covenant N65;
escrow verify_audit + trust-oracle verify_attestation N66): each verify_*
read must be PURE and repeatable, and tamper detection must be deterministic
across repeats. Named in the N65 cross-pollination queue.
"""
import pytest
from src.core import build


@pytest.fixture
def core():
    return build()


AUDIT_DIGEST = "a" * 64
FACTOR_DIGEST = "b" * 64


async def _work(core, eid, power_w=100.0, duration_s=60.0, **over):
    return await core.process({"action": "record_work", "agent_id": "agent-x",
                               "entry_id": eid, "power_w": power_w,
                               "duration_s": duration_s, **over})


async def _inventory(core, iid, agent_id="ghg-ledger-agent", mass_g=123456,
                     **over):
    payload = {"action": "record_inventory", "agent_id": agent_id,
               "inventory_id": iid, "mass_g": mass_g,
               "content_digest": AUDIT_DIGEST,
               "factor_pack_version": "2026.07-v0.1.0",
               "factor_pack_digest": FACTOR_DIGEST,
               "source_ids": ["EPA-2025", "IPCC-AR6"]}
    payload.update(over)
    return await core.process(payload)


# --- L1 verify_chain ------------------------------------------------------- #
async def test_verify_chain_is_pure_and_repeatable(core):
    for i in range(3):
        assert (await _work(core, f"e{i}"))["status"] == "ok"
    before = await core.process({"action": "list_entries", "agent_id": "agent-x"})
    first = await core.process({"action": "verify_chain", "agent_id": "agent-x"})
    second = await core.process({"action": "verify_chain", "agent_id": "agent-x"})
    after = await core.process({"action": "list_entries", "agent_id": "agent-x"})
    assert first["data"] == second["data"] == {
        "agent_id": "agent-x", "valid": True, "entry_count": 3,
    }
    assert before["data"] == after["data"]  # auditing never mutates the ledger


async def test_verify_chain_tamper_detection_is_deterministic(core):
    for i in range(3):
        await _work(core, f"e{i}")
    core._ledgers["agent-x"][1]["energy_j"] = 1.0  # tamper
    first = await core.process({"action": "verify_chain", "agent_id": "agent-x"})
    second = await core.process({"action": "verify_chain", "agent_id": "agent-x"})
    assert first["data"] == second["data"] == {
        "agent_id": "agent-x", "valid": False, "broken_at_index": 1,
    }


# --- L5 verify_attestation -------------------------------------------------- #
async def test_verify_attestation_is_pure_and_repeatable(core):
    await _work(core, "e1")
    att = (await core.process({"action": "attest", "entry_id": "e1"}))["data"]["attestation"]
    before = await core.process({"action": "list_entries", "agent_id": "agent-x"})
    first = await core.process({"action": "verify_attestation", "attestation": att})
    second = await core.process({"action": "verify_attestation", "attestation": att})
    after = await core.process({"action": "list_entries", "agent_id": "agent-x"})
    assert first["data"] == second["data"] == {"valid": True, "entry_id": "e1"}
    assert before["data"] == after["data"]  # attesting/verifying never mutates the entry


async def test_verify_attestation_tamper_detection_is_deterministic(core):
    await _work(core, "e1")
    att = (await core.process({"action": "attest", "entry_id": "e1"}))["data"]["attestation"]
    forged = {**att, "attestation_hash": "0" * 64}
    first = await core.process({"action": "verify_attestation", "attestation": forged})
    second = await core.process({"action": "verify_attestation", "attestation": forged})
    assert first["data"] == second["data"] == {"valid": False, "entry_id": "e1"}


# --- I4 verify_inventory_chain ---------------------------------------------- #
async def test_verify_inventory_chain_is_pure_and_repeatable(core):
    await _inventory(core, "inv-1")
    await _inventory(core, "inv-2", mass_g=42)
    before = await core.process({"action": "list_inventories", "agent_id": "ghg-ledger-agent"})
    first = await core.process({"action": "verify_inventory_chain", "agent_id": "ghg-ledger-agent"})
    second = await core.process({"action": "verify_inventory_chain", "agent_id": "ghg-ledger-agent"})
    after = await core.process({"action": "list_inventories", "agent_id": "ghg-ledger-agent"})
    assert first["data"] == second["data"] == {
        "agent_id": "ghg-ledger-agent", "valid": True, "inventory_count": 2,
    }
    assert before["data"] == after["data"]  # auditing never mutates inventory records


async def test_verify_inventory_chain_tamper_detection_is_deterministic(core):
    await _inventory(core, "inv-1")
    await _inventory(core, "inv-2", mass_g=42)
    core._inventories["ghg-ledger-agent"][1]["mass_g"] = 43  # tamper
    first = await core.process({"action": "verify_inventory_chain", "agent_id": "ghg-ledger-agent"})
    second = await core.process({"action": "verify_inventory_chain", "agent_id": "ghg-ledger-agent"})
    assert first["data"] == second["data"] == {
        "agent_id": "ghg-ledger-agent", "valid": False,
        "inventory_count": 2, "broken_at_index": 1,
    }
