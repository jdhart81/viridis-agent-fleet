#!/usr/bin/env python3
"""Quantity-takeoff revenue-path integration invariants (QGI1-QGI6)."""

import asyncio
import importlib.util
import os
import sys
import tempfile
import unittest
from copy import deepcopy
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


def slab_call():
    return {
        "action": "calculate_takeoff",
        "items": [{
            "id": "slab-1",
            "assembly": "concrete_slab",
            "unit_system": "imperial",
            "dimensions": {
                "length": {"value": "20", "unit": "ft"},
                "width": {"value": "30", "unit": "ft"},
                "thickness": {"value": "4", "unit": "in"},
            },
        }],
        "options": {"project_id": "gateway-integration"},
    }


class QuantityTakeoffGatewayIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        takeoff_module = load_core("quantity-takeoff-agent")
        self.takeoff = takeoff_module.build()
        metering_module = load_core("agent-metering-agent")
        self.meter = metering_module.build()
        self.store = StateStore(Path(self.tmp.name) / "state.db")
        self.store.attach("quantity-takeoff", self.takeoff)
        self.store.attach("metering", self.meter)
        self.gate = PaymentGate(self.store, self.meter, free_calls_per_day=1)
        self.gate.attach("quantity-takeoff", self.takeoff)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_qgi1_auditable_slab_then_fifty_cent_payment_required(self):
        result = call(self.takeoff, slab_call())
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["takeoff_status"],
                         "complete_for_supplied_items")
        line = result["data"]["line_items"][0]
        self.assertEqual(line["material"], "ready_mix_concrete")
        self.assertEqual(line["unit"], "yd3")
        self.assertEqual(line["net_qty"], "7.407")
        self.assertEqual(line["exact_qty"], "7.778")
        self.assertEqual(line["purchase_qty"], "7.78")
        self.assertEqual(len(result["data"]["audit_sha256"]), 64)
        self.assertEqual(
            result["data"]["notary_payload"]["content_digest"],
            result["data"]["audit_sha256"])
        self.assertTrue(result["data"]["disclaimer"])

        refused = call(self.takeoff, slab_call())
        self.assertEqual(refused["status"], "error")
        self.assertEqual(refused["error_type"], "payment_required")
        self.assertEqual(refused["http_equivalent"], 402)
        self.assertEqual(
            refused["amount_minor"], PRICE_MINOR["quantity-takeoff"])
        self.assertEqual(refused["amount_minor"], 50)
        self.assertEqual(refused["billing_path"], "per_call_freemium")

    def test_qgi2_catalog_and_verification_reads_stay_open(self):
        calculated = call(self.takeoff, slab_call())
        reads = [
            {"action": "list_assemblies"},
            {"action": "get_assembly", "assembly_type": "concrete_slab"},
            {"action": "list_material_pack"},
            {"action": "get_material_pack"},
            {"action": "verify_result", "result": calculated["data"]},
        ]
        results = [call(self.takeoff, payload) for payload in reads]
        for result in results:
            self.assertNotEqual(result.get("error_type"), "payment_required")
        verified = results[-1]["data"]
        self.assertTrue(verified["valid"])
        self.assertTrue(verified["material_pack_current"])
        self.assertEqual(verified["supplied_sha256"],
                         verified["computed_sha256"])
        self.assertEqual(getattr(self.takeoff, GATE_ATTR)["used"], 1)

    def test_qgi3_allowed_and_refused_takeoffs_are_metered(self):
        call(self.takeoff, slab_call())
        call(self.takeoff, slab_call())
        meter_id = getattr(self.takeoff, GATE_ATTR)["meter_id"]
        usage = call(
            self.meter, {"action": "usage_summary", "meter_id": meter_id})
        self.assertEqual(usage["data"]["event_count"], 2)

    def test_qgi4_tamper_detection_remains_open_after_quota(self):
        calculated = call(self.takeoff, slab_call())
        tampered = deepcopy(calculated["data"])
        tampered["line_items"][0]["purchase_qty"] = "0.00"
        verified = call(
            self.takeoff, {"action": "verify_result", "result": tampered})
        self.assertEqual(verified["status"], "ok")
        self.assertFalse(verified["data"]["valid"])
        self.assertEqual(getattr(self.takeoff, GATE_ATTR)["used"], 1)

    def test_qgi5_gateway_keeps_takeoff_live_in_22_agent_fleet_and_rails_free(self):
        from starlette.testclient import TestClient
        import viridis_mcp_gateway as gateway

        old_state_db = os.environ.get("STATE_DB")
        old_external_members = gateway.EXTERNAL_MEMBERS
        os.environ["STATE_DB"] = str(Path(self.tmp.name) / "gateway.db")
        gateway.EXTERNAL_MEMBERS = []
        try:
            with TestClient(gateway.build_app()) as client:
                health_response = client.get("/healthz")
                directory_response = client.get("/")
        finally:
            gateway.EXTERNAL_MEMBERS = old_external_members
            if old_state_db is None:
                os.environ.pop("STATE_DB", None)
            else:
                os.environ["STATE_DB"] = old_state_db

        health = health_response.json()
        directory = directory_response.json()
        gate = health["payment_gate"]
        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(directory_response.status_code, 200)
        self.assertEqual(len(gateway.MOUNTS), 28)
        self.assertEqual(len(health["agents"]), 28)
        self.assertEqual(
            gateway.MOUNTS["quantity-takeoff"], "quantity-takeoff-agent")
        self.assertEqual(
            health["agents"]["quantity-takeoff"]["version"], "0.1.0")
        self.assertTrue(health["persistence"]["available"])
        self.assertEqual(
            gate["prices_minor"]["quantity-takeoff"], 50)
        self.assertIn("quantity-takeoff", gate["gated_agents"])
        self.assertEqual(
            directory["agents"]["quantity-takeoff"]["endpoint"],
            "/quantity-takeoff/mcp")
        for rail in ("identity", "trust", "escrow", "metering",
                     "arbitration", "compute-ledger", "covenant",
                     "provenance", "offsets", "erc8004", "surety", "notary"):
            self.assertNotIn(rail, gate["gated_agents"])

    def test_qgi6_release_packaging_and_deck_pricing_are_coherent(self):
        dockerfile = (HERE / "Dockerfile").read_text()
        deck = (HERE / "deck.html").read_text()
        self.assertIn(
            "COPY quantity-takeoff-agent/ quantity-takeoff-agent/",
            dockerfile)
        self.assertIn(
            '"quantity-takeoff":"revenue · construction"', deck)
        self.assertIn('"quantity-takeoff": 50', deck)
        self.assertIn("quantity-takeoff 50\\u00a2", deck)


if __name__ == "__main__":
    unittest.main()
