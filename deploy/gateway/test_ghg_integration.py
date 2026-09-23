"""GHG-ledger revenue-path integration invariants (GGI1-GGI7)."""

import asyncio
import importlib.util
import os
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from payment_gate import GATE_ATTR, PRICE_MINOR, PaymentGate
from state_store import StateStore
from viridis_mcp_gateway import _attach_ghg_rail_composition


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


def grid_call():
    return {
        "action": "calculate_inventory",
        "activities": [{
            "activity_type": "purchased_electricity",
            "quantity": "1000",
            "unit": "kwh",
            "region": "US",
            "year": 2023,
        }],
        "options": {
            "reporting_period": "2026",
            "organization_id": "gateway-integration",
            "organizational_boundary": "operational_control",
        },
    }


class GhgGatewayIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        ghg_module = load_core("ghg-ledger-agent")
        self.ghg = ghg_module.build()
        metering_module = load_core("agent-metering-agent")
        self.meter = metering_module.build()
        compute_module = load_core("agent-compute-ledger-agent")
        self.compute = compute_module.build()
        provenance_module = load_core("agent-provenance-agent")
        self.provenance = provenance_module.build()
        self.store = StateStore(Path(self.tmp.name) / "state.db")
        self.store.attach("ghg-ledger", self.ghg)
        self.store.attach("metering", self.meter)
        self.store.attach("compute-ledger", self.compute)
        self.store.attach("provenance", self.provenance)
        _attach_ghg_rail_composition(
            self.ghg, self.compute, self.provenance)
        self.gate = PaymentGate(self.store, self.meter, free_calls_per_day=1)
        self.gate.attach("ghg-ledger", self.ghg)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_ggi1_exact_inventory_then_one_dollar_payment_required(self):
        result = call(self.ghg, grid_call())
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["inventory_status"],
                         "complete_for_supplied_activities")
        self.assertEqual(result["data"]["grand_total"]["kg_co2e"],
                         "349.742")
        self.assertEqual(
            result["data"]["scope_totals_kg_co2e"]["scope_2_location_based"],
            "349.742")
        scopes = result["data"]["scope_totals_kg_co2e"]
        scope_sum = (Decimal(scopes["scope_1"])
                     + Decimal(scopes["scope_2_location_based"])
                     + Decimal(scopes["scope_3"]))
        self.assertEqual(
            scope_sum, Decimal(result["data"]["grand_total"]["kg_co2e"]))
        self.assertEqual(len(result["data"]["audit_sha256"]), 64)
        self.assertNotIn("rail_posts", result["data"])

        audit_sha256 = result["data"]["audit_sha256"]
        input_sha256 = result["data"]["input_sha256"]
        factor_pack = result["data"]["factor_pack"]
        pack_version = (factor_pack.get("version")
                        or factor_pack.get("pack_version"))
        pack_digest = factor_pack.get("sha256") or factor_pack.get("digest")
        source_ids = result["data"]["lineage"]["source_ids_used"]
        record_id = f"ghg-{audit_sha256[:24]}"
        self.assertEqual(
            result["data"]["offset_weave"]["inventory_id"], record_id)
        self.assertEqual(
            result["data"]["notary_payload"]["content_digest"], audit_sha256)
        self.assertEqual(
            result["rail_posts"]["compute_ledger"]["status"], "ok")
        self.assertEqual(
            result["rail_posts"]["provenance"]["status"], "ok")
        self.assertEqual(
            result["rail_posts"]["compute_ledger"]["inventory_id"], record_id)
        self.assertEqual(
            result["rail_posts"]["provenance"]["artifact_id"], record_id)

        inventory = call(
            self.compute,
            {"action": "get_inventory", "inventory_id": record_id})
        artifact = call(
            self.provenance,
            {"action": "get_artifact", "artifact_id": record_id})
        self.assertEqual(inventory["status"], "ok")
        self.assertEqual(artifact["status"], "ok")
        self.assertEqual(inventory["data"]["mass_g"], 349742)
        self.assertEqual(
            inventory["data"]["content_digest"], audit_sha256)
        self.assertEqual(
            inventory["data"]["factor_pack_version"], pack_version)
        self.assertEqual(
            inventory["data"]["factor_pack_digest"], pack_digest)
        self.assertEqual(inventory["data"]["source_ids"], source_ids)
        self.assertEqual(artifact["data"]["artifact_hash"], audit_sha256)
        self.assertEqual(artifact["data"]["parent_hashes"], [pack_digest])
        self.assertEqual(artifact["data"]["relation"], "calculated_from")
        self.assertEqual(
            artifact["data"]["metadata_digest"], input_sha256)

        refused = call(self.ghg, grid_call())
        self.assertEqual(refused["error_type"], "payment_required")
        self.assertEqual(refused["amount_minor"], PRICE_MINOR["ghg-ledger"])
        self.assertEqual(refused["amount_minor"], 100)

    def test_ggi2_factor_reads_and_audit_verification_stay_free(self):
        calculated = call(self.ghg, grid_call())
        reads = [
            {"action": "list_factor_packs"},
            {"action": "get_factor_pack", "region": "US", "year": 2023},
            {"action": "verify_result", "result": calculated["data"]},
        ]
        results = [call(self.ghg, payload) for payload in reads]
        for result in results:
            self.assertNotEqual(result.get("error_type"), "payment_required")
        verified = results[-1]["data"]
        self.assertTrue(verified["valid"])
        self.assertTrue(verified["factor_pack_current"])
        self.assertEqual(verified["supplied_sha256"],
                         verified["computed_sha256"])
        self.assertEqual(getattr(self.ghg, GATE_ATTR)["used"], 1)

    def test_ggi3_every_allowed_and_refused_inventory_is_metered(self):
        call(self.ghg, grid_call())
        call(self.ghg, grid_call())
        meter_id = getattr(self.ghg, GATE_ATTR)["meter_id"]
        usage = call(
            self.meter, {"action": "usage_summary", "meter_id": meter_id})
        self.assertEqual(usage["data"]["event_count"], 2)

    def test_ggi4_repeated_audit_posts_are_idempotent_on_both_rails(self):
        self.gate.free_calls = 2
        first = call(self.ghg, grid_call())
        second = call(self.ghg, grid_call())
        self.assertEqual(
            first["data"]["audit_sha256"], second["data"]["audit_sha256"])
        self.assertTrue(
            second["rail_posts"]["compute_ledger"]["duplicate"])
        self.assertFalse(
            second["rail_posts"]["provenance"]["created"])
        self.assertEqual(
            first["rail_posts"]["compute_ledger"]["inventory_id"],
            second["rail_posts"]["compute_ledger"]["inventory_id"])
        self.assertEqual(
            first["rail_posts"]["provenance"]["artifact_id"],
            second["rail_posts"]["provenance"]["artifact_id"])

    def test_ggi5_rail_failures_are_explicit_and_inventory_still_verifies(self):
        ghg_module = load_core("ghg-ledger-agent")
        ghg = ghg_module.build()

        class BrokenRail:
            async def process(self, _payload):
                raise RuntimeError("rail unavailable")

        _attach_ghg_rail_composition(ghg, BrokenRail(), BrokenRail())
        calculated = call(ghg, grid_call())
        self.assertEqual(calculated["status"], "ok")
        self.assertEqual(
            calculated["data"]["grand_total"]["kg_co2e"], "349.742")
        self.assertEqual(
            calculated["rail_posts"]["compute_ledger"]["status"], "error")
        self.assertEqual(
            calculated["rail_posts"]["provenance"]["status"], "error")
        verified = call(
            ghg, {"action": "verify_result", "result": calculated["data"]})
        self.assertEqual(verified["status"], "ok")
        self.assertTrue(verified["data"]["valid"])

    def test_ggi6_gateway_exposes_mounted_gated_agent_in_22_agent_fleet(self):
        from starlette.testclient import TestClient
        old_state_db = os.environ.get("STATE_DB")
        os.environ["STATE_DB"] = str(Path(self.tmp.name) / "gateway.db")
        try:
            from viridis_mcp_gateway import MOUNTS, build_app
            with TestClient(build_app()) as client:
                health_response = client.get("/healthz")
                directory_response = client.get("/")
        finally:
            if old_state_db is None:
                os.environ.pop("STATE_DB", None)
            else:
                os.environ["STATE_DB"] = old_state_db

        health = health_response.json()
        directory = directory_response.json()
        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(directory_response.status_code, 200)
        self.assertEqual(len(MOUNTS), 28)
        self.assertEqual(
            MOUNTS["ghg-ledger"], "ghg-ledger-agent")
        self.assertEqual(
            health["agents"]["ghg-ledger"]["version"], "0.1.0")
        self.assertIn(
            "ghg-ledger", health["payment_gate"]["gated_agents"])
        self.assertEqual(
            health["payment_gate"]["prices_minor"]["ghg-ledger"], 100)
        self.assertEqual(
            directory["agents"]["ghg-ledger"]["endpoint"],
            "/ghg-ledger/mcp")

    def test_ggi7_conflicting_audit_id_is_an_explicit_failed_rail_post(self):
        # Derive the exact deterministic ID without touching the composed
        # cores, then occupy it on both rails with different integrity fields.
        ghg_module = load_core("ghg-ledger-agent")
        expected = call(ghg_module.build(), grid_call())
        audit_sha256 = expected["data"]["audit_sha256"]
        record_id = f"ghg-{audit_sha256[:24]}"

        hostile_inventory = call(self.compute, {
            "action": "record_inventory",
            "agent_id": "ghg-ledger-agent",
            "inventory_id": record_id,
            "mass_g": 1,
            "content_digest": "1" * 64,
            "factor_pack_version": "hostile-pack",
            "factor_pack_digest": "2" * 64,
            "source_ids": ["hostile-source"],
        })
        hostile_artifact = call(self.provenance, {
            "action": "register_artifact",
            "artifact_id": record_id,
            "artifact_hash": "3" * 64,
            "producer_agent_id": "hostile-agent",
            "parent_hashes": ["4" * 64],
            "relation": "unrelated",
            "metadata_digest": "5" * 64,
        })
        self.assertEqual(hostile_inventory["status"], "ok")
        self.assertEqual(hostile_artifact["status"], "ok")

        calculated = call(self.ghg, grid_call())
        self.assertEqual(calculated["status"], "ok")
        self.assertEqual(calculated["data"]["audit_sha256"], audit_sha256)
        for rail_name, field in (("compute_ledger", "inventory_id"),
                                 ("provenance", "artifact_id")):
            post = calculated["rail_posts"][rail_name]
            self.assertEqual(post["status"], "error")
            self.assertEqual(post["error_type"], "ConflictError")
            self.assertEqual(post["field"], field)
            self.assertEqual(post["value"], record_id)
            self.assertIn("requires identical", post["constraint"])

        # Conflict reporting never mutates the pre-existing hostile records
        # and never corrupts the independently verifiable GHG calculation.
        inventory = call(
            self.compute, {"action": "get_inventory", "inventory_id": record_id})
        artifact = call(
            self.provenance, {"action": "get_artifact", "artifact_id": record_id})
        self.assertEqual(inventory["data"]["content_digest"], "1" * 64)
        self.assertEqual(artifact["data"]["artifact_hash"], "3" * 64)
        verified = call(self.ghg, {
            "action": "verify_result", "result": calculated["data"],
        })
        self.assertTrue(verified["data"]["valid"])


if __name__ == "__main__":
    unittest.main()
