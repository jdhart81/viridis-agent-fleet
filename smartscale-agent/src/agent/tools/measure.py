from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import numpy as np
from ..dsl import MeasureOptions, MeasureResult
from ..cv.charuco import detect_charuco_and_scale
from ..cv.utils import load_image_bgr_from_bytes, load_image_bgr_from_b64
from ..cv.geometry import line_length_mm, angle_deg, circle_diameter_mm, polygon_perimeter_mm, conservative_ci95_mm

class MeasurementService:
    def __init__(self):
        pass

    def _measure_with_px_per_mm(self, img, options: MeasureOptions, px_per_mm: float, method: str, conf: float):
        ci = conservative_ci95_mm(px_sigma=0.2, px_per_mm=px_per_mm, cond=1.0)  # simplified
        value = None
        if options.measure:
            kind = options.measure.kind
            pts = options.measure.points
            if kind == "line" and len(pts) == 2:
                value = line_length_mm(pts, px_per_mm)
            elif kind == "angle" and len(pts) == 3:
                value = angle_deg(pts)
                return MeasureResult(ok=True, value_mm=value, units="deg", px_per_mm=px_per_mm, ci95_mm=ci, confidence=conf, method=method, provenance={})
            elif kind == "circle" and len(pts) == 3:
                value = circle_diameter_mm(pts, px_per_mm)
            elif kind == "polygon" and len(pts) >= 3:
                value = polygon_perimeter_mm(pts, px_per_mm)
        return MeasureResult(ok=True, value_mm=value, units="mm", px_per_mm=px_per_mm, ci95_mm=ci, confidence=conf, method=method, provenance={})

    def measure_image(self, img_bytes: bytes, options: MeasureOptions) -> MeasureResult:
        img = load_image_bgr_from_bytes(img_bytes)
        # 1) Fiducial path
        if options.mode in ("auto", "fiducial"):
            res = detect_charuco_and_scale(img,
                                           options.charuco.squares_x,
                                           options.charuco.squares_y,
                                           options.charuco.square_length_mm,
                                           options.charuco.marker_length_mm,
                                           options.charuco.dictionary)
            if res.ok and res.px_per_mm:
                return self._measure_with_px_per_mm(img, options, res.px_per_mm, method="charuco", conf=res.confidence)
            if options.mode == "fiducial":
                return MeasureResult(ok=False, message="No fiducial detected", method="charuco")

        # 2) Reference length path
        if options.mode in ("auto", "reference"):
            if options.reference_mm and len(options.ref_points) == 2:
                (x1,y1),(x2,y2) = options.ref_points
                dpx = float(np.hypot(x2-x1, y2-y1))
                px_per_mm = dpx / float(options.reference_mm)
                return self._measure_with_px_per_mm(img, options, px_per_mm, method="reference", conf=0.5)

        return MeasureResult(ok=False, message="Could not establish scale; provide fiducial or reference.", method="none")

    def measure_image_b64(self, image_b64: str, options: MeasureOptions) -> MeasureResult:
        img = load_image_bgr_from_b64(image_b64)
        # reuse flow by converting back to bytes if needed; here we directly duplicate logic
        # for brevity we'll just use measure_image via bytes to keep CI and provenance uniform
        import base64
        return self.measure_image(base64.b64decode(image_b64), options)
