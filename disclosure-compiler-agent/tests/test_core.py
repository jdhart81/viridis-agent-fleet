"""DC1-DC8 invariants for the deterministic disclosure compiler."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parents[1]
FLEET_ROOT = AGENT_ROOT.parent
sys.path.insert(0, str(AGENT_ROOT))

from src.core import (  # noqa: E402
    FRAMEWORK_PACK_SHA256, PACK, ApplicabilityError, GHGVerificationError,
    UnsupportedFrameworkError, build,
)


def real_ghg_result() -> dict:
    path = FLEET_ROOT / "ghg-ledger-agent" / "src" / "core.py"
    name = "disclosure_test_real_ghg"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    core = module.build()
    return core.calculate_inventory([
        {
            "id": "grid-1",
            "activity_type": "purchased_electricity",
            "quantity": "1000",
            "unit": "kwh",
            "region": "US",
            "year": 2023,
            "market_factor": {
                "kg_co2e_per_unit": "0.100",
                "unit": "kwh",
                "source": "supplier-specific-test-evidence",
            },
        }
    ], {"organization_id": "acme", "reporting_period": "2026",
        "organizational_boundary": "operational_control"})


def facts() -> dict:
    return {
        "company_name": "Acme Climate Works",
        "reporting_period": "2026",
        "transition_plan": {"status": "board-approved", "target_year": 2035},
        "climate_targets": {"scope": "Scopes 1-3", "target": "50% by 2035"},
        "ghg_intensity": {"value": "0.012", "unit": "tCO2e/USDm revenue"},
    }


def applicable(framework: str = "esrs-e1") -> dict:
    return {"applicability": {"framework": framework, "applies": True,
                               "reason": "regulatory-radar match rr-001",
                               "source": "regulatory-radar"}}


class DisclosureCompilerInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ghg = real_ghg_result()

    def setUp(self):
        self.core = build()

    def compile(self, company_facts=None, ghg=None, options=None):
        return self.core.compile_disclosure(
            "esrs-e1", company_facts if company_facts is not None else facts(),
            self.ghg if ghg is None else ghg,
            options if options is not None else applicable())

    def test_dc1_dc4_esrs_maps_real_ghg_and_every_value_is_cited(self):
        result = self.compile()
        self.assertEqual(result["draft_status"], "complete")
        self.assertFalse(result["inference_used"])
        mapped = {item["id"]: item for item in result["filled_datapoints"]}
        self.assertEqual(mapped["gross_scope_1"]["value"], "0.000000")
        self.assertEqual(mapped["gross_scope_2_location_based"]["value"],
                         "0.349742")
        self.assertEqual(mapped["gross_scope_2_market_based"]["value"],
                         "0.100000")
        self.assertEqual(mapped["gross_scope_3"]["value"], "0.000000")
        self.assertEqual(mapped["total_location_based"]["value"], "0.349742")
        self.assertTrue(all(len(item["citations"]) == 2 for item in mapped.values()))
        ghg_citation = mapped["gross_scope_2_location_based"]["citations"][0]
        self.assertEqual(ghg_citation["audit_sha256"], self.ghg["audit_sha256"])
        self.assertEqual(result["ghg_provenance"]["factor_pack"]["sha256"],
                         self.ghg["factor_pack"]["sha256"])

    def test_dc2_pack_is_versioned_source_linked_and_content_addressed(self):
        listed = self.core.list_frameworks()
        self.assertEqual(listed["sha256"], FRAMEWORK_PACK_SHA256)
        self.assertEqual({item["id"] for item in listed["frameworks"]},
                         {"esrs-e1", "sec-climate", "ifrs-s2", "tnfd"})
        esrs = self.core.get_framework("esrs-e1")
        self.assertEqual(esrs["framework_pack"]["version"], PACK["pack_version"])
        self.assertTrue(all(source["url"].startswith("https://")
                            for source in esrs["sources"]))

    def test_dc3_missing_is_explicit_and_completeness_is_exact_decimal(self):
        supplied = facts()
        supplied.pop("transition_plan")
        result = self.compile(company_facts=supplied)
        self.assertEqual(result["draft_status"], "partial")
        self.assertEqual(result["completeness"], {
            "filled_required": 9, "required": 10, "missing_required": 1,
            "ratio": "0.900000", "percent": "90.00"})
        self.assertEqual(result["gaps"][0]["status"], "MISSING: transition_plan")
        self.assertNotIn("transition_plan",
                         {item["id"] for item in result["filled_datapoints"]})
        rendered = json.dumps(result, sort_keys=True)
        self.assertNotIn("fabricated", rendered.lower())

    def test_dc5_tampered_real_ghg_result_is_rejected(self):
        tampered = deepcopy(self.ghg)
        tampered["esrs_e1"]["gross_scope_1"] = "999.000000"
        with self.assertRaises(GHGVerificationError):
            self.compile(ghg=tampered)
        envelope = asyncio.run(self.core.process({
            "action": "compile_disclosure", "framework": "esrs-e1",
            "company_facts": facts(), "ghg_result": tampered,
            "options": applicable(),
        }))
        self.assertEqual(envelope["status"], "error")
        self.assertEqual(envelope["error_type"], "GHGVerificationError")

    def test_dc6_audit_is_deterministic_and_tamper_detected(self):
        first = self.compile()
        second = self.compile()
        self.assertEqual(first["audit_sha256"], second["audit_sha256"])
        self.assertEqual(first["notary_payload"], second["notary_payload"])
        self.assertTrue(self.core.verify_result(first)["valid"])
        tampered = deepcopy(first)
        tampered["filled_datapoints"][0]["value"] = "Different Entity"
        checked = self.core.verify_result(tampered)
        self.assertFalse(checked["valid"])
        self.assertFalse(checked["audit_hash_valid"])

    def test_dc7_applicability_fail_closed_force_recorded_and_unsupported(self):
        with self.assertRaises(ApplicabilityError):
            self.core.compile_disclosure("tnfd", {"company_name": "Acme"},
                                         None, {"applicability": {
                                             "framework": "tnfd", "applies": False,
                                             "reason": "radar says out of scope"}})
        forced = self.core.compile_disclosure(
            "tnfd", {"company_name": "Acme"}, None,
            {"applicability": {"framework": "tnfd", "applies": False,
                               "reason": "radar says out of scope",
                               "source": "regulatory-radar"},
             "force": True, "force_reason": "internal scenario analysis"})
        self.assertTrue(forced["applicability"]["forced"])
        self.assertEqual(forced["applicability"]["force_reason"],
                         "internal scenario analysis")
        with self.assertRaises(UnsupportedFrameworkError):
            self.core.get_framework("unknown-framework")
        envelope = asyncio.run(self.core.process({
            "action": "compile_disclosure", "framework": "unknown-framework",
            "company_facts": {}, "options": {"force": True}}))
        self.assertEqual(envelope["error_type"], "UnsupportedFrameworkError")

    def test_dc8_label_disclaimer_health_and_describe(self):
        result = self.compile()
        self.assertEqual(result["label"], "disclosure draft for professional review")
        self.assertIn("not a filed", result["disclaimer"])
        described = self.core.describe()
        self.assertEqual(described["pricing"]["free_calls_per_day"], 10)
        self.assertEqual(described["pricing"]["price_minor_per_compile"], 200)
        self.assertFalse(described["inference_in_serving_path"])
        health = asyncio.run(self.core.health())
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["version"], "0.1.0")
        self.assertEqual(health["checks"]["framework_pack_sha256"],
                         FRAMEWORK_PACK_SHA256)

    def test_binary_float_rejected_before_audit(self):
        bad = facts()
        bad["ghg_intensity"] = 1.25
        envelope = asyncio.run(self.core.process({
            "action": "compile_disclosure", "framework": "esrs-e1",
            "company_facts": bad, "ghg_result": self.ghg,
            "options": applicable()}))
        self.assertEqual(envelope["status"], "error")
        self.assertEqual(envelope["error_type"], "ValidationError")


if __name__ == "__main__":
    unittest.main()
