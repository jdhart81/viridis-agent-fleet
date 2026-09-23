"""Fail-closed target selection for mutation-capable deployment smokes."""
import os

PRODUCTION_BASE = "https://mcp.viridisconservation.com"
CONFIRMATION = "I_UNDERSTAND_THIS_WRITES_PRODUCTION"


def guarded_smoke_base() -> str:
    base = os.environ.get(
        "VIRIDIS_SMOKE_BASE", "http://127.0.0.1:8402").rstrip("/")
    if (base == PRODUCTION_BASE
            and os.environ.get("VIRIDIS_PRODUCTION_SMOKE_WRITES")
            != CONFIRMATION):
        raise RuntimeError(
            "production-writing smoke blocked; use an isolated candidate or "
            f"set VIRIDIS_PRODUCTION_SMOKE_WRITES={CONFIRMATION} explicitly")
    return base
