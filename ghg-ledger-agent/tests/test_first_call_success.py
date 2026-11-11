"""A first-time caller's ordinary request should compute, or be told the exact retry.

U2 unit aliases only rename a unit (GH7 conversion is unchanged and disclosed).
T1 a failed factor lookup lists what is bundled; GH6 still fails closed and no
other year is ever substituted.
"""
import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core import build


def run(activities, options=None):
    core = build()
    return asyncio.run(core.process({"action": "calculate_inventory",
                                     "activities": activities,
                                     "options": options or {}}))["data"]


def diesel(unit, quantity="400", region="US"):
    return {"id": "gen", "activity_type": "stationary_combustion_diesel",
            "quantity": quantity, "unit": unit, "region": region, "year": 2025}


class FirstCallSuccess(unittest.TestCase):
    def test_plain_gallon_against_a_us_factor_matches_gallon_us_exactly(self):
        exact = run([diesel("gallon_us")])
        for spelling in ("gallon", "gallons", "gal", "Gallons", "US gallon"):
            alias = run([diesel(spelling)])
            line = alias["line_items"][0]
            self.assertEqual(line["status"], "determinate", spelling)
            self.assertEqual(line["kg_co2e"], exact["line_items"][0]["kg_co2e"])
            self.assertEqual(line["unit_conversion"]["input_unit_read_as"], "gallon_us")
            self.assertEqual(line["input"]["unit"], spelling)  # caller's spelling is kept
        self.assertNotIn("input_unit_read_as", exact["line_items"][0]["unit_conversion"])

    def test_common_spellings_equal_their_bundled_unit(self):
        cases = [
            ("stationary_combustion_diesel", "US", 2025, "1000", "liters", "litre"),
            ("business_travel_passenger_car", "US", 2025, "1200", "miles", "mile"),
            ("business_travel_passenger_car", "US", 2025, "1200", "kilometers", "km"),
            ("stationary_combustion_natural_gas", "US", 2025, "900", "therms", "therm"),
            ("waste_landfilled_mixed_msw", "US", 2025, "3", "tonnes", "metric_tonne"),
            ("purchased_electricity", "US", 2023, "5", "megawatt hours", "mwh"),
        ]
        for activity_type, region, year, quantity, spelled, bundled in cases:
            def one(unit):
                return run([{"id": "x", "activity_type": activity_type, "quantity": quantity,
                             "unit": unit, "region": region, "year": year}])["line_items"][0]
            alias, exact = one(spelled), one(bundled)
            self.assertEqual(alias["status"], "determinate", spelled)
            self.assertEqual(alias["kg_co2e"], exact["kg_co2e"], spelled)

    def test_ambiguous_or_unknown_units_still_fail_closed_and_list_accepted_units(self):
        for unit in ("ton", "barrel", "imperial_gallon"):
            line = run([diesel(unit)])["line_items"][0]
            self.assertEqual(line["status"], "indeterminate", unit)
            self.assertIn("no bundled conversion", line["reason"])
            self.assertIn("accepted units: gallon_us, liter, litre", line["reason"])

    def test_missing_year_fails_closed_and_names_the_bundled_years(self):
        data = run([{"id": "dc", "activity_type": "purchased_electricity",
                     "quantity": "250000", "unit": "kWh", "region": "US-ERCT", "year": 2025}])
        line = data["line_items"][0]
        self.assertEqual(line["status"], "indeterminate")
        self.assertTrue(line["excluded_from_totals"])
        self.assertEqual(data["grand_total"]["kg_co2e"], "0.000")   # nothing substituted
        self.assertIn("factor not in pack", line["reason"])
        self.assertIn("US-ERCT 2023", line["reason"])
        retry = run([{"id": "dc", "activity_type": "purchased_electricity",
                      "quantity": "250000", "unit": "kWh", "region": "US-ERCT", "year": 2023}])
        self.assertEqual(retry["line_items"][0]["status"], "determinate")

    def test_unknown_activity_type_says_so(self):
        line = run([{"id": "x", "activity_type": "jet_fuel", "quantity": "1",
                     "unit": "gallon", "region": "US", "year": 2025}])["line_items"][0]
        self.assertEqual(line["status"], "indeterminate")

    def test_alias_result_verifies_and_is_deterministic(self):
        core = build()
        first = run([diesel("gallons")])
        second = run([diesel("gallons")])
        self.assertEqual(first["audit_sha256"], second["audit_sha256"])
        verdict = asyncio.run(core.process({"action": "verify_result", "result": first}))
        self.assertEqual(verdict["status"], "ok", verdict)


if __name__ == "__main__":
    unittest.main()
