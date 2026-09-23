"""
Input validation for SmartScaleCore — guards the process() entry point against
malformed vision measurement inputs: unknown actions, missing IDs, invalid
image_data types, malformed detected_edges, and out-of-range limit values.

Cross-pollinated from fleet validation pattern (Nightkeeper 2026-04-16).

Usage:
    from src.validation import validate_process_input, ValidationError, ValidationWarning

    try:
        clean = validate_process_input(raw_data)
    except ValidationError as e:
        return {"status": "error", "error_type": "ValidationError", "message": str(e)}
"""

import logging
import math
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Valid action strings for process() router
VALID_ACTIONS = frozenset({
    "measure", "measure_from_credit_card", "get_report", "list_reports", "get_stats", "describe",
})

# Known calibration reference types (from SmartScaleCore.__init__)
KNOWN_REFERENCE_TYPES = frozenset({
    "us_penny", "us_quarter", "credit_card", "ruler_cm",
})

# Reasonable limits for list_reports
LIST_LIMIT_MIN = 1
LIST_LIMIT_MAX = 1000
LIST_LIMIT_DEFAULT = 50

# Deterministic-scaler request bounds. These limits are deliberately generous
# for ordinary photos while preventing one request from monopolizing the
# shared gateway or producing non-finite "successful" measurements.
CREDIT_CARD_OBJECTS_MAX = 200
OBJECT_LABEL_MAX = 128
PIXEL_DIMENSION_MIN = 1e-3
PIXEL_DIMENSION_MAX = 1e7
PIXEL_AREA_MAX = PIXEL_DIMENSION_MAX ** 2
PIXEL_PERIMETER_MAX = PIXEL_DIMENSION_MAX * 4


# ---------------------------------------------------------------------------
# Sentinel types
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    """Raised when an input invariant is violated — blocks processing."""

    def __init__(self, field: str, value: Any, reason: str) -> None:
        self.field = field
        self.value = value
        self.reason = reason
        super().__init__(f"[{field}] {reason} (got: {value!r})")


class ValidationWarning:
    """Advisory — emitted when an input is unusual but not blocking."""

    def __init__(self, field: str, value: Any, advisory: str) -> None:
        self.field = field
        self.value = value
        self.advisory = advisory
        logger.warning("ValidationWarning [%s]: %s (value: %r)", field, advisory, value)

    def __repr__(self) -> str:
        return f"ValidationWarning(field={self.field!r}, advisory={self.advisory!r})"


# ---------------------------------------------------------------------------
# Field-level validators
# ---------------------------------------------------------------------------

def _validate_action(data: dict) -> str:
    """Validate and return the action field."""
    action = data.get("action", "measure")
    if not isinstance(action, str) or action not in VALID_ACTIONS:
        raise ValidationError(
            "action", action,
            f"must be one of {sorted(VALID_ACTIONS)}"
        )
    return action


def _validate_image_id(data: dict, required: bool = True) -> str:
    """Validate image_id: non-empty string."""
    image_id = data.get("image_id")
    if image_id is None:
        if required:
            raise ValidationError("image_id", None, "required for 'measure' action")
        return ""
    if not isinstance(image_id, str) or not image_id.strip():
        raise ValidationError("image_id", image_id, "must be a non-empty string")
    if len(image_id) > 512:
        raise ValidationError("image_id", image_id[:32] + "...", "must be ≤512 characters")
    return image_id.strip()


def _validate_image_data(data: dict) -> Any:
    """
    Validate image_data: bytes or list-of-ints (JSON-serializable form).
    A completely absent or empty image_data is allowed (will produce low-confidence report).
    """
    image_data = data.get("image_data", b"")
    if isinstance(image_data, bytes):
        if len(image_data) == 0:
            ValidationWarning(
                "image_data", "<empty bytes>",
                "image_data is empty — measurement will have no pixel content; "
                "result quality_score will be 0.0"
            )
        return image_data
    if isinstance(image_data, list):
        # Validate all elements are ints in [0, 255] — catch corrupted payloads early
        for i, v in enumerate(image_data[:100]):  # sample first 100
            if not isinstance(v, int) or not (0 <= v <= 255):
                raise ValidationError(
                    f"image_data[{i}]", v,
                    "image_data as list must contain integers in [0, 255] (byte values)"
                )
        if len(image_data) == 0:
            ValidationWarning(
                "image_data", "<empty list>",
                "image_data list is empty — quality_score will be 0.0"
            )
        return image_data
    raise ValidationError(
        "image_data", type(image_data).__name__,
        "must be bytes or list-of-ints (JSON-serializable byte array)"
    )


