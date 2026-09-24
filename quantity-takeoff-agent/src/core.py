"""Deterministic, source-linked construction material takeoffs.

QT1  All geometry and quantity arithmetic is Decimal; exact and purchase
     quantities are distinct.
QT2  Waste is an explicit bundled default or an explicitly recorded override.
QT3  Geometry is positive, finite, and carries an explicit unit system.
QT4  Every line exposes its formula, operands, constants, and source IDs.
QT5  Units convert only through the bundled conversion table.
QT6  Unknown assemblies/materials and missing dimensions fail closed.
QT7  Purchase quantities round conservatively to a recorded increment.
QT8  Canonical inputs, pack lineage, and results form a reproducible audit hash.
QT9  Assembly, trade, and grand rollups conserve independently by unit.
"""

from __future__ import annotations

import hashlib
import json
import logging
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Optional


VERSION = "0.1.0"
DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "material_pack.v0.1.0.json"
_RAW_PACK = DATA_PATH.read_bytes()
PACK = json.loads(_RAW_PACK)
MATERIAL_PACK_SHA256 = hashlib.sha256(_RAW_PACK).hexdigest()
QTY_QUANTUM = Decimal("0.001")
_DERIVED_AUDIT_FIELDS = {"audit_sha256", "notary_payload"}


@dataclass
class AgentConfig:
    name: str = "quantity-takeoff-agent"
    version: str = VERSION
    debug: bool = False


class ValidationError(ValueError):
    def __init__(self, message: str, field: str = "", value: Any = None,
                 constraint: str = ""):
        super().__init__(message)
        self.field = field
        self.value = value
        self.constraint = constraint


class IndeterminateError(ValueError):
    """A line cannot be calculated without guessing and must be excluded."""

    def __init__(self, message: str, field: str = "", value: Any = None):
        super().__init__(message)
        self.field = field
        self.value = value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _decimal(value: Any, field: str, *, minimum: Optional[Decimal] = None,
             strictly_positive: bool = False) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValidationError(f"'{field}' must be a finite decimal", field, value,
                              "finite decimal number")
    try:
        # JSON numeric values are normalized immediately at the boundary. No
        # binary-float operation occurs anywhere in the calculation path.
        result = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValidationError(f"'{field}' must be a finite decimal", field, value,
                              "finite decimal number")
    if not result.is_finite():
        raise ValidationError(f"'{field}' must be finite", field, value, "finite")
    if strictly_positive and result <= 0:
        raise ValidationError(f"'{field}' must be > 0", field, value, "> 0")
    if minimum is not None and result < minimum:
        raise ValidationError(f"'{field}' must be >= {minimum}", field, value,
                              f">= {minimum}")
    return result


def _qty(value: Decimal) -> str:
    return format(value.quantize(QTY_QUANTUM, rounding=ROUND_HALF_UP), "f")


