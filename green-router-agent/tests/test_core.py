"""Invariant tests for green-router-agent (GR1-GR9) + fleet contract."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core import build, CERT_MAX_G, SAFETY_FACTOR

WORKLOAD = {"backend_id": "frontier_cloud", "total_tokens": 3000,
            "output_tokens": 800, "calls": 100}


@pytest.fixture
def core():
    return build()


async def _quote(core, **over):
    return await core.process({"action": "quote_footprint",
                               "workload": {**WORKLOAD, **over}})


# --- GR1 physics honesty ---------------------------------------------------- #
async def test_GR1_every_assumption_stated_with_source(core):
    r = await _quote(core)
    a = r["data"]["assumptions"]
    assert a["backend_energy"]["wh_per_1k_tokens"] == 0.30
    assert "IEA" in a["grid"]["source"]
    assert "Uptime" in a["facility_pue"]["source"]
    assert a["safety_factor"] == SAFETY_FACTOR
    assert "estimates" in a["honesty"]
    assert 0 < r["data"]["physics_context"][
        "landauer_joules_per_bit_at_300K"] < 1e-18


# --- GR2 determinism --------------------------------------------------------- #
async def test_GR2_identical_workload_identical_footprint(core):
    a = await _quote(core)
    b = await _quote(core)
    assert a["data"]["total"] == b["data"]["total"]
    assert (a["data"]["retirement_required_g"]
            == b["data"]["retirement_required_g"])


async def test_GR2_retirement_mass_is_ceil_times_safety(core):
    import math
    r = await _quote(core)
    g = r["data"]["total"]["carbon_gco2e"]
    assert r["data"]["retirement_required_g"] == max(
        1, math.ceil(g * SAFETY_FACTOR))


# --- GR3 fail-closed certification (core side) ------------------------------- #
async def test_GR3_certify_is_pending_until_retirement(core):
    r = await core.process({"action": "certify", "workload": WORKLOAD})
    assert r["status"] == "ok"
    assert r["data"]["status"] == "pending_retirement"
    assert r["data"]["retirement"]["status"] == "pending"


async def test_GR3_void_removes_pending_certificate(core):
    r = await core.process({"action": "certify", "workload": WORKLOAD})
    cid = r["data"]["certificate_id"]
    core.void_certificate(cid)
    bad = await core.process({"action": "verify_certificate",
                              "certificate_id": cid})
    assert bad["status"] == "error"


async def test_GR3_finalize_marks_certified_with_provenance(core):
    r = await core.process({"action": "certify", "workload": WORKLOAD})
    cid = r["data"]["certificate_id"]
    done = core.finalize_certificate(cid, {
        "purchase_id": cid, "mass_g": r["data"]["retirement"]["required_g"],
        "total_cost_minor": 1, "fills": [{"registry": "verra"}],
        "content_hash": "ab" * 32})
    assert done["status"] == "certified"
    assert done["retirement"]["status"] == "retired"
    assert "verify_retirement" in done["retirement"]["independent_check"]


# --- GR4 machine-verifiable -------------------------------------------------- #
async def test_GR4_verify_recomputes_and_matches(core):
    r = await core.process({"action": "certify", "workload": WORKLOAD})
    cid = r["data"]["certificate_id"]
    v = await core.process({"action": "verify_certificate",
                            "certificate_id": cid})
    assert v["data"]["footprint_recomputation_matches"] is True
    assert "x402-C" in v["data"]["note"]


# --- GR6 no invented capacity ------------------------------------------------ #
async def test_GR6_unknown_backend_teaches_options(core):
    r = await _quote(core, backend_id="cold_fusion")
    assert r["status"] == "error"
    assert "custom_backend" in r["constraint"]


async def test_GR6_custom_backend_is_caller_declared(core):
    r = await _quote(core, backend_id="my-gpu",
                     custom_backend={"id": "my-gpu",
                                     "wh_per_1k_tokens": 0.05})
    assert r["status"] == "ok"
    assert r["data"]["assumptions"]["backend_energy"]["id"] == "my-gpu"


@pytest.mark.parametrize("field,value", [
    ("success_score", float("inf")),
    ("grid_gco2e_per_kwh", float("inf")),
    ("pue", float("inf")),
])
async def test_GR6_non_finite_overrides_fail_closed(core, field, value):
    r = await _quote(core, **{field: value})
    assert r["status"] == "error"


async def test_GR6_non_finite_custom_backend_fails_closed(core):
    r = await _quote(
        core, backend_id="poison",
        custom_backend={"id": "poison", "wh_per_1k_tokens": float("inf")})
    assert r["status"] == "error"


async def test_GR6_green_route_ranks_by_carbon(core):
    r = await core.process({"action": "green_route", "workload": WORKLOAD})
    ranking = r["data"]["ranking"]
    carbons = [x["carbon_gco2e_per_call"] for x in ranking]
    assert carbons == sorted(carbons)
    assert r["data"]["greenest"]["backend_id"] == "local_small"
    assert "neurogenesis" in r["data"]["note"]      # NG7 cross-teach


# --- GR7 never raises --------------------------------------------------------- #
@pytest.mark.parametrize("bad", [None, [], "x", 5])
async def test_GR7_nondict_input_never_raises(core, bad):
    r = await core.process(bad)
    assert r["status"] == "error"
    assert r["field"] == "input_data"


async def test_GR7_bad_workload_teaches(core):
    r = await core.process({"action": "quote_footprint",
                            "workload": {"total_tokens": -1,
                                         "output_tokens": 0}})
    assert r["status"] == "error"
    assert "output_tokens" in r["message"]


# --- GR8 honest books --------------------------------------------------------- #
async def test_GR8_ledger_sums_certified_only(core):
    a = await core.process({"action": "certify", "workload": WORKLOAD})
    core.finalize_certificate(a["data"]["certificate_id"],
                              {"purchase_id": "p1", "mass_g": 7,
                               "total_cost_minor": 3, "fills": [],
                               "content_hash": "cd" * 32})
    await core.process({"action": "certify", "workload": WORKLOAD})  # pending
    led = await core.process({"action": "list_certificates"})
    assert led["data"]["count"] == 2
    assert led["data"]["certified"] == 1
    assert led["data"]["total_retired_g"] == 7
    assert led["data"]["total_offset_cost_minor"] == 3


# --- GR9 bounded -------------------------------------------------------------- #
async def test_GR9_over_cap_refused_with_teaching(core):
    r = await core.process({"action": "certify",
                            "workload": {**WORKLOAD,
                                         "calls": 10_000_000}})
    assert r["status"] == "error"
    assert r["error_type"] == "over_cap"
    assert str(CERT_MAX_G) in r["constraint"]


async def test_health_and_unknown_action(core):
    h = await core.health()
    assert h["status"] == "ok" and "retired_g" in h["checks"]
    r = await core.process({"action": "burn_coal"})
    assert r["status"] == "error" and "quote_footprint" in r["constraint"]
