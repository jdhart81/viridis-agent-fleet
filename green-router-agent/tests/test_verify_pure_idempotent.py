"""Purity + idempotency pin for `verify_certificate` (GR4).

GR4 already proves one verify call recomputes and matches, but nothing pins
that verifying is a pure READ: repeated calls on an unchanged certificate
store must return identical data payloads (the envelope timestamp is the
only legitimate difference), and auditing must never mutate the store it
inspects. Closes the last un-pinned verify_* action found by the N67
fleet-wide re-grep. Additive; GR1-GR9 untouched.
"""
import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core import build  # noqa: E402

WORKLOAD = {"backend_id": "frontier_cloud", "total_tokens": 3000,
            "output_tokens": 800, "calls": 100}


async def _certify(core):
    r = await core.process({"action": "certify", "workload": WORKLOAD})
    assert r["status"] == "ok"
    return r["data"]["certificate_id"]


async def test_verify_certificate_is_repeatable_and_pure():
    core = build()
    cid = await _certify(core)
    store_before = deepcopy(core._certificates)
    first = await core.process({"action": "verify_certificate",
                                "certificate_id": cid})
    second = await core.process({"action": "verify_certificate",
                                 "certificate_id": cid})
    assert first["status"] == "ok"
    # Envelope timestamps are live; the audit DATA must be identical.
    assert first["data"] == second["data"]
    assert first["data"]["footprint_recomputation_matches"] is True
    # Auditing must not mutate the certificate store it inspects.
    assert core._certificates == store_before


async def test_verify_verdict_is_deterministic_after_finalize():
    core = build()
    cid = await _certify(core)
    pending = await core.process({"action": "verify_certificate",
                                  "certificate_id": cid})
    required = pending["data"]["retirement"]["required_g"]
    core.finalize_certificate(cid, {
        "purchase_id": cid, "mass_g": required,
        "total_cost_minor": 1, "fills": [{"registry": "verra"}],
        "content_hash": "ab" * 32})
    first = await core.process({"action": "verify_certificate",
                                "certificate_id": cid})
    second = await core.process({"action": "verify_certificate",
                                 "certificate_id": cid})
    assert first["data"] == second["data"]
    assert first["data"]["status"] == "certified"
    assert first["data"]["footprint_recomputation_matches"] is True
