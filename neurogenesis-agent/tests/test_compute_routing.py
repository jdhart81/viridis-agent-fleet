"""NG7 — Wu Wei compute routing. One test per claim."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core import build

CHEAP_BAD = {"id": "tiny-local", "kind": "model", "quality_score": 0.3,
             "cost_per_1k_input_tokens": 0.0001,
             "cost_per_1k_output_tokens": 0.0002,
             "latency_ms": 50, "local": True, "max_context_tokens": 8192}
MID_GOOD = {"id": "mid-cloud", "kind": "model", "quality_score": 0.8,
            "cost_per_1k_input_tokens": 0.001,
            "cost_per_1k_output_tokens": 0.003,
            "latency_ms": 800, "max_context_tokens": 128000}
BIG_BEST = {"id": "frontier", "kind": "model", "quality_score": 0.97,
            "cost_per_1k_input_tokens": 0.01,
            "cost_per_1k_output_tokens": 0.03,
            "latency_ms": 2000, "max_context_tokens": 200000}
CACHE_GOOD = {
    "id": "fresh-cache", "kind": "cache", "quality_score": 0.92,
    "reliability_score": 0.99, "latency_ms": 5,
    "max_context_tokens": 128000, "local": True,
    "cache_confidence": 0.94, "cache_age_seconds": 60,
    "fixed_energy_wh": 0.0001, "capabilities": ["analysis"],
}
LOCAL_EFFICIENT = {
    "id": "small-local", "kind": "model", "execution_mode": "local",
    "quality_score": 0.85, "reliability_score": 0.95,
    "cost_per_1k_input_tokens": 0.002,
    "cost_per_1k_output_tokens": 0.004, "latency_ms": 300,
    "max_context_tokens": 128000, "local": True,
    "energy_wh_per_1k_input_tokens": 0.02,
    "energy_wh_per_1k_output_tokens": 0.04,
    "carbon_intensity_g_per_kwh": 40,
    "capabilities": ["analysis"],
}
CLOUD_HEAVY = {
    "id": "large-cloud", "kind": "model", "execution_mode": "cloud",
    "quality_score": 0.9, "reliability_score": 0.99,
    "cost_per_1k_input_tokens": 0.001,
    "cost_per_1k_output_tokens": 0.002, "latency_ms": 500,
    "max_context_tokens": 128000,
    "energy_wh_per_1k_input_tokens": 3.0,
    "energy_wh_per_1k_output_tokens": 5.0,
    "carbon_intensity_g_per_kwh": 400,
    "capabilities": ["analysis"],
}

TASK = {"id": "t1", "task_type": "analysis", "expected_input_tokens": 2000,
        "expected_output_tokens": 500, "min_quality": 0.7}


@pytest.fixture
def core():
    return build()


async def _setup(core, profiles=(CHEAP_BAD, MID_GOOD, BIG_BEST)):
    for p in profiles:
        r = await core.process({"action": "register_compute_profile",
                                "profile": p})
        assert r["status"] == "ok", r


async def test_NG7_quality_floor_is_a_hard_contract(core):
    """The cheapest profile is BELOW the floor — it must never win."""
    await _setup(core)
    r = await core.process({"action": "route_task", "task": TASK})
    assert r["status"] == "ok"
    assert r["data"]["profile_id"] != "tiny-local"      # floor honored
    assert r["data"]["quality_floor_honored"] is True


async def test_NG7_cheapest_reliable_wins(core):
    """Both mid and frontier meet the floor; mid is far cheaper -> mid."""
    await _setup(core)
    r = await core.process({"action": "route_task", "task": TASK})
    assert r["data"]["profile_id"] == "mid-cloud"


async def test_NG7_routing_is_deterministic(core):
    await _setup(core)
    a = await core.process({"action": "route_task", "task": TASK})
    b = await core.process({"action": "route_task", "task": TASK})
    assert a["data"]["profile_id"] == b["data"]["profile_id"]
    assert a["data"]["score"] == b["data"]["score"]


async def test_NG7_no_eligible_profile_teaches(core):
    """A floor nobody meets is a structured refusal, never a downgrade."""
    await _setup(core, profiles=(CHEAP_BAD,))
    r = await core.process({"action": "route_task",
                            "task": {**TASK, "min_quality": 0.9}})
    assert r["status"] == "error"
    assert r["error_type"] == "no_eligible_profile"
    assert "min_quality" in r["constraint"]


async def test_NG7_profiles_never_invented(core):
    r = await core.process({"action": "route_task", "task": TASK})
    assert r["status"] == "error"
    assert "register_compute_profile" in r["message"]


async def test_NG7_decisions_logged_and_reported_with_physics(core):
    await _setup(core)
    await core.process({"action": "route_task", "task": TASK})
    await core.process({"action": "route_task",
                        "task": {**TASK, "id": "t2"}})
    rep = await core.process({"action": "compute_efficiency_report"})
    d = rep["data"]
    assert d["decisions_total"] == 2
    assert d["by_profile"].get("mid-cloud") == 2
    assert all("reason" in x for x in d["decisions"])
    assert 0 < d["physics"]["landauer_energy_per_bit_joules_at_300K"] < 1e-18


async def test_NG7_register_validates_and_is_bounded(core):
    bad = await core.process({"action": "register_compute_profile",
                              "profile": {"kind": "model"}})
    assert bad["status"] == "error"
    assert bad["field"] == "profile"
    ok = await core.process({"action": "register_compute_profile",
                             "profile": MID_GOOD})
    assert ok["data"]["registered_profiles"] == 1
    assert "route_task" in ok["data"]["next_steps"]["route"]


async def test_NG7_health_counts_routing_state(core):
    await _setup(core)
    await core.process({"action": "route_task", "task": TASK})
    h = await core.health()
    assert h["checks"]["compute_profiles"] == 3
    assert h["checks"]["route_decisions"] == 1


async def test_NG8_energy_aware_route_prefers_lower_total_burden(core):
    await _setup(core, profiles=(LOCAL_EFFICIENT, CLOUD_HEAVY))
    r = await core.process({
        "action": "route_task",
        "task": {**TASK, "required_capabilities": ["analysis"],
                 "require_energy_estimate": True,
                 "energy_weight": 10.0,
                 "baseline_cost_usd": 0.02,
                 "baseline_energy_wh": 10.0,
                 "baseline_latency_ms": 1000},
    })
    assert r["status"] == "ok", r
    data = r["data"]
    assert data["profile_id"] == "small-local"
    assert data["execution_mode"] == "local"
    assert data["energy_estimate_status"] == "profile_token_energy_estimate"
    assert data["estimated_energy_wh"] == pytest.approx(0.06)
    assert data["estimated_energy_saved_wh"] == pytest.approx(9.94)
    assert len(data["decision_sha256"]) == 64


async def test_NG8_unknown_energy_fails_closed_when_required(core):
    await _setup(core, profiles=(MID_GOOD,))
    r = await core.process({
        "action": "route_task",
        "task": {**TASK, "require_energy_estimate": True},
    })
    assert r["status"] == "error"
    assert r["error_type"] == "no_eligible_profile"


async def test_NG8_reuse_is_allowed_only_when_fresh_and_low_risk(core):
    await _setup(core, profiles=(CACHE_GOOD, LOCAL_EFFICIENT))
    low = await core.process({
        "action": "route_task",
        "task": {**TASK, "risk": 0.2,
                 "required_capabilities": ["analysis"]},
    })
    assert low["data"]["profile_id"] == "fresh-cache"
    assert low["data"]["execution_mode"] == "reuse"
    high = await core.process({
        "action": "route_task",
        "task": {**TASK, "id": "high-risk", "risk": 0.9,
                 "required_capabilities": ["analysis"]},
    })
    assert high["data"]["profile_id"] == "small-local"


async def test_NG8_explicit_low_value_defer_avoids_compute(core):
    r = await core.process({
        "action": "route_task",
        "task": {**TASK, "allow_defer": True, "value_score": 0.01,
                 "defer_below_value": 0.1, "urgency": 0.1, "risk": 0.2,
                 "baseline_cost_usd": 0.04,
                 "baseline_energy_wh": 4.0},
    })
    assert r["status"] == "ok", r
    assert r["data"]["profile_id"] is None
    assert r["data"]["execution_mode"] == "defer"
    assert r["data"]["no_result_claimed"] is True
    assert r["data"]["estimated_energy_wh"] == 0.0


async def test_NG8_outcome_receipt_is_append_only_and_reported(core):
    await _setup(core, profiles=(LOCAL_EFFICIENT,))
    route = await core.process({
        "action": "route_task",
        "task": {**TASK, "required_capabilities": ["analysis"],
                 "require_energy_estimate": True},
    })
    decision_id = route["data"]["decision_id"]
    outcome = await core.process({
        "action": "record_route_outcome", "decision_id": decision_id,
        "success_score": 0.9, "actual_cost_usd": 0.006,
        "actual_latency_ms": 320, "actual_energy_wh": 0.065,
    })
    assert outcome["status"] == "ok", outcome
    assert len(outcome["data"]["outcome_sha256"]) == 64
    assert outcome["data"]["decision_sha256"] == \
        route["data"]["decision_sha256"]
    duplicate = await core.process({
        "action": "record_route_outcome", "decision_id": decision_id,
        "success_score": 0.8,
    })
    assert duplicate["status"] == "error"
    assert duplicate["error_type"] == "conflict"
    report = await core.process({"action": "compute_efficiency_report"})
    observed = report["data"]["observed_outcomes"]
    assert observed["count"] == 1
    assert observed["actual_energy_wh"] == pytest.approx(0.065)
    assert observed["energy_coverage"] == "1/1"


async def test_NG8_profile_and_task_bounds_validate(core):
    bad_profile = await core.process({
        "action": "register_compute_profile",
        "profile": {**LOCAL_EFFICIENT, "energy_wh_per_1k_input_tokens": -1},
    })
    assert bad_profile["status"] == "error"
    assert bad_profile["error_type"] == "ValidationError"
    await _setup(core, profiles=(LOCAL_EFFICIENT,))
    impossible = await core.process({
        "action": "route_task",
        "task": {**TASK, "max_energy_wh": 0.001,
                 "required_capabilities": ["analysis"]},
    })
    assert impossible["status"] == "error"
    assert impossible["error_type"] == "no_eligible_profile"


async def test_NG8_pre_v2_snapshot_is_forward_compatible(core):
    core._route_decisions = [{
        "task_id": "legacy", "task_type": "analysis",
        "profile_id": "old-profile", "score": 1.0,
        "estimated_cost": 0.01, "estimated_latency_ms": 100,
        "reason": "pre-v2 record", "at": "2026-07-18T00:00:00Z",
    }]
    del core._route_outcomes
    del core._route_seq
    del core._outcome_seq
    report = await core.process({"action": "compute_efficiency_report"})
    assert report["status"] == "ok", report
    assert report["data"]["legacy_decisions_unreceipted"] == 1
    assert report["data"]["v2_decisions_total"] == 0
    h = await core.health()
    assert h["checks"]["wu_wei_policy"] == "wu-wei-router-v2"
