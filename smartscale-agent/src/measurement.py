"""
Measurement Engine: Pixel-to-real-world conversion, geometric calculations, confidence scoring.
"""

import logging
import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CalibrationMatrix:
    """Calibration matrix for pixel-to-mm conversion."""
    pixels_per_mm_x: float
    pixels_per_mm_y: float
    image_width_px: int
    image_height_px: int
    reference_object: str
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

    def convert_distance(self, pixel_distance: float) -> float:
        """Convert pixel distance to mm."""
        avg_px_per_mm = (self.pixels_per_mm_x + self.pixels_per_mm_y) / 2
        if avg_px_per_mm <= 0:
            return 0.0
        return pixel_distance / avg_px_per_mm

    def convert_area(self, pixel_area: float) -> float:
        """Convert pixel area to mm^2."""
        avg_px_per_mm = (self.pixels_per_mm_x + self.pixels_per_mm_y) / 2
        if avg_px_per_mm <= 0:
            return 0.0
        return pixel_area / (avg_px_per_mm ** 2)

    def get_scale_factor(self) -> float:
        """Get average scale factor (pixels per mm)."""
        return (self.pixels_per_mm_x + self.pixels_per_mm_y) / 2


class MeasurementEngine:
    """
    Perform geometric measurements and conversions.

    Invariants:
    - Measurements only valid with proper calibration
    - Confidence scores reflect measurement uncertainty
    - All conversions use consistent calibration matrix
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.calibration: Optional[CalibrationMatrix] = None
        self.measurement_history = []

    def establish_calibration(self, reference_object: str,
                            reference_actual_size_mm: float,
                            reference_detected_size_px: float,
                            image_width_px: int,
                            image_height_px: int) -> CalibrationMatrix:
        """
        Establish calibration matrix from known reference object.

        Args:
            reference_object: Name of reference (e.g., "us_penny")
            reference_actual_size_mm: True size of reference in mm
            reference_detected_size_px: Detected size in pixels
            image_width_px: Image width
            image_height_px: Image height
        """
        if reference_detected_size_px <= 0:
            raise ValueError("Reference detected size must be > 0")

        px_per_mm = reference_detected_size_px / reference_actual_size_mm

        # Assume isotropic scaling (equal in x and y)
        self.calibration = CalibrationMatrix(
            pixels_per_mm_x=px_per_mm,
            pixels_per_mm_y=px_per_mm,
            image_width_px=image_width_px,
            image_height_px=image_height_px,
            reference_object=reference_object
        )

        logger.info(f"Calibration established: {px_per_mm:.3f} px/mm ({reference_object})")

        return self.calibration

    def measure_distance(self, pixel_distance: float) -> Tuple[float, float]:
        """
        Measure distance and return (distance_mm, confidence).

        Confidence depends on calibration quality and measurement precision.
        """
        if not self.calibration:
            logger.error("No calibration available")
            return 0.0, 0.0

        distance_mm = self.calibration.convert_distance(pixel_distance)

        # Confidence: higher if distance is moderate (not too small/large)
        # Very small distances (< 5mm) are hard to measure accurately
        if distance_mm < 5:
            confidence = 0.5 + 0.3 * (distance_mm / 5)
        elif distance_mm > 500:
            confidence = 0.8 - 0.2 * min(1.0, (distance_mm - 500) / 500)
        else:
            confidence = 0.85

        self.measurement_history.append({
            "type": "distance",
            "pixel_value": pixel_distance,
            "real_value": distance_mm,
            "confidence": confidence,
            "timestamp": datetime.utcnow()
        })

        return distance_mm, confidence

    def measure_area(self, pixel_area: float) -> Tuple[float, float]:
        """
        Measure area and return (area_mm2, confidence).
        """
        if not self.calibration:
            logger.error("No calibration available")
            return 0.0, 0.0

        area_mm2 = self.calibration.convert_area(pixel_area)

        # Confidence: area measurements are typically robust
        # Confidence decreases for very small or very large areas
        if area_mm2 < 25:  # Very small
            confidence = 0.6 + 0.2 * min(1.0, area_mm2 / 25)
        elif area_mm2 > 100000:  # Very large
            confidence = 0.8 - 0.2 * min(1.0, (area_mm2 - 100000) / 100000)
        else:
            confidence = 0.9

        self.measurement_history.append({
            "type": "area",
            "pixel_value": pixel_area,
            "real_value": area_mm2,
            "confidence": confidence,
            "timestamp": datetime.utcnow()
        })

        return area_mm2, confidence

    def measure_dimensions(self, pixel_width: float, pixel_height: float) \
            -> Tuple[Dict[str, float], float]:
        """
        Measure object dimensions and return (dimensions_dict, confidence).

        Returns:
            ({width_mm, height_mm, diagonal_mm, aspect_ratio}, confidence)
        """
        if not self.calibration:
            logger.error("No calibration available")
            return {}, 0.0

        width_mm, w_conf = self.measure_distance(pixel_width)
        height_mm, h_conf = self.measure_distance(pixel_height)

        # Diagonal
        diagonal_mm = math.sqrt(width_mm ** 2 + height_mm ** 2)

        # Aspect ratio (unitless)
        aspect_ratio = width_mm / height_mm if height_mm > 0 else 0.0

        # Confidence: product of component confidences
        confidence = min(w_conf, h_conf) * 0.95  # Slight penalty for multiple measurements

        dimensions = {
            "width_mm": width_mm,
            "height_mm": height_mm,
            "diagonal_mm": diagonal_mm,
            "aspect_ratio": aspect_ratio
        }

        self.measurement_history.append({
            "type": "dimensions",
            "pixel_values": {"width": pixel_width, "height": pixel_height},
            "real_values": dimensions,
            "confidence": confidence,
            "timestamp": datetime.utcnow()
        })

        return dimensions, confidence

    def measure_perimeter(self, pixel_perimeter: float) -> Tuple[float, float]:
        """
        Measure perimeter and return (perimeter_mm, confidence).
        """
        if not self.calibration:
            logger.error("No calibration available")
            return 0.0, 0.0

        perimeter_mm = self.calibration.convert_distance(pixel_perimeter)

        # Perimeter measurements are less reliable due to edge detection quality
        # Reduce confidence by 10%
        confidence = 0.8

        self.measurement_history.append({
            "type": "perimeter",
            "pixel_value": pixel_perimeter,
            "real_value": perimeter_mm,
            "confidence": confidence,
            "timestamp": datetime.utcnow()
        })

        return perimeter_mm, confidence

    def compute_confidence_score(self, measurement_count: int,
                                blur_score: float,
                                edge_quality: float) -> float:
        """
        Compute overall confidence score for a measurement session.

        Args:
            measurement_count: Number of objects measured
            blur_score: Image blur score (0-1, higher = blurrier)
            edge_quality: Edge detection quality (0-1, higher = better)

        Returns:
            Confidence score (0-1)
        """
        # Base: calibration quality
        base_conf = 0.7 if self.calibration else 0.3

        # Adjust for image quality
        quality_penalty = blur_score * 0.2  # Blur reduces confidence
        quality_bonus = edge_quality * 0.15  # Good edges increase confidence

        # Adjust for measurement count
        count_bonus = min(0.1, measurement_count * 0.02)

        confidence = base_conf - quality_penalty + quality_bonus + count_bonus

        return max(0.0, min(1.0, confidence))

    def get_measurement_stats(self) -> Dict:
        """Get statistics about measurements."""
        if not self.measurement_history:
            return {
                "measurements": 0,
                "average_confidence": 0.0,
                "measurement_types": []
            }

        by_type = {}
        total_confidence = 0.0

        for measure in self.measurement_history:
            mtype = measure["type"]
            by_type.setdefault(mtype, []).append(measure["confidence"])
            total_confidence += measure["confidence"]

        avg_confidence = total_confidence / len(self.measurement_history)

        type_stats = {
            mtype: {
                "count": len(confs),
                "avg_confidence": sum(confs) / len(confs)
            }
            for mtype, confs in by_type.items()
        }

        return {
            "total_measurements": len(self.measurement_history),
            "average_confidence": avg_confidence,
            "by_type": type_stats,
            "calibration": {
                "established": self.calibration is not None,
                "scale_factor_px_per_mm": (
                    self.calibration.get_scale_factor() if self.calibration else None
                )
            }
        }

    def validate_measurement(self, measurement_value: float,
                           measurement_type: str) -> Tuple[bool, str]:
        """
        Validate a measurement for reasonableness.

        Returns (is_valid, validation_message)
        """
        if not self.calibration:
            return False, "No calibration available"

        if measurement_type == "distance":
            if measurement_value < 0:
                return False, "Distance cannot be negative"
            if measurement_value < 0.1:
                return False, "Distance too small (< 0.1mm)"
            if measurement_value > 10000:
                return False, "Distance too large (> 10000mm)"
            return True, "Valid distance"

        elif measurement_type == "area":
            if measurement_value < 0:
                return False, "Area cannot be negative"
            if measurement_value < 0.01:
                return False, "Area too small (< 0.01mm^2)"
            return True, "Valid area"

        else:
            return True, "No validation rule for this type"
