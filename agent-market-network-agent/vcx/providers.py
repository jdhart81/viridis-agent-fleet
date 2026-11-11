"""Fixed, bounded local providers; no user-selected code, paths or endpoints.

These are trusted existing deterministic functions, not an untrusted workload
runtime. Takeoff reads only its bundled, versioned material pack. No tool can
register executable providers, change imports, invoke a shell or fetch a URL.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from copy import deepcopy
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any


SUM_SERVICE = "vcx.test.integer_sum.v1"
TAKEOFF_SERVICE = "fleet.quantity_takeoff.v1"
MAX_INPUT_BYTES = 32_768
MAX_OUTPUT_BYTES = 1_048_576
MAX_VALUES = 1_000
MAX_ITEMS = 25
MAX_INTEGER = 1_000_000_000
_DECIMAL = re.compile(r"^(?:0|[1-9][0-9]{0,6})(?:\.[0-9]{1,6})?$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,39}$")
_SECRET = re.compile(
    r"(?:sk[-_](?:live|test|proj)[-_]|-----BEGIN |Bearer\s|gh[pousr]_|github_pat_)",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _takeoff_module():
    # The path and module identity are fixed by the installed fleet layout;
    # neither is read from a listing or task payload. Avoid the fleet's many
    # unrelated ``src.core`` modules sharing an import name.
    path = Path(__file__).resolve().parents[2] / "quantity-takeoff-agent" / "src" / "core.py"
    name = "_viridis_vcx_quantity_takeoff_v1"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("allowlisted fleet provider is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise ValueError("allowlisted fleet provider is unavailable") from None
    return module


def _bounded_json(value: Any, maximum: int) -> str:
    """Bound traversals before serialization, rejecting non-JSON and floats."""
    remaining = 10_000

    def walk(item: Any, depth: int = 0) -> None:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 12:
            raise ValueError("service payload exceeds resource limits")
        if item is None or type(item) in {bool, int}:
            if type(item) is int and abs(item) > 10**18:
                raise ValueError("service integer exceeds resource limits")
            return
        if type(item) is str:
            if len(item) > maximum or _SECRET.search(item):
                raise ValueError("service payload contains unsupported text")
            return
        if type(item) is list:
            if len(item) > MAX_VALUES:
                raise ValueError("service payload exceeds resource limits")
            for child in item:
                walk(child, depth + 1)
            return
        if type(item) is dict:
            if len(item) > 100:
                raise ValueError("service payload exceeds resource limits")
            for key, child in item.items():
                if type(key) is not str or len(key) > 128 or _SECRET.search(key):
                    raise ValueError("service payload has unsupported fields")
                walk(child, depth + 1)
            return
        raise ValueError("service payload must use bounded JSON without floats")

    walk(value)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    if len(encoded.encode("utf-8")) > maximum:
        raise ValueError("service payload exceeds resource limits")
    return encoded


class ProviderRegistry:
    """A compiled allowlist. There is deliberately no registration method."""

    def services(self) -> list[dict]:
        dimension_schema = {
            "type": "object", "additionalProperties": False,
            "required": ["value", "unit"],
            "properties": {
                "value": {"oneOf": [
                    {"type": "integer", "minimum": 1, "maximum": 1_000_000},
                    {"type": "string", "pattern": _DECIMAL.pattern,
                     "maxLength": 14}],
                    "description": "Positive decimal, at most 1000000."},
                "unit": {"enum": ["ft", "in", "yd", "m", "cm", "mm"]},
            },
        }
        return [
            {
                "service_id": SUM_SERVICE,
                "version": "1",
                "description": "Deterministic test provider summing bounded integers.",
                "capabilities": ["integer-sum", "data-processing"],
                "task_schema": {
                    "type": "object", "additionalProperties": False,
                    "required": ["values"],
                    "properties": {"values": {"type": "array", "minItems": 1,
                        "maxItems": MAX_VALUES, "items": {"type": "integer",
                            "minimum": -MAX_INTEGER, "maximum": MAX_INTEGER}}},
                },
                "execution": "trusted-local-allowlist",
                "network_access": False,
            },
            {
                "service_id": TAKEOFF_SERVICE,
                "version": "1",
                "description": "Fleet material-pack takeoff for up to 25 concrete slabs.",
                "capabilities": ["quantity-takeoff", "construction-estimation"],
                "task_schema": {
                    "type": "object", "additionalProperties": False,
                    "required": ["items"],
                    "properties": {"items": {"type": "array", "minItems": 1,
                        "maxItems": MAX_ITEMS, "items": {
                            "type": "object", "additionalProperties": False,
                            "required": ["assembly", "unit_system", "dimensions"],
                            "properties": {
                                "id": {"type": "string", "pattern": _IDENTIFIER.pattern},
                                "assembly": {"const": "concrete_slab"},
                                "unit_system": {"enum": ["imperial", "SI"]},
                                "dimensions": {"type": "object", "additionalProperties": False,
                                    "required": ["length", "width", "thickness"],
                                    "properties": {name: deepcopy(dimension_schema)
                                        for name in ("length", "width", "thickness")}},
                            },
                        }}, "options": {"type": "object",
                        "maxProperties": 0}},
                },
                "execution": "trusted-local-allowlist",
                "network_access": False,
                "claim_boundary": "Planning-grade quantity estimate for supplied dimensions.",
            },
        ]

    def validate(self, service_id: str, payload: dict) -> dict:
        if type(service_id) is not str or service_id not in {SUM_SERVICE, TAKEOFF_SERVICE}:
            raise ValueError("service is not allowlisted")
        _bounded_json(payload, MAX_INPUT_BYTES)
        if type(payload) is not dict:
            raise ValueError("service payload must be an object")
        if service_id == SUM_SERVICE:
            if set(payload) != {"values"}:
                raise ValueError("integer sum accepts only values")
            values = payload["values"]
            if type(values) is not list or not 1 <= len(values) <= MAX_VALUES:
                raise ValueError("integer sum requires bounded values")
            if any(type(value) is not int or abs(value) > MAX_INTEGER for value in values):
                raise ValueError("integer sum requires bounded integers")
            return deepcopy(payload)
        if set(payload) not in ({"items"}, {"items", "options"}):
            raise ValueError("takeoff accepts only items and empty options")
        if "options" in payload and payload["options"] != {}:
            raise ValueError("takeoff options must be empty")
        items = payload.get("items")
        if type(items) is not list or not 1 <= len(items) <= MAX_ITEMS:
            raise ValueError("takeoff requires bounded items")
        identifiers = set()
        for item in items:
            if type(item) is not dict or set(item) not in (
                {"assembly", "unit_system", "dimensions"},
                {"id", "assembly", "unit_system", "dimensions"},
            ):
                raise ValueError("takeoff item has unsupported fields")
            if (item["assembly"] != "concrete_slab"
                    or type(item["unit_system"]) is not str
                    or item["unit_system"] not in {"imperial", "SI"}):
                raise ValueError("takeoff supports concrete slabs with explicit units")
            if "id" in item:
                ident = item["id"]
                if type(ident) is not str or not _IDENTIFIER.fullmatch(ident) or ident in identifiers:
                    raise ValueError("takeoff item identifiers must be unique bounded labels")
                identifiers.add(ident)
            dimensions = item["dimensions"]
            if type(dimensions) is not dict or set(dimensions) != {"length", "width", "thickness"}:
                raise ValueError("takeoff requires length width and thickness")
            for dimension in dimensions.values():
                if type(dimension) is not dict or set(dimension) != {"value", "unit"}:
                    raise ValueError("takeoff dimensions require value and unit")
                number = dimension["value"]
                if type(number) is int:
                    number = str(number)
                if type(number) is not str or not _DECIMAL.fullmatch(number):
                    raise ValueError("takeoff dimensions require bounded decimal values")
                if not Decimal("0") < Decimal(number) <= Decimal("1000000"):
                    raise ValueError("takeoff dimensions require bounded positive values")
                if (type(dimension["unit"]) is not str
                        or dimension["unit"] not in {"ft", "in", "yd", "m", "cm", "mm"}):
                    raise ValueError("takeoff dimension unit is unsupported")
        return deepcopy(payload)

    def execute(self, service_id: str, payload: dict) -> dict:
        normalized = self.validate(service_id, payload)
        try:
            if service_id == SUM_SERVICE:
                output = {"sum": sum(normalized["values"]),
                          "count": len(normalized["values"])}
            else:
                output = _takeoff_module().QuantityTakeoffCore().calculate_takeoff(
                    normalized["items"], normalized.get("options", {}))
                if output["takeoff_status"] != "complete_for_supplied_items":
                    raise ValueError("takeoff was not complete")
            _bounded_json(output, MAX_OUTPUT_BYTES)
            return output
        except Exception:
            raise ValueError("allowlisted provider execution failed") from None

    def verify(self, service_id: str, payload: dict, output: dict) -> bool:
        """Verify exact acceptance by bounded deterministic recomputation."""
        try:
            supplied = _bounded_json(output, MAX_OUTPUT_BYTES)
            expected = _bounded_json(self.execute(service_id, payload), MAX_OUTPUT_BYTES)
            return supplied == expected
        except Exception:
            return False
