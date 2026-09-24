"""FastAPI transport for the Viridis robustness engine agent."""

from __future__ import annotations

import os
import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.core import RobustnessAgent


agent = RobustnessAgent()
app = FastAPI(
    title="Viridis Robustness Engine Agent",
    version="0.6.0",
    description="Fail-closed governed robustness evaluation service",
)


@app.get("/health")
async def health() -> JSONResponse:
    result = await agent.health()
    return JSONResponse(result, status_code=200 if result["status"] == "ok" else 503)


@app.get("/describe")
async def describe() -> dict:
    return agent.describe()


@app.post("/evaluate")
async def evaluate(request: Request) -> JSONResponse:
    content_length = request.headers.get("content-length")
    try:
        declared_length = int(content_length) if content_length is not None else None
    except ValueError:
        return JSONResponse(
            {"status": "error", "error": "Invalid Content-Length header"},
            status_code=400,
        )
    if declared_length is not None and (
        declared_length < 0 or declared_length > agent.config.max_request_bytes
    ):
        return JSONResponse(
            {"status": "error", "error": "Request exceeds the configured size limit"},
            status_code=413,
        )
    try:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > agent.config.max_request_bytes:
                return JSONResponse(
                    {"status": "error", "error": "Request exceeds the configured size limit"},
                    status_code=413,
                )
        payload = json.loads(body.decode("utf-8"))
        result = await agent.process(payload)
        return JSONResponse(result)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JSONResponse(
            {"status": "error", "error": "Request body must be valid UTF-8 JSON"},
            status_code=400,
        )
    except ValueError as exc:
        return JSONResponse({"status": "error", "error": str(exc)}, status_code=400)
    except Exception:
        return JSONResponse(
            {"status": "error", "error": "Internal evaluation error"},
            status_code=500,
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("ROBUSTNESS_SERVICE_HOST", "0.0.0.0"),
        port=int(os.environ.get("ROBUSTNESS_SERVICE_PORT", "8080")),
    )
