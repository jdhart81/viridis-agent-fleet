"""Determinism + verify purity pin for the paid `compile_disclosure` path.

DC6 (test_core.py) already pins audit_sha256 and notary_payload equality
across two identical compiles, but not the WHOLE result, and not across
fresh core instances. disclosure-compiler is a paid x402 agent whose ESRS/
SEC/IFRS/TNFD drafts must be reproducible end-to-end for the citation chain
to mean anything; `verify_result` must be a pure, repeatable read. This
propagates the taxcredit-engine test_full_result_determinism idiom (N64)
per the standing Nightkeeper cross-pollination queue. Additive; DC1-DC8
untouched.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from copy import deepcopy
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]
FLEET_ROOT = AGENT_ROOT.parent
sys.path.insert(0, str(AGENT_ROOT))

from src.core import build  # noqa: E402


def real_ghg_result() -> dict:
    path = FLEET_ROOT / "ghg-ledger-agent" / "src" / "core.py"
    name = "determinism_test_real_ghg"
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


def applicable() -> dict:
    return {"applicability": {"framework": "esrs-e1", "applies": True,
                              "reason": "regulatory-radar match rr-001",
                              "source": "regulatory-radar"}}


class FullResultDeterminism(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ghg = real_ghg_result()

    def compile_fresh(self, company_facts=None):
        # Fresh core per call: pins cross-instance determinism, not just
        # within-instance caching behavior.
        return build().compile_disclosure(
            "esrs-e1",
            company_facts if company_facts is not None else facts(),
            self.ghg, applicable())

    def test_full_result_is_byte_identical_across_fresh_cores(self):
        a = self.compile_fresh()
        b = self.compile_fresh()
        self.assertEqual(a, b)

    def test_verify_result_is_pure_and_repeatable(self):
        result = self.compile_fresh()
        snapshot = deepcopy(result)
        first = build().verify_result(result)
        second = build().verify_result(result)
        self.assertEqual(first, second)
        self.assertTrue(first["valid"])
        # Auditing must not mutate what it inspects.
        self.assertEqual(result, snapshot)

    def test_tamper_verdict_is_deterministic_on_repeat(self):
        tampered = deepcopy(self.compile_fresh())
        tampered["filled_datapoints"][0]["value"] = "Different Entity"
        first = build().verify_result(tampered)
        second = build().verify_result(tampered)
        self.assertEqual(first, second)
        self.assertFalse(first["valid"])
        self.assertFalse(first["audit_hash_valid"])

    def test_determinism_is_not_trivial(self):
        # Guard the pins: different company facts must diverge, so the
        # equality checks cannot pass by collapsing to a constant result.
        partial = facts()
        partial.pop("transition_plan")
        one = self.compile_fresh()
        two = self.compile_fresh(company_facts=partial)
        self.assertNotEqual(one, two)
        self.assertEqual(one["draft_status"], "complete")
        self.assertEqual(two["draft_status"], "partial")


if __name__ == "__main__":
    unittest.main()
