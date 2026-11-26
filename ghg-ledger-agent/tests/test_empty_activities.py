"""An empty activities list is refused like a missing one (EL1-EL4).

EL1 calculate_inventory with [] (or the JSON text "[]") returns the same
    ValidationError envelope as missing activities, with first_call_help and
    no next_calls, instead of an empty "complete" inventory.
EL2 the paid preflight answers it before any quota, credit or seat is spent.
EL3 a non-empty request is unchanged and still takes the metered path.
EL4 the direct calculate_inventory([]) method is unchanged.
"""
import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core import EXAMPLE_REQUEST, FIRST_CALL_HELP, build

EMPTY = ([], "[]", " [] ")


def process(payload):
    return asyncio.run(build().process(payload))


def preflight(payload):
    return asyncio.run(build()._paid_preflight(payload))


def strip_time(answer):
    return {k: v for k, v in answer.items() if k != "timestamp"}


class EmptyActivities(unittest.TestCase):
    def setUp(self):
        self.missing = process({"action": "calculate_inventory"})

    def test_el1_empty_list_gets_the_missing_activities_envelope_and_example(self):
        self.assertEqual(self.missing["status"], "error")
        for activities in EMPTY:
            for options in (None, {}):
                payload = {"action": "calculate_inventory", "activities": activities}
                if options is not None:
                    payload["options"] = options
                answer = process(payload)
                self.assertEqual(answer["status"], "error", activities)
                self.assertEqual(answer["error_type"], self.missing["error_type"])
                self.assertEqual(answer["field"], "activities")
                self.assertIn("non-empty", answer["message"])
                self.assertEqual(answer["first_call_help"], self.missing["first_call_help"])
                self.assertEqual(answer["first_call_help"], FIRST_CALL_HELP)
                self.assertNotIn("next_calls", answer)
                self.assertNotIn("data", answer)
                self.assertEqual(set(answer), set(self.missing))

    def test_el2_preflight_refuses_empty_list_before_any_quota(self):
        for activities in EMPTY:
            payload = {"action": "calculate_inventory", "activities": activities}
            refusal = preflight(payload)
            self.assertIsNotNone(refusal, activities)
            self.assertEqual(strip_time(refusal), strip_time(process(payload)))
        self.assertIsNotNone(preflight({"action": "calculate_inventory"}))

    def test_el3_non_empty_request_is_unchanged_and_metered(self):
        payload = {"action": "calculate_inventory", **EXAMPLE_REQUEST}
        self.assertIsNone(preflight(payload))
        first, second = process(payload), process(payload)
        self.assertEqual(first["status"], "ok")
        self.assertEqual(first["data"]["inventory_status"], "complete_for_supplied_activities")
        self.assertEqual(first["data"]["audit_sha256"], second["data"]["audit_sha256"])
        self.assertIn("next_calls", first)
        self.assertNotIn("first_call_help", first)
        one = process({"action": "calculate_inventory",
                       "activities": EXAMPLE_REQUEST["activities"][0]})
        self.assertEqual(one["status"], "ok")  # GF1 one object is still a list of one
        self.assertIsNone(preflight({"action": "list_factor_packs"}))

    def test_el4_direct_method_still_computes_an_empty_inventory(self):
        data = build().calculate_inventory([], {})
        self.assertEqual(data["inventory_status"], "complete_for_supplied_activities")
        self.assertEqual(data["grand_total"]["kg_co2e"], "0.000")


if __name__ == "__main__":
    unittest.main()
