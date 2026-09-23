"""Signed Cliff Check product surface on the existing Tax Credit Engine.

All monetary calculations and missing-field decisions come from the engine.
Only the payment gate may execute an eligible report; this module owns the
durable, hashed design-partner redemption ledger.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import logging
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "products" / "signed-cliff-check" / "build_report.py"
logger = logging.getLogger("viridis.cliff_check")


def _report_module():
    spec = importlib.util.spec_from_file_location("signed_cliff_report", REPORT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CliffCheckService:
    KNOWN_ACTIONS = frozenset({"signed_cliff_check", "preview"})
    READ_ACTIONS = frozenset({"preview"})

    def __init__(self, tax_engine):
        self._engine = tax_engine
        self._partner_redemptions = {}
        self._partner_log = []
        self._partner_lock = threading.RLock()

    async def health(self):
        return {"status": "ok", "product": "signed-cliff-check"}

    def describe(self):
        return {"name": "signed-cliff-check", "product_on": "taxcredit-engine",
                "price_usd_per_call": "149.00"}

    def preflight(self, payload):
        if not isinstance(payload, dict) or payload.get("action") not in self.KNOWN_ACTIONS:
            return {"status": "error", "error_type": "ValidationError", "message": "invalid action"}
        if payload.get("credit") not in {"48E", "45Y"} or not isinstance(payload.get("facts"), dict):
            return {"status": "error", "error_type": "ValidationError", "message": "credit must be 48E or 45Y and facts must be an object"}
        if not all(isinstance(payload.get(k), str) and payload[k].strip() for k in ("client", "project")):
            return {"status": "error", "error_type": "ValidationError", "message": "client and project are required"}
        try:
            result = self._engine.calculate(payload["credit"], payload["facts"])
        except Exception:
            logger.exception("cliff preflight failed")
            return {"status": "error", "error_type": "ValidationError", "message": "invalid project facts"}
        missing = [f["id"].split(":", 1)[1] for f in result.get("eligibility_flags", [])
                   if f.get("id", "").startswith("required:")]
        return {"status": result["calculation_status"], "missing_facts": missing}

    async def process(self, payload):
        decision = self.preflight(payload)
        if decision["status"] == "error":
            return decision
        # The payment wrapper admits only paid, partner, or indeterminate calls.
        receipt, report_html = await asyncio.to_thread(
            _report_module().build, payload["credit"], payload["facts"],
            payload["client"], payload["project"])
        return {"status": "ok", "data": {"receipt": receipt,
                "report_html": report_html, "missing_facts": decision["missing_facts"]}}

    def redeem_partner(self, code, store):
        if not isinstance(code, str) or not code:
            return False
        configured = {hashlib.sha256(c.strip().encode()).hexdigest()
                      for c in os.environ.get("CLIFF_CHECK_PARTNER_CODES", "").split(",")
                      if c.strip()}
        digest = hashlib.sha256(code.encode()).hexdigest()
        if digest not in configured:
            return False
        with self._partner_lock:
            count = self._partner_redemptions.get(digest, 0)
            if count >= 3:
                return False
            self._partner_redemptions[digest] = count + 1
            self._partner_log.append({"code_sha256": digest,
                                      "redemption": count + 1,
                                      "at": datetime.now(timezone.utc).isoformat()})
            if not store.save("signed-cliff-check", self):
                self._partner_redemptions[digest] = count
                self._partner_log.pop()
                return False
            logger.info("cliff partner redemption recorded (code_hash_prefix=%s, redemption=%d)",
                        digest[:12], count + 1)
            return True
