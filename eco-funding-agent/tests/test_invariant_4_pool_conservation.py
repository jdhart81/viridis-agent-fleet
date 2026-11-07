"""Invariant 4 - Conservation in the simulator: releases plus remaining balance always
equal total pledges (to date, every period), and nothing is released without a met
milestone / verified outcome progress."""

from __future__ import annotations

import random

import pytest
from conftest import clone

from viridis_eco_funding import PoolSpecError, make_receipt, simulate_pool

METRICS = ["complexity_score", "d_score", "eca_ha", "connectivity_fraction", "verified_area_ha"]


def random_pool(rng: random.Random):
    horizon = rng.randint(1, 16)
    pledges = [{"id": f"k{i}", "pledger": f"pledger-{i}", "amount_minor": rng.randint(1, 10**9),
                "period": rng.randint(0, horizon)} for i in range(rng.randint(1, 12))]
    rules, budget = [], 10_000
    for i in range(rng.randint(1, 6)):
        if budget <= 0:
            break
        bps = rng.randint(1, budget)
        budget -= bps
        metric = rng.choice(METRICS)
        if rng.random() < 0.5:
            rules.append({"id": f"r{i}", "type": "milestone", "metric": metric,
                          "comparator": rng.choice([">=", ">"]),
                          "threshold": round(rng.uniform(0, 50), 3), "release_bps": bps,
                          "earliest_period": rng.randint(0, horizon)})
        else:
            base = round(rng.uniform(0, 30), 3)
            target = round(base + rng.uniform(0.1, 30), 3)
            rules.append({"id": f"r{i}", "type": "outcome_linked", "metric": metric,
                          "baseline": base, "target": target, "release_bps": bps,
                          "earliest_period": rng.randint(0, horizon)})
    observations = []
    for t in range(horizon + 1):
        if rng.random() < 0.7:
            observations.append({"id": f"o{t}", "period": t, "metrics": {
                m: round(rng.uniform(0, 50), 3) for m in rng.sample(METRICS, rng.randint(1, 3))}})
    return {"pool_id": "p", "horizon_periods": horizon, "pledges": pledges,
            "rules": rules}, observations


def _check(sim):
    pledges_by_period = {}
    for period in sim["periods"]:
        assert period["released_to_date_minor"] + period["remaining_minor"] == period["pledged_to_date_minor"]
        assert period["remaining_minor"] >= 0
        assert period["released_this_period_minor"] >= 0
        assert period["conservation_ok"] is True
        pledges_by_period[period["period"]] = period["pledged_to_date_minor"]
        for event in period["events"]:
            rule = next(r for r in sim["rules"] if r["id"] == event["rule_id"])
            assert rule["met_period"] is not None and rule["met_period"] <= period["period"]
            assert event["evidence"] is not None
            assert event["evidence"]["period"] <= period["period"]
            assert sum(event["pledges"].values()) == event["amount_minor"]
    totals = sim["totals"]
    assert totals["released_minor"] + totals["remaining_minor"] == totals["pledged_minor"]
    assert sum(p["released_minor"] + p["remaining_minor"] for p in sim["pledges"]) == totals["pledged_minor"]
    assert sum(r["released_minor"] for r in sim["rules"]) == totals["released_minor"]
    assert sim["invariants"] == {"conservation": True, "release_requires_met_rule": True}
    assert sim["simulation_only"] is True


def test_conservation_random_pools():
    rng = random.Random(4)
    for _ in range(600):
        pool, observations = random_pool(rng)
        _check(simulate_pool(pool, observations))


def test_no_observations_means_no_release():
    rng = random.Random(5)
    for _ in range(100):
        pool, _ = random_pool(rng)
        sim = simulate_pool(pool, [])
        assert sim["totals"]["released_minor"] == 0
        assert all(not p["events"] for p in sim["periods"])
        _check(sim)


def test_unmet_milestone_releases_nothing():
    pool = {"pool_id": "p", "horizon_periods": 3,
            "pledges": [{"id": "a", "pledger": "x", "amount_minor": 1000}],
            "rules": [{"id": "m", "type": "milestone", "metric": "complexity_score",
                       "comparator": ">=", "threshold": 10, "release_bps": 10000}]}
    sim = simulate_pool(pool, [{"period": 1, "metrics": {"complexity_score": 9.999}}])
    assert sim["totals"]["released_minor"] == 0
    sim = simulate_pool(pool, [{"period": 2, "metrics": {"complexity_score": 10}}])
    assert sim["totals"]["released_minor"] == 1000
    assert [p["released_this_period_minor"] for p in sim["periods"]] == [0, 0, 1000, 0]


def test_earliest_period_gates_release():
    pool = {"pool_id": "p", "horizon_periods": 4,
            "pledges": [{"id": "a", "pledger": "x", "amount_minor": 100}],
            "rules": [{"id": "m", "type": "milestone", "metric": "d_score", "comparator": ">",
                       "threshold": 0.1, "release_bps": 5000, "earliest_period": 3}]}
    sim = simulate_pool(pool, [{"period": 1, "metrics": {"d_score": 0.9}}])
    assert sim["totals"]["released_minor"] == 0