def _plain(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _increment_qty(value: Decimal, increment_text: str) -> str:
    places = max(0, -Decimal(increment_text).as_tuple().exponent)
    return f"{value:.{places}f}"


def _validate_pack() -> None:
    source_ids = {source["id"] for source in PACK.get("sources", [])}
    if not PACK.get("pack_version") or not PACK.get("assemblies"):
        raise RuntimeError("QT2/QT4: material pack is missing version or assemblies")
    for source in PACK.get("sources", []):
        if not str(source.get("url", "")).startswith("https://"):
            raise RuntimeError(f"QT4: source {source.get('id')} has no HTTPS URL")
    def validate_source_references(value: Any, path: str = "pack") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                nested_path = f"{path}.{key}"
                if key in {"source_id", "unit_conversions_source_id"}:
                    if nested not in source_ids:
                        raise RuntimeError(
                            f"QT4/QT5: {nested_path} has unresolved source {nested}")
                elif key == "source_ids":
                    unknown = set(nested or []) - source_ids
                    if unknown:
                        raise RuntimeError(
                            f"QT4: {nested_path} has unresolved sources {unknown}")
                else:
                    validate_source_references(nested, nested_path)
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                validate_source_references(nested, f"{path}[{index}]")
    validate_source_references({key: value for key, value in PACK.items()
                                if key != "sources"})
    for material, waste in PACK.get("waste_factors", {}).items():
        if waste.get("source_id") not in source_ids:
            raise RuntimeError(f"QT2: {material} waste has unresolved source")
        _decimal(waste.get("percent"), f"waste_factors.{material}.percent",
                 minimum=Decimal("0"))
    for material, rounding in PACK.get("purchase_increments", {}).items():
        if rounding.get("source_id") not in source_ids:
            raise RuntimeError(f"QT7: {material} increment has unresolved source")
        _decimal(rounding.get("quantity"), f"purchase_increments.{material}",
                 strictly_positive=True)
    for assembly, definition in PACK["assemblies"].items():
        unknown = set(definition.get("source_ids", [])) - source_ids
        if unknown:
            raise RuntimeError(f"QT4: {assembly} has unresolved sources {unknown}")
        materials = definition.get("materials") or [definition.get("material")]
        for material in materials:
            if material not in PACK["waste_factors"]:
                raise RuntimeError(f"QT2: {assembly} material {material} lacks waste")
            if material not in PACK["purchase_increments"]:
                raise RuntimeError(f"QT7: {assembly} material {material} lacks increment")


_validate_pack()
_SOURCES = {source["id"]: source for source in PACK["sources"]}


class QuantityTakeoffCore:
    KNOWN_ACTIONS = frozenset({
        "calculate_takeoff", "list_assemblies", "get_assembly",
        "list_material_pack", "get_material_pack", "verify_result",
    })
    READ_ACTIONS = frozenset({
        "list_assemblies", "get_assembly", "list_material_pack",
        "get_material_pack", "verify_result",
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
                "material_pack": PACK["pack_version"],
                "material_pack_sha256": MATERIAL_PACK_SHA256,
                "assemblies": len(PACK["assemblies"]),
                "sources": len(PACK["sources"]),
            },
        }

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": ("Deterministic material quantities with explicit waste, "
                            "purchase rounding, pack lineage, and audit hashes."),
            "capabilities": [
                "calculate_takeoff", "list_assemblies", "get_assembly",
                "list_material_pack", "get_material_pack", "verify_result",
            ],
            "inputs": {
                "items": "assemblies with explicit geometry/unit system or supported SmartScale/ProtoGen payloads",
                "options": "takeoff metadata and optional explicit unit declarations",
            },
            "outputs": {
                "line_items": "net, waste-adjusted exact, and purchase quantities",
                "rollups": "unit-resolved assembly, trade, and grand reconciliations",
                "audit_sha256": "content digest for the notary rail",
            },
            "pricing": {"free_calls_per_day": 10, "price_usd_per_call": "0.50",
                        "future_gtm": "construction B2B seat"},
            "material_pack": {"version": PACK["pack_version"],
                              "sha256": MATERIAL_PACK_SHA256},
            "disclaimer": PACK["disclaimer"],
            "a2a_role": "construction-material-takeoff",
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
            if action == "calculate_takeoff":
                items = input_data.get("items")
                options = input_data.get("options", {})
                if not isinstance(items, list):
                    raise ValidationError("'items' must be an array", "items", items,
                                          "array")
                if not isinstance(options, dict):
                    raise ValidationError("'options' must be an object", "options",
                                          options, "object")
                return {"status": "ok", "data": self.calculate_takeoff(items, options)}
            if action == "list_assemblies":
                return {"status": "ok", "data": self.list_assemblies()}
            if action == "get_assembly":
                return {"status": "ok", "data": self.get_assembly(
                    str(input_data.get("assembly_type", input_data.get("type", ""))))}
            if action == "list_material_pack":
                return {"status": "ok", "data": self.list_material_pack()}
            if action == "get_material_pack":
                return {"status": "ok", "data": self.get_material_pack()}
            if action == "verify_result":
                result = input_data.get("result")
                if not isinstance(result, dict):
                    raise ValidationError("'result' must be an object", "result", result,
                                          "object")
                return {"status": "ok", "data": self.verify_result(result)}
            raise ValidationError(f"unknown action '{action}'", "action", action,
                                  "calculate_takeoff|list_assemblies|get_assembly|"
                                  "list_material_pack|get_material_pack|verify_result")
        except ValidationError as exc:
            return self._err(str(exc), error_type="ValidationError", field=exc.field,
                             value=exc.value, constraint=exc.constraint)
        except Exception as exc:
            self.logger.exception("quantity takeoff process failed")
            return self._err(f"internal error: {exc}", error_type="RuntimeError")

    def list_assemblies(self) -> dict:
        return {
            "version": PACK["pack_version"],
            "sha256": MATERIAL_PACK_SHA256,
            "assemblies": [
                {"type": name, **deepcopy(definition)}
                for name, definition in sorted(PACK["assemblies"].items())
            ],
            "unsupported_policy": f"factor not in pack {PACK['pack_version']}",
            "disclaimer": PACK["disclaimer"],
        }

    def get_assembly(self, assembly_type: str) -> dict:
        definition = PACK["assemblies"].get(assembly_type)
        if not definition:
            raise ValidationError(
                f"assembly not in pack {PACK['pack_version']}: {assembly_type}",
                "assembly_type", assembly_type, "bundled assembly type")
        source_ids = set(definition.get("source_ids", []))
        materials = definition.get("materials") or [definition.get("material")]
        for material in materials:
            source_ids.add(PACK["waste_factors"][material]["source_id"])
            source_ids.add(PACK["purchase_increments"][material]["source_id"])
        return {
            "type": assembly_type,
            **deepcopy(definition),
            "material_pack": {"version": PACK["pack_version"],
                              "sha256": MATERIAL_PACK_SHA256},
            "waste_factors": {material: deepcopy(PACK["waste_factors"][material])
                              for material in materials},
            "purchase_increments": {
                material: deepcopy(PACK["purchase_increments"][material])
                for material in materials},
            "sources": [deepcopy(_SOURCES[source_id])
                        for source_id in sorted(source_ids)],
            "disclaimer": PACK["disclaimer"],
        }

    def list_material_pack(self) -> dict:
        return {
            "schema_version": PACK["schema_version"],
            "version": PACK["pack_version"],
            "effective_as_of": PACK["effective_as_of"],
            "sha256": MATERIAL_PACK_SHA256,
            "assembly_types": sorted(PACK["assemblies"]),
            "materials": sorted(PACK["waste_factors"]),
            "rebar_sizes": sorted(PACK["rebar_unit_weights_lb_per_ft"]),
            "steel_shapes": sorted(PACK["steel_shapes_lb_per_ft"]),
            "roof_pitches": sorted(PACK["roof_pitch_multipliers"]),
            "source_count": len(PACK["sources"]),
            "disclaimer": PACK["disclaimer"],
        }

    def get_material_pack(self) -> dict:
        return {"material_pack": deepcopy(PACK), "sha256": MATERIAL_PACK_SHA256}

    @staticmethod
    def _normalize_unit_system(value: Any) -> str:
        aliases = {"imperial": "imperial", "us": "imperial", "US": "imperial",
                   "si": "SI", "SI": "SI", "metric": "SI"}
        normalized = aliases.get(value)
        if not normalized:
            raise ValidationError("unit_system must be explicit", "unit_system", value,
                                  "imperial|SI")
        return normalized

    @staticmethod
    def _normalize_upstream(payload: dict, provider: str) -> tuple[dict, str]:
        """Normalize only unit-encoded named dimensions from known payloads."""
        provider_lower = provider.lower()
        if "smartscale" in provider_lower and isinstance(payload.get("result"), dict):
            objects = payload["result"].get("objects")
            if isinstance(objects, list):
                if len(objects) != 1 or not isinstance(objects[0], dict):
                    raise IndeterminateError(
                        "SmartScale result must contain exactly one measurement object; selection is required",
                        "smartscale.result.objects", len(objects))
                payload = objects[0]
                object_id = payload.get("id") or payload.get("object_id")
                provider = f"smartscale:{object_id}" if object_id else "smartscale"
        if "protogen" in provider_lower and isinstance(payload.get("design"), dict):
            design = payload["design"]
            design_id = design.get("id") or design.get("design_id")
            payload = design
            provider = f"protogen:{design_id}" if design_id else "protogen"
        candidates = []
        if isinstance(payload.get("dimensions_mm"), dict):
            candidates.append((payload["dimensions_mm"], False))
        if isinstance(payload.get("real_dimensions"), dict):
            candidates.append((payload["real_dimensions"], True))
        if isinstance(payload.get("target_dimensions"), dict):
            candidates.append((payload["target_dimensions"], True))
        if not candidates:
            return {}, provider
        raw, suffixed = candidates[0]
        normalized = {}
        allowed = {"length", "width", "height", "depth", "thickness"}
        for raw_name, value in raw.items():
            name = str(raw_name)
            if suffixed and name.endswith("_mm"):
                name = name[:-3]
            if name in allowed:
                normalized[name] = {"value": value, "unit": "mm"}
        return normalized, provider

    def _geometry_context(self, item: dict, options: dict) -> dict:
        dimensions = item.get("dimensions")
        supplemental_dimensions = (deepcopy(dimensions)
                                   if isinstance(dimensions, dict) else {})
        measurement_source = None
        unit_system = item.get("unit_system") or options.get("unit_system")
        dimension_units = {}
        for candidate in (options.get("dimension_units"), item.get("dimension_units")):
            if isinstance(candidate, dict):
                dimension_units.update(candidate)

        payload = None
        provider = None
        for key, label in (("smartscale", "smartscale"), ("protogen", "protogen"),
                           ("measurement_payload", "measurement_payload"),
                           ("measurement", "measurement")):
            if isinstance(item.get(key), dict):
                payload, provider = item[key], label
                break
        if payload is None and any(key in item for key in
                                   ("dimensions_mm", "real_dimensions",
                                    "target_dimensions")):
            payload = item
            provider = str(item.get("provider") or item.get("source") or "unit_encoded_payload")

        if isinstance(dimensions, dict) and any(key in dimensions for key in
                                                ("dimensions_mm", "real_dimensions",
                                                 "target_dimensions")):
            payload = dimensions
            provider = str(dimensions.get("provider") or dimensions.get("source")
                           or "unit_encoded_dimensions")
            dimensions = None

        if payload is not None:
            upstream, measurement_source = self._normalize_upstream(payload, provider or "upstream")
            if upstream:
                overlap = set(upstream) & set(supplemental_dimensions)
                if overlap:
                    raise ValidationError(
                        "explicit dimensions conflict with upstream measurement fields",
                        "dimensions", sorted(overlap), "supplemental fields only")
                dimensions = {**upstream, **supplemental_dimensions}
                unit_system = "SI"
            elif dimensions is None:
                dimensions = payload.get("dimensions") or payload.get("measurements")
            unit_system = unit_system or payload.get("unit_system")
            if isinstance(payload.get("dimension_units"), dict):
                dimension_units.update(payload["dimension_units"])

        if isinstance(dimensions, dict) and isinstance(dimensions.get("values"), dict):
            unit_system = unit_system or dimensions.get("unit_system")
            if isinstance(dimensions.get("units"), dict):
                dimension_units.update(dimensions["units"])
            dimensions = dimensions["values"]
        if not isinstance(dimensions, dict):
            raise IndeterminateError("missing required dimensions", "dimensions", dimensions)
        unit_system = self._normalize_unit_system(unit_system or dimensions.get("unit_system"))
        dimensions = {key: value for key, value in dimensions.items()
                      if key not in {"unit_system", "units", "values"}}
        return {"dimensions": dimensions, "dimension_units": dimension_units,
                "unit_system": unit_system, "measurement_source": measurement_source,
                "conversions": []}

    @staticmethod
    def _convert(value: Decimal, from_unit: str, to_unit: str,
                 group: str) -> Decimal:
        table = PACK["unit_conversions"].get(group, {})
        if from_unit not in table or to_unit not in table:
            raise ValidationError(f"no bundled conversion from {from_unit} to {to_unit}",
                                  "unit", from_unit, f"convertible to {to_unit}")
        return value * Decimal(table[from_unit]) / Decimal(table[to_unit])

    def _dim(self, ctx: dict, name: str, to_unit: str, group: str) -> Decimal:
        dimensions = ctx["dimensions"]
        if name not in dimensions or dimensions[name] in (None, ""):
            raise IndeterminateError(f"missing required dimension: {name}", name, None)
        entry = dimensions[name]
        if isinstance(entry, dict):
            if "value" not in entry or not entry.get("unit"):
                raise ValidationError(f"dimension '{name}' requires value and unit", name,
                                      entry, "{value, unit}")
            raw, unit = entry["value"], str(entry["unit"])
        else:
            unit = ctx["dimension_units"].get(name)
            if not unit:
                raise ValidationError(f"dimension '{name}' has no explicit unit", name,
                                      entry, "{value, unit} or dimension_units mapping")
            raw = entry
        value = _decimal(raw, name, strictly_positive=True)
        converted = self._convert(value, unit, to_unit, group)
        record = {"field": name, "input_value": str(raw), "input_unit": unit,
                  "output_value": _plain(converted), "output_unit": to_unit,
                  "conversion_group": group,
                  "source_id": PACK["unit_conversions_source_id"]}
        if record not in ctx["conversions"]:
            ctx["conversions"].append(record)
        return converted

    @staticmethod
    def _count(ctx: dict, name: str, *, default: Optional[str] = None,
               allow_zero: bool = False, integer: bool = True) -> Decimal:
        entry = ctx["dimensions"].get(name)
        if entry in (None, ""):
            if default is None:
                raise IndeterminateError(f"missing required dimension: {name}", name, None)
            value = Decimal(default)
        else:
            if isinstance(entry, dict):
                supplied_unit = entry.get("unit")
                if supplied_unit not in (None, "", "count", "unitless"):
                    raise ValidationError(f"'{name}' is unitless", name, entry,
                                          "unitless count")
                raw = entry.get("value")
            else:
                raw = entry
            value = _decimal(raw, name, minimum=Decimal("0") if allow_zero else None,
                             strictly_positive=not allow_zero)
        if integer and value != value.to_integral_value():
            raise ValidationError(f"'{name}' must be an integer", name, str(value),
                                  "whole number")
        return value

    @staticmethod
    def _text(ctx: dict, name: str) -> str:
        value = ctx["dimensions"].get(name)
        if value in (None, ""):
            raise IndeterminateError(f"missing required dimension: {name}", name, None)
        if isinstance(value, dict):
            value = value.get("value")
        if value in (None, ""):
            raise IndeterminateError(f"missing required dimension: {name}", name, None)
        return str(value)

    def _area(self, ctx: dict) -> tuple[Decimal, dict]:
        if ctx["dimensions"].get("area") not in (None, ""):
            area = self._dim(ctx, "area", "ft2", "area_ft2")
            return area, {"area_ft2": _plain(area), "area_basis": "supplied_area"}
        for left, right in (("length", "height"), ("width", "height"),
                            ("length", "width")):
            if (ctx["dimensions"].get(left) not in (None, "") and
                    ctx["dimensions"].get(right) not in (None, "")):
                a = self._dim(ctx, left, "ft", "length_ft")
                b = self._dim(ctx, right, "ft", "length_ft")
                return a * b, {"area_ft2": _plain(a * b),
                               "area_basis": f"{left}_ft * {right}_ft"}
        raise IndeterminateError("missing required dimension: area OR two planar dimensions",
                                 "area", None)

    @staticmethod
    def _waste(item: dict, material: str) -> dict:
        bundled = PACK["waste_factors"][material]
        override = item.get("waste_override")
        if override is None:
            percent = _decimal(bundled["percent"], "waste.percent",
                               minimum=Decimal("0"))
            return {"percent": _plain(percent),
                    "multiplier": _plain(Decimal("1") + percent / Decimal(
                        PACK["constants"]["percent_denominator"]["value"])),
                    "basis": "material_pack_default", "overridden": False,
                    "source_id": bundled["source_id"], "note": bundled.get("note")}
        reason = None
        if isinstance(override, dict):
            raw = override.get("percent")
            reason = override.get("reason")
        else:
            raw = override
        percent = _decimal(raw, "waste_override.percent", minimum=Decimal("0"))
        if percent > Decimal(PACK["constants"]["percent_denominator"]["value"]):
            raise ValidationError("waste override must be <= 100 percent",
                                  "waste_override.percent", str(percent), "0..100")
        return {"percent": _plain(percent),
                "multiplier": _plain(Decimal("1") + percent / Decimal(
                    PACK["constants"]["percent_denominator"]["value"])),
                "basis": "caller_override", "overridden": True,
                "source_id": "caller_supplied", "reason": reason,
                "replaces_default": deepcopy(bundled)}

    def _line(self, *, item: dict, item_id: str, assembly: str, trade: str,
              material: str, unit: str, net: Decimal, formula: str,
              operands: dict, source_ids: set[str], ctx: dict,
              weight: Optional[dict] = None, suffix: Optional[str] = None) -> dict:
        waste = self._waste(item, material)
        exact_raw = net * Decimal(waste["multiplier"])
        rounding = PACK["purchase_increments"][material]
        increment = Decimal(rounding["quantity"])
        purchase = ((exact_raw / increment).to_integral_value(
            rounding=ROUND_CEILING) * increment)
        all_sources = set(source_ids)
        all_sources.update(conversion["source_id"]
                           for conversion in ctx["conversions"])
        all_sources.add(PACK["constants"]["percent_denominator"]["source_id"])
        all_sources.add(rounding["source_id"])
        if waste["source_id"] != "caller_supplied":
            all_sources.add(waste["source_id"])
        line_id = f"{item_id}:{suffix or material}"
        output = {
            "id": line_id, "item_id": item_id, "status": "determinate",
            "assembly": assembly, "trade": trade, "material": material,
            "net_qty": _qty(net), "exact_qty": _qty(exact_raw),
            "purchase_qty": _increment_qty(purchase, rounding["quantity"]),
            "unit": unit,
            "quantity_semantics": {
                "net_qty": "geometry before waste",
                "exact_qty": "waste-adjusted calculation quantity at 0.001 output precision",
                "purchase_qty": "waste-adjusted quantity rounded up to purchase increment",
            },
            "waste": waste,
            "purchase_rounding": {
                "mode": "ROUND_CEILING", "increment": rounding["quantity"],
                "unit": rounding["unit"], "source_id": rounding["source_id"],
                "note": rounding.get("note"),
            },
            "formula": formula, "operands": operands,
            "geometry": {"unit_system": ctx["unit_system"],
                         "measurement_source": ctx["measurement_source"],
                         "conversions": deepcopy(ctx["conversions"])},
            "source_ids": sorted(all_sources),
            "material_pack_version": PACK["pack_version"],
        }
        if weight is not None:
            output["weight"] = weight
        return output

    def _concrete(self, item: dict, ctx: dict, assembly: str, item_id: str) -> list[dict]:
        if assembly == "concrete_slab":
            a = self._dim(ctx, "length", "ft", "length_ft")
            b = self._dim(ctx, "width", "ft", "length_ft")
            c = self._dim(ctx, "thickness", "ft", "length_ft")
            names = ("length_ft", "width_ft", "thickness_ft")
        elif assembly == "concrete_footing":
            a = self._dim(ctx, "length", "ft", "length_ft")
            b = self._dim(ctx, "width", "ft", "length_ft")
            c = self._dim(ctx, "depth", "ft", "length_ft")
            names = ("length_ft", "width_ft", "depth_ft")
        elif assembly == "concrete_wall":
            a = self._dim(ctx, "length", "ft", "length_ft")
            b = self._dim(ctx, "height", "ft", "length_ft")
            c = self._dim(ctx, "thickness", "ft", "length_ft")
            names = ("length_ft", "height_ft", "thickness_ft")
        else:
            height = self._dim(ctx, "height", "ft", "length_ft")
            column_sources = set(PACK["assemblies"][assembly]["source_ids"])
            if ctx["dimensions"].get("diameter") not in (None, ""):
                diameter = self._dim(ctx, "diameter", "ft", "length_ft")
                pi_pin = Decimal(PACK["constants"]["pi_pin"]["value"])
                circle_divisor = Decimal(
                    PACK["constants"]["circular_area_divisor"]["value"])
                volume_ft3 = pi_pin * diameter * diameter / circle_divisor * height
                operands = {"shape": "circular", "diameter_ft": _plain(diameter),
                            "height_ft": _plain(height), "pi_pin": _plain(pi_pin),
                            "circular_area_divisor": _plain(circle_divisor),
                            "net_ft3": _plain(volume_ft3)}
                column_sources.update({PACK["constants"]["pi_pin"]["source_id"],
                                       PACK["constants"]["circular_area_divisor"]["source_id"]})
            else:
                width = self._dim(ctx, "width", "ft", "length_ft")
                depth = self._dim(ctx, "depth", "ft", "length_ft")
                volume_ft3 = width * depth * height
                operands = {"shape": "rectangular", "width_ft": _plain(width),
                            "depth_ft": _plain(depth), "height_ft": _plain(height),
                            "net_ft3": _plain(volume_ft3)}
            ft3_per_yd3 = Decimal(PACK["unit_conversions"]["volume_ft3"]["yd3"])
            net = volume_ft3 / ft3_per_yd3
            operands.update({"ft3_per_yd3": _plain(ft3_per_yd3),
                             "net_yd3": _plain(net)})
            definition = PACK["assemblies"][assembly]
            density = Decimal(PACK["constants"]["concrete_density_lb_per_yd3"]["value"])
            column_sources.update({
                PACK["constants"]["concrete_density_lb_per_yd3"]["source_id"],
                PACK["unit_conversions_source_id"]})
            return [self._line(
                item=item, item_id=item_id, assembly=assembly, trade="concrete",
                material="ready_mix_concrete", unit="yd3", net=net,
                formula=definition["formula"], operands=operands,
                source_ids=column_sources, ctx=ctx,
                weight={"net_lb": _qty(net * density),
                        "density_lb_per_yd3": _plain(density)})]
        volume_ft3 = a * b * c
        ft3_per_yd3 = Decimal(PACK["unit_conversions"]["volume_ft3"]["yd3"])
        net = volume_ft3 / ft3_per_yd3
        operands = {names[0]: _plain(a), names[1]: _plain(b), names[2]: _plain(c),
                    "net_ft3": _plain(volume_ft3),
                    "ft3_per_yd3": _plain(ft3_per_yd3), "net_yd3": _plain(net)}
        definition = PACK["assemblies"][assembly]
        density = Decimal(PACK["constants"]["concrete_density_lb_per_yd3"]["value"])
        return [self._line(
            item=item, item_id=item_id, assembly=assembly, trade="concrete",
            material="ready_mix_concrete", unit="yd3", net=net,
            formula=definition["formula"], operands=operands,
            source_ids=set(definition["source_ids"]) | {
                PACK["constants"]["concrete_density_lb_per_yd3"]["source_id"],
                PACK["unit_conversions_source_id"]}, ctx=ctx,
            weight={"net_lb": _qty(net * density),
                    "density_lb_per_yd3": _plain(density)})]

    def _rebar(self, item: dict, ctx: dict, item_id: str) -> list[dict]:
        length = self._dim(ctx, "length", "ft", "length_ft")
        width = self._dim(ctx, "width", "ft", "length_ft")
        spacing = self._dim(ctx, "spacing", "ft", "length_ft")
        layers = self._count(ctx, "layers", default=PACK["constants"]["default_layers"]["value"])
        size = self._text(ctx, "bar_size")
        weight_factor = PACK["rebar_unit_weights_lb_per_ft"].get(size)
        if not weight_factor:
            raise IndeterminateError(f"rebar material not in pack {PACK['pack_version']}: {size}",
                                     "bar_size", size)
        endpoint = Decimal(PACK["constants"]["bar_grid_endpoint_addition"]["value"])
        across_width = ((width / spacing).to_integral_value(rounding=ROUND_CEILING)
                        + endpoint)
        across_length = ((length / spacing).to_integral_value(rounding=ROUND_CEILING)
                         + endpoint)
        net_lf = (across_width * length + across_length * width) * layers
        lb_per_ft = Decimal(weight_factor["value"])
        definition = PACK["assemblies"]["rebar_grid"]
        operands = {"length_ft": _plain(length), "width_ft": _plain(width),
                    "spacing_ft": _plain(spacing), "layers": _plain(layers),
                    "bars_parallel_length": _plain(across_width),
                    "bars_parallel_width": _plain(across_length),
                    "bar_size": size, "lb_per_ft": weight_factor["value"],
                    "bar_grid_endpoint_addition": _plain(endpoint),
                    "net_lf": _plain(net_lf)}
        line = self._line(
            item=item, item_id=item_id, assembly="rebar_grid", trade="reinforcing_steel",
            material="reinforcing_bar", unit="lf", net=net_lf,
            formula=definition["formula"], operands=operands,
            source_ids=set(definition["source_ids"]) | {weight_factor["source_id"],
                PACK["constants"]["bar_grid_endpoint_addition"]["source_id"]},
            ctx=ctx, weight={"bar_size": size, "lb_per_ft": weight_factor["value"],
                             "net_lb": _qty(net_lf * lb_per_ft)})
        line["weight"].update({
            "exact_lb": _qty(Decimal(line["exact_qty"]) * lb_per_ft),
            "purchase_lb": _qty(Decimal(line["purchase_qty"]) * lb_per_ft),
        })
        return [line]

    def _wood_wall(self, item: dict, ctx: dict, item_id: str) -> list[dict]:
        length = self._dim(ctx, "length", "ft", "length_ft")
        height = self._dim(ctx, "height", "ft", "length_ft")
        spacing = self._dim(ctx, "stud_spacing", "ft", "length_ft")
        corners = self._count(ctx, "corners", default="0", allow_zero=True)
        openings = self._count(ctx, "openings", default="0", allow_zero=True)
        corner_extra = Decimal(PACK["constants"]["corner_extra_studs"]["value"])
        opening_extra = Decimal(PACK["constants"]["opening_extra_studs"]["value"])
        plate_runs = Decimal(PACK["constants"]["wall_plate_runs"]["value"])
        end_stud = Decimal(PACK["constants"]["wall_end_stud"]["value"])
        nominal_thickness = Decimal(PACK["constants"]["nominal_2x4_thickness_in"]["value"])
        nominal_width = Decimal(PACK["constants"]["nominal_2x4_width_in"]["value"])
        board_foot_divisor = Decimal(PACK["constants"]["board_foot_divisor"]["value"])
        studs = ((length / spacing).to_integral_value(rounding=ROUND_CEILING)
                 + end_stud + corners * corner_extra + openings * opening_extra)
        board_ft = (nominal_thickness * nominal_width
                    * (studs * height + plate_runs * length) / board_foot_divisor)
        definition = PACK["assemblies"]["wood_wall_framing"]
        sources = set(definition["source_ids"]) | {
            PACK["constants"]["corner_extra_studs"]["source_id"],
            PACK["constants"]["opening_extra_studs"]["source_id"],
            PACK["constants"]["wall_plate_runs"]["source_id"],
            PACK["constants"]["wall_end_stud"]["source_id"],
            PACK["constants"]["nominal_2x4_thickness_in"]["source_id"],
            PACK["constants"]["nominal_2x4_width_in"]["source_id"],
            PACK["constants"]["board_foot_divisor"]["source_id"]}
        common = {"length_ft": _plain(length), "height_ft": _plain(height),
                  "stud_spacing_ft": _plain(spacing), "corners": _plain(corners),
                  "openings": _plain(openings), "corner_extra_studs": _plain(corner_extra),
                  "opening_extra_studs": _plain(opening_extra),
                  "wall_plate_runs": _plain(plate_runs), "net_studs": _plain(studs),
                  "wall_end_stud": _plain(end_stud),
                  "nominal_thickness_in": _plain(nominal_thickness),
                  "nominal_width_in": _plain(nominal_width),
                  "board_foot_divisor": _plain(board_foot_divisor),
                  "net_board_ft": _plain(board_ft), "nominal_member": "2x4"}
        return [
            self._line(item=item, item_id=item_id, assembly="wood_wall_framing",
                       trade="framing", material="wood_studs", unit="stud", net=studs,
                       formula=definition["formula"], operands=common,
                       source_ids=sources, ctx=ctx, suffix="studs"),
            self._line(item=item, item_id=item_id, assembly="wood_wall_framing",
                       trade="framing", material="dimensional_lumber", unit="board_ft",
                       net=board_ft, formula=definition["formula"], operands=common,
                       source_ids=sources, ctx=ctx, suffix="board-feet"),
        ]

    def _sheet_or_masonry(self, item: dict, ctx: dict, assembly: str,
                          item_id: str) -> list[dict]:
        area, area_operands = self._area(ctx)
        definitions = {
            "sheathing": ("wood_sheathing_4x8", "sheet",
                           PACK["constants"]["sheathing_sheet_area_ft2"],
                           lambda value, factor: value / factor),
            "drywall": ("drywall_4x8", "sheet",
                         PACK["constants"]["drywall_sheet_area_ft2"],
                         lambda value, factor: value / factor),
            "cmu_wall": ("cmu_8x8x16", "unit",
                         PACK["constants"]["cmu_units_per_ft2"],
                         lambda value, factor: value * factor),
            "brick_veneer": ("modular_brick", "brick",
                              PACK["constants"]["modular_brick_per_ft2"],
                              lambda value, factor: value * factor),
        }
        material, unit, constant, operation = definitions[assembly]
        factor = Decimal(constant["value"])
        net = operation(area, factor)
        definition = PACK["assemblies"][assembly]
        operands = {**area_operands, "factor": constant["value"],
                    "factor_source_id": constant["source_id"], "net": _plain(net)}
        return [self._line(
            item=item, item_id=item_id, assembly=assembly, trade=definition["trade"],
            material=material, unit=unit, net=net, formula=definition["formula"],
            operands=operands,
            source_ids=set(definition["source_ids"]) | {constant["source_id"]}, ctx=ctx)]

    def _dimensional_lumber(self, item: dict, ctx: dict, item_id: str) -> list[dict]:
        width = self._dim(ctx, "nominal_width", "in", "length_ft")
        thickness = self._dim(ctx, "nominal_thickness", "in", "length_ft")
        length = self._dim(ctx, "length", "ft", "length_ft")
        pieces = self._count(ctx, "pieces", default=PACK["constants"]["default_pieces"]["value"])
        board_foot_divisor = Decimal(PACK["constants"]["board_foot_divisor"]["value"])
        net = width * thickness * length * pieces / board_foot_divisor
        definition = PACK["assemblies"]["dimensional_lumber"]
        operands = {"nominal_width_in": _plain(width),
                    "nominal_thickness_in": _plain(thickness),
                    "length_ft": _plain(length), "pieces": _plain(pieces),
                    "board_foot_divisor": _plain(board_foot_divisor),
                    "net_board_ft": _plain(net)}
        return [self._line(
            item=item, item_id=item_id, assembly="dimensional_lumber", trade="framing",
            material="dimensional_lumber", unit="board_ft", net=net,
            formula=definition["formula"], operands=operands,
            source_ids=set(definition["source_ids"]) | {
                PACK["constants"]["board_foot_divisor"]["source_id"]}, ctx=ctx)]

    def _roofing(self, item: dict, ctx: dict, item_id: str) -> list[dict]:
        area, area_operands = self._area(ctx)
        pitch = self._text(ctx, "pitch")
        pitch_factor = PACK["roof_pitch_multipliers"].get(pitch)
        if not pitch_factor:
            raise IndeterminateError(f"roof pitch factor not in pack {PACK['pack_version']}: {pitch}",
                                     "pitch", pitch)
        square_area = PACK["constants"]["roofing_square_area_ft2"]
        net = area / Decimal(square_area["value"]) * Decimal(pitch_factor["value"])
        definition = PACK["assemblies"]["asphalt_shingle"]
        operands = {**area_operands, "square_area_ft2": square_area["value"],
                    "pitch": pitch, "pitch_multiplier": pitch_factor["value"],
                    "net_squares": _plain(net)}
        return [self._line(
            item=item, item_id=item_id, assembly="asphalt_shingle", trade="roofing",
            material="asphalt_shingles", unit="square", net=net,
            formula=definition["formula"], operands=operands,
            source_ids=set(definition["source_ids"]) | {
                square_area["source_id"], pitch_factor["source_id"]}, ctx=ctx)]

    def _steel(self, item: dict, ctx: dict, item_id: str) -> list[dict]:
        shape = self._text(ctx, "shape")
        shape_factor = PACK["steel_shapes_lb_per_ft"].get(shape)
        if not shape_factor:
            raise IndeterminateError(f"steel shape not in pack {PACK['pack_version']}: {shape}",
                                     "shape", shape)
        length = self._dim(ctx, "length", "ft", "length_ft")
        pieces = self._count(ctx, "pieces", default=PACK["constants"]["default_pieces"]["value"])
        net_lb = Decimal(shape_factor["value"]) * length * pieces
        lb_per_short_ton = Decimal(PACK["unit_conversions"]["mass_lb"]["short_ton"])
        net_ton = net_lb / lb_per_short_ton
        definition = PACK["assemblies"]["structural_steel"]
        operands = {"shape": shape, "shape_lb_per_ft": shape_factor["value"],
                    "length_ft": _plain(length), "pieces": _plain(pieces),
                    "lb_per_short_ton": _plain(lb_per_short_ton),
                    "net_lb": _plain(net_lb), "net_short_ton": _plain(net_ton)}
        line = self._line(
            item=item, item_id=item_id, assembly="structural_steel",
            trade="structural_steel", material="structural_steel", unit="short_ton",
            net=net_ton, formula=definition["formula"], operands=operands,
            source_ids=set(definition["source_ids"]) | {shape_factor["source_id"],
                PACK["unit_conversions_source_id"]},
            ctx=ctx, weight={"shape": shape, "lb_per_ft": shape_factor["value"],
                             "net_lb": _qty(net_lb), "net_short_ton": _qty(net_ton)})
        line["weight"].update({
            "exact_lb": _qty(Decimal(line["exact_qty"]) * lb_per_short_ton),
            "purchase_lb": _qty(Decimal(line["purchase_qty"]) * lb_per_short_ton),
        })
        return [line]

    def _sitework(self, item: dict, ctx: dict, assembly: str,
                  item_id: str) -> list[dict]:
        length = self._dim(ctx, "length", "ft", "length_ft")
        width = self._dim(ctx, "width", "ft", "length_ft")
        depth = self._dim(ctx, "depth", "ft", "length_ft")
        volume_ft3 = length * width * depth
        ft3_per_yd3 = Decimal(PACK["unit_conversions"]["volume_ft3"]["yd3"])
        volume_yd3 = volume_ft3 / ft3_per_yd3
        definition = PACK["assemblies"][assembly]
        operands = {"length_ft": _plain(length), "width_ft": _plain(width),
                    "depth_ft": _plain(depth), "net_ft3": _plain(volume_ft3),
                    "ft3_per_yd3": _plain(ft3_per_yd3),
                    "net_yd3": _plain(volume_yd3)}
        if assembly == "excavation":
            return [self._line(
                item=item, item_id=item_id, assembly=assembly, trade="sitework",
                material="excavated_earth", unit="yd3", net=volume_yd3,
                formula=definition["formula"], operands=operands,
                source_ids=set(definition["source_ids"]) | {
                    PACK["unit_conversions_source_id"]}, ctx=ctx)]
        density = PACK["constants"]["aggregate_density_short_ton_per_yd3"]
        net_ton = volume_yd3 * Decimal(density["value"])
        operands.update({"density_short_ton_per_yd3": density["value"],
                         "density_source_id": density["source_id"],
                         "net_short_ton": _plain(net_ton)})
        return [self._line(
            item=item, item_id=item_id, assembly=assembly, trade="sitework",
            material="aggregate_base", unit="short_ton", net=net_ton,
            formula=definition["formula"], operands=operands,
            source_ids=set(definition["source_ids"]) | {density["source_id"],
                PACK["unit_conversions_source_id"]}, ctx=ctx)]

    def _paint(self, item: dict, ctx: dict, item_id: str) -> list[dict]:
        area, area_operands = self._area(ctx)
        coats = self._count(ctx, "coats")
        coverage = PACK["constants"]["paint_coverage_ft2_per_gallon"]
        net = area / Decimal(coverage["value"]) * coats
        definition = PACK["assemblies"]["paint"]
        operands = {**area_operands, "coats": _plain(coats),
                    "coverage_ft2_per_gallon": coverage["value"],
                    "coverage_source_id": coverage["source_id"],
                    "net_gallons": _plain(net)}
        return [self._line(
            item=item, item_id=item_id, assembly="paint", trade="finishes",
            material="paint", unit="gallon", net=net,
            formula=definition["formula"], operands=operands,
            source_ids=set(definition["source_ids"]) | {coverage["source_id"]}, ctx=ctx)]

    def _calculate_item(self, item: dict, options: dict, index: int) -> list[dict]:
        assembly = str(item.get("assembly", ""))
        if not assembly:
            raise IndeterminateError("missing required field: assembly", "assembly", None)
        if assembly not in PACK["assemblies"]:
            raise IndeterminateError(f"assembly not in pack {PACK['pack_version']}: {assembly}",
                                     "assembly", assembly)
        ctx = self._geometry_context(item, options)
        item_id = str(item.get("id") or f"item-{index + 1:04d}")
        if assembly.startswith("concrete_"):
            return self._concrete(item, ctx, assembly, item_id)
        if assembly == "rebar_grid":
            return self._rebar(item, ctx, item_id)
        if assembly == "wood_wall_framing":
            return self._wood_wall(item, ctx, item_id)
        if assembly in {"sheathing", "drywall", "cmu_wall", "brick_veneer"}:
            return self._sheet_or_masonry(item, ctx, assembly, item_id)
        if assembly == "dimensional_lumber":
            return self._dimensional_lumber(item, ctx, item_id)
        if assembly == "asphalt_shingle":
            return self._roofing(item, ctx, item_id)
        if assembly == "structural_steel":
            return self._steel(item, ctx, item_id)
        if assembly in {"excavation", "aggregate_base"}:
            return self._sitework(item, ctx, assembly, item_id)
        if assembly == "paint":
            return self._paint(item, ctx, item_id)
        raise IndeterminateError(f"assembly not implemented in pack {PACK['pack_version']}: {assembly}",
                                 "assembly", assembly)

    @staticmethod
    def _add_totals(target: dict, line: dict) -> None:
        unit = line["unit"]
        bucket = target.setdefault(unit, {"net_qty": Decimal("0"),
                                          "exact_qty": Decimal("0"),
                                          "purchase_qty": Decimal("0")})
        for key in bucket:
            bucket[key] += Decimal(line[key])

    @staticmethod
    def _format_totals(target: dict) -> dict:
        return {unit: {key: _qty(value) for key, value in values.items()}
                for unit, values in sorted(target.items())}

    def _build_rollups(self, lines: list[dict]) -> tuple[list[dict], dict, dict]:
        assemblies: dict[str, dict] = {}
        trades: dict[str, dict] = {}
        grand: dict = {}
        for line in lines:
            assembly = assemblies.setdefault(line["item_id"], {
                "item_id": line["item_id"], "assembly": line["assembly"],
                "trade": line["trade"], "raw": {}})
            self._add_totals(assembly["raw"], line)
            self._add_totals(trades.setdefault(line["trade"], {}), line)
            self._add_totals(grand, line)
        assembly_rollups = [
            {"item_id": value["item_id"], "assembly": value["assembly"],
             "trade": value["trade"],
             "totals_by_unit": self._format_totals(value["raw"])}
            for value in assemblies.values()
        ]
        trade_rollups = {trade: {"totals_by_unit": self._format_totals(values)}
                         for trade, values in sorted(trades.items())}
        return assembly_rollups, trade_rollups, self._format_totals(grand)

    def calculate_takeoff(self, items: list, options: dict) -> dict:
        if not items:
            raise ValidationError("'items' must contain at least one item", "items", items,
                                  "non-empty array")
        requested_pack = options.get("material_pack_version")
        if requested_pack and requested_pack != PACK["pack_version"]:
            raise ValidationError("requested material pack is not bundled",
                                  "options.material_pack_version", requested_pack,
                                  PACK["pack_version"])
        inputs = {"items": deepcopy(items), "options": deepcopy(options)}
        lines = []
        indeterminate = []
        seen_ids = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValidationError("each takeoff item must be an object",
                                      f"items[{index}]", item, "object")
            item_id = str(item.get("id") or f"item-{index + 1:04d}")
            if item_id in seen_ids:
                raise ValidationError("item ids must be unique", "id", item_id, "unique")
            seen_ids.add(item_id)
            try:
                lines.extend(self._calculate_item(item, options, index))
            except IndeterminateError as exc:
                indeterminate.append({
                    "id": item_id, "assembly": item.get("assembly"),
                    "status": "indeterminate", "reason": str(exc),
                    "field": exc.field, "value": exc.value,
                    "excluded_from_totals": True,
                    "material_pack_version": PACK["pack_version"],
                })
        assembly_rollups, trade_rollups, grand_units = self._build_rollups(lines)
        if lines and not indeterminate:
            status = "complete_for_supplied_items"
        elif lines:
            status = "partial_indeterminate"
        else:
            status = "indeterminate"
        source_ids = sorted({source_id for line in lines
                             for source_id in line["source_ids"]
                             if source_id in _SOURCES})
        input_sha = _digest(inputs)
        result = {
            "takeoff_status": status,
            "project_id": options.get("project_id"),
            "revision_id": options.get("revision_id"),
            "inputs": inputs,
            "input_sha256": input_sha,
            "line_items": lines,
            "indeterminate": indeterminate,
            "assembly_rollups": assembly_rollups,
            "trade_rollups": trade_rollups,
            "grand_rollup": {
                "totals_by_unit": grand_units,
                "determinate_line_count": len(lines),
                "indeterminate_item_count": len(indeterminate),
                "coverage_complete_for_supplied_items": not indeterminate,
                "conservation_basis": "unit-resolved; unlike units are never summed",
            },
            "material_pack": {
                "version": PACK["pack_version"],
                "effective_as_of": PACK["effective_as_of"],
                "sha256": MATERIAL_PACK_SHA256,
                "sources_used": [deepcopy(_SOURCES[source_id])
                                 for source_id in source_ids],
            },
            "lineage": {
                "producer": {"agent_id": self.config.name,
                             "version": self.config.version},
                "input_sha256": input_sha,
                "material_pack": {"version": PACK["pack_version"],
                                  "sha256": MATERIAL_PACK_SHA256},
                "source_ids_used": source_ids,
                "upstream_measurements": sorted({
                    line["geometry"]["measurement_source"] for line in lines
                    if line["geometry"].get("measurement_source")}),
            },
            "downstream": {
                "cost_estimator_ready": bool(lines),
                "quantity_source": "line_items",
                "audit_binding": "audit_sha256",
            },
            "disclaimer": PACK["disclaimer"],
        }
        self.assert_conservation(result)
        result["audit_sha256"] = _digest(result)
        takeoff_id = "qt-" + result["audit_sha256"][:24]
        result["notary_payload"] = self._notary_payload(result["audit_sha256"], takeoff_id)
        return result

    @staticmethod
    def _notary_payload(audit_sha256: str, takeoff_id: str) -> dict:
        return {"content_digest": audit_sha256,
                "context": f"quantity-takeoff:takeoff:{takeoff_id}",
                "digest_algorithm": "sha256"}

    def assert_conservation(self, result: dict) -> None:
        lines = [line for line in result.get("line_items", [])
                 if line.get("status") == "determinate"]
        expected_assemblies, expected_trades, expected_grand = self._build_rollups(lines)
        if result.get("assembly_rollups") != expected_assemblies:
            raise AssertionError("QT9 conservation drift: assembly rollups")
        if result.get("trade_rollups") != expected_trades:
            raise AssertionError("QT9 conservation drift: trade rollups")
        grand = result.get("grand_rollup", {})
        if grand.get("totals_by_unit") != expected_grand:
            raise AssertionError("QT9 conservation drift: grand rollup")
        if grand.get("determinate_line_count") != len(lines):
            raise AssertionError("QT9 conservation drift: determinate line count")
        for line in lines:
            exact = Decimal(line["exact_qty"])
            purchase = Decimal(line["purchase_qty"])
            increment = Decimal(line["purchase_rounding"]["increment"])
            if purchase < exact:
                raise AssertionError(f"QT7 conservative rounding drift: {line['id']}")
            if purchase % increment != 0:
                raise AssertionError(f"QT7 purchase increment drift: {line['id']}")

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
        expected_notary = self._notary_payload(supplied, "qt-" + supplied[:24])
        notary_valid = result.get("notary_payload") == expected_notary
        return {
            "valid": (bool(supplied) and supplied == computed
                      and conservation_valid and notary_valid),
            "audit_hash_valid": bool(supplied) and supplied == computed,
            "conservation_valid": conservation_valid,
            "conservation_error": conservation_error,
            "notary_payload_valid": notary_valid,
            "supplied_sha256": supplied,
            "computed_sha256": computed,
            "material_pack_current": (result.get("material_pack", {}).get("sha256")
                                      == MATERIAL_PACK_SHA256),
            "current_material_pack_sha256": MATERIAL_PACK_SHA256,
        }


def build(config: Optional[AgentConfig] = None) -> QuantityTakeoffCore:
    return QuantityTakeoffCore(config)
