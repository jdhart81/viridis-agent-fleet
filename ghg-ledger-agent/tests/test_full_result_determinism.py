"""Determinism + verify purity pin for the paid `calculate_inventory` path.

GH8 (test_core.py) already pins audit_sha256 equality across two identical
calls, but only the digest field, and only within one core instance.
ghg-ledger is a paid x402 agent whose output feeds disclosure-compiler's
CSRD/ESRS drafts; its WHOLE result must be reproducible across fresh core
instances, and `verify_result` must be a pure, repeatable read. This
propagates the taxcredit-engine test_full_result_determinism idiom (N64)
per the standing Nightkeeper cross-pollination queue. Additive; GH1-GH9
untouched.
"""
import asyncio
import unittest
from copy import deepcopy

from src.core import build


def run(payload):
    # Fresh core per call: pins cross-instance determinism, not just
    # within-instance caching behavior.
    return asyncio.run(build().process(payload))


def _calc(activities, options):
    result = run({"action": "calculate_inventory", "activities": activities,
                  "options": options})
    assert result["status"] == "ok", result
    return result["data"]


def _verify(result):
    envelope = run({"action": "verify_result", "result": result})
    assert envelope["status"] == "ok", envelope
    return envelope["data"]


ACTIVITIES = [{"id": "gas-1",
               "activity_type": "stationary_combustion_natural_gas",
               "quantity": "1", "unit": "therm", "region": "US",
               "year": 2025}]
OPTIONS = {"organization_id": "acme", "reporting_period": "2025",
           "offset_buyer": "acme"}


class FullResultDeterminism(unittest.TestCase):
    def test_full_result_is_byte_identical_across_fresh_cores(self):
        a = _calc(ACTIVITIES, OPTIONS)
        b = _calc(ACTIVITIES, OPTIONS)
        self.assertEqual(a, b)

    def test_verify_result_is_pure_and_repeatable(self):
        result = _calc(ACTIVITIES, OPTIONS)
        snapshot = deepcopy(result)
        first = _verify(result)
        second = _verify(result)
        self.assertEqual(first, second)
        self.assertTrue(first["valid"])
        # Auditing must not mutate what it inspects.
        self.assertEqual(result, snapshot)

    def test_tamper_verdict_is_deterministic_on_repeat(self):
        tampered = deepcopy(_calc(ACTIVITIES, OPTIONS))
        tampered["line_items"][0]["kg_co2e"] = "5.999"
        first = _verify(tampered)
        second = _verify(tampered)
        self.assertEqual(first, second)
        self.assertFalse(first["valid"])
        self.assertFalse(first["audit_hash_valid"])

    def test_determinism_is_not_trivial(self):
        # Guard the pins: different inputs must diverge, so the equality
        # checks above cannot pass by collapsing to a constant result.
        one = _calc(ACTIVITIES, OPTIONS)
        two = _calc([{**ACTIVITIES[0], "quantity": "2"}], OPTIONS)
        self.assertNotEqual(one, two)
        self.assertNotEqual(one["grand_total"]["kg_co2e"],
                            two["grand_total"]["kg_co2e"])


if __name__ == "__main__":
    unittest.main()