def test_outcome_linked_ratchet_and_late_pledges():
    pool = {"pool_id": "p", "horizon_periods": 4,
            "pledges": [{"id": "a", "pledger": "x", "amount_minor": 10_000},
                        {"id": "b", "pledger": "y", "amount_minor": 10_000, "period": 3}],
            "rules": [{"id": "o", "type": "outcome_linked", "metric": "eca_ha",
                       "baseline": 10, "target": 20, "release_bps": 10_000}]}
    obs = [{"period": 1, "metrics": {"eca_ha": 15}},     # 50 %
           {"period": 2, "metrics": {"eca_ha": 12}},     # regress: no clawback, no new release
           {"period": 4, "metrics": {"eca_ha": 25}}]     # capped at 100 %
    sim = simulate_pool(pool, obs)
    released = [p["released_this_period_minor"] for p in sim["periods"]]
    assert released == [0, 5000, 0, 5000, 10000]
    assert sim["totals"] == {"pledged_minor": 20000, "released_minor": 20000, "remaining_minor": 0}
    _check(sim)


def test_requires_receipt_ignores_hypothetical_and_invalid_receipts(woodland_site, example_pool):
    receipt = make_receipt(woodland_site)
    hypothetical = [{"id": "h", "period": 0, "metrics": {"complexity_score": 100}}]
    sim = simulate_pool(example_pool, hypothetical)
    m1 = next(r for r in sim["rules"] if r["id"] == "m1-baseline-receipt")
    assert m1["status"] == "not met"

    tampered = clone(receipt)
    tampered["result"]["quantities"]["complexity_score"]["value"] = 999
    sim = simulate_pool(example_pool, [{"id": "t", "period": 0, "receipt": tampered}])
    assert sim["observations"][0]["accepted"] is False
    assert sim["totals"]["released_minor"] == 0

    sim = simulate_pool(example_pool, [{"id": "r", "period": 0, "receipt": receipt}])
    m1 = next(r for r in sim["rules"] if r["id"] == "m1-baseline-receipt")
    assert m1["status"] == "met" and m1["evidence"]["basis"] == "receipt"
    assert sim["periods"][0]["released_this_period_minor"] == (250000 + 1000000) * 1500 // 10000
    _check(sim)


def test_receipt_for_other_site_is_rejected(woodland_site, example_pool):
    other = clone(woodland_site)
    other["site_id"] = "somewhere-else"
    sim = simulate_pool(example_pool, [{"id": "r", "period": 0, "receipt": make_receipt(other)}])
    assert sim["observations"][0]["accepted"] is False
    assert sim["observations"][0]["reason"] == "receipt is for a different site"


def test_release_bps_over_10000_rejected():
    pool = {"pool_id": "p", "horizon_periods": 1,
            "pledges": [{"id": "a", "pledger": "x", "amount_minor": 1}],
            "rules": [{"id": "m1", "type": "milestone", "metric": "d_score", "comparator": ">=",
                       "threshold": 0, "release_bps": 6000},
                      {"id": "m2", "type": "milestone", "metric": "d_score", "comparator": ">=",
                       "threshold": 0, "release_bps": 4001}]}
    with pytest.raises(PoolSpecError, match="at most 10000"):
        simulate_pool(pool, [])


@pytest.mark.parametrize("bad, message", [
    ({"pledges": []}, "pledges"),
    ({"rules": [{"id": "r", "type": "bogus"}]}, "type"),
    ({"pledges": [{"id": "a", "pledger": "x", "amount_minor": 0}]}, "amount_minor"),
    ({"pledges": [{"id": "a", "pledger": "x", "amount_minor": 5, "period": 99}]}, "period"),
    ({"horizon_periods": 0}, "horizon_periods"),
    ({"extra": 1}, "unknown"),
])
def test_invalid_pools_rejected(bad, message):
    pool = {"pool_id": "p", "horizon_periods": 2,
            "pledges": [{"id": "a", "pledger": "x", "amount_minor": 5}],
            "rules": [{"id": "m", "type": "milestone", "metric": "d_score", "comparator": ">=",
                       "threshold": 0, "release_bps": 100}]}
    pool.update(bad)
    with pytest.raises(PoolSpecError, match=message):
        simulate_pool(pool, [])


@pytest.mark.parametrize("obs, message", [
    ([{"period": 9, "metrics": {"d_score": 1}}], "period"),
    ([{"period": 0}], "exactly one"),
    ([{"period": 0, "metrics": {"d_score": 1}}, {"period": 0, "metrics": {"d_score": 2}}], "already"),
    ([{"period": 0, "metrics": {"price": 1}}], "unknown metric"),
    ([{"period": 0, "metrics": {"d_score": 1}, "basis": "receipt"}], "hypothetical"),
])
def test_invalid_observations_rejected(obs, message):
    pool = {"pool_id": "p", "horizon_periods": 2,
            "pledges": [{"id": "a", "pledger": "x", "amount_minor": 5}],
            "rules": [{"id": "m", "type": "milestone", "metric": "d_score", "comparator": ">=",
                       "threshold": 0, "release_bps": 100}]}
    with pytest.raises(PoolSpecError, match=message):
        simulate_pool(pool, obs)


