"""Deterministic, source-linked compliance disclosure compiler.

DC1  Templates only: values come from explicit inputs; no generation/inference.
DC2  Framework schemas and sources are bundled, versioned, and hashed.
DC3  Missing required datapoints remain explicit MISSING gaps.
DC4  Every filled value cites its exact supplied fact or verified GHG field.
DC5  Supplied GHG inventories must pass the real GHG-ledger verifier and be current.
DC6  Canonical content produces a reproducible audit SHA and notary payload.
DC7  Framework applicability is explicit; only an explicit force can override it.
DC8  Every result is labeled a draft for professional review with a disclaimer.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Optional


VERSION = "0.1.0"
DATA_PATH = (Path(__file__).resolve().parents[1] / "data" /
             "framework_packs.v0.1.0.json")
_RAW_PACK = DATA_PATH.read_bytes()
PACK = json.loads(_RAW_PACK)
FRAMEWORK_PACK_SHA256 = hashlib.sha256(_RAW_PACK).hexdigest()
_SOURCE_BY_ID = {item["id"]: item for item in PACK["sources"]}
_DERIVED_FIELDS = frozenset({"audit_sha256", "notary_payload"})
_RATIO_QUANTUM = Decimal("0.000001")
_PERCENT_QUANTUM = Decimal("0.01")
_MISSING = object()


@dataclass
class AgentConfig:
    name: str = "disclosure-compiler-agent"
    version: str = VERSION
    debug: bool = False


class ValidationError(ValueError):
    def __init__(self, message: str, field: str = "", value: Any = None,
                 constraint: str = ""):
        super().__init__(message)
        self.field = field
        self.value = value
        self.constraint = constraint


class UnsupportedFrameworkError(ValidationError):
    pass


class ApplicabilityError(ValidationError):
    pass


class GHGVerificationError(ValidationError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _validate_json_values(value: Any, field: str) -> None:
    """Reject binary floats and non-JSON object types before canonical hashing."""
    if isinstance(value, float):
        raise ValidationError(
            f"'{field}' contains a binary float; use a decimal string",
            field, value, "JSON values with decimal quantities encoded as strings")
    if value is None or isinstance(value, (str, int, bool, Decimal)):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_values(item, f"{field}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValidationError(f"'{field}' object keys must be strings",
                                      field, type(key).__name__, "string keys")
            _validate_json_values(item, f"{field}.{key}")
        return
    raise ValidationError(f"'{field}' contains an unsupported value type",
                          field, type(value).__name__, "JSON-compatible values")


def _lookup(container: dict, path: str) -> Any:
    current: Any = container
    for component in path.split("."):
        if not isinstance(current, dict) or component not in current:
            return _MISSING
        current = current[component]
    return current


def _present(value: Any) -> bool:
    if value is _MISSING or value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _validate_pack() -> None:
    required_top = {"schema_version", "pack_version", "effective_as_of",
                    "disclaimer", "sources", "frameworks", "ghg_verifier"}
    if required_top - set(PACK):
        raise RuntimeError("DC2: framework pack is missing required top-level fields")
    if len(_SOURCE_BY_ID) != len(PACK["sources"]):
        raise RuntimeError("DC2: duplicate framework source id")
    if set(PACK["frameworks"]) != {"esrs-e1", "sec-climate", "ifrs-s2", "tnfd"}:
        raise RuntimeError("DC2: MVP framework coverage drift")
    for framework_id, framework in PACK["frameworks"].items():
        source_ids = set(framework.get("source_ids", []))
        if not source_ids or source_ids - set(_SOURCE_BY_ID):
            raise RuntimeError(f"DC2: invalid sources for {framework_id}")
        seen = set()
        for point in framework.get("datapoints", []):
            required = {"id", "label", "section", "requirement", "required",
                        "expected_input", "source_id"}
            if required - set(point):
                raise RuntimeError(f"DC2: malformed datapoint in {framework_id}")
            if point["id"] in seen:
                raise RuntimeError(f"DC2: duplicate datapoint {point['id']}")
            seen.add(point["id"])
            expected = point["expected_input"]
            if expected.get("source") not in {"company_facts", "ghg_result"}:
                raise RuntimeError(f"DC1: unsupported input source in {framework_id}")
            if not isinstance(expected.get("path"), str) or not expected["path"]:
                raise RuntimeError(f"DC4: missing input path in {framework_id}")
            if point["source_id"] not in _SOURCE_BY_ID:
                raise RuntimeError(f"DC2: unknown datapoint source in {framework_id}")


_validate_pack()


def _load_ghg_verifier():
    """Load the fleet's real GHG core without importing a colliding ``src``."""
    path = Path(__file__).resolve().parents[2] / "ghg-ledger-agent" / "src" / "core.py"
    if not path.is_file():
        raise GHGVerificationError(
            "GHG verifier is unavailable; supplied inventory cannot be trusted",
            "ghg_result", None, "current ghg-ledger core present")
    name = "viridis_disclosure_ghg_verifier"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise GHGVerificationError("GHG verifier could not be loaded")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module.build()


