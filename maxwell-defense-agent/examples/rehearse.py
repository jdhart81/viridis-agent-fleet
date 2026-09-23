"""Unpaid local sample; requires explicit process-local candidate opt-in."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.core import MaxwellDefenseCore

report = asyncio.run(MaxwellDefenseCore().process({
    "action": "rehearse_defense", "client_hashes_per_second": 100000,
    "client_p95_budget_ms": 250, "backend_cost_ms": 2000, "peak_requests_per_second": 100,
}))
print(json.dumps({"execution": "local_unpaid_fixture", "report": report}, indent=2))