@pytest.mark.parametrize("rule, message", [
    ({"type": "milestone", "comparator": "<", "threshold": 1}, "comparator"),
    ({"type": "milestone", "comparator": "<=", "threshold": 1}, "comparator"),
    ({"type": "outcome_linked", "baseline": 10, "target": 0}, "target must exceed baseline"),
    ({"type": "outcome_linked", "baseline": 5, "target": 5}, "target must exceed baseline"),
])
def test_rules_cannot_reward_ecological_decline(rule, message):
    pool = {"pool_id": "p", "horizon_periods": 1,
            "pledges": [{"id": "a", "pledger": "x", "amount_minor": 5}],
            "rules": [{"id": "r", "metric": "complexity_score", "release_bps": 100, **rule}]}
    with pytest.raises(PoolSpecError, match=message):
        simulate_pool(pool, [])


@pytest.mark.parametrize("drop", ["site_id", "calendar"])
def test_receipt_rules_need_site_and_calendar(example_pool, drop):
    pool = clone(example_pool)
    del pool[drop]
    with pytest.raises(PoolSpecError, match="site_id and calendar"):
        simulate_pool(pool, [])


def test_receipt_cannot_be_replayed_or_moved_to_another_period(woodland_site, example_pool):
    receipt = make_receipt(woodland_site)          # observed_at 2026-10-31 -> quarter 0
    sim = simulate_pool(example_pool, [{"id": "q0", "period": 0, "receipt": receipt},
                                       {"id": "q5", "period": 5, "receipt": receipt}])
    log = {o["id"]: o for o in sim["observations"]}
    assert log["q0"]["accepted"] is True
    assert log["q5"]["accepted"] is False and log["q5"]["reason"] == "receipt already used in this pool"

    sim = simulate_pool(example_pool, [{"id": "late", "period": 6, "receipt": receipt}])
    assert sim["observations"][0]["accepted"] is False
    assert "falls in period 0, not period 6" in sim["observations"][0]["reason"]
    assert sim["totals"]["released_minor"] == 0

    old = clone(woodland_site)
    old["observed_at"] = "1999-01-01"
    sim = simulate_pool(example_pool, [{"id": "old", "period": 8, "receipt": make_receipt(old)}])
    assert sim["observations"][0]["accepted"] is False and "observed_at" in sim["observations"][0]["reason"]

    undated = clone(woodland_site)
    del undated["observed_at"]
    sim = simulate_pool(example_pool, [{"id": "u", "period": 0, "receipt": make_receipt(undated)}])
    assert sim["observations"][0]["accepted"] is False


def test_calendar_validation(example_pool):
    pool = clone(example_pool)
    pool["calendar"] = {"start": "not-a-date", "period_months": 3}
    with pytest.raises(PoolSpecError, match="ISO date"):
        simulate_pool(pool, [])
    pool["calendar"] = {"start": "2026-10-01", "period_months": 0}
    with pytest.raises(PoolSpecError, match="period_months"):
        simulate_pool(pool, [])


@pytest.mark.parametrize("field, value, message", [
    ("pool_id", "", "pool_id"), ("unit", {"code": "USD"}, "minor_per_major"),
    ("unit", {"code": "USD", "minor_per_major": 100, "x": 1}, "unknown"),
    ("schema", "vef-pool/9", "schema"), ("rules", [], "rules"), ("pledges", "x", "pledges"),
    ("site_id", 5, "site_id"), ("period_label", "", "period_label"),
])
def test_pool_field_validation(example_pool, field, value, message):
    pool = clone(example_pool)
    pool[field] = value
    with pytest.raises(PoolSpecError, match=message):
        simulate_pool(pool, [])


@pytest.mark.parametrize("patch, message", [
    ({"id": "m1-baseline-receipt"}, "duplicate rule"),
    ({"metric": "price"}, "metric"),
    ({"release_bps": 0}, "release_bps"),
    ({"requires_receipt": "yes"}, "true or false"),
    ({"earliest_period": 99}, "earliest_period"),
    ({"threshold": "abc"}, "number"),
    ({"bogus": 1}, "unknown"),
])
def test_rule_field_validation(example_pool, patch, message):
    pool = clone(example_pool)
    rule = {"id": "extra", "type": "milestone", "metric": "d_score", "comparator": ">=",
            "threshold": 0, "release_bps": 1}
    rule.update(patch)
    pool["rules"] = pool["rules"] + [rule]
    with pytest.raises(PoolSpecError, match=message):
        simulate_pool(pool, [])


def test_pledge_validation(example_pool):
    pool = clone(example_pool)
    pool["pledges"] = pool["pledges"] + [dict(pool["pledges"][0])]
    with pytest.raises(PoolSpecError, match="duplicate pledge"):
        simulate_pool(pool, [])
    pool = clone(example_pool)
    pool["pledges"][0]["pledger"] = ""
    with pytest.raises(PoolSpecError, match="pledger"):
        simulate_pool(pool, [])
