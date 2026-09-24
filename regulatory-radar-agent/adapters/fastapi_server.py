"""
FastAPI server for regulatory-radar-agent.

Exposes core functionality as REST endpoints with request validation,
error handling, and logging.
"""

import logging
from typing import Optional, List, Dict, Tuple
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from datetime import datetime
import asyncio

from regulatory_radar_agent.src.core import (
    RegulatoryRadarCore,
    Jurisdiction,
    Sector,
    RegulatorAlertConfig,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Regulatory Radar Agent",
    description="Environmental regulation monitoring and compliance assessment",
    version="0.1.0",
)

# Global agent instance
agent = RegulatoryRadarCore(debug=False)


# Request/Response models
class ScanRequest(BaseModel):
    """Scan regulations request."""
    jurisdiction: str = Field(..., description="Target jurisdiction: eu, us, uk, ca, au, jp, sg, global")
    sector: Optional[str] = Field(None, description="Optional sector filter")
    query: Optional[str] = Field(None, description="Optional text search")


class ComplianceAssessmentRequest(BaseModel):
    """Compliance assessment request."""
    company_name: str = Field(..., description="Company identifier")
    jurisdiction: str = Field(..., description="Jurisdiction")
    sector: str = Field(..., description="Industry sector")
    current_practices: Dict[str, bool] = Field(
        ...,
        description="Current practice implementations"
    )


class OpportunityDetectionRequest(BaseModel):
    """Opportunity detection request."""
    jurisdiction: str = Field(..., description="Target jurisdiction")
    sector: str = Field(..., description="Industry sector")


class TNFDReportRequest(BaseModel):
    """TNFD report generation request."""
    company_name: str = Field(..., description="Company identifier")
    governance_data: Optional[Dict[str, str]] = Field(None)
    strategy_data: Optional[Dict[str, str]] = Field(None)
    risk_data: Optional[Dict[str, str]] = Field(None)
    biodiversity_score: float = Field(..., ge=0, le=1, description="Current biodiversity score 0-1")


class CSRDReportRequest(BaseModel):
    """CSRD report generation request."""
    company_name: str = Field(..., description="Company identifier")
    environmental_data: Optional[Dict[str, str]] = Field(None)
    governance_data: Optional[Dict[str, str]] = Field(None)
    materiality_impacts: List[str] = Field(default_factory=list)
    materiality_financial: List[str] = Field(default_factory=list)


class AlertRequest(BaseModel):
    """Alert generation request."""
    jurisdictions: List[str] = Field(..., description="List of jurisdictions to watch")
    sectors: List[str] = Field(..., description="List of sectors to watch")
    days_before_deadline: int = Field(90, ge=1, le=365)


def parse_jurisdiction(jurisdiction_str: str) -> Jurisdiction:
    """Convert string to Jurisdiction enum."""
    try:
        return Jurisdiction[jurisdiction_str.upper()]
    except KeyError:
        raise ValueError(f"Invalid jurisdiction: {jurisdiction_str}")


def parse_sector(sector_str: str) -> Sector:
    """Convert string to Sector enum."""
    try:
        return Sector[sector_str.upper()]
    except KeyError:
        raise ValueError(f"Invalid sector: {sector_str}")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return await agent.health()


@app.get("/describe")
async def describe():
    """Get agent capabilities and description."""
    return agent.describe()


