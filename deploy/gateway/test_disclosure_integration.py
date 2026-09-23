#!/usr/bin/env python3
"""Disclosure compiler release-path integration invariants (DGI1-DGI4)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))


class DisclosureCompilerGatewayIntegration(unittest.TestCase):
    def test_dgi1_payment_gate_and_release_image_price_the_compiler_exactly(self):
        from payment_gate import PRICE_MINOR
        import importlib.util

        dockerfile = (HERE / "Dockerfile").read_text()
        core_path = ROOT / "disclosure-compiler-agent" / "src" / "core.py"
        spec = importlib.util.spec_from_file_location(
            "disclosure_core_read_policy", core_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)
        self.assertEqual(PRICE_MINOR["disclosure-compiler"], 200)
        self.assertIn(
            "list_frameworks", module.DisclosureCompilerCore.READ_ACTIONS)
        self.assertIn(
            "get_framework", module.DisclosureCompilerCore.READ_ACTIONS)
        self.assertIn(
            "COPY disclosure-compiler-agent/ disclosure-compiler-agent/",
            dockerfile)

    def test_dgi2_catalog_v020_unlocks_coverage_but_not_checkout(self):
        catalog_path = (ROOT / "subscriptions-agent" / "data" /
                        "plan_catalog.v0.2.0.json")
        catalog = json.loads(catalog_path.read_text())
        self.assertEqual(catalog["pack_version"], "0.2.0")
        plans = {plan["id"]: plan for plan in catalog["plans"]}
        for plan_id in ("energy-seat", "climate-seat", "compliance-seat"):
            plan = plans[plan_id]
            self.assertTrue(plan["coverage_ready"])
            self.assertIsNone(plan["stripe_price_id"])
            self.assertEqual(plan["approval_status"], "draft")
            self.assertFalse(plan["checkout_enabled"])
            self.assertIn("disclosure-compiler", plan["covered_agents"])

    def test_dgi3_gateway_exposes_agent_and_seats_stay_fail_closed(self):
        from starlette.testclient import TestClient
        import viridis_mcp_gateway as gateway

        with tempfile.TemporaryDirectory() as tmp:
            old_db = os.environ.get("STATE_DB")
            old_members = gateway.EXTERNAL_MEMBERS
            os.environ["STATE_DB"] = str(Path(tmp) / "gateway.db")
            gateway.EXTERNAL_MEMBERS = []
            try:
                with TestClient(gateway.build_app()) as client:
                    health_response = client.get("/healthz")
                    directory_response = client.get("/")
                    seats_response = client.get("/seats")
            finally:
                gateway.EXTERNAL_MEMBERS = old_members
                if old_db is None:
                    os.environ.pop("STATE_DB", None)
                else:
                    os.environ["STATE_DB"] = old_db

        self.assertEqual(health_response.status_code, 200,
                         health_response.text)
        self.assertEqual(directory_response.status_code, 200)
        self.assertEqual(seats_response.status_code, 200)
        health = health_response.json()
        directory = directory_response.json()
        self.assertEqual(len(gateway.MOUNTS), 28)
        self.assertEqual(len(health["agents"]), 28)
        self.assertEqual(
            gateway.MOUNTS["disclosure-compiler"],
            "disclosure-compiler-agent")
        self.assertEqual(
            health["agents"]["disclosure-compiler"]["version"], "0.1.0")
        self.assertIn(
            "disclosure-compiler", health["payment_gate"]["gated_agents"])
        self.assertEqual(
            health["payment_gate"]["prices_minor"]["disclosure-compiler"],
            200)
        self.assertEqual(health["agents"]["hive"]["checks"]["rails_mode"],
                         "wired")
        self.assertEqual(
            health["agents"]["hive"]["checks"]["solvers_registered"], 3)
        self.assertEqual(health["payment_gate"]["prices_minor"]["hive"], 500)
        self.assertEqual(
            health["payment_gate"]["free_calls_per_day_by_agent"]["hive"], 0)
        self.assertEqual(
            directory["agents"]["hive"]["endpoint"], "/hive/mcp")
        self.assertEqual(
            health["subscriptions"]["checks"]["plan_catalog_version"],
            "0.2.0")
        self.assertEqual(
            directory["agents"]["disclosure-compiler"]["endpoint"],
            "/disclosure-compiler/mcp")
        # All five plans remain deliberately non-buyable until Justin records
        # approved recurring Price IDs in a later catalog pack.
        self.assertEqual(seats_response.text.count(
            "Coming soon — notify me"), 5)
        self.assertNotIn("Continue to Stripe", seats_response.text)
        for plan_id in ("disclosure-compiler", "ghg-ledger",
                        "taxcredit-engine", "regulatory-radar"):
            self.assertIn(plan_id, seats_response.text)

    def test_dgi4_deck_maps_role_price_and_visible_footnote(self):
        deck = (HERE / "deck.html").read_text()
        self.assertIn(
            '"disclosure-compiler":"revenue · compliance"', deck)
        self.assertIn('"disclosure-compiler":200', deck)
        self.assertIn('"disclosure-compiler": 200', deck)
        self.assertIn("disclosure-compiler $2", deck)


if __name__ == "__main__":
    unittest.main()
