"""Legacy non-production SmartScale image API prototype.

This module is not launched by the production gateway and does not establish
an image-measurement product claim.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import logging
import base64
import json
from datetime import datetime

from src.core import SmartScaleCore
from src.version import SMARTSCALE_VERSION
from src.vision import VisionEngine, EdgePoint, DetectedContour
from src.measurement import MeasurementEngine

logger = logging.getLogger(__name__)

# Initialize agents
scale = SmartScaleCore()
vision = VisionEngine()
measurement = MeasurementEngine()

app = FastAPI(
    title="SmartScale Legacy Image Prototype",
    version=SMARTSCALE_VERSION,
    description="Non-production experimental surface; not the public SmartScale MCP"
)


# ========== REQUEST/RESPONSE MODELS ==========

class CalibrationRequest(BaseModel):
    reference_type: str  # e.g., "us_penny", "ruler_cm"
    image_id: str


class MeasurementResponse(BaseModel):
    report_id: str
    image_id: str
    timestamp: str
    quality_score: float
    object_count: int
    calibrated: bool


class ObjectDimensions(BaseModel):
    object_id: str
    label: str
    width_mm: Optional[float]
    height_mm: Optional[float]
    area_mm2: Optional[float]
    perimeter_mm: Optional[float]
    confidence: float


# ========== MEASUREMENT ENDPOINTS ==========

@app.post("/measure")
async def measure_image(image: UploadFile = File(...),
                       reference_type: Optional[str] = Form(None)) -> MeasurementResponse:
    """
    Upload image and perform measurement.

    Args:
        image: Image file (JPEG, PNG)
        reference_type: Optional calibration reference ("us_penny", "ruler_cm", etc.)
    """
    try:
        # Read image data
        image_data = await image.read()

        # Simulate image array (in production, use PIL/OpenCV)
        image_id = f"img_{len(scale.reports) + 1}"

        # Create mock image array for edge detection
        mock_image_array = [
            [i * j % 256 for j in range(100)]
            for i in range(100)
        ]

        # Edge detection
        contours = vision.detect_edges(mock_image_array)
        contours = vision.filter_contours_by_size(contours)

        # Extract properties
        detected_edges = []
        for contour in contours:
            props = vision.extract_contour_properties(contour)
            detected_edges.append({
                "width": props.get("width", 0),
                "height": props.get("height", 0),
                "area": props.get("area", 0),
                "perimeter": props.get("perimeter", 0),
                "confidence": props.get("confidence", 0.5),
                "label": contour.label or f"object_{len(detected_edges) + 1}"
            })

        # Perform measurement
        report = scale.process_image(
            image_id=image_id,
            image_data=image_data,
            detected_edges=detected_edges,
            reference_type=reference_type
        )

        # Establish measurement if calibrated
        if report.calibration and detected_edges:
            ref = detected_edges[0]
            measurement.establish_calibration(
                reference_object=reference_type or "unknown",
                reference_actual_size_mm=report.calibration.actual_size_mm,
                reference_detected_size_px=ref.get("width", report.calibration.actual_size_mm),
                image_width_px=100,
                image_height_px=100
            )

            # Convert measurements
            for obj in report.objects:
                if measurement.calibration:
                    obj.real_width_mm, _ = measurement.measure_distance(obj.pixel_width)
                    obj.real_height_mm, _ = measurement.measure_distance(obj.pixel_height)
                    obj.real_area_mm2, _ = measurement.measure_area(obj.pixel_area)
                    obj.real_perimeter_mm, _ = measurement.measure_perimeter(obj.pixel_perimeter)

        return MeasurementResponse(
            report_id=report.report_id,
            image_id=image_id,
            timestamp=report.timestamp.isoformat(),
            quality_score=report.quality_score,
            object_count=len(report.objects),
            calibrated=report.calibration is not None
        )

    except Exception as e:
        logger.error(f"Measurement error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/measurement/{report_id}")
async def get_measurement(report_id: str):
    """Get a measurement report."""
    report = scale.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")

    return {
        "report_id": report.report_id,
        "image_id": report.image_id,
        "timestamp": report.timestamp.isoformat(),
        "quality_score": report.quality_score,
        "calibrated": report.calibration is not None,
        "calibration": {
            "name": report.calibration.name,
            "ratio_px_per_mm": report.calibration.calibration_ratio
        } if report.calibration else None,
        "objects": [
            {
                "object_id": obj.object_id,
                "label": obj.label,
                "pixel_width": obj.pixel_width,
                "pixel_height": obj.pixel_height,
                "pixel_area": obj.pixel_area,
                "real_width_mm": obj.real_width_mm,
                "real_height_mm": obj.real_height_mm,
                "real_area_mm2": obj.real_area_mm2,
                "real_perimeter_mm": obj.real_perimeter_mm,
                "confidence": obj.confidence
            }
            for obj in report.objects
        ]
    }


@app.get("/measurement/{report_id}/object/{object_id}")
async def get_object_dimensions(report_id: str, object_id: str) -> ObjectDimensions:
    """Get dimensions for a specific object."""
    dims = scale.get_object_dimensions(report_id, object_id)
    if not dims:
        raise HTTPException(status_code=404, detail=f"Object not found: {object_id}")

    return ObjectDimensions(**dims)


@app.post("/calibrate")
async def calibrate(request: CalibrationRequest):
    """Perform calibration on an image."""
    try:
        report = scale.get_report(request.image_id)
        if not report:
            raise HTTPException(status_code=404, detail=f"Image not found: {request.image_id}")

        if report.calibration:
            return {
                "status": "calibrated",
                "reference": report.calibration.name,
                "ratio_px_per_mm": report.calibration.calibration_ratio
            }
        else:
            return {
                "status": "not_calibrated",
                "message": "No reference detected in image"
            }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/measurement/{report_id}/json")
async def export_json(report_id: str):
    """Export measurement report as JSON."""
    json_str = scale.export_report_json(report_id)
    if not json_str:
        raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")

    return JSONResponse(content=json.loads(json_str))


# ========== CALIBRATION ENDPOINTS ==========

@app.get("/calibration/references")
async def list_calibration_references():
    """List available calibration references."""
    return {
        "references": [
            {
                "type": ref_type,
                "name": ref.name,
                "actual_size_mm": ref.actual_size_mm
            }
            for ref_type, ref in scale.calibration_references.items()
        ]
    }


# ========== STATISTICS ENDPOINTS ==========

@app.get("/stats")
async def get_stats():
    """Get engine statistics."""
    return scale.get_stats()


@app.get("/measurement/stats/all")
async def get_all_stats():
    """Get comprehensive statistics."""
    return {
        "scale": scale.get_stats(),
        "measurements": measurement.get_measurement_stats()
    }


# ========== HEALTH ENDPOINTS ==========

@app.get("/health")
async def health_check():
    """Health check."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": SMARTSCALE_VERSION
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
