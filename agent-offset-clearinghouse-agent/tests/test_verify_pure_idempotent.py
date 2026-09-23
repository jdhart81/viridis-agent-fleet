"""Purity/idempotency pin for verify_certificate (O4) and verify_disbursement
(D5) — the two clearinghouse verify_* reads not yet pinned for repeatability
(verify_retirement/O13 already has this in test_verify_retirement.py). Mirrors
the fleet-wide verify_* idiom (metering verify_chain N64; arbitration/surety/
provenance/erc8004/covenant N65; escrow/trust-oracle/compute-ledger N66):
each verify_* read must be PURE and repeatable, and tamper detection must be
deterministic across repeats. Offset-clearinghouse carries the live 15%
Viridis Conservation withhold (D3) — priority 2 in the N65 queue after escrow.
"""
import pytest
from src.core import build


@pytest.fixture
def core():
    return build()


async def _credit(core, mass_g=1000, price=500, project="forest-1", vref="dscore:abc"):
    return await core.process({"action": "list_credit", "issuer": "viridis",
                               "project_id": project, "mass_g": mass_g,
                               "price_minor_per_kg": price,
                               "verification_ref": vref})


async def _buy(core, pid, mass_g, buyer="agent-x"):
    return await core.process({"action": "buy_offset", "buyer": buyer,
                               "purchase_id": pid, "mass_g": mass_g})


async def _project(core, pid, vref="dscore:v", **kw):
    return await core.process({"action": "register_project", "project_id": pid,
                               "verification_ref": vref, **kw})


# --- O4 verify_certificate --------------------------------------------------- #
async def test_verify_certificate_is_pure_and_repeatable(core):
    await _credit(core, mass_g=1000)
    r = await _buy(core, "p1", 250)
    cert = r["data"]
    book_before = await core.process({"action": "book"})
    first = await core.process({"action": "verify_certificate", "certificate": cert})
    second = await core.process({"action": "verify_certificate", "certificate": cert})
    book_after = await core.process({"action": "book"})
    assert first["data"] == second["data"] == {
        "valid": True, "hash_ok": True, "on_ledger": True,
    }
    assert book_before["data"] == book_after["data"]  # verifying never mutates the book


async def test_verify_certificate_forgery_detection_is_deterministic(core):
    await _credit(core, mass_g=1000)
    r = await _buy(core, "p1", 250)
    forged = {**r["data"], "mass_g": 999999}
    first = await core.process({"action": "verify_certificate", "certificate": forged})
    second = await core.process({"action": "verify_certificate", "certificate": forged})
    assert first["data"] == second["data"] == {
        "valid": False, "hash_ok": False, "on_ledger": True,
    }


# --- D5 verify_disbursement --------------------------------------------------- #
async def test_verify_disbursement_is_pure_and_repeatable(core):
    await _project(core, "forest")
    await _credit(core, mass_g=100000, price=1000, project="forest")
    await _buy(core, "b1", 5000)
    await core.process({"action": "certify_disbursement", "batch_id": "b-1"})

    sched_before = await core.process({"action": "disbursement_schedule"})
    first = await core.process({"action": "verify_disbursement"})
    second = await core.process({"action": "verify_disbursement"})
    sched_after = await core.process({"action": "disbursement_schedule"})

    assert first["data"] == second["data"] == {
        "valid": True, "batches": 1,
        "total_disbursed_minor": first["data"]["total_disbursed_minor"],
        "conserved": True,
    }
    # auditing never re-certifies or otherwise changes what's owed
    assert sched_before["data"] == sched_after["data"]


async def test_verify_disbursement_tamper_detection_is_deterministic(core):
    await _project(core, "forest")
    await _credit(core, mass_g=100000, price=1000, project="forest")
    await _buy(core, "b1", 5000)
    await core.process({"action": "certify_disbursement", "batch_id": "b-1"})
    core._disbursements[0]["total_project_payout_minor"] = 999999  # tamper

    first = await core.process({"action": "verify_disbursement"})
    second = await core.process({"action": "verify_disbursement"})
    assert first["data"] == second["data"] == {"valid": False, "broken_at_index": 0}
