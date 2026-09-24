"""
FastAPI Deployment Adapter

Wraps AgentCore in HTTP endpoints for Docker/Kubernetes/Cloud Run deployment.
This is the "glue layer" between your core logic and HTTP.

To run:
    uvicorn adapters.fastapi_server:app --reload --port 8080

Or via Docker:
    docker run -p 8080:8080 my-agent
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import your core agent here (replace with your subclass)
from src.core import AgentCore, AgentConfig

# ============================================================================
# Configuration
# ============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
AGENT_NAME = os.getenv("AGENT_NAME", "agent")
AGENT_VERSION = "0.1.0"

# Configure logging
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================================
# Agent Initialization
# ============================================================================

# Create agent instance (replace AgentCore with your subclass)
config = AgentConfig(
    name=AGENT_NAME,
    version=AGENT_VERSION,
    debug=(LOG_LEVEL == "DEBUG")
)
agent = AgentCore(config)


# ============================================================================
# FastAPI App Lifecycle
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for app startup/shutdown.
    Override to add custom initialization/cleanup logic.
    """
    logger.info(f"Starting {AGENT_NAME} v{AGENT_VERSION}")
    # Add startup logic here (db connections, cache initialization, etc.)
    yield
    logger.info(f"Shutting down {AGENT_NAME}")
    # Add cleanup logic here


app = FastAPI(
    title=AGENT_NAME,
    version=AGENT_VERSION,
    description="Viridis Agent deployed via FastAPI",
    lifespan=lifespan
)

# Enable CORS for cross-origin requests (adjust as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Request Logging Middleware
# ============================================================================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log incoming requests and response times."""
    logger.info(f"{request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"Response: {response.status_code}")
    return response


# ============================================================================
# Health & Discovery Endpoints
# ============================================================================

@app.get("/health", tags=["health"])
async def health():
    """
    Health check endpoint.

    Returns agent status and dependency health.
    """
    try:
        health_data = await agent.health()
        status_code = 200 if health_data.get("status") == "ok" else 503
        return JSONResponse(content=health_data, status_code=status_code)
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return JSONResponse(
            content={
                "status": "error",
                "agent": AGENT_NAME,
                "error": str(e)
            },
            status_code=500
        )


@app.get("/describe", tags=["discovery"])
async def describe():
    """
    Describe agent capabilities for discovery and composition.

    Returns agent metadata, input schema, output schema, and capabilities.
    """
    try:
        description = agent.describe()
        return JSONResponse(content=description)
    except Exception as e:
        logger.error(f"Describe failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Main Processing Endpoint
# ============================================================================

@app.post("/process", tags=["processing"])
async def process(payload: dict):
    """
    Main processing endpoint.

    Accepts agent-specific input, processes it, and returns results.

    Args:
        payload: Dictionary with agent inputs (format depends on agent)

    Returns:
        Dictionary with results:
            {
                "status": "ok" | "error",
                "data": <result>,
                "error": <optional error message>
            }
    """
    try:
        logger.debug(f"Processing payload: {payload}")
        result = await agent.process(payload)
        logger.debug(f"Process result: {result}")
        return JSONResponse(content=result)
    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        return JSONResponse(
            content={
                "status": "error",
                "error": str(e),
                "data": None
            },
            status_code=400
        )
    except Exception as e:
        logger.error(f"Processing failed: {e}", exc_info=True)
        return JSONResponse(
            content={
                "status": "error",
                "error": str(e),
                "data": None
            },
            status_code=500
        )


# ============================================================================
# Info Endpoint
# ============================================================================

@app.get("/info", tags=["metadata"])
async def info():
    """Return agent metadata."""
    return JSONResponse(content={
        "name": AGENT_NAME,
        "version": AGENT_VERSION,
        "status": "running"
    })


# ============================================================================
# Root Endpoint
# ============================================================================

@app.get("/", tags=["root"])
async def root():
    """Root endpoint with quick navigation."""
    return JSONResponse(content={
        "agent": AGENT_NAME,
        "version": AGENT_VERSION,
        "endpoints": {
            "health": "/health",
            "describe": "/describe",
            "process": "/process (POST)",
            "info": "/info",
            "docs": "/docs",
            "openapi": "/openapi.json"
        }
    })


# ============================================================================
# Exception Handlers
# ============================================================================

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle validation errors."""
    logger.warning(f"Validation error: {exc}")
    return JSONResponse(
        status_code=400,
        content={
            "status": "error",
            "error": str(exc),
            "data": None
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error": "Internal server error",
            "data": None
        }
    )


# ============================================================================
# Entrypoint for direct execution
# ============================================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting FastAPI server on {host}:{port}")
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=LOG_LEVEL.lower()
    )
