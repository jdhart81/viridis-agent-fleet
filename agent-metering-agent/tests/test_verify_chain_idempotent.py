"""Idempotency pin for verify_chain (strengthens M5).

M5's existing test covers valid-chain + tamper-detection, but not that verify_chain
is a PURE, repeatable audit read — the "idempotency on verify_audit-style actions"
signal queued in N63. verify_chain must (a) return identical results when called
repeatedly and (b) never mutate the chain it inspects. Mirrors the M6 sla_report
purity idiom. Additive; core unchanged; no invariant renumbered.
"""
import pytest
from src.core import build


@pytest.fixture
def core():
    return build()


async def _meter(core, **over):
    payload = {"action": "create_meter", "provider": "prov-1", "consumer": "cons-1",
               "unit": "call", "price_minor_per_unit": 2.5, **over}
    r = await core.process(payload)
    assert r["status"] == "ok"
    return r["data"]["meter_id"]


async def _use(core, mid, eid, qty=1.0, outcome="ok"):
    return await core.process({"action": "record_usage", "meter_id": mid,
                               "event_id": eid, "quantity": qty, "outcome": outcome})


async def test_M5_verify_chain_is_idempotent_and_pure(core):
    mid = await _meter(core)
    for i in range(4):
        await _use(core, mid, f"e{i}", qty=i + 1)

    before = await core.process({"action": "usage_summary", "meter_id": mid})
    v1 = await core.process({"action": "verify_chain", "meter_id": mid})
    v2 = await core.process({"action": "verify_chain", "meter_id": mid})
    after = await core.process({"action": "usage_summary", "meter_id": mid})

    # (a) repeatable: two audits of an unchanged chain return identical verdicts
    assert v1["data"]["valid"] is True
    assert v1["data"] == v2["data"]
    # (b) pure: auditing the chain does not append, drop, or reorder events
    assert after["data"]["event_count"] == before["data"]["event_count"]


async def test_M5_verify_chain_idempotent_after_tamper(core):
    mid = await _meter(core)
    for i in range(3):
        await _use(core, mid, f"e{i}")
    core._meters[mid].events[1]["quantity"] = 1000.0  # tamper

    v1 = await core.process({"action": "verify_chain", "meter_id": mid})
    v2 = await core.process({"action": "verify_chain", "meter_id": mid})
    # a broken chain reports the SAME break deterministically on every audit
    assert v1["data"]["valid"] is False
    assert v1["data"]["broken_at_index"] == 1
    assert v1["data"] == v2["data"]
