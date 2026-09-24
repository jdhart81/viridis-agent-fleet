"""
FastAPI Server for ProtoGen Agent
Endpoints: /analyze-spec, /generate-bom, /estimate-cost, /dfm-check, /health
"""

import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import asyncio
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core import ProtoGenCore, ProductSpec
from manufacturing import ManufacturingLibrary
from cost_engine import CostEngine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="ProtoGen API",
    description="AI Manufacturing Assistant - Generates manufacturing plans from product specifications",
    version="0.1.0",
)

# Initialize core components
protogen_core = ProtoGenCore()
mfg_library = ManufacturingLibrary()
cost_engine = CostEngine()


# ============================================================================
# Pydantic Models
# ============================================================================

class TargetDimensions(BaseModel):
    length_mm: float = Field(..., gt=0, description="Length in millimeters")
    width_mm: float = Field(..., gt=0, description="Width in millimeters")
    height_mm: float = Field(..., gt=0, description="Height in millimeters")


class ToleranceSpec(BaseModel):
    general: str = Field(default="±0.1mm", description="General tolerance (e.g., ±0.1mm)")
    critical: str = Field(default="±0.05mm", description="Critical feature tolerance")


class ProductSpecRequest(BaseModel):
    name: str = Field(..., description="Product name")
    description: str = Field(..., description="Product description")
    primary_material: str = Field(..., description="Primary material (aluminum, steel, plastic_abs, etc.)")
    estimated_volume: int = Field(..., gt=0, description="Estimated annual production volume")
    target_dimensions: TargetDimensions
    tolerances: Optional[ToleranceSpec] = Field(default_factory=ToleranceSpec)
    surface_finish: str = Field(default="raw", description="Surface finish (raw, anodized, painted, polished)")
    assembly_complexity: str = Field(default="moderate", description="simple, moderate, or complex")
    lead_time_weeks: int = Field(default=12, ge=1, description="Target lead time in weeks")
    target_unit_cost: Optional[float] = Field(None, gt=0, description="Target unit cost in USD")


class BOMResponse(BaseModel):
    name: str
    material: str
    quantity: float
    unit_cost: float
    supplier: str
    lead_time_days: int


class ProcessStepResponse(BaseModel):
    sequence: int
    process_type: str
    description: str
    equipment: str
    cost_per_unit: float
    setup_hours: float
    lead_time_days: int


class CostBreakdown(BaseModel):
    material_cost: float
    labor_cost: float
    tooling_amortization: float
    subtotal_manufacturing: float
    overhead: float
    profit_margin: float
    selling_price_per_unit: float
    annual_revenue_estimate: float


class ManufacturingPlanResponse(BaseModel):
    spec_id: str
    product_name: str
    created_at: str
    bom: List[BOMResponse]
    process_sequence: List[ProcessStepResponse]
    dfm_issues: List[str]
    cost_breakdown: CostBreakdown
    supplier_recommendations: Dict[str, str]
    feasibility_score: float


class AnalyzeSpecResponse(BaseModel):
    status: str
    plan: Optional[ManufacturingPlanResponse] = None
    message: Optional[str] = None
    timestamp: str


class CostEstimateRequest(BaseModel):
    material: str = Field(..., description="Material name")
    volume_cm3: float = Field(..., gt=0, description="Part volume in cubic centimeters")
    annual_quantity: int = Field(..., gt=0, description="Annual production quantity")
    process_type: str = Field(..., description="Manufacturing process (e.g., CNC_machining)")


class CostEstimateResponse(BaseModel):
    process_type: str
    unit_cogs: float
    annual_cost: float
    selling_price_per_unit: float
    gross_margin_pct: float
    break_even_units: int


class DFMCheckRequest(BaseModel):
    primary_material: str
    tolerances: Optional[ToleranceSpec] = Field(default_factory=ToleranceSpec)
    surface_finish: str = Field(default="raw")
    estimated_volume: int = Field(..., gt=0)


