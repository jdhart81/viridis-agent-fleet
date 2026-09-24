from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Any, Dict
import json
from .orchestrator import Orchestrator
from .dsl import MeasureRequest, MeasureOptions
from ..version import SMARTSCALE_VERSION

app = FastAPI(
    title="SmartScale ChArUco Prototype",
    version=SMARTSCALE_VERSION,
    description="Non-production experimental image-measurement surface",
)
orchestrator = Orchestrator()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/measure")
async def measure(image: UploadFile = File(...),
                  options: Optional[str] = Form(None)):
    try:
        img_bytes = await image.read()
        opts = MeasureOptions() if options is None else MeasureOptions.model_validate_json(options)
        result = orchestrator.tools.measure.measure_image(img_bytes, opts)
        return JSONResponse(result.model_dump())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/specs")
async def specs(query: str):
    result = orchestrator.tools.specs.search(query)
    return JSONResponse(result)

class AgentChatIn(BaseModel):
    message: str
    image_b64: Optional[str] = None
    context: Dict[str, Any] = {}

@app.post("/agent/chat")
async def agent_chat(body: AgentChatIn):
    reply = orchestrator.handle_message(body.message, body.image_b64, body.context)
    return JSONResponse(reply)
