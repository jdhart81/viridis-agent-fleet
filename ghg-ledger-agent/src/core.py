"""Deterministic, source-linked greenhouse-gas inventory accounting.

GH1  All mass/CO2e arithmetic is Decimal. CO2e is emitted at 3 dp, HALF_UP.
GH2  Factors are bundled, versioned, source-linked, and content-addressed.
GH3  The GWP-100 profile is explicit; gas mass and CO2e stay distinguishable.
GH4  Scope/category classification is caller-supplied or deterministically mapped.
GH5  Scope 2 location- and market-based results are never collapsed.
GH6  Unknown activity, region/year, or required data fails closed per line.
GH7  Units must match or convert through the bundled deterministic table.
GH8  Canonical inputs, factor lineage, and results form a reproducible audit hash.
GH9  Line, category, scope, and grand totals conserve exactly or fail loud.
"""

from __future__ import annotations

import hashlib
import json
import logging
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Optional


VERSION = "0.1.0"
DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "factor_packs.v0.1.0.json"
_RAW_PACK = DATA_PATH.read_bytes()
PACK = json.loads(_RAW_PACK)
FACTOR_PACK_SHA256 = hashlib.sha256(_RAW_PACK).hexdigest()
KG_QUANTUM = Decimal("0.001")
GAS_QUANTUM = Decimal("0.000001")
TONNE_QUANTUM = Decimal("0.000001")
_DERIVED_AUDIT_FIELDS = {
    # These fields depend on audit_sha256 and therefore cannot be inputs to the
    # same hash. verify_result deterministically rebuilds and compares them.
    "audit_sha256", "notary_payload", "offset_weave",
}


@dataclass
class AgentConfig:
    name: str = "ghg-ledger-agent"
    version: str = VERSION
    debug: bool = False


class ValidationError(ValueError):
    def __init__(self, message: str, field: str = "", value: Any = None,
                 constraint: str = ""):
        super().__init__(message)
        self.field = field
        self.value = value
        self.constraint = constraint


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _decimal(value: Any, field: str, *, minimum: Optional[Decimal] = None) -> Decimal:
    if value is None or isinstance(value, (bool, float)):
        raise ValidationError(
            f"'{field}' must be an integer or decimal string (binary floats are rejected)",
            field, value, "Decimal-compatible string or integer")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValidationError(f"'{field}' must be a finite decimal", field, value,
                              "finite Decimal")
    if not result.is_finite():
        raise ValidationError(f"'{field}' must be finite", field, value, "finite")
    if minimum is not None and result < minimum:
        raise ValidationError(f"'{field}' must be >= {minimum}", field, value,
                              f">= {minimum}")
    return result


def _year(value: Any, field: str = "year") -> int:
    if isinstance(value, bool) or value is None:
        raise ValidationError(f"'{field}' must be an integer year", field, value,
                              "integer")
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text.isdigit():
        raise ValidationError(f"'{field}' must be an integer year", field, value,
                              "integer")
    return int(text)


def _kg(value: Decimal) -> str:
    return format(value.quantize(KG_QUANTUM, rounding=ROUND_HALF_UP), "f")


def _gas_kg(value: Decimal) -> str:
    return format(value.quantize(GAS_QUANTUM, rounding=ROUND_HALF_UP), "f")


def _tonnes(value_kg: Decimal) -> str:
    return format((value_kg / Decimal("1000")).quantize(
        TONNE_QUANTUM, rounding=ROUND_HALF_UP), "f")


