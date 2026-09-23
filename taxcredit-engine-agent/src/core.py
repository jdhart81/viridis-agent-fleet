"""Deterministic US clean-energy tax-credit scenario engine.

The engine deliberately separates arithmetic from tax judgment. It calculates
only when every modeled eligibility fact is explicit; omitted facts produce an
``indeterminate`` scenario, never an optimistic eligibility assumption.

TC1  Money uses Decimal throughout and is rounded once, to cents, HALF_UP.
TC2  45V tier boundaries are exact and require external GREET evidence.
TC3  45Q applies date/path/DAC/PWA rates and annual capture thresholds.
TC4  45Y/48E coordination and eligibility gates fail closed.
TC5  45X uses component-specific rates and category-specific phaseouts.
TC6  Missing modeled facts return indeterminate, not eligible.
TC7  Every result is content-addressed and independently verifiable.
TC8  Bad input never escapes process(); version/health/describe agree.
TC9  Every calculation carries the versioned official-source rule pack.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


VERSION = "0.1.0"
DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "rule_packs.v0.1.0.json"
_RAW_RULES = DATA_PATH.read_bytes()
RULES = json.loads(_RAW_RULES)
RULE_PACK_SHA256 = hashlib.sha256(_RAW_RULES).hexdigest()
CENT = Decimal("0.01")


@dataclass
class AgentConfig:
    name: str = "taxcredit-engine-agent"
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
    if isinstance(value, bool) or value is None:
        raise ValidationError(f"'{field}' must be a decimal number", field, value,
                              "decimal")
    try:
        if isinstance(value, float) and not math.isfinite(value):
            raise InvalidOperation
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValidationError(f"'{field}' must be a finite decimal number", field,
                              value, "finite decimal")
    if not result.is_finite():
        raise ValidationError(f"'{field}' must be finite", field, value, "finite")
    if minimum is not None and result < minimum:
        raise ValidationError(f"'{field}' must be >= {minimum}", field, value,
                              f">= {minimum}")
    return result


def _year(value: Any) -> int:
    if isinstance(value, bool):
        raise ValidationError("'tax_year' must be an integer", "tax_year", value,
                              "integer year")
    try:
        year = int(value)
    except (TypeError, ValueError):
        raise ValidationError("'tax_year' must be an integer", "tax_year", value,
                              "integer year")
    if str(year) != str(value).strip() and not isinstance(value, int):
        raise ValidationError("'tax_year' must be an integer", "tax_year", value,
                              "integer year")
    return year


def _date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValidationError(f"'{field}' must be YYYY-MM-DD", field, value,
                              "ISO date")


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"'{field}' must be true or false", field, value,
                              "boolean")
    return value


def _money(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), "f")


def _plain(value: Decimal) -> str:
    return format(value.normalize(), "f")


class TaxCreditEngineCore:
    KNOWN_ACTIONS = frozenset({
        "calculate", "list_rule_packs", "get_rule_pack", "verify_result",
    })
    READ_ACTIONS = frozenset({
        "list_rule_packs", "get_rule_pack", "verify_result",
    })

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self.logger = logging.getLogger(self.config.name)
        self.logger.setLevel(logging.DEBUG if self.config.debug else logging.INFO)

    async def health(self) -> dict:
        return {"status": "ok", "agent": self.config.name,
                "version": self.config.version, "timestamp": _now(),
                "checks": {"rule_pack": RULES["pack_version"],
                           "rule_pack_sha256": RULE_PACK_SHA256,
                           "credits": len(RULES["rule_packs"])}}

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": ("Deterministic, auditable scenario estimates for US "
                            "clean-energy credits 45Q, 45V, 45Y, 48E, and 45X."),
            "capabilities": ["calculate", "list_rule_packs", "get_rule_pack",
                             "verify_result"],
            "inputs": {"credit": "45Q|45V|45Y|48E|45X",
                       "facts": "credit-specific explicit facts"},
            "outputs": {"calculation_status": "eligible|ineligible|indeterminate",
                        "credit_amount_usd": "decimal string or null",
                        "audit_sha256": "content digest for notary"},
            "pricing": {"free_calls_per_day": 100, "price_usd_per_call": "2.00"},
            "a2a_role": "clean-energy-tax-credit-calculation",
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
            if action == "calculate":
                facts = input_data.get("facts")
                if not isinstance(facts, dict):
                    raise ValidationError("'facts' must be an object", "facts", facts,
                                          "object")
                return {"status": "ok", "data": self.calculate(
                    str(input_data.get("credit", "")).upper(), facts)}
            if action == "list_rule_packs":
                return {"status": "ok", "data": self.list_rule_packs()}
            if action == "get_rule_pack":
                return {"status": "ok", "data": self.get_rule_pack(
                    str(input_data.get("credit", "")).upper())}
            if action == "verify_result":
                result = input_data.get("result")
                if not isinstance(result, dict):
                    raise ValidationError("'result' must be an object", "result", result,
                                          "object")
                return {"status": "ok", "data": self.verify_result(result)}
            raise ValidationError(f"unknown action '{action}'", "action", action,
                                  "calculate|list_rule_packs|get_rule_pack|verify_result")
        except ValidationError as exc:
            return self._err(str(exc), error_type="ValidationError", field=exc.field,
                             value=exc.value, constraint=exc.constraint)
        except Exception as exc:  # TC8
            self.logger.exception("tax-credit process failed")
            return self._err(f"internal error: {exc}", error_type="RuntimeError")

    def list_rule_packs(self) -> dict:
        return {"schema_version": RULES["schema_version"],
                "pack_version": RULES["pack_version"],
                "effective_as_of": RULES["effective_as_of"],
                "rule_pack_sha256": RULE_PACK_SHA256,
                "credits": sorted(RULES["rule_packs"]),
                "disclaimer": RULES["disclaimer"]}

    def get_rule_pack(self, credit: str) -> dict:
        if credit not in RULES["rule_packs"]:
            raise ValidationError("unsupported credit", "credit", credit,
                                  "45Q|45V|45Y|48E|45X")
        ids = RULES["rule_packs"][credit]["source_ids"]
        sources = [s for s in RULES["sources"] if s["id"] in ids]
        return {"credit": credit, "pack_version": RULES["pack_version"],
                "rule_pack_sha256": RULE_PACK_SHA256,
                "rules": deepcopy(RULES["rule_packs"][credit]),
                "sources": sources, "disclaimer": RULES["disclaimer"]}

    @staticmethod
    def _missing(facts: dict, fields: Iterable[str]) -> list[str]:
        return [field for field in fields if field not in facts or facts[field] is None]

    def _indeterminate(self, credit: str, facts: dict, missing: list[str]) -> dict:
        return self._finalize(credit, facts, {
            "calculation_status": "indeterminate",
            "credit_amount_usd": None,
            "rate": None,
            "tier": None,
            "eligibility_flags": [{"id": f"required:{f}", "status": "unknown",
                                    "detail": "required modeled fact is missing"}
                                   for f in missing],
            "assumptions": [],
            "audit_trail": [{"rule_id": "TC6", "formula": "fail closed",
                             "result": f"missing: {', '.join(missing)}"}],
        })

    def _finalize(self, credit: str, facts: dict, body: dict) -> dict:
        source_pack = self.get_rule_pack(credit)
        result = {"credit": credit, "tax_year": facts.get("tax_year"), **body,
                  "rule_pack": {"version": RULES["pack_version"],
                                "effective_as_of": RULES["effective_as_of"],
                                "sha256": RULE_PACK_SHA256,
                                "sources": source_pack["sources"]},
                  "input_sha256": _digest(facts),
                  "disclaimer": RULES["disclaimer"]}
        content = deepcopy(result)
        result["audit_sha256"] = _digest(content)
        result["notary_payload"] = {
            "content_digest": result["audit_sha256"],
            "context": f"taxcredit-engine:{credit}:{facts.get('tax_year', 'unknown')}",
            "digest_algorithm": "sha256",
        }
        return result

    def verify_result(self, result: dict) -> dict:
        supplied = str(result.get("audit_sha256", ""))
        content = deepcopy(result)
        content.pop("audit_sha256", None)
        content.pop("notary_payload", None)
        computed = _digest(content)
        return {"valid": bool(supplied) and supplied == computed,
                "supplied_sha256": supplied, "computed_sha256": computed,
                "rule_pack_current": (result.get("rule_pack", {}).get("sha256") ==
                                      RULE_PACK_SHA256)}

    def calculate(self, credit: str, facts: dict) -> dict:
        if credit not in RULES["rule_packs"]:
            raise ValidationError("unsupported credit", "credit", credit,
                                  "45Q|45V|45Y|48E|45X")
        return getattr(self, f"_calculate_{credit.lower()}")(facts)

    @staticmethod
    def _flag(flags: list, rule_id: str, passed: bool, detail: str) -> None:
        flags.append({"id": rule_id, "status": "pass" if passed else "fail",
                      "detail": detail})

    def _calculate_45q(self, facts: dict) -> dict:
        required = ["tax_year", "metric_tons", "facility_type", "disposal_path",
                    "pwa_met", "construction_begin_date", "placed_in_service_date",
                    "captured_and_disposed_in_us",
                    "tax_exempt_bond_financing_percent"]
        if facts.get("facility_type") == "electricity_generating_facility":
            required.append("capture_design_capacity_percent")
        missing = self._missing(facts, required)
        if missing:
            return self._indeterminate("45Q", facts, missing)
        year = _year(facts["tax_year"])
        if year not in {2025, 2026}:
            raise ValidationError("tax year is not in the pinned 45Q pack",
                                  "tax_year", year, "2025|2026")
        tons = _decimal(facts["metric_tons"], "metric_tons", minimum=Decimal("0"))
        facility = str(facts["facility_type"])
        path = str(facts["disposal_path"])
        if facility not in {"direct_air_capture", "electricity_generating_facility",
                            "other_industrial_facility"}:
            raise ValidationError("unsupported facility_type", "facility_type", facility,
                                  "direct_air_capture|electricity_generating_facility|other_industrial_facility")
        if path not in {"secure_storage", "utilization"}:
            raise ValidationError("unsupported disposal_path", "disposal_path", path,
                                  "secure_storage|utilization")
        pwa = _bool(facts["pwa_met"], "pwa_met")
        construction = _date(facts["construction_begin_date"], "construction_begin_date")
        placed = _date(facts["placed_in_service_date"], "placed_in_service_date")
        if placed < date(2023, 1, 1):
            result = self._indeterminate("45Q", facts, [])
            result["eligibility_flags"] = [{
                "id": "45Q-LEGACY", "status": "unknown",
                "detail": "pre-2023 equipment uses legacy branches outside this MVP pack"}]
            result["audit_trail"] = [{"rule_id": "45Q-SCOPE",
                                      "formula": "modern scenarios only",
                                      "result": "pre-2023 branch not calculated"}]
            content = deepcopy(result)
            content.pop("audit_sha256", None)
            content.pop("notary_payload", None)
            result["audit_sha256"] = _digest(content)
            result["notary_payload"]["content_digest"] = result["audit_sha256"]
            return result
        in_us = _bool(facts["captured_and_disposed_in_us"],
                      "captured_and_disposed_in_us")
        bond = _decimal(facts["tax_exempt_bond_financing_percent"],
                        "tax_exempt_bond_financing_percent", minimum=Decimal("0"))
        if bond > 100:
            raise ValidationError("bond financing percent must be <= 100",
                                  "tax_exempt_bond_financing_percent", str(bond),
                                  "0..100")
        rules = RULES["rule_packs"]["45Q"]
        category = "direct_air_capture" if facility == "direct_air_capture" else "general"
        era = "on_or_after_parity" if placed >= date(2025, 7, 5) else "before_parity"
        rate = Decimal(rules["base_rates_usd_per_metric_ton"][category][era][path])
        if pwa:
            rate *= Decimal(rules["pwa_multiplier"])
        threshold = Decimal(rules["annual_capture_threshold_metric_tons"][facility])
        flags: list = []
        self._flag(flags, "45Q-US", in_us, "capture/disposal or utilization in US")
        self._flag(flags, "45Q-CONSTRUCTION", construction < date(2033, 1, 1),
                   "construction begins before 2033")
        self._flag(flags, "45Q-THRESHOLD", tons >= threshold,
                   f"{_plain(tons)} tons vs {_plain(threshold)} minimum")
        if facility == "electricity_generating_facility":
            design = _decimal(facts["capture_design_capacity_percent"],
                              "capture_design_capacity_percent", minimum=Decimal("0"))
            self._flag(flags, "45Q-DESIGN", design >= Decimal("75"),
                       "capture design capacity must be at least 75%")
        eligible = all(f["status"] == "pass" for f in flags)
        bond_reduction = min(bond, Decimal("15"))
        reduction_factor = (Decimal("100") - bond_reduction) / Decimal("100")
        amount = tons * rate * reduction_factor if eligible else Decimal("0")
        return self._finalize("45Q", facts, {
            "calculation_status": "eligible" if eligible else "ineligible",
            "credit_amount_usd": _money(amount),
            "rate": {"amount_usd": _plain(rate), "per": "metric_ton",
                     "era": era, "pwa_multiplier_applied": pwa,
                     "tax_exempt_bond_reduction_percent": _plain(bond_reduction)},
            "tier": category, "eligibility_flags": flags, "assumptions": [],
            "audit_trail": [{"rule_id": "45Q-RATE", "formula": "tons × rate",
                             "operands": {"metric_tons": _plain(tons),
                                          "rate_usd": _plain(rate),
                                          "bond_reduction_factor": _plain(reduction_factor)},
                             "result_usd": _money(amount)}],
        })

    def _calculate_45v(self, facts: dict) -> dict:
        required = ["tax_year", "kg_hydrogen", "lifecycle_kg_co2e_per_kg_h2",
                    "greet_version", "evidence_digest", "pwa_met",
                    "produced_in_us", "construction_begin_date",
                    "placed_in_service_date", "section_45q_claimed_for_facility"]
        required.append("tax_exempt_bond_financing_percent")
        missing = self._missing(facts, required)
        if missing:
            return self._indeterminate("45V", facts, missing)
        year = _year(facts["tax_year"])
        rates = RULES["rule_packs"]["45V"]["rates_usd_per_kg"].get(str(year))
        if rates is None:
            raise ValidationError("tax year is not in the pinned 45V pack", "tax_year",
                                  year, "2025|2026")
        kg = _decimal(facts["kg_hydrogen"], "kg_hydrogen", minimum=Decimal("0"))
        emissions = _decimal(facts["lifecycle_kg_co2e_per_kg_h2"],
                             "lifecycle_kg_co2e_per_kg_h2", minimum=Decimal("0"))
        pwa = _bool(facts["pwa_met"], "pwa_met")
        produced_us = _bool(facts["produced_in_us"], "produced_in_us")
        conflict = _bool(facts["section_45q_claimed_for_facility"],
                         "section_45q_claimed_for_facility")
        construction = _date(facts["construction_begin_date"], "construction_begin_date")
        placed = _date(facts["placed_in_service_date"], "placed_in_service_date")
        bond = _decimal(facts["tax_exempt_bond_financing_percent"],
                        "tax_exempt_bond_financing_percent", minimum=Decimal("0"))
        if bond > 100:
            raise ValidationError("bond financing percent must be <= 100",
                                  "tax_exempt_bond_financing_percent", str(bond),
                                  "0..100")
        evidence = str(facts["evidence_digest"]).lower()
        evidence_ok = len(evidence) == 64 and all(c in "0123456789abcdef" for c in evidence)
        tier = None
        for candidate in rates:
            lower = candidate.get("emissions_gte")
            upper_lt = candidate.get("emissions_lt")
            upper_lte = candidate.get("emissions_lte")
            if ((lower is None or emissions >= Decimal(lower)) and
                    (upper_lt is None or emissions < Decimal(upper_lt)) and
                    (upper_lte is None or emissions <= Decimal(upper_lte))):
                tier = candidate
                break
        flags: list = []
        self._flag(flags, "45V-US", produced_us, "hydrogen produced in US")
        self._flag(flags, "45V-CONSTRUCTION", construction < date(2028, 1, 1),
                   "construction begins before 2028")
        self._flag(flags, "45V-10YEAR", placed.year <= year < placed.year + 10,
                   "production falls in 10-year credit period")
        self._flag(flags, "45V-NO-45Q", not conflict,
                   "same facility/process does not claim section 45Q")
        self._flag(flags, "45V-GREET", bool(str(facts["greet_version"]).strip()) and evidence_ok,
                   "external GREET version and SHA-256 evidence supplied")
        self._flag(flags, "45V-EMISSIONS", tier is not None,
                   "verified lifecycle emissions must be <= 4 kg CO2e/kg H2")
        eligible = all(f["status"] == "pass" for f in flags)
        rate = Decimal(tier["base_rate"]) if tier else Decimal("0")
        if pwa:
            rate *= Decimal(RULES["rule_packs"]["45V"]["pwa_multiplier"])
        bond_reduction = min(bond, Decimal("15"))
        reduction_factor = (Decimal("100") - bond_reduction) / Decimal("100")
        amount = kg * rate * reduction_factor if eligible else Decimal("0")
        return self._finalize("45V", facts, {
            "calculation_status": "eligible" if eligible else "ineligible",
            "credit_amount_usd": _money(amount),
            "rate": {"amount_usd": _plain(rate), "per": "kg_hydrogen",
                     "pwa_multiplier_applied": pwa,
                     "tax_exempt_bond_reduction_percent": _plain(bond_reduction)},
            "tier": tier["tier"] if tier else None, "eligibility_flags": flags,
            "assumptions": ["Lifecycle intensity is accepted from the supplied external GREET evidence; this service does not run GREET."],
            "audit_trail": [{"rule_id": "45V-TIER-RATE", "formula": "kg H2 × tier rate",
                             "operands": {"kg_hydrogen": _plain(kg),
                                          "lifecycle_intensity": _plain(emissions),
                                          "rate_usd": _plain(rate),
                                          "bond_reduction_factor": _plain(reduction_factor)},
                             "result_usd": _money(amount)}],
        })

    def _electricity_common(self, credit: str, facts: dict,
                            amount_field: str) -> tuple[Optional[dict], dict]:
        required = ["tax_year", "tax_year_begin_date", amount_field,
                    "lifecycle_emissions_g_co2e_per_kwh",
                    "placed_in_service_date", "construction_begin_date",
                    "produced_in_us", "nameplate_capacity_mw", "pwa_met",
                    "specified_foreign_entity", "foreign_influenced_entity",
                    "material_assistance_from_pfe", "technology",
                    "tax_exempt_bond_financing_percent"]
        if credit == "45Y":
            required.extend(["disposition", "claimed_conflicting_credit"])
        else:
            required.extend(["claimed_45y", "domestic_content_met",
                             "energy_community", "low_income_bonus_percentage_points",
                             "low_income_allocation_received",
                             "low_income_allocation_ratio_percent"])
        missing = self._missing(facts, required)
        if missing:
            return self._indeterminate(credit, facts, missing), {}
        year = _year(facts["tax_year"])
        if credit == "48E" and year not in {2025, 2026}:
            raise ValidationError("tax year is not in the pinned 48E pack",
                                  "tax_year", year, "2025|2026")
        tax_year_begin = _date(facts["tax_year_begin_date"],
                               "tax_year_begin_date")
        placed = _date(facts["placed_in_service_date"], "placed_in_service_date")
        construction = _date(facts["construction_begin_date"], "construction_begin_date")
        emissions = _decimal(facts["lifecycle_emissions_g_co2e_per_kwh"],
                             "lifecycle_emissions_g_co2e_per_kwh")
        capacity = _decimal(facts["nameplate_capacity_mw"], "nameplate_capacity_mw",
                            minimum=Decimal("0"))
        pwa = _bool(facts["pwa_met"], "pwa_met")
        produced_us = _bool(facts["produced_in_us"], "produced_in_us")
        sfe = _bool(facts["specified_foreign_entity"], "specified_foreign_entity")
        fie = _bool(facts["foreign_influenced_entity"], "foreign_influenced_entity")
        material_pfe = _bool(facts["material_assistance_from_pfe"],
                             "material_assistance_from_pfe")
        technology = str(facts["technology"]).lower()
        bond = _decimal(facts["tax_exempt_bond_financing_percent"],
                        "tax_exempt_bond_financing_percent", minimum=Decimal("0"))
        if bond > 100:
            raise ValidationError("bond financing percent must be <= 100",
                                  "tax_exempt_bond_financing_percent", str(bond),
                                  "0..100")
        flags: list = []
        self._flag(flags, f"{credit}-US", produced_us, "facility/production is in US")
        self._flag(flags, f"{credit}-EMISSIONS", emissions <= 0,
                   "greenhouse-gas emissions rate must be no greater than zero")
        self._flag(flags, f"{credit}-PLACED", placed >= date(2025, 1, 1),
                   "qualified facility/property placed in service after 2024")
        entity_restriction_applies = tax_year_begin > date(2025, 7, 4)
        entity_ok = not entity_restriction_applies or (not sfe and not fie)
        self._flag(flags, f"{credit}-ENTITY", entity_ok,
                   "PFE entity restriction applied according to tax-year begin date")
        pfe_ok = not (construction >= date(2026, 1, 1) and material_pfe)
        self._flag(flags, f"{credit}-PFE", pfe_ok,
                   "post-2025 construction has no modeled material assistance from PFE")
        wind_solar_ok = not (technology in {"wind", "solar"} and
                             construction > date(2026, 7, 4) and
                             placed > date(2027, 12, 31))
        self._flag(flags, f"{credit}-WIND-SOLAR-TERM", wind_solar_ok,
                   "modeled wind/solar termination rule")
        context = {"year": year, "placed": placed, "construction": construction,
                   "tax_year_begin": tax_year_begin,
                   "emissions": emissions, "capacity": capacity, "pwa": pwa,
                   "flags": flags, "bond": bond}
        return None, context

    def _calculate_45y(self, facts: dict) -> dict:
        early, c = self._electricity_common("45Y", facts, "kwh")
        if early is not None:
            return early
        year = c["year"]
        rates = RULES["rule_packs"]["45Y"]["rates_usd_per_kwh"].get(str(year))
        if rates is None:
            raise ValidationError("tax year is not in the pinned 45Y pack", "tax_year",
                                  year, "2025|2026")
        kwh = _decimal(facts["kwh"], "kwh", minimum=Decimal("0"))
        disposition = str(facts["disposition"]).lower()
        disposition_ok = disposition in {"sold_to_unrelated_person",
                                         "consumed_with_unrelated_meter",
                                         "stored_with_unrelated_meter"}
        conflict = _bool(facts["claimed_conflicting_credit"],
                         "claimed_conflicting_credit")
        self._flag(c["flags"], "45Y-DISPOSITION", disposition_ok,
                   "eligible sale, consumption, or storage disposition")
        self._flag(c["flags"], "45Y-NO-CONFLICT", not conflict,
                   "no 45/45J/45Q/45U/48/48A/48E claim for facility")
        increased = (c["pwa"] or c["capacity"] < Decimal("1") or
                     c["construction"] < date(2023, 1, 29))
        rate_key = "increased" if increased else "base"
        rate = Decimal(rates[rate_key])
        eligible = all(f["status"] == "pass" for f in c["flags"])
        bond_reduction = min(c["bond"], Decimal("15"))
        reduction_factor = (Decimal("100") - bond_reduction) / Decimal("100")
        amount = kwh * rate * reduction_factor if eligible else Decimal("0")
        assumptions = []
        if rates.get("derived"):
            assumptions.append("2026 45Y rate is the pinned statutory inflation/rounding derivation; refresh when superseded by later IRS guidance.")
        return self._finalize("45Y", facts, {
            "calculation_status": "eligible" if eligible else "ineligible",
            "credit_amount_usd": _money(amount),
            "rate": {"amount_usd": _plain(rate), "per": "kwh",
                     "rate_class": rate_key,
                     "tax_exempt_bond_reduction_percent": _plain(bond_reduction)},
            "eligibility_flags": c["flags"], "assumptions": assumptions,
            "audit_trail": [{"rule_id": "45Y-ANNUAL-RATE",
                             "formula": "eligible kWh × annual applicable amount",
                             "operands": {"kwh": _plain(kwh),
                                          "rate_usd_per_kwh": _plain(rate),
                                          "bond_reduction_factor": _plain(reduction_factor)},
                             "result_usd": _money(amount)}],
        })

    def _calculate_48e(self, facts: dict) -> dict:
        early, c = self._electricity_common("48E", facts, "qualified_investment_usd")
        if early is not None:
            return early
        investment = _decimal(facts["qualified_investment_usd"],
                              "qualified_investment_usd", minimum=Decimal("0"))
        claimed_45y = _bool(facts["claimed_45y"], "claimed_45y")
        domestic = _bool(facts["domestic_content_met"], "domestic_content_met")
        community = _bool(facts["energy_community"], "energy_community")
        low_income = _decimal(facts["low_income_bonus_percentage_points"],
                              "low_income_bonus_percentage_points",
                              minimum=Decimal("0"))
        if low_income not in {Decimal("0"), Decimal("10"), Decimal("20")}:
            raise ValidationError("low-income bonus must be 0, 10, or 20",
                                  "low_income_bonus_percentage_points", str(low_income),
                                  "0|10|20")
        allocation = _bool(facts["low_income_allocation_received"],
                           "low_income_allocation_received")
        allocation_ratio = _decimal(facts["low_income_allocation_ratio_percent"],
                                    "low_income_allocation_ratio_percent",
                                    minimum=Decimal("0"))
        if allocation_ratio > 100:
            raise ValidationError("allocation ratio must be <= 100",
                                  "low_income_allocation_ratio_percent",
                                  str(allocation_ratio), "0..100")
        low_income_ok = (low_income == 0 or
                         (allocation and c["capacity"] < 5 and allocation_ratio > 0))
        self._flag(c["flags"], "48E-LOW-INCOME-ALLOCATION", low_income_ok,
                   "10/20-point bonus requires allocation, positive capacity ratio, and facility under 5 MW")
        self._flag(c["flags"], "48E-NO-45Y", not claimed_45y,
                   "same facility does not claim 45Y")
        increased = (c["pwa"] or c["capacity"] < Decimal("1") or
                     c["construction"] < date(2023, 1, 29))
        rules = RULES["rule_packs"]["48E"]
        rate_class = "increased" if increased else "base"
        percent = Decimal(rules["increased_percentage"] if increased
                          else rules["base_percentage"])
        if domestic:
            percent += Decimal(rules["domestic_content_bonus_percentage_points"][rate_class])
        if community:
            percent += Decimal(rules["energy_community_bonus_percentage_points"][rate_class])
        effective_low_income = low_income * allocation_ratio / Decimal("100")
        percent += effective_low_income
        bond_reduction = min(c["bond"], Decimal("15"))
        reduction_factor = (Decimal("100") - bond_reduction) / Decimal("100")
        eligible = all(f["status"] == "pass" for f in c["flags"])
        amount = investment * percent / Decimal("100") * reduction_factor \
            if eligible else Decimal("0")
        return self._finalize("48E", facts, {
            "calculation_status": "eligible" if eligible else "ineligible",
            "credit_amount_usd": _money(amount),
            "rate": {"percentage": _plain(percent),
                     "rate_class": rate_class,
                     "low_income_effective_percentage_points": _plain(effective_low_income),
                     "tax_exempt_bond_reduction_percent": _plain(bond_reduction)},
            "tier": "increased" if increased else "base",
            "eligibility_flags": c["flags"], "assumptions": [],
            "audit_trail": [{"rule_id": "48E-PERCENTAGE",
                             "formula": "investment × total percentage × bond reduction",
                             "operands": {"qualified_investment_usd": _plain(investment),
                                          "total_percentage": _plain(percent),
                                          "reduction_factor": _plain(reduction_factor)},
                             "result_usd": _money(amount)}],
        })

    def _calculate_45x(self, facts: dict) -> dict:
        required = ["tax_year", "tax_year_begin_date", "component_type", "produced_in_us",
                    "sold_to_unrelated_person", "related_party_election",
                    "substantially_transformed", "meets_component_definition",
                    "claimed_48c", "specified_foreign_entity",
                    "foreign_influenced_entity", "material_assistance_from_pfe"]
        missing = self._missing(facts, required)
        if missing:
            return self._indeterminate("45X", facts, missing)
        year = _year(facts["tax_year"])
        if year < 2023:
            raise ValidationError("45X is not available before 2023", "tax_year",
                                  year, ">= 2023")
        tax_year_begin = _date(facts["tax_year_begin_date"],
                               "tax_year_begin_date")
        component_type = str(facts["component_type"])
        rules = RULES["rule_packs"]["45X"]
        component = rules["components"].get(component_type)
        if component is None:
            raise ValidationError("component is not in this enumerated MVP pack",
                                  "component_type", component_type,
                                  "one of: " + ", ".join(sorted(rules["components"])))
        produced_us = _bool(facts["produced_in_us"], "produced_in_us")
        unrelated = _bool(facts["sold_to_unrelated_person"],
                          "sold_to_unrelated_person")
        related_election = _bool(facts["related_party_election"],
                                 "related_party_election")
        transformed = _bool(facts["substantially_transformed"],
                            "substantially_transformed")
        definition = _bool(facts["meets_component_definition"],
                           "meets_component_definition")
        claimed_48c = _bool(facts["claimed_48c"], "claimed_48c")
        sfe = _bool(facts["specified_foreign_entity"], "specified_foreign_entity")
        fie = _bool(facts["foreign_influenced_entity"], "foreign_influenced_entity")
        material_pfe = _bool(facts["material_assistance_from_pfe"],
                             "material_assistance_from_pfe")
        flags: list = []
        self._flag(flags, "45X-US", produced_us, "component produced in US or possession")
        self._flag(flags, "45X-SALE", unrelated or related_election,
                   "qualified unrelated sale or related-person election")
        self._flag(flags, "45X-TRANSFORM", transformed,
                   "substantial transformation requirement")
        self._flag(flags, "45X-DEFINITION", definition,
                   "component-specific statutory definition is met")
        self._flag(flags, "45X-NO-48C", not claimed_48c,
                   "property was not used at a facility with a conflicting 48C claim")
        pfe_restriction_applies = tax_year_begin > date(2025, 7, 4)
        self._flag(flags, "45X-ENTITY",
                   not pfe_restriction_applies or (not sfe and not fie),
                   "PFE entity restriction applied according to tax-year begin date")
        self._flag(flags, "45X-PFE",
                   not pfe_restriction_applies or not material_pfe,
                   "material-assistance restriction applied according to tax-year begin date")
        wind = component_type in {"wind_blade", "wind_nacelle", "wind_tower",
                                  "offshore_wind_vessel",
                                  "offshore_wind_fixed_foundation",
                                  "offshore_wind_floating_foundation"}
        self._flag(flags, "45X-WIND-TERM", not wind or year <= 2027,
                   "wind component credit terminates after 2027")
        if wind:
            category = "wind"
        elif component_type == "critical_mineral":
            category = "critical_mineral"
        elif component_type == "metallurgical_coal":
            category = "metallurgical_coal"
        else:
            category = "general"
        phaseouts = rules["phaseout_percent_by_tax_year"][category]
        if category == "critical_mineral":
            phase = (phaseouts["through_2030"] if year <= 2030 else
                     phaseouts.get(str(year), phaseouts["after_2033"]))
        elif category == "metallurgical_coal":
            phase = phaseouts["through_2029"] if year <= 2029 else phaseouts["after_2029"]
        elif category == "wind":
            phase = phaseouts["through_2027"] if year <= 2027 else phaseouts["after_2027"]
        else:
            phase = (phaseouts["through_2029"] if year <= 2029 else
                     phaseouts.get(str(year), phaseouts["after_2032"]))
        phase_percent = Decimal(phase)
        self._flag(flags, "45X-PHASEOUT", phase_percent > 0,
                   f"category phaseout factor is {_plain(phase_percent)}%")
        if component["rate_kind"] == "per_unit":
            if "quantity" not in facts:
                return self._indeterminate("45X", facts, ["quantity"])
            basis = _decimal(facts["quantity"], "quantity", minimum=Decimal("0"))
            rate = Decimal(component["rate"])
            raw = basis * rate
            rate_view = {"amount_usd": _plain(rate), "per": component["unit"]}
            operands = {"quantity": _plain(basis), "unit": component["unit"],
                        "rate_usd": _plain(rate)}
        else:
            basis_field = component["basis_field"]
            if basis_field not in facts:
                return self._indeterminate("45X", facts, [basis_field])
            basis = _decimal(facts[basis_field], basis_field, minimum=Decimal("0"))
            rate = Decimal(component["rate_percent"])
            raw = basis * rate / Decimal("100")
            rate_view = {"percentage": _plain(rate), "of": basis_field}
            operands = {basis_field: _plain(basis), "rate_percentage": _plain(rate)}
        eligible = all(f["status"] == "pass" for f in flags)
        amount = raw * phase_percent / Decimal("100") if eligible else Decimal("0")
        rate_view["phaseout_percentage"] = _plain(phase_percent)
        return self._finalize("45X", facts, {
            "calculation_status": "eligible" if eligible else "ineligible",
            "credit_amount_usd": _money(amount), "rate": rate_view,
            "tier": component_type, "eligibility_flags": flags, "assumptions": [],
            "audit_trail": [{"rule_id": "45X-COMPONENT-RATE",
                             "formula": "component basis × rate × phaseout",
                             "operands": operands,
                             "phaseout_percentage": _plain(phase_percent),
                             "result_usd": _money(amount)}],
        })


def build() -> TaxCreditEngineCore:
    return TaxCreditEngineCore()
