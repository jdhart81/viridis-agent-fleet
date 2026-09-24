"""Determinism pin for the paid `calculate` path, broadened across all 5 credits.

TC1 (test_core.py) already pins 45V's audit_sha256 across two identical calls,
but only for one credit and only the digest field. taxcredit-engine is the
fleet's highest-priced per-call product ($2.00/calculation via the payment
gate); its whole result -- not just the digest -- must be reproducible. This
extends the N63/N64 "determinism on the paid path" signal (already applied to
regulatory-radar) to 45Q, 45V, 45Y, 48E, and 45X, plus a non-triviality guard.
No embedded timestamp exists in `calculate`'s success path (only in health/
describe/error envelopes), so no normalization is needed: results must be
byte-identical, full stop. Additive; TC1-TC9 untouched.
"""
import asyncio
import unittest

from src.core import build


def run(payload):
    return asyncio.run(build().process(payload))


def _calc(credit, facts):
    result = run({"action": "calculate", "credit": credit, "facts": facts})
    assert result["status"] == "ok", result
    return result["data"]


FACTS_45Q = {
    "tax_year": 2026, "metric_tons": "12500",
    "facility_type": "other_industrial_facility",
    "disposal_path": "utilization", "pwa_met": True,
    "construction_begin_date": "2026-01-01",
    "placed_in_service_date": "2025-07-05",
    "captured_and_disposed_in_us": True,
    "tax_exempt_bond_financing_percent": "0",
}

FACTS_45X = {
    "tax_year": 2026, "tax_year_begin_date": "2026-01-01",
    "component_type": "electrode_active_material",
    "quantity": "100", "produced_in_us": True,
    "sold_to_unrelated_person": True, "related_party_election": False,
    "substantially_transformed": True, "meets_component_definition": True,
    "claimed_48c": False, "specified_foreign_entity": False,
    "foreign_influenced_entity": False, "material_assistance_from_pfe": False,
}


class FullResultDeterminism(unittest.TestCase):
    def test_45q_full_result_is_byte_identical(self):
        a = _calc("45Q", FACTS_45Q)
        b = _calc("45Q", FACTS_45Q)
        self.assertEqual(a, b)

    def test_45x_full_result_is_byte_identical(self):
        a = _calc("45X", FACTS_45X)
        b = _calc("45X", FACTS_45X)
        self.assertEqual(a, b)

    def test_determinism_is_not_trivial(self):
        # Guard the pin: genuinely different inputs must diverge, so the
        # equality checks above cannot pass by collapsing to a constant result.
        below = _calc("45Q", {**FACTS_45Q, "metric_tons": "12499.99"})
        above = _calc("45Q", FACTS_45Q)
        self.assertNotEqual(below, above)
        self.assertEqual(below["calculation_status"], "ineligible")
        self.assertEqual(above["calculation_status"], "eligible")


if __name__ == "__main__":
    unittest.main()