def _validate_detected_edges(data: dict) -> List[Dict]:
    """
    Validate detected_edges: list of dicts, each with at least an 'area' key.
    An empty list is valid (no objects found) but emits a warning.
    """
    edges = data.get("detected_edges", [])
    if not isinstance(edges, list):
        raise ValidationError(
            "detected_edges", type(edges).__name__,
            "must be a list of edge dicts (e.g. [{\"contour\": [...], \"area\": 100}])"
        )
    if len(edges) == 0:
        ValidationWarning(
            "detected_edges", [],
            "detected_edges is empty — no objects will be measured; "
            "report will contain 0 MeasuredObjects"
        )
    for i, edge in enumerate(edges[:50]):  # validate first 50
        if not isinstance(edge, dict):
            raise ValidationError(
                f"detected_edges[{i}]", type(edge).__name__,
                "each edge must be a dict with at minimum an 'area' key"
            )
    return edges


def _validate_positive_number(
    data: dict,
    field: str,
    required: bool = True,
    *,
    minimum: float = PIXEL_DIMENSION_MIN,
    maximum: float = PIXEL_DIMENSION_MAX,
) -> Any:
    """Validate a finite positive numeric field inside explicit bounds."""
    value = data.get(field)
    if value is None:
        if required:
            raise ValidationError(field, None, "field is required")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(field, value, "must be a finite positive number")
    if not math.isfinite(value):
        raise ValidationError(field, value, "must be finite")
    if not minimum <= value <= maximum:
        raise ValidationError(
            field, value, f"must be between {minimum:g} and {maximum:g}"
        )
    return float(value)


def _validate_credit_card_objects(data: dict) -> List[Dict]:
    """Validate object pixel boxes for credit-card scaling."""
    objects = data.get("objects", [])
    if not isinstance(objects, list) or not objects:
        raise ValidationError(
            "objects", objects,
            "must be a non-empty list of objects with pixel_width and pixel_height"
        )
    if len(objects) > CREDIT_CARD_OBJECTS_MAX:
        raise ValidationError(
            "objects", f"<{len(objects)} objects>",
            f"must contain at most {CREDIT_CARD_OBJECTS_MAX} objects"
        )
    cleaned: List[Dict] = []
    for i, obj in enumerate(objects):
        if not isinstance(obj, dict):
            raise ValidationError(f"objects[{i}]", type(obj).__name__, "must be a dict")
        clean_obj = dict(obj)
        label = obj.get("label")
        if label is not None:
            if not isinstance(label, str):
                raise ValidationError(
                    f"objects[{i}].label", label, "must be a string if provided"
                )
            label = label.strip()
            if not label:
                raise ValidationError(
                    f"objects[{i}].label", label, "must not be empty if provided"
                )
            if len(label) > OBJECT_LABEL_MAX:
                raise ValidationError(
                    f"objects[{i}].label", label[:32] + "...",
                    f"must be at most {OBJECT_LABEL_MAX} characters"
                )
            clean_obj["label"] = label
        for field in ("pixel_width", "pixel_height"):
            value = obj.get(field)
            if (isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not PIXEL_DIMENSION_MIN <= value <= PIXEL_DIMENSION_MAX):
                raise ValidationError(
                    f"objects[{i}].{field}", value,
                    f"must be finite and between {PIXEL_DIMENSION_MIN:g} "
                    f"and {PIXEL_DIMENSION_MAX:g}"
                )
            clean_obj[field] = float(value)
        for field in ("pixel_area", "pixel_perimeter"):
            if field in obj and obj[field] is not None:
                value = obj[field]
                maximum = (PIXEL_AREA_MAX if field == "pixel_area"
                           else PIXEL_PERIMETER_MAX)
                if (isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value)
                        or not PIXEL_DIMENSION_MIN <= value <= maximum):
                    raise ValidationError(
                        f"objects[{i}].{field}", value,
                        f"must be finite and between {PIXEL_DIMENSION_MIN:g} "
                        f"and {maximum:g} if provided"
                    )
                clean_obj[field] = float(value)
        if "confidence" in obj and obj["confidence"] is not None:
            confidence = obj["confidence"]
            if (isinstance(confidence, bool)
                    or not isinstance(confidence, (int, float))
                    or not math.isfinite(confidence)
                    or not 0 <= confidence <= 1):
                raise ValidationError(
                    f"objects[{i}].confidence", confidence,
                    "must be finite and between 0 and 1 if provided"
                )
            clean_obj["confidence"] = float(confidence)
        cleaned.append(clean_obj)
    return cleaned


