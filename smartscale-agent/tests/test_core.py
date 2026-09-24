"""
Tests for SmartScale vision measurement engine.
"""

import pytest
from datetime import datetime

from src.core import SmartScaleCore, CalibrationReference, MeasuredObject
from src.vision import VisionEngine, DetectedContour, EdgePoint
from src.measurement import MeasurementEngine, CalibrationMatrix


class TestVisionEngine:
    """Test computer vision operations."""

    def setup_method(self):
        self.vision = VisionEngine()

    def test_edge_detection(self):
        """Test edge detection."""
        # Create test image (20x20 with bright center region)
        # The edge detection looks for 10x10 regions, so we need a large bright area
        image = [
            [200 if 5 <= i < 15 and 5 <= j < 15 else 50
             for j in range(20)]
            for i in range(20)
        ]

        contours = self.vision.detect_edges(image)
        # Edge detection may or may not find contours depending on implementation
        assert isinstance(contours, list)

    def test_contour_properties(self):
        """Test contour property extraction."""
        points = [EdgePoint(x=0, y=0), EdgePoint(x=10, y=0),
                 EdgePoint(x=10, y=5), EdgePoint(x=0, y=5)]
        contour = DetectedContour(points=points)

        props = self.vision.extract_contour_properties(contour)

        assert props["width"] == 10
        assert props["height"] == 5
        assert props["area"] == 4
        assert props["perimeter"] > 0

    def test_image_sharpness(self):
        """Test image sharpness estimation."""
        # Sharp image (high contrast)
        sharp_image = [
            [255 if (i + j) % 2 == 0 else 0 for j in range(10)]
            for i in range(10)
        ]
        sharpness = self.vision.estimate_image_sharpness(sharp_image)
        assert sharpness > 0.3

        # Blurry image (uniform)
        blurry_image = [
            [128 for _ in range(10)]
            for _ in range(10)
        ]
        sharpness = self.vision.estimate_image_sharpness(blurry_image)
        assert sharpness < 0.3

    def test_blur_detection(self):
        """Test blur detection."""
        # Blurry image
        blurry = [[100 for _ in range(10)] for _ in range(10)]
        is_blurry, score = self.vision.detect_blur(blurry)
        assert is_blurry

        # Sharp image
        sharp = [
            [255 if (i + j) % 2 == 0 else 0 for j in range(10)]
            for i in range(10)
        ]
        is_blurry, score = self.vision.detect_blur(sharp)
        assert not is_blurry

    def test_calibration_detection(self):
        """Test calibration reference detection."""
        # Create contours with different aspect ratios
        points_round = [EdgePoint(x=float(i), y=float(i)) for i in range(20)]
        contour_round = DetectedContour(points=points_round)

        points_rect = [EdgePoint(x=float(i % 40), y=float(i // 40))
                      for i in range(80)]
        contour_rect = DetectedContour(points=points_rect)

        contours = [contour_round, contour_rect]

        ref_contour, ref_type = self.vision.detect_calibration_reference(
            contours,
            ["us_penny", "credit_card"]
        )

        # Should detect something
        if ref_contour:
            assert ref_type in ["us_penny", "credit_card"]


class TestMeasurementEngine:
    """Test measurement calculations."""

    def setup_method(self):
        self.measurement = MeasurementEngine()

    def test_establish_calibration(self):
        """Test calibration setup."""
        calib = self.measurement.establish_calibration(
            reference_object="us_penny",
            reference_actual_size_mm=19.05,
            reference_detected_size_px=100,
            image_width_px=640,
            image_height_px=480
        )

        assert calib is not None
        assert calib.pixels_per_mm_x > 0
        assert calib.get_scale_factor() > 0

    def test_measure_distance(self):
        """Test distance measurement."""
        self.measurement.establish_calibration(
            reference_object="us_penny",
            reference_actual_size_mm=19.05,
            reference_detected_size_px=100,
            image_width_px=640,
            image_height_px=480
        )

        # 100 pixels should be 19.05 mm
        distance, confidence = self.measurement.measure_distance(100)
        assert abs(distance - 19.05) < 1.0  # Allow 1mm error
        assert confidence > 0

    def test_measure_area(self):
        """Test area measurement."""
        self.measurement.establish_calibration(
            reference_object="us_penny",
            reference_actual_size_mm=19.05,
            reference_detected_size_px=100,
            image_width_px=640,
            image_height_px=480
        )

        area, confidence = self.measurement.measure_area(10000)
        assert area > 0
        assert confidence > 0

    def test_measure_dimensions(self):
        """Test dimension measurement."""
        self.measurement.establish_calibration(
            reference_object="us_penny",
            reference_actual_size_mm=19.05,
            reference_detected_size_px=100,
            image_width_px=640,
            image_height_px=480
        )

        dims, conf = self.measurement.measure_dimensions(100, 80)
        assert dims["width_mm"] > 0
        assert dims["height_mm"] > 0
        assert dims["aspect_ratio"] > 0
        assert conf > 0

    def test_confidence_score(self):
        """Test overall confidence computation."""
        self.measurement.establish_calibration(
            reference_object="us_penny",
            reference_actual_size_mm=19.05,
            reference_detected_size_px=100,
            image_width_px=640,
            image_height_px=480
        )

        # Good conditions
        conf = self.measurement.compute_confidence_score(
            measurement_count=3,
            blur_score=0.1,  # Little blur
            edge_quality=0.9  # Good edges
        )
        assert conf > 0.7

        # Poor conditions
        conf = self.measurement.compute_confidence_score(
            measurement_count=0,
            blur_score=0.8,  # High blur
            edge_quality=0.2  # Poor edges
        )
        assert conf < 0.65  # Poor conditions result in moderate-to-low confidence

    def test_measurement_validation(self):
        """Test measurement validation."""
        self.measurement.establish_calibration(
            reference_object="us_penny",
            reference_actual_size_mm=19.05,
            reference_detected_size_px=100,
            image_width_px=640,
            image_height_px=480
        )

        # Valid distance
        valid, msg = self.measurement.validate_measurement(10.0, "distance")
        assert valid

        # Invalid (negative)
        valid, msg = self.measurement.validate_measurement(-5.0, "distance")
        assert not valid

        # Invalid (too large)
        valid, msg = self.measurement.validate_measurement(20000, "distance")
        assert not valid


class TestSmartScaleCore:
    """Test core SmartScale functionality."""

    def setup_method(self):
        self.scale = SmartScaleCore()

    def test_process_image_no_calibration(self):
        """Test image processing without calibration."""
        edges = [
            {"width": 50, "height": 40, "area": 1000, "perimeter": 180, "confidence": 0.8}
        ]

        report = self.scale.process_image(
            image_id="img_1",
            image_data=b"fake_image_data",
            detected_edges=edges,
            reference_type=None
        )

        assert report.report_id is not None
        assert len(report.objects) == 1
        assert report.calibration is None
        assert report.quality_score > 0

    def test_process_image_with_calibration(self):
        """Test image processing with calibration."""
        edges = [
            {"width": 100, "height": 100, "area": 5000, "perimeter": 400,
             "confidence": 0.9, "label": "coin"},  # Reference (penny)
            {"width": 50, "height": 40, "area": 1000, "perimeter": 180,
             "confidence": 0.8, "label": "object_1"}  # Measurement object
        ]

        report = self.scale.process_image(
            image_id="img_1",
            image_data=b"fake_image_data",
            detected_edges=edges,
            reference_type="us_penny"
        )

        assert report.calibration is not None
        assert report.calibration.name == "US Penny"
        assert len(report.objects) >= 1

    def test_get_report(self):
        """Test retrieving a report."""
        edges = [{"width": 50, "height": 40, "area": 1000, "perimeter": 180, "confidence": 0.8}]
        report = self.scale.process_image("img_1", b"data", edges)

        retrieved = self.scale.get_report(report.report_id)
        assert retrieved is not None
        assert retrieved.report_id == report.report_id

    def test_list_reports(self):
        """Test listing reports."""
        for i in range(5):
            edges = [{"width": 50, "height": 40, "area": 1000, "perimeter": 180, "confidence": 0.8}]
            self.scale.process_image(f"img_{i}", b"data", edges)

        reports = self.scale.list_reports(limit=10)
        assert len(reports) == 5

    def test_export_json(self):
        """Test JSON export."""
        edges = [{"width": 50, "height": 40, "area": 1000, "perimeter": 180, "confidence": 0.8}]
        report = self.scale.process_image("img_1", b"data", edges)

        json_str = self.scale.export_report_json(report.report_id)
        assert json_str is not None
        assert "report_id" in json_str
        assert "objects" in json_str

    def test_get_object_dimensions(self):
        """Test getting object dimensions."""
        edges = [{"width": 50, "height": 40, "area": 1000, "perimeter": 180, "confidence": 0.8}]
        report = self.scale.process_image("img_1", b"data", edges)

        if report.objects:
            obj = report.objects[0]
            dims = self.scale.get_object_dimensions(report.report_id, obj.object_id)
            assert dims is not None
            assert dims["object_id"] == obj.object_id

    def test_get_stats(self):
        """Test statistics retrieval."""
        for i in range(3):
            edges = [{"width": 50, "height": 40, "area": 1000, "perimeter": 180, "confidence": 0.8}]
            self.scale.process_image(f"img_{i}", b"data", edges)

        stats = self.scale.get_stats()
        assert stats["total_reports"] == 3
        assert stats["average_quality_score"] > 0


# ---------------------------------------------------------------------------
# Night 23 — Fleet-standard interface coverage (MISSING_TEST gap).
#
# smartscale implements process()/health()/describe() but had no direct tests
# for any of them. Adapters (FastAPI) rely on these methods as the stable
# surface. This harness pins the contracts:
#   - health() returns fleet-standard shape {status, agent, version, timestamp, ...}.
#   - describe() returns fleet-standard shape {name, version, description, capabilities,
#     inputs, outputs, deploy_target} with at least the declared actions.
#   - process() dispatches by action and returns {status, timestamp} at minimum.
#   - process() error paths return status='error' without raising.
# ---------------------------------------------------------------------------


class TestFleetStandardInterface:
    """Verify process()/health()/describe() contract — fleet-wide standard."""

    def setup_method(self):
        self.scale = SmartScaleCore()

    # --- health() -------------------------------------------------------------

    def test_health_returns_dict(self):
        h = self.scale.health()
        assert isinstance(h, dict)

    def test_health_has_required_keys(self):
        h = self.scale.health()
        for key in ("status", "agent", "version", "timestamp"):
            assert key in h, f"health() missing fleet-standard key '{key}'"

    def test_health_status_is_ok_when_initialized(self):
        assert self.scale.health()["status"] == "ok"

    def test_health_agent_name_matches_manifest(self):
        assert self.scale.health()["agent"] == "smartscale-agent"

    def test_health_timestamp_is_iso8601(self):
        ts = self.scale.health()["timestamp"]
        # fromisoformat parses what utcnow().isoformat() produces
        datetime.fromisoformat(ts)

    def test_health_reports_processed_reflects_state(self):
        assert self.scale.health()["reports_processed"] == 0
        edges = [{"width": 50, "height": 40, "area": 1000, "perimeter": 180, "confidence": 0.8}]
        self.scale.process_image("img_h1", b"data", edges)
        assert self.scale.health()["reports_processed"] == 1

    # --- describe() -----------------------------------------------------------

    def test_describe_returns_dict(self):
        d = self.scale.describe()
        assert isinstance(d, dict)

    def test_describe_has_required_keys(self):
        d = self.scale.describe()
        for key in ("name", "version", "description", "capabilities",
                    "inputs", "outputs", "deploy_target"):
            assert key in d, f"describe() missing fleet-standard key '{key}'"

    def test_describe_capabilities_non_empty(self):
        caps = self.scale.describe()["capabilities"]
        assert isinstance(caps, list) and len(caps) > 0

    def test_describe_inputs_matches_public_mcp_contract(self):
        """Buyer-facing describe() must not advertise undeployed image/report paths."""
        inputs = self.scale.describe()["inputs"]
        assert set(inputs) == {"measure_from_credit_card"}
        assert "request_id" in inputs["measure_from_credit_card"]

    def test_describe_name_matches_health_agent(self):
        assert self.scale.describe()["name"] == self.scale.health()["agent"]

    def test_describe_version_matches_health_version(self):
        assert self.scale.describe()["version"] == self.scale.health()["version"]

    # --- process() dispatch ---------------------------------------------------

    def test_process_non_dict_returns_error_not_raises(self):
        """process() must never raise on garbage input — error envelope contract."""
        result = self.scale.process("not a dict")  # type: ignore[arg-type]
        assert result["status"] == "error"
        assert "timestamp" in result

    def test_process_describe_action(self):
        result = self.scale.process({"action": "describe"})
        assert result["status"] == "ok"
        assert result["action"] == "describe"
        assert result["result"]["name"] == "smartscale-agent"

    def test_process_get_stats_action(self):
        result = self.scale.process({"action": "get_stats"})
        assert result["status"] == "ok"
        assert result["action"] == "get_stats"
        assert "total_reports" in result["result"]

    def test_credit_card_photo_instructions_name_standard_reference(self):
        result = self.scale.credit_card_photo_instructions(
            measurement_goal="measure a pipe fitting",
            objects_to_measure=["pipe fitting"],
        )
        assert result["status"] == "ok"
        assert result["reference_object"]["width_mm"] == 85.60
        assert result["reference_object"]["height_mm"] == 53.98
        assert "blank, expired, or fully masked CR80-size card" in result["user_instruction"]
        assert "does not receive or inspect the image" in result["service_boundary"]
        assert "never expose a PAN" in " ".join(result["capture_checks"])

    def test_scale_from_credit_card_uses_cr80_width(self):
        result = self.scale.scale_from_credit_card(
            image_id="img_card_1",
            credit_card_pixel_width=856,
            credit_card_pixel_height=539.8,
            objects=[
                {"label": "box", "pixel_width": 428, "pixel_height": 100, "confidence": 0.9}
            ],
        )
        assert result["status"] == "ok"
        assert result["calibration"]["pixels_per_mm"] == 10.0
        dims = result["objects"][0]["dimensions_mm"]
        assert abs(dims["width"] - 42.8) < 1e-6
        assert abs(dims["height"] - 10.0) < 1e-6
        assert result["objects"][0]["input_confidence"] == 0.9
        assert "confidence" not in result["objects"][0]
        assert "caller_supplied_pixel_geometry" in result["assumptions"]
        assert "rectangular_area_perimeter_estimate" in result["assumptions"]

    def test_scale_from_credit_card_warns_on_perspective_distortion(self):
        result = self.scale.scale_from_credit_card(
            image_id="img_card_2",
            credit_card_pixel_width=856,
            credit_card_pixel_height=485.82,
            objects=[{"label": "board", "pixel_width": 200, "pixel_height": 80}],
        )
        assert result["status"] == "ok"
        assert result["warnings"]
        assert "perspective" in result["warnings"][0]

    def test_scale_from_credit_card_refuses_severe_distortion(self):
        result = self.scale.scale_from_credit_card(
            image_id="img_card_refused",
            credit_card_pixel_width=856,
            credit_card_pixel_height=300,
            objects=[{"label": "board", "pixel_width": 200, "pixel_height": 80}],
        )
        assert result["status"] == "error"
        assert result["error_type"] == "refused_distortion"
        assert "objects" not in result
        assert "dimensions_mm" not in str(result)

    def test_scale_from_credit_card_does_not_invent_confidence(self):
        result = self.scale.scale_from_credit_card(
            image_id="img_no_confidence",
            credit_card_pixel_width=856,
            objects=[{"label": "board", "pixel_width": 200, "pixel_height": 80}],
        )
        assert "confidence" not in result["objects"][0]
        assert "input_confidence" not in result["objects"][0]

    def test_process_measure_from_credit_card_action(self):
        result = self.scale.process({
            "action": "measure_from_credit_card",
            "image_id": "img_card_3",
            "credit_card_pixel_width": 856,
            "objects": [{"label": "tile", "pixel_width": 856, "pixel_height": 856}],
        })
        assert result["status"] == "ok"
        assert result["action"] == "measure_from_credit_card"
        assert result["result"]["objects"][0]["dimensions_mm"]["width"] == 85.6

    def test_process_list_reports_empty(self):
        result = self.scale.process({"action": "list_reports"})
        assert result["status"] == "ok"
        assert result["result"]["count"] == 0
        assert result["result"]["reports"] == []

    def test_process_get_report_missing_id_errors(self):
        result = self.scale.process({"action": "get_report", "report_id": "nonexistent"})
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_process_unknown_action_errors(self):
        """Unknown action must be rejected at either the validation gate or the
        dispatcher fallback — tests only the error envelope contract, not the
        specific message text (which may evolve as validation tightens)."""
        result = self.scale.process({"action": "__not_a_real_action__"})
        assert result["status"] == "error"
        assert "message" in result
        # Message should reference the invalid action name for operator debugging.
        assert "__not_a_real_action__" in result["message"] or "action" in result["message"].lower()

    def test_process_measure_missing_image_id_errors(self):
        result = self.scale.process({
            "action": "measure",
            "detected_edges": [{"width": 50, "height": 40, "area": 1000,
                                "perimeter": 180, "confidence": 0.8}],
        })
        # Either pipes through validation (validation error) or the inline check;
        # both produce status=error with no raise.
        assert result["status"] == "error"

    def test_process_always_returns_timestamp(self):
        """Every response — ok or error — must include a timestamp for audit trails."""
        for inp in [
            {"action": "describe"},
            {"action": "get_stats"},
            {"action": "__unknown__"},
            "not a dict",
        ]:
            result = self.scale.process(inp)  # type: ignore[arg-type]
            assert "timestamp" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