@app.post("/scan")
async def scan_regulations(request: ScanRequest):
    """
    Scan regulations for jurisdiction and sector.

    Returns list of applicable regulations with deadlines and requirements.
    """
    try:
        jurisdiction = parse_jurisdiction(request.jurisdiction)
        sector = parse_sector(request.sector) if request.sector else None

        result = await agent.scan_regulations(
            jurisdiction=jurisdiction,
            sector=sector,
            query=request.query,
        )

        return {
            "success": True,
            "data": result,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except ValueError as e:
        logger.error(f"Invalid input: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error scanning regulations: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/assess-compliance")
async def assess_compliance(request: ComplianceAssessmentRequest):
    """
    Assess company's compliance against applicable regulations.

    Returns compliance score, gaps, and priority remediation actions.
    """
    try:
        jurisdiction = parse_jurisdiction(request.jurisdiction)
        sector = parse_sector(request.sector)

        assessment = await agent.assess_compliance(
            company_name=request.company_name,
            jurisdiction=jurisdiction,
            sector=sector,
            current_practices=request.current_practices,
        )

        return {
            "success": True,
            "data": {
                "company_name": assessment.company_name,
                "jurisdiction": assessment.jurisdiction.value,
                "sector": assessment.sector.value,
                "assessment_date": assessment.assessment_date.isoformat(),
                "overall_compliance_level": assessment.overall_compliance_level.value,
                "compliance_percentage": assessment.compliance_percentage,
                "gaps_count": len(assessment.gaps),
                "gaps": [
                    {
                        "regulation": g.regulation_name,
                        "requirement": g.requirement,
                        "deadline_days": g.deadline_days,
                        "risk_level": g.risk_level,
                        "estimated_effort_hours": g.estimated_effort_hours,
                    }
                    for g in assessment.gaps[:10]
                ],
                "priority_actions": assessment.priority_actions,
                "summary": assessment.summary,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    except ValueError as e:
        logger.error(f"Invalid input: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error assessing compliance: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/detect-opportunities")
async def detect_opportunities(request: OpportunityDetectionRequest):
    """
    Identify business opportunities from regulatory changes.

    Returns list of opportunities with market size and Viridis fit scores.
    """
    try:
        jurisdiction = parse_jurisdiction(request.jurisdiction)
        sector = parse_sector(request.sector)

        opportunities = await agent.detect_opportunities(
            jurisdiction=jurisdiction,
            sector=sector,
        )

        return {
            "success": True,
            "data": {
                "jurisdiction": jurisdiction.value,
                "sector": sector.value,
                "opportunities_count": len(opportunities),
                "opportunities": [
                    {
                        "opportunity_type": opp.opportunity_type,
                        "description": opp.description,
                        "affected_companies": opp.affected_companies_estimated,
                        "market_size": opp.market_size_estimate,
                        "viridis_fit_score": round(opp.viridis_fit_score, 2),
                        "timeline_months": opp.timeline_months,
                    }
                    for opp in opportunities[:10]
                ],
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    except ValueError as e:
        logger.error(f"Invalid input: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error detecting opportunities: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/generate-tnfd")
async def generate_tnfd(request: TNFDReportRequest):
    """
    Generate TNFD-aligned disclosure report.

    Returns structured report with governance, strategy, risk management, and metrics.
    """
    try:
        report = await agent.generate_tnfd_report(
            company_name=request.company_name,
            governance_data=request.governance_data,
            strategy_data=request.strategy_data,
            risk_data=request.risk_data,
            biodiversity_score=request.biodiversity_score,
        )

        return {
            "success": True,
            "data": {
                "company_name": report.company_name,
                "report_date": report.report_date.isoformat(),
                "governance": report.governance,
                "strategy": report.strategy,
                "risk_management": report.risk_management,
                "metrics_targets": report.metrics_targets,
                "executive_summary": report.executive_summary,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error generating TNFD report: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/generate-csrd")
async def generate_csrd(request: CSRDReportRequest):
    """
    Generate CSRD-aligned sustainability report.

    Returns structured report with double materiality assessment, metrics, and action plans.
    """
    try:
        report = await agent.generate_csrd_report(
            company_name=request.company_name,
            environmental_data=request.environmental_data,
            governance_data=request.governance_data,
            materiality_impacts=request.materiality_impacts,
            materiality_financial=request.materiality_financial,
        )

        return {
            "success": True,
            "data": {
                "company_name": report.company_name,
                "report_date": report.report_date.isoformat(),
                "governance_and_organization": report.governance_and_organization,
                "strategy_and_value_creation": report.strategy_and_value_creation,
                "double_materiality_assessment": report.double_materiality_assessment,
                "metrics_and_targets": report.metrics_and_targets,
                "action_plans": report.action_plans,
                "executive_summary": report.executive_summary,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error generating CSRD report: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/forecast/{jurisdiction}")
async def forecast(jurisdiction: str):
    """
    Get regulatory forecast for jurisdiction.

    Returns predicted upcoming regulatory changes and political signals.
    """
    try:
        jurisdiction_enum = parse_jurisdiction(jurisdiction)

        forecast = await agent.regulatory_forecast(
            jurisdiction=jurisdiction_enum,
            forecast_months=12,
        )

        return {
            "success": True,
            "data": {
                "jurisdiction": forecast.jurisdiction.value,
                "forecast_period_months": forecast.forecast_period_months,
                "likely_changes": forecast.likely_changes,
                "confidence_level": forecast.confidence_level,
                "political_signals": forecast.political_signals,
                "recommendation": forecast.recommendation,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    except ValueError as e:
        logger.error(f"Invalid jurisdiction: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating forecast: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/alerts")
async def generate_alerts(request: AlertRequest):
    """
    Generate regulatory alerts for watchlisted jurisdictions/sectors.

    Returns critical alerts with deadline information and recommended actions.
    """
    try:
        jurisdictions = [parse_jurisdiction(j) for j in request.jurisdictions]
        sectors = [parse_sector(s) for s in request.sectors]

        watchlist = [(j, s) for j in jurisdictions for s in sectors]

        config = RegulatorAlertConfig(
            jurisdictions=jurisdictions,
            sectors=sectors,
            days_before_deadline=request.days_before_deadline,
        )

        alerts = await agent.generate_alerts(watchlist=watchlist, alert_config=config)

        return {
            "success": True,
            "data": alerts,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except ValueError as e:
        logger.error(f"Invalid input: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating alerts: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/")
async def root():
    """Root endpoint with agent info."""
    return {
        "agent": "regulatory-radar",
        "version": "0.1.0",
        "description": "Environmental regulation monitoring and compliance assessment",
        "endpoints": {
            "POST /scan": "Scan applicable regulations",
            "POST /assess-compliance": "Assess compliance gaps",
            "POST /detect-opportunities": "Identify business opportunities",
            "POST /generate-tnfd": "Generate TNFD report",
            "POST /generate-csrd": "Generate CSRD report",
            "GET /forecast/{jurisdiction}": "Regulatory forecast",
            "POST /alerts": "Generate regulatory alerts",
            "GET /health": "Health check",
            "GET /describe": "Agent description",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
