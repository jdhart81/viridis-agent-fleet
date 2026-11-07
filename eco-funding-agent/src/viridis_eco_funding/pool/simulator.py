"""Deterministic pool simulator. SIMULATION ONLY: no funds exist in this software.

Accounting model (Invariant 4):

* Every amount is an integer number of minor units, so conservation is exact.
* For each active pledge k and rule r, the cumulative entitlement is
  ``floor(amount_k * effective_bps_r / 10000)``. ``effective_bps_r`` is ``release_bps``
  once a milestone is met, or ``release_bps * progress`` for an outcome-linked rule.
  Both only ever increase (latch / ratchet), so each period's release
  ``entitlement - already_released`` is never negative and nothing is clawed back.
* A cell can only release when its rule is met (milestone) or has positive verified
  progress (outcome-linked). The simulator asserts this, and the invariant checks are
  part of the output.
* Because sum(release_bps) <= 10000, releases never exceed pledges, and at every period
  ``released_to_date + remaining == pledged_to_date``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from .._decimal import ONE, ZERO, clamp, floor_int, pinned, publish, quantize_input
from ..canonical import to_canonical_data
from ..constants import CONJECTURE_LABEL
from ..receipt import verify_receipt
from .schema import COMPARATORS, LEGAL_NOTICE, METRICS, PoolSpecError, normalize_pool

BPS = Decimal(10_000)


def _compare(value: Decimal, comparator: str, threshold: Decimal) -> bool:
    assert comparator in COMPARATORS
    return value >= threshold if comparator == ">=" else value > threshold


def _calendar_period(calendar: dict[str, Any], observed_at: Any) -> int | None:
    """Period index of an ISO date on the pool calendar, or None if unusable."""
    if not isinstance(observed_at, str) or len(observed_at) < 10:
        return None
    try:
        day = date.fromisoformat(observed_at[:10])
    except ValueError:
        return None
    start = date.fromisoformat(calendar["start"])
    months = (day.year - start.year) * 12 + (day.month - start.month) - (1 if day.day < start.day else 0)
    return None if months < 0 else months // calendar["period_months"]


def _readings(pool: dict[str, Any], observations: Any) -> tuple[dict[int, dict[str, dict[str, Any]]],
                                                               list[dict[str, Any]]]:
    if observations is None:
        observations = []
    if not isinstance(observations, list):
        raise PoolSpecError("observations: expected a list")
    by_period: dict[int, dict[str, dict[str, Any]]] = {}
    log: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_seals: set[str] = set()
    for index, raw in enumerate(observations):
        field = f"observations[{index}]"
        if not isinstance(raw, dict):
            raise PoolSpecError(f"{field}: expected an object")
        extra = sorted(set(raw) - {"id", "period", "metrics", "receipt", "basis", "note"})
        if extra:
            raise PoolSpecError(f"{field}: unknown key(s) {extra}")
        obs_id = raw.get("id") or f"obs-{index}"
        if not isinstance(obs_id, str) or obs_id in seen_ids:
            raise PoolSpecError(f"{field}.id: missing or duplicate observation id")
        seen_ids.add(obs_id)
        period = raw.get("period")
        if isinstance(period, bool) or not isinstance(period, int) or not 0 <= period <= pool["horizon_periods"]:
            raise PoolSpecError(f"{field}.period: integer between 0 and horizon_periods")
        has_receipt, has_metrics = raw.get("receipt") is not None, raw.get("metrics") is not None
        if has_receipt == has_metrics:
            raise PoolSpecError(f"{field}: give exactly one of 'receipt' or 'metrics'")
        values: dict[str, Decimal] = {}
        if has_receipt:
            report = verify_receipt(raw["receipt"])
            reason = ""
            if not report["valid"]:
                reason = "receipt failed verification"
            else:
                receipt = to_canonical_data(raw["receipt"])
                seal = receipt["seal"]["digest"]
                if pool["site_id"] is not None and receipt["result"]["site_id"] != pool["site_id"]:
                    reason = "receipt is for a different site"
                elif seal in seen_seals:
                    reason = "receipt already used in this pool"
                elif pool["calendar"] is not None:
                    receipt_period = _calendar_period(pool["calendar"], receipt["result"]["observed_at"])
                    if receipt_period is None:
                        reason = "receipt has no usable observed_at date on or after the pool calendar start"
                    elif receipt_period != period:
                        reason = (f"receipt observed_at falls in period {receipt_period}, "
                                  f"not period {period}")
            if reason:
                log.append({"id": obs_id, "period": period, "basis": "receipt",
                            "accepted": False, "reason": reason})
                continue
            seen_seals.add(seal)
            basis = "receipt"
            for metric in METRICS:
                quantity = receipt["result"]["quantities"].get(metric)
                if quantity is not None:
                    values[metric] = quantity["value"]
        else:
            basis = raw.get("basis", "hypothetical")
            if basis != "hypothetical":
                raise PoolSpecError(f"{field}.basis: metric readings without a receipt are "
                                    "'hypothetical'")
            metrics = raw["metrics"]
            if not isinstance(metrics, dict) or not metrics:
                raise PoolSpecError(f"{field}.metrics: expected a non-empty object")
            for metric, value in metrics.items():
                if metric not in METRICS:
                    raise PoolSpecError(f"{field}.metrics: unknown metric {metric!r}")
                try:
                    values[metric] = quantize_input(value, field=f"{field}.metrics.{metric}")
                except ValueError as exc:
                    raise PoolSpecError(str(exc)) from exc
        slot = by_period.setdefault(period, {})
        for metric, value in values.items():
            if metric in slot:
                raise PoolSpecError(f"{field}: metric {metric!r} already has a reading in "
                                    f"period {period}")
            slot[metric] = {"value": value, "basis": basis, "observation_id": obs_id}
        log.append({"id": obs_id, "period": period, "basis": basis, "accepted": True,
                    "reason": "", "metrics": sorted(values)})
    return by_period, log


@pinned
def simulate_pool(pool_spec: Any, observations: Any = None) -> dict[str, Any]:
    pool = normalize_pool(pool_spec)
    readings, observation_log = _readings(pool, observations)
    rules = pool["rules"]
    pledges = pool["pledges"]

    state = {r["id"]: {"met": False, "met_period": None, "progress": ZERO, "evidence": None}
             for r in rules}
    released = {p["id"]: {r["id"]: 0 for r in rules} for p in pledges}
    periods: list[dict[str, Any]] = []
    conservation_ok = True
    release_requires_met = True
    released_to_date = 0

    for t in range(pool["horizon_periods"] + 1):
        slot = readings.get(t, {})
        for rule in rules:
            st = state[rule["id"]]
            reading = slot.get(rule["metric"])
            if reading is None or t < rule["earliest_period"]:
                continue
            if rule["requires_receipt"] and reading["basis"] != "receipt":
                continue
            evidence = {"observation_id": reading["observation_id"], "basis": reading["basis"],
                        "metric": rule["metric"], "value": reading["value"], "period": t}
            if rule["type"] == "milestone":
                if not st["met"] and _compare(reading["value"], rule["comparator"], rule["threshold"]):
                    st.update(met=True, met_period=t, evidence=evidence)
            else:
                progress = clamp((reading["value"] - rule["baseline"])
                                 / (rule["target"] - rule["baseline"]), ZERO, ONE)
                if progress > st["progress"]:
                    st.update(progress=progress, evidence=evidence,
                              met=True, met_period=st["met_period"] if st["met_period"] is not None else t)

        events: dict[str, dict[str, Any]] = {}
        pledged_to_date = 0
        for pledge in pledges:
            if pledge["period"] > t:
                continue
            pledged_to_date += pledge["amount_minor"]
            for rule in rules:
                st = state[rule["id"]]
                if rule["type"] == "milestone":
                    bps = Decimal(rule["release_bps"]) if st["met"] else ZERO
                else:
                    bps = Decimal(rule["release_bps"]) * st["progress"]
                entitled = floor_int(Decimal(pledge["amount_minor"]) * bps / BPS)
                delta = entitled - released[pledge["id"]][rule["id"]]
                if delta < 0:  # impossible under latch/ratchet; hard guard
                    raise AssertionError("negative release")
                if delta == 0:
                    continue
                if not st["met"]:
                    release_requires_met = False
                    raise AssertionError("Invariant 4: release without a met rule")
                released[pledge["id"]][rule["id"]] = entitled
                event = events.setdefault(rule["id"], {"rule_id": rule["id"], "amount_minor": 0,
                                                       "pledges": {}, "evidence": st["evidence"]})
                event["amount_minor"] += delta
                event["pledges"][pledge["id"]] = delta
        released_this_period = sum(e["amount_minor"] for e in events.values())
        released_to_date += released_this_period
        remaining = sum(p["amount_minor"] - sum(released[p["id"]].values())
                        for p in pledges if p["period"] <= t)
        ok = released_to_date + remaining == pledged_to_date and remaining >= 0
        conservation_ok = conservation_ok and ok
        if not ok:
            raise AssertionError("Invariant 4: conservation violated")
        periods.append({
            "period": t,
            "pledged_to_date_minor": pledged_to_date,
            "released_this_period_minor": released_this_period,
            "released_to_date_minor": released_to_date,
            "remaining_minor": remaining,
            "events": [events[key] for key in sorted(events)],
            "conservation_ok": ok,
        })

    total_pledged = sum(p["amount_minor"] for p in pledges)
    rule_summary = []
    for rule in rules:
        st = state[rule["id"]]
        effective = (Decimal(rule["release_bps"]) if st["met"] else ZERO) if rule["type"] == "milestone" \
            else Decimal(rule["release_bps"]) * st["progress"]
        rule_summary.append({
            "id": rule["id"], "type": rule["type"], "metric": rule["metric"],
            "status": ("met" if st["met"] else "not met") if rule["type"] == "milestone" else
                      ("complete" if st["progress"] == ONE else "partial" if st["met"] else "not met"),
            "met_period": st["met_period"],
            "progress": ONE if (rule["type"] == "milestone" and st["met"]) else publish(st["progress"]),
            "effective_bps": publish(effective),
            "released_minor": sum(released[p["id"]][rule["id"]] for p in pledges),
            "evidence": st["evidence"],
        })
    pledge_summary = [{
        "id": p["id"], "pledger": p["pledger"], "amount_minor": p["amount_minor"],
        "period": p["period"],
        "released_minor": sum(released[p["id"]].values()),
        "remaining_minor": p["amount_minor"] - sum(released[p["id"]].values()),
    } for p in pledges]
    total_released = sum(item["released_minor"] for item in pledge_summary)
    uses_bound = any(METRICS[rule["metric"]] for rule in rules)
    explanation = (
        f"SIMULATION ONLY. Pool {pool['pool_id']}: {total_pledged} {pool['unit']['code']} minor "
        f"units pledged; {total_released} would be released under the rules by period "
        f"{pool['horizon_periods']} and {total_pledged - total_released} would remain in the pool. "
        "Every release is an outcome-linked or milestone release backed by a met rule, and "
        "releases plus remaining balance equal total pledges in every period. ")
    if uses_bound:
        explanation += ("At least one rule uses a metric derived from the intelligence bound, which "
                        "is a conjecture; do not tie real releases to it without independent review. ")
    explanation += LEGAL_NOTICE
    return to_canonical_data({
        "schema": pool["schema"],
        "pool_id": pool["pool_id"],
        "simulation_only": True,
        "unit": pool["unit"],
        "period_label": pool["period_label"],
        "calendar": pool["calendar"],
        "totals": {"pledged_minor": total_pledged, "released_minor": total_released,
                   "remaining_minor": total_pledged - total_released},
        "periods": periods,
        "rules": rule_summary,
        "pledges": pledge_summary,
        "observations": observation_log,
        "invariants": {"conservation": conservation_ok,
                       "release_requires_met_rule": release_requires_met},
        "uses_intelligence_bound": uses_bound,
        "labels": {"intelligence_bound": CONJECTURE_LABEL if uses_bound else "not used"},
        "explanation": explanation,
        "notice": LEGAL_NOTICE,
    })
