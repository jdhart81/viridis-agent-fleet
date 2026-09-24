"""
SmartScaleCore: deterministic CR80 pixel-geometry scaling.

The production MCP does not receive or inspect images. Callers supply the
reference-card and object pixel geometry; SmartScale performs bounded,
deterministic conversion to millimetres.

--- INVARIANTS (spec-invariance contract; one test each in tests/test_invariants.py) ---
S1  process() never raises on malformed input; returns a structured error
    envelope {status:"error", error_type, message, timestamp}.
S2  Unknown action is rejected with a ValidationError envelope that names the
    supported actions.
S3  CR80 linear scaling: pixels_per_mm = credit_card_pixel_width / 85.60;
    object mm dimensions scale linearly and deterministically (same input ->
    same output).
S4  describe().name == health().agent; capabilities are non-empty.
S5  Unknown report_id -> error envelope, never a crash.
S6  A valid measure_from_credit_card call returns status "ok" with per-object
    dimensions_mm.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
import json
import uuid

from src.validation import validate_process_input, ValidationError
from src.version import SMARTSCALE_VERSION

logger = logging.getLogger(__name__)

CR80_CREDIT_CARD_WIDTH_MM = 85.60
CR80_CREDIT_CARD_HEIGHT_MM = 53.98
CREDIT_CARD_ASPECT_TOLERANCE_PCT = 8.0
CREDIT_CARD_ASPECT_REFUSAL_PCT = 15.0


@dataclass
class CalibrationReference:
    """Calibration reference object (coin, ruler, credit card)."""
    name: str
    actual_size_mm: float
    detection_confidence: float  # 0-1, how sure we are it's this object
    detected_pixel_size: Optional[float] = None
    calibration_ratio: Optional[float] = None  # pixels_per_mm


@dataclass
class MeasuredObject:
    """Measured object from image."""
    object_id: str
    label: str  # "object_1", "coin", etc.
    pixel_width: float
    pixel_height: float
    pixel_area: float
    pixel_perimeter: float
    real_width_mm: Optional[float] = None
    real_height_mm: Optional[float] = None
    real_area_mm2: Optional[float] = None
    real_perimeter_mm: Optional[float] = None
    confidence: float = 0.5  # Detection confidence 0-1
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MeasurementReport:
    """Complete measurement report for an image."""
    report_id: str
    image_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    calibration: Optional[CalibrationReference] = None
    objects: List[MeasuredObject] = field(default_factory=list)
    quality_score: float = 0.5  # 0-1, image quality assessment
    processing_time_ms: float = 0.0
    annotations: Dict[str, Any] = field(default_factory=dict)  # User labels, notes


class SmartScaleCore:
    """
    Vision-based measurement engine.

    Invariants:
    - Each report_id is unique
    - Calibration ratio is required before converting pixels to real dimensions
    - Measurements are only computed if calibration is available
    - Confidence scores guide measurement reliability
    - All dimensions include units (mm, mm2, mm)
    """
    KNOWN_ACTIONS = frozenset({
        "measure", "measure_from_credit_card", "get_report", "list_reports",
        "get_stats", "describe",
    })
    READ_ACTIONS = frozenset({
        "get_report", "list_reports", "get_stats", "describe",
    })

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}

        # Storage
        self.reports: Dict[str, MeasurementReport] = {}
        self.report_counter = 0
        self.object_counter = 0

        # Known calibration references
        self.calibration_references = {
            "us_penny": CalibrationReference(
                name="US Penny",
                actual_size_mm=19.05,
                detection_confidence=0.95
            ),
            "us_quarter": CalibrationReference(
                name="US Quarter",
                actual_size_mm=24.26,
                detection_confidence=0.95
            ),
            "credit_card": CalibrationReference(
                name="Credit Card",
                actual_size_mm=CR80_CREDIT_CARD_WIDTH_MM,
                detection_confidence=0.90
            ),
            "ruler_cm": CalibrationReference(
                name="Ruler (1cm mark)",
                actual_size_mm=10.0,
                detection_confidence=0.92
            )
        }

    def credit_card_photo_instructions(
        self,
        measurement_goal: str = "",
        objects_to_measure: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Return operator-facing instructions for CR80-calibrated pixel scaling.

        The public MCP never receives the image. A human, UI, or upstream
        vision system must supply the card and object pixel geometry.
        """
        objects_to_measure = objects_to_measure or []
        return {
            "status": "ok",
            "workflow": "credit_card_reference_measurement",
            "measurement_goal": measurement_goal,
            "objects_to_measure": objects_to_measure,
            "reference_object": {
                "name": "standard CR80-size card",
                "width_mm": CR80_CREDIT_CARD_WIDTH_MM,
                "height_mm": CR80_CREDIT_CARD_HEIGHT_MM,
            },
            "service_boundary": (
                "SmartScale does not receive or inspect the image. Supply the "
                "card and object pixel geometry from a human picker, UI, or "
                "upstream vision system."
            ),
            "user_instruction": (
                "Use a blank, expired, or fully masked CR80-size card. Place it "
                "flat in the same plane as the objects. Keep its outer edges "
                "visible, not bent, and near the objects. Capture straight-on "
                "when possible to reduce perspective distortion."
            ),
            "capture_checks": [
                "only the card outline is needed; never expose a PAN, expiry, CVV, signature, or cardholder name",
                "CR80-size card and measured objects are on the same flat plane",
                "camera is as square to the plane as possible",
                "object edges are visible and not hidden by shadows",
                "do not use the result for safety-critical or legal metrology without verification",
            ],
        }

    def scale_from_credit_card(
        self,
        image_id: str,
        credit_card_pixel_width: float,
        objects: List[Dict[str, Any]],
        credit_card_pixel_height: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Scale object pixel boxes from a standard CR80 credit card reference.

        Args:
            image_id: Unique image identifier.
            credit_card_pixel_width: Detected/picked pixel width of the card.
            objects: List of pixel measurements. Each object should contain
                pixel_width and pixel_height; pixel_area/perimeter are optional.
            credit_card_pixel_height: Optional detected/picked pixel height of
                the card, used as a consistency check.
        """
        if not image_id or not isinstance(image_id, str):
            raise ValueError("image_id must be a non-empty string")
        if credit_card_pixel_width <= 0:
            raise ValueError("credit_card_pixel_width must be > 0")
        if not objects:
            raise ValueError("objects must be a non-empty list")

        pixels_per_mm = credit_card_pixel_width / CR80_CREDIT_CARD_WIDTH_MM
        warnings = []
        height_pixels_per_mm = None
        aspect_error_pct = None

        if credit_card_pixel_height is not None:
            if credit_card_pixel_height <= 0:
                raise ValueError("credit_card_pixel_height must be > 0 if provided")
            height_pixels_per_mm = credit_card_pixel_height / CR80_CREDIT_CARD_HEIGHT_MM
            aspect_error_pct = abs(height_pixels_per_mm - pixels_per_mm) / pixels_per_mm * 100
            if aspect_error_pct > CREDIT_CARD_ASPECT_TOLERANCE_PCT:
                warnings.append(
                    "CR80 width/height scale disagreement suggests perspective "
                    "distortion; recapture straight-on."
                )
            if aspect_error_pct > CREDIT_CARD_ASPECT_REFUSAL_PCT:
                return {
                    "status": "error",
                    "error_type": "refused_distortion",
                    "action": "measure_from_credit_card",
                    "image_id": image_id,
                    "message": (
                        "Reference aspect disagreement exceeds the 15% safety "
                        "limit; no dimensions were returned."
                    ),
                    "calibration": {
                        "reference": "standard CR80-size card",
                        "standard_width_mm": CR80_CREDIT_CARD_WIDTH_MM,
                        "standard_height_mm": CR80_CREDIT_CARD_HEIGHT_MM,
                        "credit_card_pixel_width": credit_card_pixel_width,
                        "credit_card_pixel_height": credit_card_pixel_height,
                        "pixels_per_mm": pixels_per_mm,
                        "height_pixels_per_mm": height_pixels_per_mm,
                        "aspect_error_pct": aspect_error_pct,
                    },
                    "assumptions": ["coplanar_2d_geometry"],
                    "warnings": warnings,
                    "timestamp": datetime.utcnow().isoformat(),
                }

        scaled_objects = []
        rectangle_estimate_used = False
        for i, obj in enumerate(objects):
            pixel_width = float(obj.get("pixel_width", 0))
            pixel_height = float(obj.get("pixel_height", 0))
            if pixel_width <= 0 or pixel_height <= 0:
                raise ValueError(f"objects[{i}] pixel_width and pixel_height must be > 0")

            if obj.get("pixel_area") is None:
                rectangle_estimate_used = True
            if obj.get("pixel_perimeter") is None:
                rectangle_estimate_used = True
            pixel_area = float(obj.get("pixel_area") or (pixel_width * pixel_height))
            pixel_perimeter = float(obj.get("pixel_perimeter") or (2 * (pixel_width + pixel_height)))

            scaled = {
                "label": obj.get("label", f"object_{i + 1}"),
                "pixels": {
                    "width": pixel_width,
                    "height": pixel_height,
                    "area": pixel_area,
                    "perimeter": pixel_perimeter,
                },
                "dimensions_mm": {
                    "width": pixel_width / pixels_per_mm,
                    "height": pixel_height / pixels_per_mm,
                    "area_mm2": pixel_area / (pixels_per_mm ** 2),
                    "perimeter": pixel_perimeter / pixels_per_mm,
                },
            }
            if obj.get("confidence") is not None:
                scaled["input_confidence"] = obj["confidence"]
            scaled_objects.append(scaled)

        return {
            "status": "ok",
            "action": "measure_from_credit_card",
            "image_id": image_id,
            "calibration": {
                "reference": "standard CR80-size card",
                "standard_width_mm": CR80_CREDIT_CARD_WIDTH_MM,
                "standard_height_mm": CR80_CREDIT_CARD_HEIGHT_MM,
                "credit_card_pixel_width": credit_card_pixel_width,
                "credit_card_pixel_height": credit_card_pixel_height,
                "pixels_per_mm": pixels_per_mm,
                "height_pixels_per_mm": height_pixels_per_mm,
                "aspect_error_pct": aspect_error_pct,
            },
            "objects": scaled_objects,
            "assumptions": [
                "caller_supplied_pixel_geometry",
                "coplanar_2d_geometry",
                *(["rectangular_area_perimeter_estimate"]
                  if rectangle_estimate_used else []),
            ],
            "warnings": warnings,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def process_image(self, image_id: str, image_data: bytes,
                     detected_edges: List[Dict[str, Any]],
                     reference_type: Optional[str] = None) -> MeasurementReport:
        """
        Process an image and extract measurements.

        Args:
            image_id: Unique identifier for image
            image_data: Raw image bytes
            detected_edges: Pre-detected edges [{"contour": [...], "area": 100, ...}]
            reference_type: Calibration reference ("us_penny", "ruler_cm", etc.)

        Returns:
            Complete measurement report
        """
        self.report_counter += 1
        report_id = f"report_{self.report_counter}"

        report = MeasurementReport(
            report_id=report_id,
            image_id=image_id
        )

        # Step 1: Establish calibration
        calibration = None
        if reference_type:
            calibration = self._calibrate_from_reference(
                reference_type,
                detected_edges
            )
            report.calibration = calibration
        else:
            logger.warning(f"No calibration reference provided for {image_id}")

        # Step 2: Detect and measure objects
        report.objects = self._detect_and_measure_objects(
            detected_edges,
            calibration=report.calibration
        )

        # Step 3: Assess quality
        report.quality_score = self._assess_image_quality(
            image_data,
            len(report.objects),
            calibration is not None
        )

        # Store report
        self.reports[report_id] = report

        logger.info(f"Measurement report created: {report_id} ({len(report.objects)} objects)")

        return report

    def _calibrate_from_reference(self, reference_type: str,
                                 detected_edges: List[Dict]) -> Optional[CalibrationReference]:
        """
        Find and calibrate using a reference object.

        Assumes the largest contour is the reference (or manual specification).
        """
        if reference_type not in self.calibration_references:
            logger.error(f"Unknown reference type: {reference_type}")
            return None

        template = self.calibration_references[reference_type]

        if not detected_edges:
            logger.warning("No edges detected for calibration")
            return None

        # Find the reference in detected edges (usually the largest contour)
        largest_edge = max(detected_edges, key=lambda e: e.get("area", 0))

        calibration = CalibrationReference(
            name=template.name,
            actual_size_mm=template.actual_size_mm,
            detection_confidence=template.detection_confidence,
            detected_pixel_size=largest_edge.get("width", template.actual_size_mm)
        )

        # Compute calibration ratio (pixels per mm)
        if calibration.detected_pixel_size > 0:
            calibration.calibration_ratio = (
                calibration.detected_pixel_size / calibration.actual_size_mm
            )

        logger.info(f"Calibration established: {template.name} "
                   f"({calibration.calibration_ratio:.2f} px/mm)")

        return calibration

    def _detect_and_measure_objects(self, detected_edges: List[Dict],
                                   calibration: Optional[CalibrationReference]) -> List[MeasuredObject]:
        """
        Detect and measure all objects in the image.

        Skip the calibration reference itself (largest contour if calibrated).
        """
        objects = []

        for i, edge in enumerate(detected_edges):
            # Skip reference if it's the largest edge
            if calibration and i == 0 and edge.get("area") == max(e.get("area", 0) for e in detected_edges):
                continue

            obj = self._measure_object(edge, calibration)
            objects.append(obj)

        return objects

    def _measure_object(self, edge: Dict, calibration: Optional[CalibrationReference]) -> MeasuredObject:
        """Measure a single detected object."""
        self.object_counter += 1

        # Extract pixel measurements from edge
        pixel_width = edge.get("width", 0.0)
        pixel_height = edge.get("height", 0.0)
        pixel_area = edge.get("area", 0.0)
        pixel_perimeter = edge.get("perimeter", 0.0)

        obj = MeasuredObject(
            object_id=f"obj_{self.object_counter}",
            label=edge.get("label", f"object_{self.object_counter}"),
            pixel_width=pixel_width,
            pixel_height=pixel_height,
            pixel_area=pixel_area,
            pixel_perimeter=pixel_perimeter,
            confidence=edge.get("confidence", 0.5)
        )

        # Convert to real dimensions if calibrated
        if calibration and calibration.calibration_ratio and calibration.calibration_ratio > 0:
            ratio = calibration.calibration_ratio
            obj.real_width_mm = pixel_width / ratio
            obj.real_height_mm = pixel_height / ratio
            obj.real_area_mm2 = pixel_area / (ratio ** 2)
            obj.real_perimeter_mm = pixel_perimeter / ratio

        return obj

    def _assess_image_quality(self, image_data: bytes,
                             object_count: int,
                             has_calibration: bool) -> float:
        """Assess image quality for measurements."""
        score = 0.5

        # Image size penalty (too small or too large is bad)
        if 100_000 < len(image_data) < 5_000_000:
            score += 0.2
        else:
            score -= 0.1

        # Object detection bonus
        if object_count > 0:
            score += 0.15 * min(1.0, object_count / 5)  # Max 5 objects for bonus
        else:
            score -= 0.2

        # Calibration bonus
        if has_calibration:
            score += 0.2

        return max(0.0, min(1.0, score))

    def get_report(self, report_id: str) -> Optional[MeasurementReport]:
        """Get a measurement report."""
        return self.reports.get(report_id)

    def list_reports(self, limit: int = 50) -> List[MeasurementReport]:
        """List recent reports."""
        reports = sorted(
            self.reports.values(),
            key=lambda r: r.timestamp,
            reverse=True
        )
        return reports[:limit]

    def get_object_dimensions(self, report_id: str, object_id: str) -> Optional[Dict]:
        """Get dimensions of a specific measured object."""
        report = self.reports.get(report_id)
        if not report:
            return None

        for obj in report.objects:
            if obj.object_id == object_id:
                return {
                    "object_id": obj.object_id,
                    "label": obj.label,
                    "width_mm": obj.real_width_mm,
                    "height_mm": obj.real_height_mm,
                    "area_mm2": obj.real_area_mm2,
                    "perimeter_mm": obj.real_perimeter_mm,
                    "confidence": obj.confidence,
                    "calibrated": report.calibration is not None
                }

        return None

    def export_report_json(self, report_id: str) -> Optional[str]:
        """Export report as JSON."""
        report = self.reports.get(report_id)
        if not report:
            return None

        data = {
            "report_id": report.report_id,
            "image_id": report.image_id,
            "timestamp": report.timestamp.isoformat(),
            "quality_score": report.quality_score,
            "calibration": {
                "name": report.calibration.name,
                "ratio_px_per_mm": report.calibration.calibration_ratio
            } if report.calibration else None,
            "objects": [
                {
                    "object_id": obj.object_id,
                    "label": obj.label,
                    "pixels": {
                        "width": obj.pixel_width,
                        "height": obj.pixel_height,
                        "area": obj.pixel_area,
                        "perimeter": obj.pixel_perimeter
                    },
                    "real_dimensions": {
                        "width_mm": obj.real_width_mm,
                        "height_mm": obj.real_height_mm,
                        "area_mm2": obj.real_area_mm2,
                        "perimeter_mm": obj.real_perimeter_mm
                    } if obj.real_width_mm else None,
                    "confidence": obj.confidence
                }
                for obj in report.objects
            ]
        }

        return json.dumps(data, indent=2)

    def get_stats(self) -> Dict:
        """Get engine statistics."""
        reports = list(self.reports.values())

        total_objects = sum(len(r.objects) for r in reports)
        avg_quality = (
            sum(r.quality_score for r in reports) / len(reports)
            if reports else 0.0
        )

        calibrated_reports = sum(1 for r in reports if r.calibration)

        return {
            "total_reports": len(reports),
            "total_objects_measured": total_objects,
            "average_quality_score": avg_quality,
            "calibrated_reports": calibrated_reports,
            "uncalibrated_reports": len(reports) - calibrated_reports
        }

    def process(self, input_data: Dict) -> Dict:
        """
        Fleet-standard process() entry point for SmartScale.

        Routes to the appropriate measurement or reporting operation.

        Actions:
        - "measure": Process an image and extract object dimensions.
            Required: image_id (str), image_data (bytes or list of ints),
                      detected_edges (list of dicts)
            Optional: reference_type (str, calibration object name)
        - "get_report": Retrieve a completed measurement report by ID.
            Required: report_id (str)
        - "list_reports": List recent measurement reports.
            Optional: limit (int, default 50)
        - "get_stats": Return engine-level statistics.
        - "describe": Return agent capability manifest.

        Returns:
            {"status": "ok"|"error", "result": ..., "timestamp": ...}
        """
        if not isinstance(input_data, dict):
            return {
                "status": "error",
                "error_type": "ValidationError",
                "message": "input_data must be a dict",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # --- Validation gate ---
        try:
            input_data = validate_process_input(input_data)
        except ValidationError as ve:
            return {
                "status": "error",
                "error_type": "ValidationError",
                "field": ve.field,
                "message": str(ve),
                "timestamp": datetime.utcnow().isoformat(),
            }

        action = input_data.get("action", "measure")

        try:
            if action == "measure":
                image_id = input_data.get("image_id")
                image_data_raw = input_data.get("image_data", b"")
                detected_edges = input_data.get("detected_edges", [])
                reference_type = input_data.get("reference_type")

                if not image_id or not isinstance(image_id, str):
                    return {
                        "status": "error",
                        "message": "image_id is required and must be a string",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                if not isinstance(detected_edges, list):
                    return {
                        "status": "error",
                        "message": "detected_edges must be a list",
                        "timestamp": datetime.utcnow().isoformat(),
                    }

                # Accept bytes or list-of-ints (JSON-serializable form)
                if isinstance(image_data_raw, list):
                    image_data_bytes = bytes(image_data_raw)
                elif isinstance(image_data_raw, bytes):
                    image_data_bytes = image_data_raw
                else:
                    image_data_bytes = b""

                report = self.process_image(
                    image_id=image_id,
                    image_data=image_data_bytes,
                    detected_edges=detected_edges,
                    reference_type=reference_type,
                )

                result = json.loads(self.export_report_json(report.report_id) or "{}")
                return {
                    "status": "ok",
                    "action": "measure",
                    "result": result,
                    "timestamp": datetime.utcnow().isoformat(),
                }

            elif action == "measure_from_credit_card":
                result = self.scale_from_credit_card(
                    image_id=input_data["image_id"],
                    credit_card_pixel_width=input_data["credit_card_pixel_width"],
                    credit_card_pixel_height=input_data.get("credit_card_pixel_height"),
                    objects=input_data["objects"],
                )
                if result.get("status") != "ok":
                    return result
                return {
                    "status": "ok",
                    "action": "measure_from_credit_card",
                    "result": result,
                    "timestamp": datetime.utcnow().isoformat(),
                }

            elif action == "get_report":
                report_id = input_data.get("report_id")
                if not report_id or not isinstance(report_id, str):
                    return {
                        "status": "error",
                        "message": "report_id is required and must be a string",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                report = self.get_report(report_id)
                if report is None:
                    return {
                        "status": "error",
                        "message": f"Report '{report_id}' not found",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                result = json.loads(self.export_report_json(report_id) or "{}")
                return {
                    "status": "ok",
                    "action": "get_report",
                    "result": result,
                    "timestamp": datetime.utcnow().isoformat(),
                }

            elif action == "list_reports":
                limit = input_data.get("limit", 50)
                if not isinstance(limit, int) or limit < 1:
                    limit = 50
                reports = self.list_reports(limit=limit)
                return {
                    "status": "ok",
                    "action": "list_reports",
                    "result": {
                        "count": len(reports),
                        "reports": [
                            {
                                "report_id": r.report_id,
                                "image_id": r.image_id,
                                "timestamp": r.timestamp.isoformat(),
                                "objects_detected": len(r.objects),
                                "quality_score": r.quality_score,
                                "calibrated": r.calibration is not None,
                            }
                            for r in reports
                        ],
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                }

            elif action == "get_stats":
                return {
                    "status": "ok",
                    "action": "get_stats",
                    "result": self.get_stats(),
                    "timestamp": datetime.utcnow().isoformat(),
                }

            elif action == "describe":
                return {
                    "status": "ok",
                    "action": "describe",
                    "result": self.describe(),
                    "timestamp": datetime.utcnow().isoformat(),
                }

            else:
                return {
                    "status": "error",
                    "message": (
                        f"Unknown action '{action}'. "
                        "Valid: measure, measure_from_credit_card, get_report, "
                        "list_reports, get_stats, describe"
                    ),
                    "timestamp": datetime.utcnow().isoformat(),
                }

        except Exception as exc:
            logger.error("process() error for action=%s: %s", action, exc, exc_info=True)
            return {
                "status": "error",
                "message": str(exc),
                "timestamp": datetime.utcnow().isoformat(),
            }

    def describe(self) -> Dict:
        """Agent capability manifest — fleet standard interface."""
        return {
            "name": "smartscale-agent",
            "version": SMARTSCALE_VERSION,
            "description": (
                "Deterministically converts caller-supplied CR80 reference and "
                "coplanar object pixel geometry into millimetres. The public "
                "MCP does not receive images or detect cards or objects."
            ),
            "capabilities": [
                "deterministic_pixel_scaling",
                "cr80_reference_scaling",
                "perspective_sanity_check",
                "distortion_refusal",
            ],
            "inputs": {
                "measure_from_credit_card": {
                    "image_id": "str — caller-defined source identifier",
                    "credit_card_pixel_width": "finite float — caller-supplied CR80 card pixel width",
                    "credit_card_pixel_height": "finite float (optional) — caller-supplied height for distortion check",
                    "objects": "1..200 objects with bounded pixel_width and pixel_height",
                    "request_id": "str (optional) — retry-safe idempotency key",
                },
            },
            "outputs": {
                "measure_from_credit_card": (
                    "Deterministic millimetre dimensions, explicit assumptions, "
                    "and warning/refusal semantics"
                ),
            },
            "credit_card_reference": {
                "standard": "CR80",
                "width_mm": CR80_CREDIT_CARD_WIDTH_MM,
                "height_mm": CR80_CREDIT_CARD_HEIGHT_MM,
            },
            "claim_boundary": (
                "Non-safety-critical 2D scaling only. No image ingestion, "
                "object detection, legal metrology, or fabrication tolerance guarantee."
            ),
            "deploy_target": "remote_mcp_shared_gateway",
            "revenue_model": "$0.50 per state-changing scaling call after the free allowance",
        }

    def health(self) -> Dict:
        """Health check — fleet standard interface."""
        return {
            "status": "ok",
            "agent": "smartscale-agent",
            "version": SMARTSCALE_VERSION,
            "timestamp": datetime.utcnow().isoformat(),
            "reports_processed": len(self.reports),
            "capabilities": [
                "deterministic_pixel_scaling",
                "cr80_reference_scaling",
                "perspective_sanity_check",
                "distortion_refusal",
            ],
        }
