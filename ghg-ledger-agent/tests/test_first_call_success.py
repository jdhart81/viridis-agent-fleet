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

    def test_a_later_activity_year_uses_the_latest_earlier_factor_and_says_so(self):
        data = run([{"id": "dc", "activity_type": "purchased_electricity",
                     "quantity": "250000", "unit": "kWh", "region": "US-ERCT", "year": 2025}])
        line = data["line_items"][0]
        self.assertEqual(line["status"], "determinate")
        self.assertEqual(line["factor_vintage"]["factor_year"], 2023)
        exact = run([{"id": "dc", "activity_type": "purchased_electricity",
                      "quantity": "250000", "unit": "kWh", "region": "US-ERCT", "year": 2023}])
        self.assertEqual(line["kg_co2e"], exact["line_items"][0]["kg_co2e"])   # same factor, same number
        self.assertNotIn("factor_vintage", exact["line_items"][0])

    def test_an_activity_year_before_every_bundled_factor_fails_closed(self):
        data = run([{"id": "dc", "activity_type": "purchased_electricity",
                     "quantity": "250000", "unit": "kWh", "region": "US-ERCT", "year": 2021}])
        line = data["line_items"][0]
        self.assertEqual(line["status"], "indeterminate")
        self.assertTrue(line["excluded_from_totals"])
        self.assertEqual(data["grand_total"]["kg_co2e"], "0.000")   # nothing substituted
        self.assertIn("factor not in pack", line["reason"])
        self.assertIn("US-ERCT 2023", line["reason"])

    def test_one_object_or_a_json_string_is_read_as_the_activity_list(self):
        import asyncio, json
        from src import core as ghg
        item = {"id": "e", "activity_type": "purchased_electricity", "quantity": "100",
                "unit": "kWh", "region": "US", "year": 2023}
        engine = ghg.build()
        want = asyncio.run(engine.process({"action": "calculate_inventory", "activities": [item]}))
        for shape in (item, json.dumps([item]), json.dumps(item)):
            got = asyncio.run(engine.process({"action": "calculate_inventory", "activities": shape,
                                              "options": None}))
            self.assertEqual(got["status"], "ok", shape)
            self.assertEqual(got["data"]["audit_sha256"], want["data"]["audit_sha256"])
        for shape in (None, "not json", 7, "[broken"):
            got = asyncio.run(engine.process({"action": "calculate_inventory", "activities": shape}))
            self.assertEqual(got["status"], "error")
            self.assertIn("first_call_help", got)

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


class PartialResultStillTeaches(unittest.TestCase):
    def test_one_failed_line_among_good_ones_returns_the_help(self):
        core = build()
        response = asyncio.run(core.process({"action": "calculate_inventory", "activities": [
            diesel("gallons"),
            {"id": "fleet", "activity_type": "mobile_combustion_gasoline", "quantity": "500",
             "unit": "gallons", "region": "US", "year": 2025}], "options": {}}))
        self.assertEqual(response["data"]["inventory_status"], "partial_indeterminate")
        self.assertIn("first_call_help", response)
        self.assertNotIn("first_call_help", response["data"])


class GridSubregions(unittest.TestCase):
    """EG1-EG3: every EPA eGRID2023 subregion is bundled, as published."""
    CODES = ("AKGD AKMS AZNM CAMX ERCT FRCC HIMS HIOA MROE MROW NEWE NWPP NYCW NYLI NYUP "
             "PRMS RFCE RFCM RFCW RMPA SPNO SPSO SRMV SRMW SRSO SRTV SRVC").split()

    def test_eg1_all_27_subregions_compute_for_a_2025_activity(self):
        data = run([{"id": code, "activity_type": "purchased_electricity", "quantity": 1000,
                     "unit": "kWh", "region": f"US-{code}", "year": 2025} for code in self.CODES])
        self.assertEqual(data["inventory_status"], "complete_for_supplied_activities")
        self.assertEqual(len(data["line_items"]), 27)
        for line in data["line_items"]:
            self.assertEqual(line["factor"]["year"], 2023)
            self.assertEqual(line["factor_vintage"]["activity_year"], 2025)

    def test_eg2_published_gas_rates_are_used_digit_for_digit(self):
        from decimal import Decimal
        from src.core import PACK
        factor = PACK["factors"]["epa_egrid2023_nyup"]
        self.assertEqual(factor["co2e_or_gas_breakdown"], {
            "kind": "gas_breakdown", "mass_unit": "lb",
            "mass_per_unit": {"co2": "242.1", "ch4_fossil": "0.011", "n2o": "0.001"}})
        line = run([{"id": "ny", "activity_type": "purchased_electricity", "quantity": "1",
                     "unit": "MWh", "region": "US-NYUP", "year": 2023}])["line_items"][0]
        gwp = PACK["gwp_profile"]["values"]
        lb = (Decimal("242.1") + Decimal("0.011") * Decimal(gwp["ch4_fossil"])
              + Decimal("0.001") * Decimal(gwp["n2o"]))
        want = (lb * Decimal("0.45359237")).quantize(Decimal("0.001"))
        self.assertEqual(Decimal(line["kg_co2e"]), want)
        self.assertEqual(line["gas_breakdown"]["resolution"], "gas_resolved")
        self.assertIn("epa-egrid2023-summary-tables-rev2", line["factor"]["source_ids"])

    def test_eg3_earlier_results_for_the_three_original_grid_factors_are_unchanged(self):
        for region, want in (("US", "349.742"),):
            line = run([{"id": "g", "activity_type": "purchased_electricity", "quantity": "1000",
                         "unit": "kwh", "region": region, "year": 2023}])["line_items"][0]
            self.assertEqual(line["kg_co2e"], want)
            self.assertEqual(line["gas_breakdown"]["resolution"], "direct_co2e_only")
