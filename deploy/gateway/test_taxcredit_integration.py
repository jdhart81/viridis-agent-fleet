"""Tax-credit revenue-path integration invariants (TGI1-TGI4)."""

import asyncio
import hashlib
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from payment_gate import GATE_ATTR, PRICE_MINOR, PaymentGate
from state_store import StateStore


def load_core(agent_dir: str):
    for name in [n for n in list(sys.modules)
                 if n == "src" or n.startswith("src.")]:
        del sys.modules[name]
    package = importlib.util.spec_from_file_location(
        "src", ROOT / agent_dir / "src" / "__init__.py",
        submodule_search_locations=[str(ROOT / agent_dir / "src")])
    module = importlib.util.module_from_spec(package)
    sys.modules["src"] = module
    package.loader.exec_module(module)
    core_spec = importlib.util.spec_from_file_location(
        "src.core", ROOT / agent_dir / "src" / "core.py")
    core_module = importlib.util.module_from_spec(core_spec)
    sys.modules["src.core"] = core_module
    core_spec.loader.exec_module(core_module)
    return core_module


def call(core, payload):
    result = core.process(payload)
    return asyncio.run(result) if asyncio.iscoroutine(result) else result


def h2_call():
    return {
        "action": "calculate", "credit": "45V", "facts": {
            "tax_year": 2026, "kg_hydrogen": "10",
            "lifecycle_kg_co2e_per_kg_h2": "0.4",
            "greet_version": "45VH2-GREET-2025",
            "evidence_digest": hashlib.sha256(b"report").hexdigest(),
            "pwa_met": True, "produced_in_us": True,
            "construction_begin_date": "2026-01-01",
            "placed_in_service_date": "2026-01-01",
            "section_45q_claimed_for_facility": False,
            "tax_exempt_bond_financing_percent": "0",
        }}


class TaxCreditGatewayIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tax_module = load_core("taxcredit-engine-agent")
        self.tax = tax_module.build()
        metering_module = load_core("agent-metering-agent")
        self.meter = metering_module.build()
        self.store = StateStore(Path(self.tmp.name) / "state.db")
        self.store.attach("taxcredit-engine", self.tax)
        self.store.attach("metering", self.meter)
        self.gate = PaymentGate(self.store, self.meter, free_calls_per_day=1)
        self.gate.attach("taxcredit-engine", self.tax)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_tgi1_paid_price_and_free_tier(self):
        self.assertEqual(call(self.tax, h2_call())["status"], "ok")
        refused = call(self.tax, h2_call())
        self.assertEqual(refused["error_type"], "payment_required")
        self.assertEqual(refused["amount_minor"], PRICE_MINOR["taxcredit-engine"])
        self.assertEqual(refused["amount_minor"], 200)

    def test_tgi2_read_and_verify_actions_stay_free(self):
        call(self.tax, h2_call())
        for action in ("list_rule_packs", "get_rule_pack", "verify_result"):
            payload = {"action": action, "credit": "45V", "result": {}}
            result = call(self.tax, payload)
            self.assertNotEqual(result.get("error_type"), "payment_required")
        self.assertEqual(getattr(self.tax, GATE_ATTR)["used"], 1)

    def test_tgi3_every_allowed_and_refused_call_is_metered(self):
        call(self.tax, h2_call())
        call(self.tax, h2_call())
        meter_id = getattr(self.tax, GATE_ATTR)["meter_id"]
        usage = call(self.meter, {"action": "usage_summary", "meter_id": meter_id})
        self.assertEqual(usage["data"]["event_count"], 2)

    def test_tgi4_gateway_health_exposes_taxcredit_in_22_agent_fleet(self):
        from starlette.testclient import TestClient
        os.environ["STATE_DB"] = str(Path(self.tmp.name) / "gateway.db")
        from viridis_mcp_gateway import MOUNTS, build_app
        with TestClient(build_app()) as client:
            response = client.get("/healthz")
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(MOUNTS), 28)
        self.assertEqual(body["agents"]["taxcredit-engine"]["version"], "0.1.0")
        self.assertIn("taxcredit-engine", body["payment_gate"]["gated_agents"])
        self.assertEqual(
            body["payment_gate"]["prices_minor"]["taxcredit-engine"], 200)


if __name__ == "__main__":
    unittest.main()
