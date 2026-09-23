"""
FastAPI server for narrative-engine-agent.

REST endpoints for narrative generation across multiple formats and audiences.
"""

import logging
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime

from narrative_engine_agent.src.core import (
    NarrativeEngineCore,
    AudienceType,
    NarrativeFormat,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Narrative Engine Agent",
    description="Translates ecological intelligence into decision-maker-ready narratives",
    version="0.1.0",
)

# Global agent instance
agent = NarrativeEngineCore(debug=False)


# Request models
class TranslateRequest(BaseModel):
    """Narrative translation request."""
    agent_output: Dict[str, Any] = Field(..., description="Raw data from Viridis agent")
    audience_type: str = Field(
        ...,
        description="Audience: institutional_investor, policymaker, grant_funder, journalist, general_public, etc."
    )
    format: str = Field(
        ...,
        description="Format: investor_deck, policy_brief, grant_proposal, press_release, executive_summary"
    )
    key_message: Optional[str] = Field(None, description="Optional override for primary message")


class InvestorNarrativeRequest(BaseModel):
    """Investor pitch generation request."""
    data: Dict[str, Any] = Field(..., description="Agent output with market, traction, financial metrics")
    key_message: Optional[str] = Field(None, description="Optional pitch angle")


class PolicyBriefRequest(BaseModel):
    """Policy brief generation request."""
    data: Dict[str, Any] = Field(..., description="Agent output with policy data")
    jurisdiction: Optional[str] = Field(None, description="Target jurisdiction")
    key_message: Optional[str] = Field(None, description="Optional policy recommendation")


class GrantProposalRequest(BaseModel):
    """Grant proposal generation request."""
    data: Dict[str, Any] = Field(..., description="Agent output with project data")
    funder_type: Optional[str] = Field(None, description="Target funder (foundation, government, agency)")
    key_message: Optional[str] = Field(None, description="Optional project title")


class PressReleaseRequest(BaseModel):
    """Press release generation request."""
    data: Dict[str, Any] = Field(..., description="Agent output with announcement data")
    key_message: Optional[str] = Field(None, description="Headline")


class ExecutiveSummaryRequest(BaseModel):
    """Executive summary generation request."""
    data: Dict[str, Any] = Field(..., description="Agent output")
    audience_type: str = Field(..., description="Target audience")
    key_message: Optional[str] = Field(None, description="Optional title")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return await agent.health()


@app.get("/describe")
async def describe():
    """Get agent capabilities."""
    return agent.describe()