def _validate_reference_type(data: dict) -> Any:
    """
    Validate reference_type (optional). If provided and not in known types, warn.
    Unknown types are allowed — SmartScaleCore may support dynamic calibration in future.
    """
    ref = data.get("reference_type")
    if ref is None:
        return None
    if not isinstance(ref, str) or not ref.strip():
        raise ValidationError(
            "reference_type", ref,
            "must be a non-empty string or omitted"
        )
    ref = ref.strip()
    if ref not in KNOWN_REFERENCE_TYPES:
        ValidationWarning(
            "reference_type", ref,
            f"unknown reference type — known types are {sorted(KNOWN_REFERENCE_TYPES)}; "
            "calibration will be skipped if this type is not registered"
        )
    return ref


def _validate_report_id(data: dict) -> str:
    """Validate report_id: non-empty string."""
    report_id = data.get("report_id")
    if report_id is None:
        raise ValidationError("report_id", None, "required for 'get_report' action")
    if not isinstance(report_id, str) or not report_id.strip():
        raise ValidationError("report_id", report_id, "must be a non-empty string")
    return report_id.strip()


def _validate_limit(data: dict) -> int:
    """Validate limit for list_reports: positive int, clamped to [1, 1000]."""
    limit = data.get("limit", LIST_LIMIT_DEFAULT)
    if not isinstance(limit, int) or isinstance(limit, bool):
        ValidationWarning(
            "limit", limit,
            f"non-integer limit ignored; using default {LIST_LIMIT_DEFAULT}"
        )
        return LIST_LIMIT_DEFAULT
    if limit < LIST_LIMIT_MIN:
        raise ValidationError(
            "limit", limit,
            f"must be a positive integer ≥ {LIST_LIMIT_MIN}"
        )
    if limit > LIST_LIMIT_MAX:
        ValidationWarning(
            "limit", limit,
            f"limit > {LIST_LIMIT_MAX} may impact performance; clamped to {LIST_LIMIT_MAX}"
        )
        return LIST_LIMIT_MAX
    return limit


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

def validate_process_input(data: dict) -> Dict[str, Any]:
    """
    Validate a process() input dict for SmartScaleCore.

    Raises ValidationError if a blocking invariant is violated.
    Emits ValidationWarning (via logger) for advisory conditions.

    Returns a cleaned copy of the input dict with normalized values.
    """
    if not isinstance(data, dict):
        raise ValidationError("input", type(data).__name__, "process() input must be a dict")

    out: Dict[str, Any] = dict(data)
    action = _validate_action(data)
    out["action"] = action

    if action == "measure":
        out["image_id"] = _validate_image_id(data, required=True)
        out["image_data"] = _validate_image_data(data)
        out["detected_edges"] = _validate_detected_edges(data)
        out["reference_type"] = _validate_reference_type(data)

    elif action == "measure_from_credit_card":
        out["image_id"] = _validate_image_id(data, required=True)
        out["credit_card_pixel_width"] = _validate_positive_number(
            data, "credit_card_pixel_width", required=True
        )
        out["credit_card_pixel_height"] = _validate_positive_number(
            data, "credit_card_pixel_height", required=False
        )
        out["objects"] = _validate_credit_card_objects(data)

    elif action == "get_report":
        out["report_id"] = _validate_report_id(data)

    elif action == "list_reports":
        out["limit"] = _validate_limit(data)

    elif action in ("get_stats", "describe"):
        pass  # No required fields for these read-only actions

    return out


