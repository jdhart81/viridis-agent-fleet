"""Funding-pool schema (``vef-pool/0.1``): pledges and release rules. Modelling only.

A pool spec describes pledges (amounts in integer minor units of a *label* such as
"USD"; nothing is denominated, held or moved by this software) and release rules:

* ``milestone``: release ``release_bps`` basis points of every active pledge once a
  verified reading of ``metric`` satisfies ``comparator threshold`` (latched: once met,
  stays met);
* ``outcome_linked``: release up to ``release_bps`` in proportion to verified progress
  from ``baseline`` toward ``target`` (ratchet: progress never goes backwards, nothing is
  clawed back).

The sum of ``release_bps`` over all rules may not exceed 10 000, so releases can never
exceed pledges.

Every v0.1 metric is better when higher, so rules can only reward improvement: milestone
comparators are ``>=`` or ``>``, and an outcome-linked target must exceed its baseline.

A rule with ``requires_receipt: true`` counts only readings from receipts that verify,
belong to the pool's ``site_id``, have an ``observed_at`` date inside the observation's
period on the pool ``calendar``, and have not already been used in the pool. Pools with
such rules must therefore set ``site_id`` and ``calendar``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Mapping

from .._decimal import pinned, quantize_input
from ..canonical import to_canonical_data
from ..constants import POOL_SCHEMA

METRICS = {
    "complexity_score": False,
    "d_score": False,
    "data_richness": False,
    "soil_index": False,
    "eca_ha": False,
    "verified_area_ha": False,
    "connectivity_fraction": False,
    "stated_bound_bits_per_s": True,
    "complexity_capacity_bits_per_s": True,
}
"""metric -> whether it derives from the intelligence bound (a conjecture)."""

COMPARATORS = (">=", ">")
MAX_PLEDGES = 5000
MAX_RULES = 50
MAX_HORIZON = 600
MAX_AMOUNT_MINOR = 10**15

LEGAL_NOTICE = ("Any real funding pool needs legal review before money moves. This software "
                "holds, moves and releases no funds: it models how a pool's pledge and "
                "release rules would behave.")


class PoolSpecError(ValueError):
    pass


def _obj(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PoolSpecError(f"{field}: expected an object")
    return value


def _only(value: Mapping[str, Any], allowed: set[str], field: str) -> None:
    extra = sorted(set(value) - allowed)
    if extra:
        raise PoolSpecError(f"{field}: unknown key(s) {extra}")


def _text(value: Any, field: str, *, required: bool = True, max_len: int = 200) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise PoolSpecError(f"{field}: expected a non-empty string")
    if len(value.strip()) > max_len:
        raise PoolSpecError(f"{field}: longer than {max_len} characters")
    return value.strip()


def _int(value: Any, field: str, low: int, high: int) -> int:
    if isinstance(value, Decimal) and value == value.to_integral_value():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise PoolSpecError(f"{field}: expected an integer")
    if not low <= value <= high:
        raise PoolSpecError(f"{field}: must be between {low} and {high}, got {value}")
    return value


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise PoolSpecError(f"{field}: expected true or false")
    return value


def _dec(value: Any, field: str) -> Decimal:
    try:
        return quantize_input(value, field=field)
    except ValueError as exc:
        raise PoolSpecError(str(exc)) from exc


@pinned
def normalize_pool(raw: Any) -> dict[str, Any]:
    data = _obj(to_canonical_data(_obj(raw, "pool")), "pool")
    _only(data, {"schema", "pool_id", "name", "site_id", "unit", "horizon_periods",
                 "period_label", "calendar", "pledges", "rules"}, "pool")
    if data.get("schema", POOL_SCHEMA) != POOL_SCHEMA:
        raise PoolSpecError(f"schema: expected {POOL_SCHEMA!r}")
    horizon = _int(data.get("horizon_periods"), "horizon_periods", 1, MAX_HORIZON)

    unit = _obj(data.get("unit", {"code": "units", "minor_per_major": 100}), "unit")
    _only(unit, {"code", "minor_per_major"}, "unit")

    pledges_raw = data.get("pledges")
    if not isinstance(pledges_raw, list) or not pledges_raw:
        raise PoolSpecError("pledges: expected a non-empty list")
    if len(pledges_raw) > MAX_PLEDGES:
        raise PoolSpecError(f"pledges: at most {MAX_PLEDGES}")
    pledges: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(pledges_raw):
        field = f"pledges[{index}]"
        spec = _obj(item, field)
        _only(spec, {"id", "pledger", "amount_minor", "period"}, field)
        pledge_id = _text(spec.get("id"), f"{field}.id", max_len=120)
        if pledge_id in pledges:
            raise PoolSpecError(f"{field}.id: duplicate pledge id {pledge_id!r}")
        pledges[pledge_id] = {
            "id": pledge_id,
            "pledger": _text(spec.get("pledger"), f"{field}.pledger", max_len=120),
            "amount_minor": _int(spec.get("amount_minor"), f"{field}.amount_minor", 1,
                                 MAX_AMOUNT_MINOR),
            "period": _int(spec.get("period", 0), f"{field}.period", 0, horizon),
        }

    rules_raw = data.get("rules")
    if not isinstance(rules_raw, list) or not rules_raw:
        raise PoolSpecError("rules: expected a non-empty list")
    if len(rules_raw) > MAX_RULES:
        raise PoolSpecError(f"rules: at most {MAX_RULES}")
    rules: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(rules_raw):
        field = f"rules[{index}]"
        spec = _obj(item, field)
        rule_type = spec.get("type")
        common = {"id", "type", "metric", "release_bps", "earliest_period", "requires_receipt",
                  "description"}
        if rule_type == "milestone":
            _only(spec, common | {"comparator", "threshold"}, field)
        elif rule_type == "outcome_linked":
            _only(spec, common | {"baseline", "target"}, field)
        else:
            raise PoolSpecError(f"{field}.type: expected 'milestone' or 'outcome_linked'")
        rule_id = _text(spec.get("id"), f"{field}.id", max_len=120)
        if rule_id in rules:
            raise PoolSpecError(f"{field}.id: duplicate rule id {rule_id!r}")
        metric = spec.get("metric")
        if metric not in METRICS:
            raise PoolSpecError(f"{field}.metric: expected one of {sorted(METRICS)}")
        rule: dict[str, Any] = {
            "id": rule_id,
            "type": rule_type,
            "metric": metric,
            "release_bps": _int(spec.get("release_bps"), f"{field}.release_bps", 1, 10_000),
            "earliest_period": _int(spec.get("earliest_period", 0), f"{field}.earliest_period",
                                    0, horizon),
            "requires_receipt": _bool(spec.get("requires_receipt", False),
                                      f"{field}.requires_receipt"),
            "description": _text(spec.get("description"), f"{field}.description",
                                 required=False, max_len=500),
        }
        if rule_type == "milestone":
            if spec.get("comparator") not in COMPARATORS:
                raise PoolSpecError(f"{field}.comparator: expected one of {list(COMPARATORS)} "
                                    "(all metrics are better when higher; rules reward improvement only)")
            rule["comparator"] = spec["comparator"]
            rule["threshold"] = _dec(spec.get("threshold"), f"{field}.threshold")
        else:
            rule["baseline"] = _dec(spec.get("baseline"), f"{field}.baseline")
            rule["target"] = _dec(spec.get("target"), f"{field}.target")
            if rule["target"] <= rule["baseline"]:
                raise PoolSpecError(f"{field}: target must exceed baseline "
                                    "(all metrics are better when higher; rules reward improvement only)")
        rules[rule_id] = rule
    total_bps = sum(rule["release_bps"] for rule in rules.values())
    if total_bps > 10_000:
        raise PoolSpecError(f"rules: release_bps sum to {total_bps}; at most 10000 "
                            "(releases may never exceed pledges)")

    site_id = data.get("site_id")
    calendar = None
    if data.get("calendar") is not None:
        cal = _obj(data["calendar"], "calendar")
        _only(cal, {"start", "period_months"}, "calendar")
        try:
            start = date.fromisoformat(_text(cal.get("start"), "calendar.start", max_len=10))
        except ValueError as exc:
            raise PoolSpecError("calendar.start: expected an ISO date YYYY-MM-DD") from exc
        calendar = {"start": start.isoformat(),
                    "period_months": _int(cal.get("period_months"), "calendar.period_months", 1, 120)}
    if any(rule["requires_receipt"] for rule in rules.values()):
        if site_id is None or calendar is None:
            raise PoolSpecError("rules with requires_receipt need the pool's site_id and calendar, so "
                                "receipts cannot be counted for another site or replayed into "
                                "another period")
    return {
        "schema": POOL_SCHEMA,
        "pool_id": _text(data.get("pool_id"), "pool_id", max_len=120),
        "name": _text(data.get("name"), "name", required=False),
        "site_id": _text(site_id, "site_id", max_len=120) if site_id is not None else None,
        "unit": {"code": _text(unit.get("code"), "unit.code", max_len=12),
                 "minor_per_major": _int(unit.get("minor_per_major"), "unit.minor_per_major",
                                         1, 1_000_000)},
        "horizon_periods": horizon,
        "period_label": _text(data.get("period_label", "period"), "period_label", max_len=40),
        "calendar": calendar,
        "pledges": [pledges[key] for key in sorted(pledges)],
        "rules": [rules[key] for key in sorted(rules)],
    }