class DFMCheckResponse(BaseModel):
    feasibility_score: float
    issues: List[str]
    recommendations: List[str]


class HealthResponse(BaseModel):
    status: str
    agent: str
    version: str
    timestamp: str
    capabilities: List[str]


# ============================================================================
# Endpoints
# ============================================================================

@app.post("/analyze-spec", response_model=AnalyzeSpecResponse)
async def analyze_spec(request: ProductSpecRequest) -> AnalyzeSpecResponse:
    """
    Analyze product specification and generate manufacturing plan.

    Returns:
    - BOM (Bill of Materials)
    - Process sequence
    - DFM issues and recommendations
    - Cost breakdown
    - Supplier recommendations
    - Feasibility score
    """
    try:
        logger.info(f"Analyzing spec for {request.name}")

        # Convert request to dict for core processing
        input_data = {
            "name": request.name,
            "description": request.description,
            "primary_material": request.primary_material,
            "estimated_volume": request.estimated_volume,
            "target_dimensions": {
                "length_mm": request.target_dimensions.length_mm,
                "width_mm": request.target_dimensions.width_mm,
                "height_mm": request.target_dimensions.height_mm,
            },
            "tolerances": {
                "general": request.tolerances.general,
                "critical": request.tolerances.critical,
            },
            "surface_finish": request.surface_finish,
            "assembly_complexity": request.assembly_complexity,
            "lead_time_weeks": request.lead_time_weeks,
            "target_unit_cost": request.target_unit_cost,
        }

        result = await protogen_core.process(input_data)

        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])

        plan_data = result["plan"]
        plan_response = ManufacturingPlanResponse(
            spec_id=plan_data["spec_id"],
            product_name=plan_data["product_name"],
            created_at=plan_data["created_at"],
            bom=[BOMResponse(**bom_item) for bom_item in plan_data["bom"]],
            process_sequence=[ProcessStepResponse(**step) for step in plan_data["process_sequence"]],
            dfm_issues=plan_data["dfm_issues"],
            cost_breakdown=CostBreakdown(**plan_data["cost_breakdown"]),
            supplier_recommendations=plan_data["supplier_recommendations"],
            feasibility_score=plan_data["feasibility_score"],
        )

        return AnalyzeSpecResponse(
            status="success",
            plan=plan_response,
            timestamp=result["timestamp"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing spec: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/estimate-cost", response_model=CostEstimateResponse)
async def estimate_cost(request: CostEstimateRequest) -> CostEstimateResponse:
    """
    Estimate manufacturing cost for a given material, process, and volume.

    Returns:
    - Per-unit COGS
    - Annual cost
    - Recommended selling price
    - Gross margin %
    - Break-even volume
    """
    try:
        logger.info(f"Estimating cost for {request.material} via {request.process_type}")

        # Get material cost
        material_cost_dict = protogen_core.material_costs
        material_cost_per_kg = material_cost_dict.get(request.material.lower(), 5.0)

        # Estimate material cost
        density_map = {
            "aluminum": 2.7,
            "steel": 7.85,
            "stainless_steel": 8.0,
            "plastic_abs": 1.05,
            "plastic_petg": 1.27,
            "nylon": 1.14,
        }
        density = density_map.get(request.material.lower(), 2.0)

        material_cost = cost_engine.estimate_material_cost(
            request.volume_cm3,
            density,
            material_cost_per_kg,
            scrap_rate=0.05,
        )

        # Estimate process cost
        process_cost = cost_engine.estimate_labor_cost(
            request.volume_cm3 / 10,  # Rough time estimate
            hourly_rate=120,
            process_efficiency=0.85,
        )

        # Calculate total COGS
        cogs_breakdown = cost_engine.calculate_per_unit_cost(
            material_cost=material_cost,
            labor_cost=process_cost,
            process_cost=process_cost * 0.5,
            tooling_amortization=0.0,
        )
        unit_cogs = cogs_breakdown["total_cogs"]

        # Apply volume discounts
        discounted = cost_engine.apply_volume_discount(unit_cogs, request.annual_quantity)
        final_cogs = discounted["unit_cost_after_discount"]

        # Calculate selling price
        selling_price_dict = cost_engine.calculate_selling_price(final_cogs, gross_margin_target=0.40)

        # Break-even
        contribution_margin = selling_price_dict["selling_price"] - final_cogs
        breakeven = cost_engine.calculate_break_even(fixed_costs=10000, unit_contribution_margin=contribution_margin)

        return CostEstimateResponse(
            process_type=request.process_type,
            unit_cogs=final_cogs,
            annual_cost=round(final_cogs * request.annual_quantity, 2),
            selling_price_per_unit=selling_price_dict["selling_price"],
            gross_margin_pct=selling_price_dict["gross_margin_pct"],
            break_even_units=breakeven,
        )

    except Exception as e:
        logger.error(f"Error estimating cost: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dfm-check", response_model=DFMCheckResponse)
async def dfm_check(request: DFMCheckRequest) -> DFMCheckResponse:
    """
    Perform Design for Manufacturability analysis.

    Identifies potential issues and provides recommendations.
    """
    try:
        logger.info(f"Performing DFM check for {request.primary_material}")

        issues = []
        recommendations = []
        feasibility = 1.0

        # Tolerance analysis
        critical_tolerance = float(request.tolerances.critical.replace("±", "").split("m")[0])
        if critical_tolerance < 0.05:
            issues.append("Critical tolerances <0.05mm require precision machining (CNC, SLA)")
            recommendations.append("Consider 5-axis CNC or SLA 3D printing for tight tolerances")
            feasibility -= 0.15

        # Volume vs process
        if request.estimated_volume > 50000:
            recommendations.append("High volume (>50K/yr): Consider injection molding for cost reduction")
        elif request.estimated_volume < 100:
            issues.append("Low volume (<100 units): Avoid high-cost processes like injection molding")
            recommendations.append("Use 3D printing, CNC, or job shop for prototypes")
            feasibility -= 0.1

        # Material processing
        material = request.primary_material.lower()
        compatible_processes = mfg_library.find_compatible_processes(material)
        if not compatible_processes:
            issues.append(f"No standard processes available for {material}")
            feasibility -= 0.2

        # Surface finish
        finish = request.surface_finish
        if finish not in ["raw", "anodized", "painted", "polished"]:
            issues.append(f"Surface finish '{finish}' may require custom processing")

        # Assembly complexity with volume
        if request.estimated_volume > 10000:
            recommendations.append("Consider design for automated assembly to reduce labor costs")

        feasibility = max(0.0, min(1.0, feasibility))

        return DFMCheckResponse(
            feasibility_score=feasibility,
            issues=issues,
            recommendations=recommendations,
        )

    except Exception as e:
        logger.error(f"Error in DFM check: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/processes", response_model=Dict[str, Any])
async def list_processes() -> Dict[str, Any]:
    """Get available manufacturing processes and their capabilities."""
    try:
        return mfg_library.process_summary()
    except Exception as e:
        logger.error(f"Error listing processes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    health = await protogen_core.health()
    return HealthResponse(
        status=health["status"],
        agent=health["agent"],
        version=health["version"],
        timestamp=health["timestamp"],
        capabilities=health["capabilities"],
    )


@app.get("/describe")
async def describe() -> Dict[str, Any]:
    """Get agent description and capabilities."""
    return protogen_core.describe()


@app.get("/")
async def root():
    """Root endpoint with API documentation link."""
    return {
        "agent": "ProtoGen Manufacturing Assistant",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": [
            "POST /analyze-spec - Generate full manufacturing plan",
            "POST /estimate-cost - Quick cost estimation",
            "POST /dfm-check - Design for Manufacturability analysis",
            "GET /processes - List available manufacturing processes",
            "GET /health - Health check",
            "GET /describe - Agent capabilities",
        ],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