# ---------------------------------------------------------------------------
# Inline tests (run with: python -m src.validation)
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    import sys
    passed = 0
    failed = 0

    def check(label: str, fn, expect_error: bool = False):
        nonlocal passed, failed
        try:
            result = fn()
            if expect_error:
                print(f"  FAIL [{label}]: expected ValidationError, got result: {result}")
                failed += 1
            else:
                print(f"  PASS [{label}]")
                passed += 1
        except ValidationError as e:
            if expect_error:
                print(f"  PASS [{label}]: caught expected error: {e}")
                passed += 1
            else:
                print(f"  FAIL [{label}]: unexpected ValidationError: {e}")
                failed += 1
        except Exception as e:
            print(f"  FAIL [{label}]: unexpected exception {type(e).__name__}: {e}")
            failed += 1

    print("\n=== validate_process_input: action ===")
    check("valid action: measure",
          lambda: validate_process_input({"action": "measure", "image_id": "img1", "image_data": b"\x00", "detected_edges": []}))
    check("valid action: get_report",
          lambda: validate_process_input({"action": "get_report", "report_id": "r1"}))
    check("valid action: list_reports",
          lambda: validate_process_input({"action": "list_reports", "limit": 10}))
    check("valid action: get_stats",
          lambda: validate_process_input({"action": "get_stats"}))
    check("valid action: describe",
          lambda: validate_process_input({"action": "describe"}))
    check("invalid action: unknown",
          lambda: validate_process_input({"action": "fly"}), expect_error=True)
    check("invalid action: empty string",
          lambda: validate_process_input({"action": ""}), expect_error=True)

    print("\n=== validate_image_id ===")
    check("valid image_id",
          lambda: validate_process_input({"action": "measure", "image_id": "cam1_frame_042", "image_data": b"\xff", "detected_edges": []}))
    check("missing image_id for measure",
          lambda: validate_process_input({"action": "measure", "image_data": b""}), expect_error=True)
    check("empty image_id",
          lambda: validate_process_input({"action": "measure", "image_id": "", "image_data": b""}), expect_error=True)
    check("image_id too long",
          lambda: validate_process_input({"action": "measure", "image_id": "x" * 513, "image_data": b""}), expect_error=True)

    print("\n=== validate_image_data ===")
    check("valid bytes",
          lambda: validate_process_input({"action": "measure", "image_id": "i1", "image_data": b"\x01\x02\x03", "detected_edges": []}))
    check("valid list-of-ints",
          lambda: validate_process_input({"action": "measure", "image_id": "i1", "image_data": [0, 128, 255], "detected_edges": []}))
    check("invalid list element (float)",
          lambda: validate_process_input({"action": "measure", "image_id": "i1", "image_data": [0, 1.5, 255], "detected_edges": []}), expect_error=True)
    check("invalid list element (out of range)",
          lambda: validate_process_input({"action": "measure", "image_id": "i1", "image_data": [0, 300, 255], "detected_edges": []}), expect_error=True)
    check("invalid type (string)",
          lambda: validate_process_input({"action": "measure", "image_id": "i1", "image_data": "jpeg_data", "detected_edges": []}), expect_error=True)

    print("\n=== validate_detected_edges ===")
    check("valid edges",
          lambda: validate_process_input({"action": "measure", "image_id": "i1", "image_data": b"\x01", "detected_edges": [{"contour": [], "area": 100}, {"area": 50}]}))
    check("invalid edges (not a list)",
          lambda: validate_process_input({"action": "measure", "image_id": "i1", "image_data": b"\x01", "detected_edges": "none"}), expect_error=True)
    check("invalid edge element (not a dict)",
          lambda: validate_process_input({"action": "measure", "image_id": "i1", "image_data": b"\x01", "detected_edges": ["bad"]}), expect_error=True)

    print("\n=== validate_reference_type ===")
    check("valid known reference_type",
          lambda: validate_process_input({"action": "measure", "image_id": "i1", "image_data": b"\x01", "detected_edges": [], "reference_type": "us_penny"}))
    check("unknown reference_type (warn only)",
          lambda: validate_process_input({"action": "measure", "image_id": "i1", "image_data": b"\x01", "detected_edges": [], "reference_type": "custom_chip"}))
    check("invalid reference_type (int)",
          lambda: validate_process_input({"action": "measure", "image_id": "i1", "image_data": b"\x01", "detected_edges": [], "reference_type": 42}), expect_error=True)

    print("\n=== validate_report_id ===")
    check("valid report_id",
          lambda: validate_process_input({"action": "get_report", "report_id": "rpt-001"}))
    check("missing report_id",
          lambda: validate_process_input({"action": "get_report"}), expect_error=True)
    check("empty report_id",
          lambda: validate_process_input({"action": "get_report", "report_id": ""}), expect_error=True)

    print("\n=== validate_limit ===")
    check("valid limit",
          lambda: validate_process_input({"action": "list_reports", "limit": 25}))
    check("limit = 0 (invalid)",
          lambda: validate_process_input({"action": "list_reports", "limit": 0}), expect_error=True)
    check("limit > 1000 (clamped, warn)",
          lambda: validate_process_input({"action": "list_reports", "limit": 9999}))
    check("non-int limit (default applied, warn)",
          lambda: validate_process_input({"action": "list_reports", "limit": "all"}))

    print(f"\n=== Results: {passed} passed, {failed} failed ===")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    _run_tests()