class DisclosureCompilerCore:
    KNOWN_ACTIONS = frozenset({
        "compile_disclosure", "list_frameworks", "get_framework",
        "verify_result",
    })
    READ_ACTIONS = frozenset({
        "list_frameworks", "get_framework", "verify_result",
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
                "framework_pack": PACK["pack_version"],
                "framework_pack_sha256": FRAMEWORK_PACK_SHA256,
                "frameworks": len(PACK["frameworks"]),
                "datapoints": sum(len(item["datapoints"])
                                  for item in PACK["frameworks"].values()),
                "inference_in_serving_path": False,
            },
        }

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": ("Deterministic, cited, gap-flagged disclosure drafts "
                            "for professional review."),
            "capabilities": ["compile_disclosure", "list_frameworks",
                             "get_framework", "verify_result"],
            "frameworks": sorted(PACK["frameworks"]),
            "framework_pack": {"version": PACK["pack_version"],
                               "sha256": FRAMEWORK_PACK_SHA256},
            "pricing": {"free_calls_per_day": 10,
                        "price_minor_per_compile": 200,
                        "currency": "USD"},
            "composition": ["regulatory-radar", "ghg-ledger", "notary",
                            "metering", "subscriptions"],
            "inference_in_serving_path": False,
            "label": "disclosure draft for professional review",
            "disclaimer": PACK["disclaimer"],
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
            if action == "compile_disclosure":
                facts = input_data.get("company_facts")
                options = input_data.get("options", {})
                ghg_result = input_data.get("ghg_result")
                if not isinstance(facts, dict):
                    raise ValidationError("'company_facts' must be an object",
                                          "company_facts", facts, "object")
                if not isinstance(options, dict):
                    raise ValidationError("'options' must be an object",
                                          "options", options, "object")
                if ghg_result is not None and not isinstance(ghg_result, dict):
                    raise ValidationError("'ghg_result' must be an object",
                                          "ghg_result", ghg_result, "object")
                return {"status": "ok", "data": self.compile_disclosure(
                    str(input_data.get("framework", "")), facts,
                    ghg_result, options)}
            if action == "list_frameworks":
                return {"status": "ok", "data": self.list_frameworks()}
            if action == "get_framework":
                return {"status": "ok", "data": self.get_framework(
                    str(input_data.get("framework", "")))}
            if action == "verify_result":
                result = input_data.get("result")
                if not isinstance(result, dict):
                    raise ValidationError("'result' must be an object",
                                          "result", result, "object")
                return {"status": "ok", "data": self.verify_result(result)}
            raise ValidationError(
                f"unknown action '{action}'", "action", action,
                "compile_disclosure|list_frameworks|get_framework|verify_result")
        except (UnsupportedFrameworkError, ApplicabilityError,
                GHGVerificationError, ValidationError) as exc:
            return self._err(str(exc), error_type=type(exc).__name__,
                             field=exc.field, value=exc.value,
                             constraint=exc.constraint)
        except Exception as exc:
            self.logger.exception("disclosure compiler process failed")
            return self._err(f"internal error: {exc}", error_type="RuntimeError")

    def list_frameworks(self) -> dict:
        return {
            "schema_version": PACK["schema_version"],
            "version": PACK["pack_version"],
            "effective_as_of": PACK["effective_as_of"],
            "sha256": FRAMEWORK_PACK_SHA256,
            "frameworks": [
                {"id": key, "name": value["name"], "status": value["status"],
                 "required_datapoints": sum(1 for item in value["datapoints"]
                                             if item["required"]),
                 "source_ids": deepcopy(value["source_ids"]),
                 **({"note": value["note"]} if value.get("note") else {})}
                for key, value in sorted(PACK["frameworks"].items())
            ],
            "unsupported_policy": "unsupported frameworks are rejected",
            "disclaimer": PACK["disclaimer"],
        }

    def get_framework(self, framework: str) -> dict:
        item = PACK["frameworks"].get(framework)
        if item is None:
            raise UnsupportedFrameworkError(
                f"unsupported framework '{framework}'", "framework", framework,
                "one of: " + ", ".join(sorted(PACK["frameworks"])))
        return {
            "id": framework,
            **deepcopy(item),
            "framework_pack": {"version": PACK["pack_version"],
                               "sha256": FRAMEWORK_PACK_SHA256},
            "sources": [deepcopy(_SOURCE_BY_ID[source_id])
                        for source_id in item["source_ids"]],
            "disclaimer": PACK["disclaimer"],
        }

    @staticmethod
    def _normalize_applicability(framework: str, options: dict) -> dict:
        force = options.get("force", False)
        if not isinstance(force, bool):
            raise ValidationError("'options.force' must be boolean",
                                  "options.force", force, "boolean")
        raw = options.get("applicability")
        record: Optional[dict] = None
        if isinstance(raw, dict):
            if "framework" in raw or "applies" in raw:
                record = raw
            elif framework in raw:
                candidate = raw[framework]
                record = candidate if isinstance(candidate, dict) else {
                    "framework": framework, "applies": candidate}
        elif isinstance(raw, list):
            matches = [item for item in raw if isinstance(item, dict)
                       and item.get("framework") == framework]
            if len(matches) > 1:
                raise ApplicabilityError(
                    "ambiguous applicability: multiple records for framework",
                    "options.applicability", framework, "exactly one record")
            record = matches[0] if matches else None
        if record is None:
            legacy = options.get("applicable_frameworks")
            if isinstance(legacy, list) and framework in legacy:
                record = {"framework": framework, "applies": True,
                          "reason": "included in options.applicable_frameworks",
                          "source": "caller"}
        applies = record.get("applies") if isinstance(record, dict) else None
        if applies not in {True, False}:
            if not force:
                raise ApplicabilityError(
                    "framework applicability must be supplied explicitly",
                    "options.applicability", raw,
                    "record with framework, applies:boolean, reason")
            applies = False
        if isinstance(record, dict) and record.get("framework") not in {None, framework}:
            raise ApplicabilityError("applicability record names another framework",
                                     "options.applicability.framework",
                                     record.get("framework"), framework)
        reason = record.get("reason") if isinstance(record, dict) else None
        source = record.get("source") if isinstance(record, dict) else None
        if not isinstance(reason, str) or not reason.strip():
            reason = "no applicability reason supplied"
        if not isinstance(source, str) or not source.strip():
            source = "caller"
        if not applies and not force:
            raise ApplicabilityError(
                f"framework '{framework}' is not applicable; set force:true "
                "only for an explicitly recorded scenario draft",
                "options.applicability.applies", applies, "true or force:true")
        return {"framework": framework, "applies": applies,
                "reason": reason.strip(), "source": source.strip(),
                "forced": force and not applies,
                "force_reason": (str(options.get("force_reason") or
                                     "explicit caller override")
                                 if force else None)}

    @staticmethod
    def _verify_ghg(ghg_result: dict) -> dict:
        verifier = _load_ghg_verifier()
        verification = verifier.verify_result(deepcopy(ghg_result))
        if (not verification.get("valid") or
                not verification.get("factor_pack_current")):
            raise GHGVerificationError(
                "GHG result failed audit verification or uses a stale factor pack",
                "ghg_result.audit_sha256", ghg_result.get("audit_sha256"),
                "valid current ghg-ledger result")
        expected = PACK["ghg_verifier"]
        factor_pack = ghg_result.get("factor_pack", {})
        if (factor_pack.get("version") != expected["factor_pack_version"] or
                factor_pack.get("sha256") != expected["factor_pack_sha256"]):
            raise GHGVerificationError(
                "GHG result lineage does not match the disclosure pack's pinned verifier",
                "ghg_result.factor_pack", factor_pack,
                f"{expected['factor_pack_version']} / {expected['factor_pack_sha256']}")
        return verification

    @staticmethod
    def _notary_payload(audit_sha256: str, framework: str) -> dict:
        return {
            "content_digest": audit_sha256,
            "context": (f"disclosure-compiler:draft:{framework}:"
                        f"{audit_sha256[:24]}"),
            "digest_algorithm": "sha256",
        }

    def compile_disclosure(self, framework: str, company_facts: dict,
                           ghg_result: Optional[dict] = None,
                           options: Optional[dict] = None) -> dict:
        options = options or {}
        schema = PACK["frameworks"].get(framework)
        if schema is None:
            raise UnsupportedFrameworkError(
                f"unsupported framework '{framework}'", "framework", framework,
                "one of: " + ", ".join(sorted(PACK["frameworks"])))
        _validate_json_values(company_facts, "company_facts")
        _validate_json_values(options, "options")
        if ghg_result is not None:
            _validate_json_values(ghg_result, "ghg_result")
        applicability = self._normalize_applicability(framework, options)
        ghg_verification = (self._verify_ghg(ghg_result)
                            if ghg_result is not None else None)

        filled = []
        gaps = []
        required_count = 0
        filled_required = 0
        for point in schema["datapoints"]:
            expected = point["expected_input"]
            source_name = expected["source"]
            container = company_facts if source_name == "company_facts" else ghg_result
            value = (_lookup(container, expected["path"])
                     if isinstance(container, dict) else _MISSING)
            if point["required"]:
                required_count += 1
            common = {
                "id": point["id"], "section": point["section"],
                "label": point["label"], "requirement": point["requirement"],
                "required": point["required"],
                "expected_input": deepcopy(expected),
                "framework_source_id": point["source_id"],
                **({"unit": point["unit"]} if point.get("unit") else {}),
            }
            if not _present(value):
                if point["required"]:
                    gaps.append({
                        **common,
                        "status": f"MISSING: {point['id']}",
                        "reason": (f"required datapoint not supplied at "
                                   f"{source_name}.{expected['path']}"),
                        "excluded_from_filled": True,
                    })
                continue
            if point["required"]:
                filled_required += 1
            data_citation = {
                "type": ("supplied_fact" if source_name == "company_facts"
                         else "verified_ghg_result"),
                "path": f"{source_name}.{expected['path']}",
            }
            if source_name == "ghg_result":
                data_citation.update({
                    "audit_sha256": ghg_result["audit_sha256"],
                    "factor_pack": deepcopy(ghg_result["factor_pack"]),
                })
            filled.append({
                **common, "status": "filled", "value": deepcopy(value),
                "citations": [
                    data_citation,
                    {"type": "framework_requirement",
                     "source": deepcopy(_SOURCE_BY_ID[point["source_id"]])},
                ],
            })

        ratio = (Decimal(filled_required) / Decimal(required_count)
                 if required_count else Decimal("1"))
        ratio_text = format(ratio.quantize(_RATIO_QUANTUM,
                                            rounding=ROUND_HALF_UP), "f")
        percent_text = format((ratio * Decimal("100")).quantize(
            _PERCENT_QUANTUM, rounding=ROUND_HALF_UP), "f")
        inputs = {"framework": framework,
                  "company_facts": deepcopy(company_facts),
                  "ghg_result": deepcopy(ghg_result),
                  "options": deepcopy(options)}
        source_ids_used = list(dict.fromkeys(
            [*schema["source_ids"],
             *(point["framework_source_id"] for point in filled)]))
        result = {
            "draft_status": ("complete" if not gaps else
                             "missing" if not filled else "partial"),
            "label": "disclosure draft for professional review",
            "framework": {
                "id": framework, "name": schema["name"],
                "status": schema["status"],
                **({"note": schema["note"]} if schema.get("note") else {}),
            },
            "applicability": applicability,
            "inputs": inputs,
            "input_sha256": _digest(inputs),
            "filled_datapoints": filled,
            "gaps": gaps,
            "completeness": {
                "filled_required": filled_required,
                "required": required_count,
                "missing_required": required_count - filled_required,
                "ratio": ratio_text,
                "percent": percent_text,
            },
            "ghg_provenance": ({
                "audit_sha256": ghg_result["audit_sha256"],
                "factor_pack": deepcopy(ghg_result["factor_pack"]),
                "verification": {
                    "valid": True, "factor_pack_current": True,
                    "computed_sha256": ghg_verification["computed_sha256"],
                },
            } if ghg_result is not None else None),
            "framework_pack": {
                "version": PACK["pack_version"],
                "effective_as_of": PACK["effective_as_of"],
                "sha256": FRAMEWORK_PACK_SHA256,
                "source_ids_used": source_ids_used,
                "sources_used": [deepcopy(_SOURCE_BY_ID[source_id])
                                 for source_id in source_ids_used],
            },
            "inference_used": False,
            "disclaimer": PACK["disclaimer"],
        }
        self._assert_structure(result)
        result["audit_sha256"] = _digest(result)
        result["notary_payload"] = self._notary_payload(
            result["audit_sha256"], framework)
        return result

    @staticmethod
    def _assert_structure(result: dict) -> None:
        filled = result["filled_datapoints"]
        gaps = result["gaps"]
        if any(not item.get("citations") for item in filled):
            raise AssertionError("DC4: filled datapoint without citation")
        if any(not str(item.get("status", "")).startswith("MISSING: ")
               for item in gaps):
            raise AssertionError("DC3: gap without explicit MISSING label")
        completeness = result["completeness"]
        required = completeness["required"]
        filled_required = sum(1 for item in filled if item["required"])
        missing_required = sum(1 for item in gaps if item["required"])
        if (filled_required != completeness["filled_required"] or
                missing_required != completeness["missing_required"] or
                filled_required + missing_required != required):
            raise AssertionError("DC3: completeness conservation drift")
        ratio = (Decimal(filled_required) / Decimal(required)
                 if required else Decimal("1"))
        if Decimal(completeness["ratio"]) != ratio.quantize(
                _RATIO_QUANTUM, rounding=ROUND_HALF_UP):
            raise AssertionError("DC3: completeness ratio drift")
        if result.get("label") != "disclosure draft for professional review":
            raise AssertionError("DC8: honest label drift")
        if result.get("inference_used") is not False:
            raise AssertionError("DC1: inference marker drift")

    def verify_result(self, result: dict) -> dict:
        supplied = str(result.get("audit_sha256", ""))
        content = deepcopy(result)
        for field in _DERIVED_FIELDS:
            content.pop(field, None)
        computed = _digest(content)
        try:
            self._assert_structure(result)
            structure_valid = True
            structure_error = None
        except (AssertionError, KeyError, TypeError, ValueError) as exc:
            structure_valid = False
            structure_error = str(exc)
        framework = result.get("framework", {}).get("id", "")
        expected_notary = (self._notary_payload(supplied, framework)
                           if supplied and isinstance(framework, str) else None)
        notary_payload_valid = result.get("notary_payload") == expected_notary
        pack_current = (result.get("framework_pack", {}).get("sha256")
                        == FRAMEWORK_PACK_SHA256)
        return {
            "valid": (bool(supplied) and supplied == computed and structure_valid
                      and notary_payload_valid),
            "audit_hash_valid": bool(supplied) and supplied == computed,
            "structure_valid": structure_valid,
            "structure_error": structure_error,
            "notary_payload_valid": notary_payload_valid,
            "supplied_sha256": supplied,
            "computed_sha256": computed,
            "framework_pack_current": pack_current,
            "current_framework_pack_sha256": FRAMEWORK_PACK_SHA256,
        }


def build(config: Optional[AgentConfig] = None) -> DisclosureCompilerCore:
    return DisclosureCompilerCore(config)