def _plain(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _validate_pack() -> None:
    required = {"activity_type", "unit", "region", "year",
                "co2e_or_gas_breakdown", "source_id"}
    source_ids = {source["id"] for source in PACK.get("sources", [])}
    if len(PACK.get("scope3_categories", {})) != 15:
        raise RuntimeError("GH4: factor pack must enumerate all 15 Scope 3 categories")
    for factor_id, factor in PACK.get("factors", {}).items():
        missing = required - set(factor)
        if missing:
            raise RuntimeError(f"GH2: {factor_id} missing {sorted(missing)}")
        unknown_sources = set(factor.get("source_ids", [factor["source_id"]])) - source_ids
        if unknown_sources:
            raise RuntimeError(f"GH2: {factor_id} has unknown sources {unknown_sources}")
        group = factor.get("conversion_group")
        if group not in PACK.get("unit_conversions", {}):
            raise RuntimeError(f"GH7: {factor_id} has unknown conversion group {group}")
        if factor["unit"] not in PACK["unit_conversions"][group]:
            raise RuntimeError(f"GH7: {factor_id} base unit absent from {group}")
    gwp = PACK.get("gwp_profile", {})
    for gas in ("co2", "ch4_fossil", "ch4_non_fossil", "n2o"):
        if gas not in gwp.get("values", {}):
            raise RuntimeError(f"GH3: GWP profile missing {gas}")


_validate_pack()
GWP_PROFILE_SHA256 = _digest(PACK["gwp_profile"])
_SOURCES = {source["id"]: source for source in PACK["sources"]}


class GHGLedgerCore:
    KNOWN_ACTIONS = frozenset({
        "calculate_inventory", "classify_activity", "list_factor_packs",
        "get_factor_pack", "verify_result",
    })
    READ_ACTIONS = frozenset({
        "classify_activity", "list_factor_packs", "get_factor_pack",
        "verify_result",
    })

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self.logger = logging.getLogger(self.config.name)
        self.logger.setLevel(logging.DEBUG if self.config.debug else logging.INFO)

    async def health(self) -> dict:
        return {
            "status": "ok",
            "agent": self.config.name,
            "version": self.config.version,
            "timestamp": _now(),
            "checks": {
                "factor_pack": PACK["pack_version"],
                "factor_pack_sha256": FACTOR_PACK_SHA256,
                "gwp_set": PACK["gwp_profile"]["id"],
                "factors": len(PACK["factors"]),
                "scope3_categories": len(PACK["scope3_categories"]),
            },
        }

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": ("Deterministic Scope 1/2/3 GHG inventories with "
                            "versioned factors, dual Scope 2, and audit hashes."),
            "capabilities": [
                "calculate_inventory", "classify_activity", "list_factor_packs",
                "get_factor_pack", "verify_result",
            ],
            "inputs": {"activities": "array of explicit activity records",
                       "options": "inventory metadata and optional market/offset data"},
            "outputs": {"line_items": "gas-resolved CO2e calculations",
                        "scope_2_dual_reporting": "location + market methods",
                        "audit_sha256": "content digest for notary"},
            "pricing": {"free_calls_per_day": 100, "price_usd_per_call": "1.00",
                        "future_gtm": "B2B monthly seat"},
            "factor_pack": {"version": PACK["pack_version"],
                            "sha256": FACTOR_PACK_SHA256},
            "a2a_role": "ghg-accounting",
        }

    def _err(self, message: str, *, error_type: str = "Error", field: str = "",
             value: Any = None, constraint: str = "") -> dict:
        return {"status": "error", "error_type": error_type, "field": field,
                "value": value, "constraint": constraint, "message": message,
                "timestamp": _now()}

    async def process(self, input_data: dict) -> dict:
        try:
            if not isinstance(input_data, dict):
                raise ValidationError("input must be an object", "input",
                                      type(input_data).__name__, "object")
            action = input_data.get("action")
            if action == "calculate_inventory":
                activities = input_data.get("activities")
                options = input_data.get("options", {})
                if not isinstance(activities, list):
                    raise ValidationError("'activities' must be an array", "activities",
                                          activities, "array")
                if not isinstance(options, dict):
                    raise ValidationError("'options' must be an object", "options",
                                          options, "object")
                return {"status": "ok", "data": self.calculate_inventory(
                    activities, options)}
            if action == "classify_activity":
                activity = input_data.get("activity")
                if not isinstance(activity, dict):
                    raise ValidationError("'activity' must be an object", "activity",
                                          activity, "object")
                return {"status": "ok", "data": self.classify_activity(activity)}
            if action == "list_factor_packs":
                return {"status": "ok", "data": self.list_factor_packs()}
            if action == "get_factor_pack":
                return {"status": "ok", "data": self.get_factor_pack(
                    str(input_data.get("region", "")), _year(input_data.get("year")))}
            if action == "verify_result":
                result = input_data.get("result")
                if not isinstance(result, dict):
                    raise ValidationError("'result' must be an object", "result", result,
                                          "object")
                return {"status": "ok", "data": self.verify_result(result)}
            raise ValidationError(f"unknown action '{action}'", "action", action,
                                  "calculate_inventory|classify_activity|"
                                  "list_factor_packs|get_factor_pack|verify_result")
        except ValidationError as exc:
            return self._err(str(exc), error_type="ValidationError", field=exc.field,
                             value=exc.value, constraint=exc.constraint)
        except Exception as exc:  # fail loud, but preserve fleet envelope
            self.logger.exception("GHG ledger process failed")
            return self._err(f"internal error: {exc}", error_type="RuntimeError")

    def list_factor_packs(self) -> dict:
        factors = PACK["factors"]
        return {
            "schema_version": PACK["schema_version"],
            "version": PACK["pack_version"],
            "effective_as_of": PACK["effective_as_of"],
            "sha256": FACTOR_PACK_SHA256,
            "gwp_set": {**deepcopy(PACK["gwp_profile"]),
                        "sha256": GWP_PROFILE_SHA256},
            "regions": sorted({factor["region"] for factor in factors.values()}),
            "years": sorted({factor["year"] for factor in factors.values()}),
            "activity_types": sorted({factor["activity_type"]
                                      for factor in factors.values()}),
            "factor_count": len(factors),
            "disclaimer": PACK["disclaimer"],
        }

    def get_factor_pack(self, region: str, year: int) -> dict:
        selected = {factor_id: deepcopy(factor)
                    for factor_id, factor in PACK["factors"].items()
                    if factor["region"] == region and factor["year"] == year}
        if not selected:
            raise ValidationError(
                f"factor not in pack {PACK['pack_version']} for region={region}, year={year}",
                "region/year", {"region": region, "year": year},
                "exact bundled region and year")
        source_ids = {
            source_id
            for factor in selected.values()
            for source_id in (factor.get("source_ids") or [factor["source_id"]])
        }
        # The returned pack includes the explicit GWP profile; include its
        # source record too so a caller never receives an unresolved lineage ID.
        source_ids.add(PACK["gwp_profile"]["source_id"])
        return {
            "region": region, "year": year,
            "factor_pack": {"version": PACK["pack_version"],
                            "sha256": FACTOR_PACK_SHA256,
                            "effective_as_of": PACK["effective_as_of"]},
            "gwp_set": {**deepcopy(PACK["gwp_profile"]),
                        "sha256": GWP_PROFILE_SHA256},
            "unit_conversions": deepcopy(PACK["unit_conversions"]),
            "factors": selected,
            "sources": [deepcopy(_SOURCES[source_id])
                        for source_id in sorted(source_ids)],
            "disclaimer": PACK["disclaimer"],
        }

    def classify_activity(self, activity: dict) -> dict:
        activity_type = str(activity.get("activity_type", ""))
        mapped = PACK["classification_map"].get(activity_type)
        if not mapped:
            return {
                "supported": False, "activity_type": activity_type,
                "suggestion": None,
                "reason": f"activity_type not in classification map v{PACK['pack_version']}",
                "scope3_categories": deepcopy(PACK["scope3_categories"]),
                "method": "deterministic_mapping_no_match",
            }
        return {
            "supported": True, "activity_type": activity_type,
            "suggestion": deepcopy(mapped),
            "method": "deterministic_mapping",
            "mapping_version": PACK["pack_version"],
            "scope3_categories": deepcopy(PACK["scope3_categories"]),
        }

    @staticmethod
    def _normalize_scope(value: Any) -> Optional[str]:
        aliases = {1: "scope_1", 2: "scope_2", 3: "scope_3",
                   "1": "scope_1", "2": "scope_2", "3": "scope_3",
                   "scope1": "scope_1", "scope2": "scope_2",
                   "scope3": "scope_3", "scope_1": "scope_1",
                   "scope_2": "scope_2", "scope_3": "scope_3"}
        return aliases.get(value)

    @staticmethod
    def _enforce_applicability(activity: dict, factor: dict) -> None:
        applicability = factor.get("applicability")
        if not isinstance(applicability, dict):
            return
        requirements = applicability.get("requires") or {}
        for field, expected in requirements.items():
            supplied = activity.get(field)
            if supplied != expected:
                raise ValidationError(
                    f"factor applicability requires {field}={expected!r}; "
                    f"coverage outside {applicability.get('id', 'this factor')} is "
                    f"not in pack {PACK['pack_version']}",
                    field, supplied, f"exact value {expected!r}")

    def _classification(self, activity: dict, factor: dict) -> dict:
        mapped = PACK["classification_map"].get(factor["activity_type"])
        caller_supplied = "scope" in activity and activity.get("scope") is not None
        if caller_supplied:
            scope = self._normalize_scope(activity.get("scope"))
            if not scope:
                raise ValidationError("invalid scope", "scope", activity.get("scope"),
                                      "scope_1|scope_2|scope_3")
            category_from_caller = bool(activity.get("category"))
            category = (activity.get("category") if category_from_caller
                        else factor["category"])
            scope3_from_caller = bool(activity.get("scope3_category"))
            scope3 = (activity.get("scope3_category")
                      if scope3_from_caller else None)
            if scope == "scope_3" and not scope3:
                scope3 = (mapped or {}).get("scope3_category")
            field_sources = {
                "scope": "caller_supplied",
                "category": ("caller_supplied" if category_from_caller
                             else "factor_pack"),
                "scope3_category": (
                    "caller_supplied" if scope3_from_caller
                    else "deterministic_mapping" if scope == "scope_3"
                    else "not_applicable"),
            }
            required_sources = [field_sources["scope"], field_sources["category"]]
            if scope == "scope_3":
                required_sources.append(field_sources["scope3_category"])
            method = ("caller_supplied" if all(
                source == "caller_supplied" for source in required_sources)
                else "mixed_caller_and_bundled_mapping")
        else:
            if not mapped:
                raise ValidationError("activity has no deterministic classification",
                                      "activity_type", factor["activity_type"],
                                      "caller scope/category required")
            scope, category, scope3 = (mapped["scope"], mapped["category"],
                                       mapped["scope3_category"])
            method = "deterministic_mapping"
            field_sources = {
                "scope": "deterministic_mapping",
                "category": "deterministic_mapping",
                "scope3_category": ("deterministic_mapping"
                                    if scope == "scope_3" else "not_applicable"),
            }
        if scope != factor["scope"]:
            raise ValidationError("supplied scope conflicts with bundled factor",
                                  "scope", scope, factor["scope"])
        if scope == "scope_3" and scope3 not in PACK["scope3_categories"]:
            raise ValidationError("invalid or missing Scope 3 category",
                                  "scope3_category", scope3,
                                  "one of the 15 bundled GHG Protocol categories")
        return {"scope": scope, "category": str(category),
                "scope3_category": scope3, "method": method,
                "field_sources": field_sources}

    def _find_factor(self, activity: dict) -> tuple[str, dict]:
        required = ("activity_type", "region", "year")
        missing = [field for field in required
                   if field not in activity or activity[field] in (None, "")]
        if missing:
            raise ValidationError(f"missing required field(s): {', '.join(missing)}",
                                  missing[0], None, "required")
        activity_type = str(activity["activity_type"])
        region = str(activity["region"])
        year = _year(activity["year"])
        factor_id = activity.get("factor_id")
        if factor_id:
            factor = PACK["factors"].get(str(factor_id))
            if not factor:
                raise ValidationError(
                    f"factor not in pack {PACK['pack_version']}: {factor_id}",
                    "factor_id", factor_id, "bundled factor id")
            if (factor["activity_type"], factor["region"], factor["year"]) != (
                    activity_type, region, year):
                raise ValidationError("factor_id conflicts with activity type/region/year",
                                      "factor_id", factor_id,
                                      "exact factor lineage match")
            self._enforce_applicability(activity, factor)
            return str(factor_id), factor
        matches = [(fid, factor) for fid, factor in PACK["factors"].items()
                   if factor["activity_type"] == activity_type
                   and factor["region"] == region and factor["year"] == year]
        if not matches:
            raise ValidationError(
                f"factor not in pack {PACK['pack_version']} for activity_type="
                f"{activity_type}, region={region}, year={year}",
                "activity_type/region/year",
                {"activity_type": activity_type, "region": region, "year": year},
                "exact bundled factor; nearest-year substitution is forbidden")
        if len(matches) != 1:
            raise ValidationError("multiple factors match; factor_id is required",
                                  "factor_id", None, "one exact bundled factor")
        factor_id, factor = matches[0]
        self._enforce_applicability(activity, factor)
        return factor_id, factor

    @staticmethod
    def _convert(quantity: Decimal, from_unit: str, to_unit: str,
                 preferred_group: Optional[str] = None) -> tuple[Decimal, str]:
        groups = PACK["unit_conversions"]
        order = ([preferred_group] if preferred_group else []) + [
            group for group in groups if group != preferred_group]
        for group in order:
            table = groups.get(group, {})
            if from_unit in table and to_unit in table:
                converted = quantity * Decimal(table[from_unit]) / Decimal(table[to_unit])
                return converted, group
        raise ValidationError(f"no bundled conversion from {from_unit} to {to_unit}",
                              "unit", from_unit, f"convertible to {to_unit}")

    @staticmethod
    def _mass_factor_to_kg(mass_unit: str) -> Decimal:
        table = PACK["unit_conversions"]["mass_kg"]
        if mass_unit not in table:
            raise ValidationError("unknown factor mass unit", "mass_unit", mass_unit,
                                  "bundled mass conversion")
        return Decimal(table[mass_unit])

    def _factor_math(self, factor: dict, quantity_in_factor_unit: Decimal) -> tuple[Decimal, dict, dict]:
        definition = factor["co2e_or_gas_breakdown"]
        kind = definition.get("kind")
        if kind == "gas_breakdown":
            raw_masses: dict[str, Decimal] = {}
            contributions: dict[str, Decimal] = {}
            gases = {}
            for gas, per_unit in definition.get("kg_per_unit", {}).items():
                if gas not in PACK["gwp_profile"]["values"]:
                    raise RuntimeError(f"GH3: no GWP for gas {gas}")
                mass = quantity_in_factor_unit * Decimal(per_unit)
                contribution = mass * Decimal(PACK["gwp_profile"]["values"][gas])
                raw_masses[gas] = mass
                contributions[gas] = contribution
                gases[gas] = {"kg_gas": _gas_kg(mass),
                              "gwp100": PACK["gwp_profile"]["values"][gas],
                              "kg_co2e": _kg(contribution)}
            total = sum(contributions.values(), Decimal("0"))
            breakdown = {"resolution": ("gas_resolved_partial"
                                         if definition.get("coverage_note")
                                         else "gas_resolved"), "gases": gases,
                         "direct_co2e": None}
            if definition.get("coverage_note"):
                breakdown["coverage_note"] = definition["coverage_note"]
            return total, breakdown, contributions
        if kind == "direct_co2e":
            mass_factor = self._mass_factor_to_kg(str(definition.get("mass_unit", "kg")))
            total = quantity_in_factor_unit * Decimal(definition["value"]) * mass_factor
            breakdown = {
                "resolution": "direct_co2e_only",
                "gases": {},
                "direct_co2e": {"kg_co2e": _kg(total),
                                 "gas_masses_available": False},
            }
            if definition.get("coverage_note"):
                breakdown["coverage_note"] = definition["coverage_note"]
            return total, breakdown, {"direct_co2e": total}
        raise RuntimeError(f"GH2: unsupported factor kind {kind}")

    @staticmethod
    def _apportion_output_contributions(
            contributions: dict[str, Decimal], line_total: Decimal,
            breakdown: dict) -> dict[str, Decimal]:
        """Round one line once while keeping its displayed components exact.

        Largest-remainder apportionment converts raw contributions to 0.001 kg
        output units whose sum is exactly the already-rounded line total. This
        avoids independently rounding every gas and then drifting at rollup.
        """
        if not contributions:
            return {}
        unit = KG_QUANTUM
        base_units = {
            gas: int((value / unit).to_integral_value(rounding=ROUND_FLOOR))
            for gas, value in contributions.items()
        }
        target_units = int(line_total / unit)
        remaining = target_units - sum(base_units.values())
        if remaining < 0 or remaining > len(base_units):
            raise AssertionError("GH9 output apportionment is outside its exact bounds")
        order = sorted(
            contributions,
            key=lambda gas: (
                -((contributions[gas] / unit) - Decimal(base_units[gas])), gas))
        for gas in order[:remaining]:
            base_units[gas] += 1
        displayed = {gas: Decimal(units) * unit
                     for gas, units in base_units.items()}
        if sum(displayed.values(), Decimal("0")) != line_total:
            raise AssertionError("GH9 line component apportionment drift")

        gases = breakdown.get("gases") or {}
        for gas, value in displayed.items():
            if gas in gases:
                gases[gas]["kg_co2e"] = _kg(value)
        direct = breakdown.get("direct_co2e")
        if isinstance(direct, dict) and "direct_co2e" in displayed:
            direct["kg_co2e"] = _kg(displayed["direct_co2e"])
        breakdown["output_rounding"] = {
            "precision_kg_co2e": "0.001",
            "mode": "ROUND_HALF_UP",
            "component_allocation": "largest_remainder",
        }
        return displayed

    def _market_factor(self, activity: dict, options: dict, line_id: str) -> Optional[dict]:
        direct = activity.get("market_factor")
        mapped = (options.get("market_based_factors") or {}).get(line_id) \
            if isinstance(options.get("market_based_factors", {}), dict) else None
        selected = direct if direct is not None else mapped
        if selected is None:
            return None
        if not isinstance(selected, dict):
            raise ValidationError("market_factor must be an object", "market_factor",
                                  selected, "object")
        for field in ("kg_co2e_per_unit", "unit", "source"):
            if field not in selected or selected[field] in (None, ""):
                raise ValidationError(f"market_factor missing '{field}'",
                                      f"market_factor.{field}", None, "required")
        return selected

    def _calculate_line(self, activity: dict, options: dict, index: int) -> tuple[dict, dict]:
        line_id = str(activity.get("id") or f"line-{index + 1:04d}")
        factor_id, factor = self._find_factor(activity)
        if "quantity" not in activity:
            raise ValidationError("missing required field: quantity", "quantity", None,
                                  "required")
        if "unit" not in activity or not activity.get("unit"):
            raise ValidationError("missing required field: unit", "unit", None, "required")
        quantity = _decimal(activity["quantity"], "quantity", minimum=Decimal("0"))
        input_unit = str(activity["unit"])
        converted, conversion_group = self._convert(
            quantity, input_unit, factor["unit"], factor["conversion_group"])
        classification = self._classification(activity, factor)
        raw_total, breakdown, contributions = self._factor_math(factor, converted)
        line_total = Decimal(_kg(raw_total))
        contributions = self._apportion_output_contributions(
            contributions, line_total, breakdown)
        source_ids = set(factor.get("source_ids") or [factor["source_id"]])
        if breakdown["resolution"].startswith("gas_resolved"):
            source_ids.add(PACK["gwp_profile"]["source_id"])
        line = {
            "id": line_id,
            "status": "determinate",
            "activity_type": factor["activity_type"],
            "input": {"quantity": str(activity["quantity"]), "unit": input_unit,
                      "region": factor["region"], "year": factor["year"]},
            "classification": classification,
            "factor": {"id": factor_id, "activity_type": factor["activity_type"],
                       "unit": factor["unit"], "region": factor["region"],
                       "year": factor["year"], "source_id": factor["source_id"],
                       "source_ids": sorted(source_ids),
                       "applicability": deepcopy(factor.get("applicability"))},
            "unit_conversion": {"group": conversion_group,
                                "quantity_in_factor_unit": _plain(converted),
                                "factor_unit": factor["unit"]},
            "gas_breakdown": breakdown,
            "kg_co2e": _kg(line_total),
        }
        market_internal = None
        if classification["scope"] == "scope_2":
            try:
                market = self._market_factor(activity, options, line_id)
                if market is None:
                    line["scope_2"] = {
                        "location_based_kg_co2e": _kg(line_total),
                        "market_based_kg_co2e": None,
                        "market_based_status": "indeterminate_not_supplied",
                        "market_based_reason": ("supplier/REC/residual-mix factor was "
                                                "not supplied; location value is not reused"),
                    }
                else:
                    market_value = _decimal(market["kg_co2e_per_unit"],
                                            "market_factor.kg_co2e_per_unit",
                                            minimum=Decimal("0"))
                    market_quantity, market_group = self._convert(
                        quantity, input_unit, str(market["unit"]),
                        factor["conversion_group"])
                    market_internal = Decimal(_kg(market_quantity * market_value))
                    line["scope_2"] = {
                        "location_based_kg_co2e": _kg(line_total),
                        "market_based_kg_co2e": _kg(market_internal),
                        "market_based_status": "determinate_supplied_factor",
                        "market_factor": {"kg_co2e_per_unit": str(market["kg_co2e_per_unit"]),
                                          "unit": str(market["unit"]),
                                          "source": str(market["source"]),
                                          "conversion_group": market_group},
                    }
            except ValidationError as exc:
                line["scope_2"] = {
                    "location_based_kg_co2e": _kg(line_total),
                    "market_based_kg_co2e": None,
                    "market_based_status": "indeterminate_invalid_factor",
                    "market_based_reason": str(exc),
                }
        return line, {"line_total": line_total, "contributions": contributions,
                      "market_total": market_internal,
                      "source_ids": sorted(source_ids),
                      "factor_id": factor_id}

    def calculate_inventory(self, activities: list, options: dict) -> dict:
        inputs = {"activities": deepcopy(activities), "options": deepcopy(options)}
        lines: list[dict] = []
        indeterminate: list[dict] = []
        scope_values = {"scope_1": Decimal("0"), "scope_2": Decimal("0"),
                        "scope_3": Decimal("0")}
        category_values = {"scope_1": {}, "scope_2": {},
                           "scope_3": {key: Decimal("0")
                                       for key in PACK["scope3_categories"]}}
        gas_values: dict[str, Decimal] = {}
        market_values: list[Decimal] = []
        market_indeterminate: list[dict] = []
        source_ids: set[str] = set()
        factor_ids: list[str] = []
        regions: set[str] = set()
        years: set[int] = set()

        for index, activity in enumerate(activities):
            line_id = (str(activity.get("id") or f"line-{index + 1:04d}")
                       if isinstance(activity, dict) else f"line-{index + 1:04d}")
            if not isinstance(activity, dict):
                failure = {"id": line_id, "status": "indeterminate",
                           "reason": "activity must be an object", "activity": activity}
                lines.append(failure)
                indeterminate.append(failure)
                continue
            try:
                line, internal = self._calculate_line(activity, options, index)
            except (ValidationError, RuntimeError) as exc:
                failure = {"id": line_id, "status": "indeterminate",
                           "activity_type": activity.get("activity_type"),
                           "reason": str(exc), "excluded_from_totals": True}
                lines.append(failure)
                indeterminate.append(failure)
                continue
            lines.append(line)
            scope = line["classification"]["scope"]
            amount = internal["line_total"]
            scope_values[scope] += amount
            category_key = (line["classification"]["scope3_category"]
                            if scope == "scope_3" else line["classification"]["category"])
            category_values[scope].setdefault(category_key, Decimal("0"))
            category_values[scope][category_key] += amount
            for gas, contribution in internal["contributions"].items():
                gas_values[gas] = gas_values.get(gas, Decimal("0")) + contribution
            if scope == "scope_2":
                if internal["market_total"] is None:
                    market_indeterminate.append({"id": line["id"],
                                                 "reason": line["scope_2"]["market_based_reason"]})
                else:
                    market_values.append(internal["market_total"])
            source_ids.update(internal["source_ids"])
            factor_ids.append(internal["factor_id"])
            regions.add(line["factor"]["region"])
            years.add(line["factor"]["year"])

        scope1 = sum((Decimal(line["kg_co2e"]) for line in lines
                      if line.get("status") == "determinate"
                      and line["classification"]["scope"] == "scope_1"), Decimal("0"))
        scope2_location = sum((Decimal(line["kg_co2e"]) for line in lines
                               if line.get("status") == "determinate"
                               and line["classification"]["scope"] == "scope_2"), Decimal("0"))
        scope3 = sum((Decimal(line["kg_co2e"]) for line in lines
                      if line.get("status") == "determinate"
                      and line["classification"]["scope"] == "scope_3"), Decimal("0"))
        location_grand = scope1 + scope2_location + scope3
        has_scope2 = any(line.get("status") == "determinate"
                         and line["classification"]["scope"] == "scope_2"
                         for line in lines)
        market_complete = not market_indeterminate
        scope2_market = sum(market_values, Decimal("0")) if market_complete else None
        market_grand = (scope1 + scope3 + scope2_market
                        if scope2_market is not None else None)
        determinate_count = sum(1 for line in lines if line.get("status") == "determinate")
        status = ("complete_for_supplied_activities" if not indeterminate
                  else "indeterminate" if not determinate_count else "partial_indeterminate")
        mass_g = int(location_grand * Decimal("1000"))

        scope_totals = {
            "scope_1": _kg(scope1),
            "scope_2_location_based": _kg(scope2_location),
            "scope_2_market_based": _kg(scope2_market) if scope2_market is not None else None,
            "scope_3": _kg(scope3),
        }
        category_rollups = {
            scope: {key: _kg(value) for key, value in sorted(values.items())}
            for scope, values in category_values.items()
        }
        grand_total = {
            "kg_co2e": _kg(location_grand),
            "mass_g": mass_g,
            "location_based_kg_co2e": _kg(location_grand),
            "market_based_kg_co2e": (_kg(market_grand)
                                      if market_grand is not None else None),
            "determinate_line_count": determinate_count,
            "indeterminate_line_count": len(indeterminate),
            "coverage_complete": not indeterminate,
        }
        factor_refs = [{"id": factor_id,
                        "region": PACK["factors"][factor_id]["region"],
                        "year": PACK["factors"][factor_id]["year"]}
                       for factor_id in sorted(set(factor_ids))]
        input_sha = _digest(inputs)
        lineage = {
            "producer": {"agent_id": self.config.name, "version": self.config.version},
            "input_sha256": input_sha,
            "factor_pack": {"version": PACK["pack_version"],
                            "sha256": FACTOR_PACK_SHA256,
                            "regions": sorted(regions), "years": sorted(years),
                            "factors": factor_refs},
            "gwp_set": {"id": PACK["gwp_profile"]["id"],
                        "sha256": GWP_PROFILE_SHA256,
                        "source_id": PACK["gwp_profile"]["source_id"]},
            "source_ids_used": sorted(source_ids),
        }
        result = {
            "inventory_status": status,
            "organization_id": options.get("organization_id"),
            "reporting_period": options.get("reporting_period"),
            "organizational_boundary": options.get("organizational_boundary"),
            "inputs": inputs,
            "input_sha256": input_sha,
            "line_items": lines,
            "indeterminate": indeterminate,
            "gas_breakdown_kg_co2e": {gas: _kg(value)
                                       for gas, value in sorted(gas_values.items())},
            "scope_totals_kg_co2e": scope_totals,
            "category_rollups_kg_co2e": category_rollups,
            "scope_2_dual_reporting": {
                "location_based_kg_co2e": _kg(scope2_location),
                "market_based_kg_co2e": (_kg(scope2_market)
                                          if scope2_market is not None else None),
                "market_based_status": ("not_applicable" if not has_scope2
                                        else "complete" if market_complete
                                        else "indeterminate"),
                "indeterminate": market_indeterminate,
            },
            "grand_total": grand_total,
            "esrs_e1": {
                "unit": "metric_tonnes_co2e",
                "gross_scope_1": _tonnes(scope1),
                "gross_scope_2_location_based": _tonnes(scope2_location),
                "gross_scope_2_market_based": (_tonnes(scope2_market)
                                                if scope2_market is not None else None),
                "gross_scope_3": _tonnes(scope3),
                "total_location_based": _tonnes(location_grand),
                "total_market_based": (_tonnes(market_grand)
                                       if market_grand is not None else None),
                "shape_only_not_filing_advice": True,
            },
            "factor_pack": {
                "version": PACK["pack_version"],
                "effective_as_of": PACK["effective_as_of"],
                "sha256": FACTOR_PACK_SHA256,
                "gwp_set_id": PACK["gwp_profile"]["id"],
                "gwp_set_sha256": GWP_PROFILE_SHA256,
                "sources_used": [deepcopy(_SOURCES[source_id])
                                 for source_id in sorted(source_ids)],
            },
            "lineage": lineage,
            "disclaimer": PACK["disclaimer"],
        }
        self.assert_conservation(result)
        result["audit_sha256"] = _digest(result)
        inventory_id = "ghg-" + result["audit_sha256"][:24]
        result["notary_payload"] = self._notary_payload(
            result["audit_sha256"], inventory_id)
        result["offset_weave"] = self._offset_weave(result, options, inventory_id)
        return result

    @staticmethod
    def _notary_payload(audit_sha256: str, inventory_id: str) -> dict:
        return {
            "content_digest": audit_sha256,
            "context": f"ghg-ledger:inventory:{inventory_id}",
            "digest_algorithm": "sha256",
        }

    def _offset_weave(self, result: dict, options: dict, inventory_id: str) -> dict:
        buyer = options.get("offset_buyer")
        mass_g = result["grand_total"]["mass_g"]
        ready = isinstance(buyer, str) and bool(buyer.strip()) and mass_g > 0
        purchase_id = None
        if ready:
            supplied = options.get("offset_purchase_id")
            if supplied is not None:
                if not isinstance(supplied, str) or not supplied.strip():
                    raise ValidationError(
                        "'options.offset_purchase_id' must be a non-empty string",
                        "options.offset_purchase_id", type(supplied).__name__,
                        "non-empty string")
                purchase_id = supplied
            else:
                purchase_id = "ghg-" + hashlib.sha256(
                    f"{buyer}:{result['audit_sha256']}".encode()).hexdigest()[:24]
        coverage_complete = result["grand_total"]["coverage_complete"]
        required = [] if isinstance(buyer, str) and buyer.strip() else ["options.offset_buyer"]
        warnings = []
        if not coverage_complete:
            warnings.append("indeterminate activities are excluded; dry-run is determinate subtotal only")
        if mass_g == 0:
            warnings.append("grand total is zero; offset purchase is not ready")
        return {
            "target": "agent-offset-clearinghouse-agent.buy_offset",
            "dry_run_ready": ready,
            "commit_ready": ready and coverage_complete,
            "basis": ("complete_inventory" if coverage_complete
                      else "determinate_subtotal_only"),
            "buy_offset_args": ({"buyer": buyer, "purchase_id": purchase_id,
                                 "mass_g": mass_g, "dry_run": True}
                                if ready else None),
            "net_position_args": ({"buyer": buyer, "emitted_g": mass_g}
                                  if ready else None),
            "required_inputs": required,
            "source": {"audit_sha256": result["audit_sha256"],
                       # Bind the weave to the pack recorded in this audited
                       # result. Historical results must remain verifiable
                       # after the process loads a newer current pack.
                       "factor_pack_sha256": result["factor_pack"]["sha256"],
                       "mass_source": "grand_total.mass_g",
                       "conversion": "kg_co2e * 1000"},
            "warnings": warnings,
            "inventory_id": inventory_id,
        }

    @staticmethod
    def assert_conservation(result: dict) -> None:
        determinate = [line for line in result.get("line_items", [])
                       if line.get("status") == "determinate"]
        line_sum = sum((Decimal(line["kg_co2e"]) for line in determinate), Decimal("0"))
        scopes = result["scope_totals_kg_co2e"]
        scope_sum = (Decimal(scopes["scope_1"])
                     + Decimal(scopes["scope_2_location_based"])
                     + Decimal(scopes["scope_3"]))
        grand = Decimal(result["grand_total"]["kg_co2e"])
        category_sum = sum(
            (Decimal(value) for values in result["category_rollups_kg_co2e"].values()
             for value in values.values()), Decimal("0"))
        if not (line_sum == scope_sum == grand == category_sum):
            raise AssertionError(
                f"GH9 conservation drift: lines={line_sum}, scopes={scope_sum}, "
                f"categories={category_sum}, grand={grand}")
        for line in determinate:
            breakdown = line.get("gas_breakdown") or {}
            component_sum = sum(
                (Decimal(gas["kg_co2e"])
                 for gas in (breakdown.get("gases") or {}).values()),
                Decimal("0"))
            direct = breakdown.get("direct_co2e")
            if isinstance(direct, dict):
                component_sum += Decimal(direct["kg_co2e"])
            if component_sum != Decimal(line["kg_co2e"]):
                raise AssertionError(
                    f"GH9 line gas-component drift for {line.get('id')}: "
                    f"components={component_sum}, line={line['kg_co2e']}")
        gas_rollup_sum = sum(
            (Decimal(value)
             for value in result.get("gas_breakdown_kg_co2e", {}).values()),
            Decimal("0"))
        if gas_rollup_sum != grand:
            raise AssertionError(
                f"GH9 gas rollup drift: gases={gas_rollup_sum}, grand={grand}")
        if result["grand_total"]["mass_g"] != int(grand * Decimal("1000")):
            raise AssertionError("GH9 mass_g drift")
        dual = result["scope_2_dual_reporting"]
        if dual["market_based_status"] in {"complete", "not_applicable"}:
            market_line_sum = sum(
                (Decimal(line["scope_2"]["market_based_kg_co2e"])
                 for line in determinate
                 if line["classification"]["scope"] == "scope_2"), Decimal("0"))
            market_scope = Decimal(scopes["scope_2_market_based"] or "0")
            if market_line_sum != market_scope:
                raise AssertionError("GH9 market-based Scope 2 drift")
            market_grand = result["grand_total"]["market_based_kg_co2e"]
            if market_grand is not None:
                expected = Decimal(scopes["scope_1"]) + Decimal(scopes["scope_3"]) + market_scope
                if Decimal(market_grand) != expected:
                    raise AssertionError("GH9 market-based grand-total drift")

    def verify_result(self, result: dict) -> dict:
        supplied = str(result.get("audit_sha256", ""))
        content = deepcopy(result)
        for field in _DERIVED_AUDIT_FIELDS:
            content.pop(field, None)
        computed = _digest(content)
        try:
            self.assert_conservation(result)
            conservation_valid = True
            conservation_error = None
        except (AssertionError, KeyError, InvalidOperation, TypeError) as exc:
            conservation_valid = False
            conservation_error = str(exc)
        inventory_id = "ghg-" + supplied[:24]
        expected_notary = self._notary_payload(supplied, inventory_id)
        notary_payload_valid = result.get("notary_payload") == expected_notary
        offset_error = None
        try:
            inputs = result.get("inputs")
            if not isinstance(inputs, dict) or not isinstance(inputs.get("options"), dict):
                raise ValidationError("audited inputs.options is missing or invalid")
            expected_offset = self._offset_weave(
                result, inputs["options"], inventory_id)
            offset_weave_valid = result.get("offset_weave") == expected_offset
        except (ValidationError, KeyError, TypeError, InvalidOperation) as exc:
            offset_weave_valid = False
            offset_error = str(exc)
        derived_payloads_valid = notary_payload_valid and offset_weave_valid
        return {
            "valid": (bool(supplied) and supplied == computed
                      and conservation_valid and derived_payloads_valid),
            "audit_hash_valid": bool(supplied) and supplied == computed,
            "conservation_valid": conservation_valid,
            "conservation_error": conservation_error,
            "derived_payloads_valid": derived_payloads_valid,
            "notary_payload_valid": notary_payload_valid,
            "offset_weave_valid": offset_weave_valid,
            "offset_weave_error": offset_error,
            "supplied_sha256": supplied,
            "computed_sha256": computed,
            "factor_pack_current": (result.get("factor_pack", {}).get("sha256")
                                    == FACTOR_PACK_SHA256),
            "current_factor_pack_sha256": FACTOR_PACK_SHA256,
        }


def build(config: Optional[AgentConfig] = None) -> GHGLedgerCore:
    return GHGLedgerCore(config)
