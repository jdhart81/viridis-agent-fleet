"""Determinism + verify purity pin for the paid `calculate_takeoff` path.

QT8 (test_core.py) already pins audit_sha256 equality across two identical
calls, but only the digest field, and only within one core instance.
quantity-takeoff is a paid x402 agent selling reproducible construction
takeoffs; its WHOLE result must be byte-identical across fresh core
instances, and `verify_result` must be a pure, repeatable read. This
propagates the taxcredit-engine test_full_result_determinism idiom (N64)
per the standing Nightkeeper cross-pollination queue. Additive; QT1-QT9
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


def _calc(items, options):
    result = run({"action": "calculate_takeoff", "items": items,
                  "options": options})
    assert result["status"] == "ok", result
    return result["data"]


def _verify(result):
    envelope = run({"action": "verify_result", "result": result})
    assert envelope["status"] == "ok", envelope
    return envelope["data"]


def slab(**extra):
    item = {
        "id": "slab-1", "assembly": "concrete_slab",
        "unit_system": "imperial",
        "dimensions": {
            "length": {"value": "20", "unit": "ft"},
            "width": {"value": "30", "unit": "ft"},
            "thickness": {"value": "4", "unit": "in"},
        },
    }
    item.update(extra)
    return item


OPTIONS = {"project_id": "job-7", "revision_id": "r1"}


class FullResultDeterminism(unittest.TestCase):
    def test_full_result_is_byte_identical_across_fresh_cores(self):
        a = _calc([slab()], OPTIONS)
        b = _calc([slab()], OPTIONS)
        self.assertEqual(a, b)

    def test_verify_result_is_pure_and_repeatable(self):
        result = _calc([slab()], OPTIONS)
        snapshot = deepcopy(result)
        first = _verify(result)
        second = _verify(result)
        self.assertEqual(first, second)
        self.assertTrue(first["valid"])
        # Auditing must not mutate what it inspects.
        self.assertEqual(result, snapshot)

    def test_tamper_verdict_is_deterministic_on_repeat(self):
        tampered = deepcopy(_calc([slab()], OPTIONS))
        tampered["line_items"][0]["exact_qty"] = "999.000"
        first = _verify(tampered)
        second = _verify(tampered)
        self.assertEqual(first, second)
        self.assertFalse(first["valid"])
        self.assertFalse(first["audit_hash_valid"])

    def test_determinism_is_not_trivial(self):
        # Guard the pins: different geometry must diverge, so the equality
        # checks above cannot pass by collapsing to a constant result.
        one = _calc([slab()], OPTIONS)
        two = _calc([slab(dimensions={
            "length": {"value": "21", "unit": "ft"},
            "width": {"value": "30", "unit": "ft"},
            "thickness": {"value": "4", "unit": "in"},
        })], OPTIONS)
        self.assertNotEqual(one, two)
        self.assertNotEqual(one["line_items"][0]["exact_qty"],
                            two["line_items"][0]["exact_qty"])


if __name__ == "__main__":
    unittest.main()
