"""Purity + idempotency pin for `verify_result` (TC7's audit read).

TC7 proves tamper detection and test_full_result_determinism (N64) pins the
paid `calculate` path, but nothing pins that verify_result itself is a pure,
repeatable read: repeated verifies of an unchanged result must be identical,
must not mutate the result they inspect, and a tamper verdict must be
deterministic on repeat. taxcredit-engine is the fleet's highest-priced
per-call product ($2.00/calculation); its audit read completes the
determinism story. Closes an N67 re-grep finding. Additive; TC1-TC9
untouched.
"""
import asyncio
import unittest
from copy import deepcopy

from src.core import build


def run(payload):
    # Fresh core per call: pins cross-instance repeatability.
    return asyncio.run(build().process(payload))


FACTS_45Q = {
    "tax_year": 2026, "metric_tons": "12500",
    "facility_type": "other_industrial_facility",
    "disposal_path": "utilization", "pwa_met": True,
    "construction_begin_date": "2026-01-01",
    "placed_in_service_date": "2025-07-05",
    "captured_and_disposed_in_us": True,
    "tax_exempt_bond_financing_percent": "0",
}


def _calc():
    result = run({"action": "calculate", "credit": "45Q", "facts": FACTS_45Q})
    assert result["status"] == "ok", result
    return result["data"]


def _verify(result):
    envelope = run({"action": "verify_result", "result": result})
    assert envelope["status"] == "ok", envelope
    return envelope["data"]


class VerifyResultPureIdempotent(unittest.TestCase):
    def test_verify_result_is_pure_and_repeatable(self):
        result = _calc()
        snapshot = deepcopy(result)
        first = _verify(result)
        second = _verify(result)
        self.assertEqual(first, second)
        self.assertTrue(first["valid"])
        # Auditing must not mutate what it inspects.
        self.assertEqual(result, snapshot)

    def test_tamper_verdict_is_deterministic_on_repeat(self):
        tampered = deepcopy(_calc())
        tampered["credit_amount_usd"] = "999999.00"
        first = _verify(tampered)
        second = _verify(tampered)
        self.assertEqual(first, second)
        self.assertFalse(first["valid"])


if __name__ == "__main__":
    unittest.main()