@app.post("/translate")
async def translate(request: TranslateRequest):
    """
    Translate agent output to narrative for specific audience and format.

    Routes to appropriate narrative function based on format.
    """
    try:
        # Validate audience and format
        try:
            AudienceType[request.audience_type.upper()]
            NarrativeFormat[request.format.upper()]
        except KeyError as e:
            raise HTTPException(status_code=400, detail=f"Invalid audience or format: {str(e)}")

        narrative = await agent.translate(
            agent_output=request.agent_output,
            audience_type=request.audience_type,
            format_type=request.format,
            key_message=request.key_message,
        )

        return {
            "success": True,
            "data": {
                "narrative_id": narrative.narrative_id,
                "format": narrative.format.value,
                "audience": narrative.audience.value,
                "title": narrative.title,
                "content": narrative.content,
                "key_claims": narrative.key_claims,
                "call_to_action": narrative.call_to_action,
                "quality_score": round(narrative.quality_score, 2),
                "generation_timestamp": narrative.generation_timestamp.isoformat(),
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error translating narrative: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/investor-narrative")
async def investor_narrative(request: InvestorNarrativeRequest):
    """
    Generate investor pitch narrative.

    Frames ecological data as investment thesis with market opportunity,
    traction, financial projections, and ROI.
    """
    try:
        narrative = await agent.investor_narrative(
            data=request.data,
            audience=AudienceType.INSTITUTIONAL_INVESTOR,
            key_message=request.key_message,
        )

        return {
            "success": True,
            "data": {
                "narrative_id": narrative.narrative_id,
                "title": narrative.title,
                "content": narrative.content,
                "key_claims": narrative.key_claims,
                "call_to_action": narrative.call_to_action,
                "quality_score": round(narrative.quality_score, 2),
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error generating investor narrative: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/policy-brief")
async def policy_brief(request: PolicyBriefRequest):
    """
    Generate policy brief narrative.

    Translates to policy language: executive summary, evidence base,
    options analysis, cost-benefit, recommendation.
    """
    try:
        narrative = await agent.policy_brief(
            data=request.data,
            audience=AudienceType.POLICYMAKER,
            key_message=request.key_message,
        )

        return {
            "success": True,
            "data": {
                "narrative_id": narrative.narrative_id,
                "title": narrative.title,
                "content": narrative.content,
                "key_claims": narrative.key_claims,
                "call_to_action": narrative.call_to_action,
                "quality_score": round(narrative.quality_score, 2),
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error generating policy brief: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/grant-proposal")
async def grant_proposal(request: GrantProposalRequest):
    """
    Generate grant proposal narrative.

    Structures as: needs statement, objectives, evaluation plan, budget,
    organizational capacity, sustainability.
    """
    try:
        narrative = await agent.grant_proposal(
            data=request.data,
            audience=AudienceType.GRANT_FUNDER,
            key_message=request.key_message,
        )

        return {
            "success": True,
            "data": {
                "narrative_id": narrative.narrative_id,
                "title": narrative.title,
                "content": narrative.content,
                "key_claims": narrative.key_claims,
                "call_to_action": narrative.call_to_action,
                "quality_score": round(narrative.quality_score, 2),
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error generating grant proposal: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/press-release")
async def press_release(request: PressReleaseRequest):
    """
    Generate press release narrative (AP style).

    Headlines, lede, quotes, boilerplate, contact info.
    """
    try:
        narrative = await agent.press_release(
            data=request.data,
            audience=AudienceType.JOURNALIST,
            key_message=request.key_message,
        )

        return {
            "success": True,
            "data": {
                "narrative_id": narrative.narrative_id,
                "title": narrative.title,
                "content": narrative.content,
                "call_to_action": narrative.call_to_action,
                "quality_score": round(narrative.quality_score, 2),
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error generating press release: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/executive-summary")
async def executive_summary(request: ExecutiveSummaryRequest):
    """
    Generate one-page executive summary.

    Distills complex data into: hook, problem, solution, impact, next steps.
    """
    try:
        # Parse audience
        try:
            audience = AudienceType[request.audience_type.upper()]
        except KeyError:
            audience = AudienceType.GENERAL_PUBLIC

        narrative = await agent.executive_summary(
            data=request.data,
            audience=audience,
            key_message=request.key_message,
        )

        return {
            "success": True,
            "data": {
                "narrative_id": narrative.narrative_id,
                "title": narrative.title,
                "content": narrative.content,
                "key_claims": narrative.key_claims,
                "call_to_action": narrative.call_to_action,
                "quality_score": round(narrative.quality_score, 2),
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error generating executive summary: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "agent": "narrative-engine",
        "version": "0.1.0",
        "description": "Translates ecological intelligence into decision-maker-ready narratives",
        "supported_audiences": [
            "institutional_investor",
            "retail_investor",
            "policymaker",
            "regulator",
            "scientist",
            "journalist",
            "grant_funder",
            "board_member",
            "general_public",
        ],
        "supported_formats": [
            "investor_deck",
            "policy_brief",
            "grant_proposal",
            "press_release",
            "executive_summary",
            "academic_paper",
            "newsletter",
        ],
        "endpoints": {
            "POST /translate": "Translate to any audience/format",
            "POST /investor-narrative": "Generate investor pitch",
            "POST /policy-brief": "Generate policy brief",
            "POST /grant-proposal": "Generate grant proposal",
            "POST /press-release": "Generate press release",
            "POST /executive-summary": "Generate 1-page summary",
            "GET /health": "Health check",
            "GET /describe": "Agent description",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
