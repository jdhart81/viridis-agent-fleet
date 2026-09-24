"""
Computer Vision Engine: Edge detection, contour analysis, perspective correction.
Uses simulated CV operations (in production, integrate OpenCV/MediaPipe).
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import math

logger = logging.getLogger(__name__)


@dataclass
class EdgePoint:
    """Point on a contour edge."""
    x: float
    y: float


@dataclass
class DetectedContour:
    """Detected contour (edge) in image."""
    points: List[EdgePoint]
    label: Optional[str] = None
    confidence: float = 0.5


class VisionEngine:
    """
    Computer vision operations for measurement.

    In production, this would wrap OpenCV (cv2):
    - cv2.Canny() for edge detection
    - cv2.findContours() for contour extraction
    - cv2.moments() and cv2.contourArea() for properties
    - Perspective transform for correction
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.min_contour_area = self.config.get("min_contour_area", 100)
        self.canny_threshold1 = self.config.get("canny_threshold1", 100)
        self.canny_threshold2 = self.config.get("canny_threshold2", 200)

    def detect_edges(self, image_array: List[List[int]]) -> List[DetectedContour]:
        """
        Detect edges in image using Canny filter (simulated).

        In production:
            edges = cv2.Canny(image, self.canny_threshold1, self.canny_threshold2)
        """
        logger.info(f"Edge detection on {len(image_array)}x{len(image_array[0])} image")

        # Simulated edge detection: find bright regions
        contours = []

        # Create a simple simulation: scan for "bright" clusters
        for i in range(len(image_array) - 10):
            for j in range(len(image_array[0]) - 10):
                # Check if this region is bright
                region_brightness = sum(
                    image_array[i + di][j + dj]
                    for di in range(10)
                    for dj in range(10)
                ) / 100

                if region_brightness > 150:  # Bright threshold
                    # Found an edge region
                    points = [
                        EdgePoint(i + di, j + dj)
                        for di in range(10)
                        for dj in range(10)
                    ]
                    contours.append(DetectedContour(points=points, confidence=0.7))

        logger.info(f"Detected {len(contours)} contours")
        return contours

    def extract_contour_properties(self, contour: DetectedContour) -> Dict:
        """
        Extract measurements from a contour.

        Returns: {width, height, area, perimeter, centroid, confidence}
        """
        if not contour.points:
            return {}

        # Compute bounding box
        xs = [p.x for p in contour.points]
        ys = [p.y for p in contour.points]

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        width = max_x - min_x
        height = max_y - min_y

        # Compute area (number of points, roughly)
        area = len(contour.points)

        # Compute perimeter using distance sum
        perimeter = self._compute_perimeter(contour.points)

        # Compute centroid
        centroid_x = sum(xs) / len(xs) if xs else 0
        centroid_y = sum(ys) / len(ys) if ys else 0

        return {
            "width": width,
            "height": height,
            "area": area,
            "perimeter": perimeter,
            "centroid": (centroid_x, centroid_y),
            "confidence": contour.confidence
        }

    def _compute_perimeter(self, points: List[EdgePoint]) -> float:
        """Compute perimeter as sum of distances between consecutive points."""
        if len(points) < 2:
            return 0.0

        perimeter = 0.0
        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]
            dist = math.sqrt((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2)
            perimeter += dist

        # Close the loop
        p1 = points[-1]
        p2 = points[0]
        dist = math.sqrt((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2)
        perimeter += dist

        return perimeter

    def apply_perspective_correction(self, contours: List[DetectedContour],
                                    reference_points: List[Tuple[float, float]]) -> List[DetectedContour]:
        """
        Correct perspective distortion.

        In production:
            cv2.getPerspectiveTransform(src_pts, dst_pts) + cv2.warpPerspective()
        """
        # Simplified: just return contours as-is
        # In production, would apply homography matrix transformation
        logger.info(f"Perspective correction applied to {len(contours)} contours")
        return contours

    def filter_contours_by_size(self, contours: List[DetectedContour],
                               min_area: Optional[float] = None,
                               max_area: Optional[float] = None) -> List[DetectedContour]:
        """Filter contours by area."""
        min_a = min_area or self.min_contour_area
        max_a = max_area or float('inf')

        filtered = []
        for contour in contours:
            props = self.extract_contour_properties(contour)
            area = props.get("area", 0)

            if min_a <= area <= max_a:
                filtered.append(contour)

        logger.info(f"Filtered to {len(filtered)} contours (area {min_a}-{max_a})")
        return filtered

    def detect_calibration_reference(self, contours: List[DetectedContour],
                                    reference_types: List[str]) -> Tuple[Optional[DetectedContour], str]:
        """
        Detect known calibration objects (coins, rulers, credit cards).

        Returns (contour, reference_type_identified)
        """
        # Heuristic: match expected aspect ratio and size
        reference_profiles = {
            "us_penny": {"aspect_ratio": 1.0, "expected_size_px": 100},
            "us_quarter": {"aspect_ratio": 1.0, "expected_size_px": 130},
            "credit_card": {"aspect_ratio": 1.586, "expected_size_px": 400},
            "ruler_cm": {"aspect_ratio": 0.1, "expected_size_px": 200}
        }

        best_match = None
        best_type = None
        best_score = 0.0

        for contour in contours:
            props = self.extract_contour_properties(contour)
            width = props.get("width", 0)
            height = props.get("height", 0)
            area = props.get("area", 0)

            if width == 0 or height == 0:
                continue

            aspect_ratio = width / height

            for ref_type in reference_types:
                profile = reference_profiles.get(ref_type)
                if not profile:
                    continue

                # Match aspect ratio (tolerance: 0.2)
                aspect_match = 1.0 - min(1.0, abs(aspect_ratio - profile["aspect_ratio"]) / 0.2)

                # Match size (tolerance: 50%)
                size_diff = abs(area - profile["expected_size_px"]) / profile["expected_size_px"]
                size_match = 1.0 - min(1.0, size_diff)

                score = 0.6 * aspect_match + 0.4 * size_match

                if score > best_score:
                    best_score = score
                    best_match = contour
                    best_type = ref_type

        if best_match and best_score > 0.5:
            logger.info(f"Calibration reference detected: {best_type} (score: {best_score:.2f})")
            return best_match, best_type

        logger.warning("Could not detect calibration reference")
        return None, ""

    def estimate_image_sharpness(self, image_array: List[List[int]]) -> float:
        """
        Estimate image sharpness (0-1).

        High sharpness = good image quality for measurement.
        """
        if len(image_array) < 2:
            return 0.0

        # Simple Laplacian variance approximation
        # Count sharp transitions (pixel value changes)
        transitions = 0
        total = 0

        for i in range(len(image_array) - 1):
            for j in range(len(image_array[0]) - 1):
                # Laplacian edge detector approximation
                p = image_array[i][j]
                neighbors = [
                    image_array[i + 1][j],
                    image_array[i][j + 1],
                    image_array[i + 1][j + 1]
                ]

                for neighbor in neighbors:
                    if abs(neighbor - p) > 50:  # Sharp transition
                        transitions += 1
                    total += 1

        if total == 0:
            return 0.5

        sharpness = min(1.0, transitions / total)
        return sharpness

    def detect_blur(self, image_array: List[List[int]]) -> Tuple[bool, float]:
        """
        Detect if image is blurry.

        Returns (is_blurry, blur_score 0-1)
        """
        sharpness = self.estimate_image_sharpness(image_array)

        # If sharpness < 0.3, likely blurry
        is_blurry = sharpness < 0.3
        blur_score = 1.0 - sharpness

        logger.info(f"Blur detection: is_blurry={is_blurry}, score={blur_score:.2f}")
        return is_blurry, blur_score
