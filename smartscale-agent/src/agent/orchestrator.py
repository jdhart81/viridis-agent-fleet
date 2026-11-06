from typing import Any, Dict, Optional

# Bound at import time on purpose: the MCP gateway evicts every `src*` module
# between agent loads, so a call-time relative import here would resolve
# against another agent's `src` package (gateway G1/G2).
from .dsl import MeasureOptions
from .tools.measure import MeasurementService
from .tools.specs import SpecsService

class Toolset:
    def __init__(self):
        self.measure = MeasurementService()
        self.specs = SpecsService()

class Orchestrator:
    def __init__(self):
        self.tools = Toolset()

    def handle_message(self, text: str, image_b64: Optional[str], context: Dict[str, Any]):
        t = text.lower().strip()
        # Very simple intent routing for demo purposes
        if any(k in t for k in ["spec", "dimensions", "size of", "how big", "width", "height", "depth"]):
            q = t.replace("specs", "").replace("specifications", "").strip()
            data = self.tools.specs.search(q)
            return {"type": "specs", "query": q, "results": data}
        if any(k in t for k in ["measure", "length", "angle", "diameter", "radius", "polygon", "area"]):
            if not image_b64:
                return {"type": "measure", "ok": False, "reason": "image_b64 required"}
            # Default options for NL path
            opts = MeasureOptions()
            # For NL, we require front-end to provide picks later; here we just run scale estimation
            result = self.tools.measure.measure_image_b64(image_b64, opts)
            return {"type": "measure", "result": result.model_dump()}
        return {"type": "chat", "message": "I can measure from an image (with scale) or fetch specs. Ask me to 'measure' or for 'specs'."}
