"""GH1-GH9 invariant and fleet-contract tests for ghg-ledger-agent."""

import ast
import asyncio
import json
import re
import unittest
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import src.core as core_module
from src.core import (FACTOR_PACK_SHA256, GWP_PROFILE_SHA256, PACK,
                      build)


def call(core, payload):
    return asyncio.run(core.process(payload))


def grid(**extra):
    activity = {"id": "grid-1", "activity_type": "purchased_electricity",
                "quantity": "1000", "unit": "kwh", "region": "US", "year": 2023}
    activity.update(extra)
    return activity


def natural_gas(quantity="1", unit="therm", **extra):
    activity = {"id": "gas-1", "activity_type": "stationary_combustion_natural_gas",
                "quantity": quantity, "unit": unit, "region": "US", "year": 2025}
    activity.update(extra)
    return activity


class GHGLedgerInvariants(unittest.TestCase):
    def setUp(self):
        self.core = build()

    def calculate(self, activities, options=None):
        response = call(self.core, {"action": "calculate_inventory",
                                    "activities": activities,
                                    "options": options or {}})
        self.assertEqual(response["status"], "ok", response)
        return response["data"]

    # GH1 — Decimal throughout; one fixed 3dp HALF_UP output boundary.
    def test_GH1_decimal_only_math_and_exact_egrid_rounding(self):
        result = self.calculate([grid()])
        self.assertEqual(result["line_items"][0]["kg_co2e"], "349.742")
        self.assertEqual(result["grand_total"]["kg_co2e"], "349.742")
        self.assertRegex(result["grand_total"]["kg_co2e"], r"^-?\d+\.\d{3}$")
        source = Path(__file__).resolve().parents[1] / "src" / "core.py"
        tree = ast.parse(source.read_text())
        float_literals = [node.value for node in ast.walk(tree)
                          if isinstance(node, ast.Constant)
                          and isinstance(node.value, float)]
        self.assertEqual(float_literals, [])
        rejected = self.calculate([grid(quantity=1000.0)])
        self.assertEqual(rejected["inventory_status"], "indeterminate")
        self.assertIn("binary floats are rejected", rejected["indeterminate"][0]["reason"])

    # GH2 — literal factor schema, source links, version, and raw-file digest.
    def test_GH2_bundled_versioned_source_linked_pack(self):
        self.assertRegex(FACTOR_PACK_SHA256, r"^[0-9a-f]{64}$")
        required = {"activity_type", "unit", "region", "year",
                    "co2e_or_gas_breakdown", "source_id"}
        source_ids = {source["id"] for source in PACK["sources"]}
        self.assertGreaterEqual(len(PACK["factors"]), 14)
        for factor in PACK["factors"].values():
            self.assertTrue(required <= set(factor))
            self.assertIn(factor["source_id"], source_ids)
        for source in PACK["sources"]:
            self.assertTrue(source["url"].startswith("https://"))
        result = self.calculate([natural_gas()])
        self.assertEqual(result["factor_pack"]["sha256"], FACTOR_PACK_SHA256)
        self.assertTrue(result["factor_pack"]["sources_used"])
        used_ids = {source["id"] for source in result["factor_pack"]["sources_used"]}
        self.assertIn("epa-ghg-factor-hub-2025", used_ids)
        self.assertIn(PACK["gwp_profile"]["source_id"], used_ids)

    # GH3 — explicit AR6 GWP-100, gas mass, and CO2e contributions.
    def test_GH3_explicit_gwp_and_natural_gas_breakdown(self):
        result = self.calculate([natural_gas()])
        line = result["line_items"][0]
        self.assertEqual(result["factor_pack"]["gwp_set_id"],
                         "ipcc_ar6_gwp100_v0.1.0")
        self.assertEqual(result["factor_pack"]["gwp_set_sha256"], GWP_PROFILE_SHA256)
        self.assertEqual(PACK["gwp_profile"]["values"]["ch4_fossil"], "29.8")
        self.assertEqual(PACK["gwp_profile"]["values"]["ch4_non_fossil"], "27.2")
        self.assertEqual(PACK["gwp_profile"]["values"]["n2o"], "273")
        self.assertEqual(line["kg_co2e"], "5.312")
        gases = line["gas_breakdown"]["gases"]
        self.assertEqual(gases["co2"]["kg_gas"], "5.306000")
        self.assertEqual(gases["ch4_fossil"]["kg_gas"], "0.000100")
        self.assertEqual(gases["n2o"]["kg_gas"], "0.000010")
        self.assertEqual(gases["ch4_fossil"]["gwp100"], "29.8")

    # GH4 — all 15 categories exist; classification basis is explicit.
    def test_GH4_scope_classification_mapping_or_caller(self):
        mapped = call(self.core, {"action": "classify_activity",
                                  "activity": {"activity_type":
                                               "business_travel_passenger_car"}})
        self.assertTrue(mapped["data"]["supported"])
        self.assertEqual(mapped["data"]["suggestion"]["scope"], "scope_3")
        self.assertEqual(mapped["data"]["suggestion"]["scope3_category"],
                         "category_6_business_travel")
        self.assertEqual(len(mapped["data"]["scope3_categories"]), 15)
        caller = self.calculate([natural_gas(scope="1",
                                             category="caller_stationary")])
        classification = caller["line_items"][0]["classification"]
        self.assertEqual(classification["method"], "caller_supplied")
        self.assertEqual(classification["category"], "caller_stationary")
        mixed = self.calculate([{
            "activity_type": "purchased_goods_spend", "quantity": "1",
            "unit": "usd", "region": "US", "year": 2026, "scope": "3",
        }])["line_items"][0]["classification"]
        self.assertEqual(mixed["method"], "mixed_caller_and_bundled_mapping")
        self.assertEqual(mixed["field_sources"]["scope"], "caller_supplied")
        self.assertEqual(mixed["field_sources"]["category"], "factor_pack")
        self.assertEqual(mixed["field_sources"]["scope3_category"],
                         "deterministic_mapping")

    # GH5 — independent location and market totals; no location fallback.
    def test_GH5_scope2_dual_reporting_diverges(self):
        activity = grid(market_factor={"kg_co2e_per_unit": "0.100",
                                       "unit": "kwh", "source": "supplier-contract-7"})
        result = self.calculate([activity])
        dual = result["scope_2_dual_reporting"]
        self.assertEqual(dual["location_based_kg_co2e"], "349.742")
        self.assertEqual(dual["market_based_kg_co2e"], "100.000")
        self.assertEqual(dual["market_based_status"], "complete")
        self.assertEqual(result["grand_total"]["location_based_kg_co2e"], "349.742")
        self.assertEqual(result["grand_total"]["market_based_kg_co2e"], "100.000")
        absent = self.calculate([grid()])
        self.assertIsNone(absent["scope_2_dual_reporting"]["market_based_kg_co2e"])
        self.assertEqual(absent["scope_2_dual_reporting"]["market_based_status"],
                         "indeterminate")

    # GH6 — unknown activity/year is explicit and excluded from totals.
    def test_GH6_unknown_fails_closed_and_never_nearest_year(self):
        unknown = {"id": "unknown", "activity_type": "space_magic",
                   "quantity": "99", "unit": "kg", "region": "MARS", "year": 2026}
        wrong_year = grid(id="wrong-year", year=2026)
        result = self.calculate([grid(), unknown, wrong_year])
        self.assertEqual(result["inventory_status"], "partial_indeterminate")
        self.assertEqual(result["grand_total"]["kg_co2e"], "349.742")
        self.assertEqual(result["grand_total"]["indeterminate_line_count"], 2)
        self.assertTrue(all(item["excluded_from_totals"] for item in result["indeterminate"]))
        self.assertIn("factor not in pack", result["indeterminate"][0]["reason"])
        self.assertIn("year=2026", result["indeterminate"][1]["reason"])

        mobile_missing = self.calculate([{
            "activity_type": "mobile_combustion_gasoline", "quantity": "1",
            "unit": "gallon_us", "region": "US", "year": 2025,
        }])
        self.assertEqual(mobile_missing["inventory_status"], "indeterminate")
        self.assertIn("mobile_source_class='nonroad_four_stroke'",
                      mobile_missing["indeterminate"][0]["reason"])
        mobile = self.calculate([{
            "activity_type": "mobile_combustion_gasoline", "quantity": "1",
            "unit": "gallon_us", "region": "US", "year": 2025,
            "mobile_source_class": "nonroad_four_stroke",
        }])
        line = mobile["line_items"][0]
        self.assertEqual(line["factor"]["applicability"]["id"],
                         "epa_nonroad_four_stroke_gasoline_2025")
        used_ids = {source["id"] for source in mobile["factor_pack"]["sources_used"]}
        self.assertIn(PACK["gwp_profile"]["source_id"], used_ids)

    # GH7 — deterministic conversions and no reinterpretation.
    def test_GH7_unit_integrity_therm_kwh_diesel_litre_and_bad_unit(self):
        therm = self.calculate([natural_gas("1", "therm")])
        kwh = self.calculate([natural_gas("29.3071070172222", "kwh")])
        self.assertEqual(therm["grand_total"]["kg_co2e"], "5.312")
        self.assertEqual(kwh["grand_total"]["kg_co2e"], "5.312")
        diesel = self.calculate([{
            "activity_type": "stationary_combustion_diesel", "quantity": "1",
            "unit": "litre", "region": "US", "year": 2025,
        }])
        self.assertEqual(diesel["grand_total"]["kg_co2e"], "2.706")
        bad = self.calculate([natural_gas("1", "passenger_mile")])
        self.assertEqual(bad["inventory_status"], "indeterminate")
        self.assertIn("no bundled conversion", bad["indeterminate"][0]["reason"])

    # GH8 — deterministic audit, notary shape, and tamper detection.
    def test_GH8_reproducible_audit_and_tamper_detection(self):
        options = {"organization_id": "acme", "reporting_period": "2025",
                   "offset_buyer": "acme"}
        first = self.calculate([natural_gas()], options)
        second = self.calculate([natural_gas()], options)
        self.assertEqual(first["audit_sha256"], second["audit_sha256"])
        self.assertNotIn("timestamp", json.dumps(first))
        self.assertEqual(first["notary_payload"]["content_digest"],
                         first["audit_sha256"])
        verified = call(self.core, {"action": "verify_result", "result": first})["data"]
        self.assertTrue(verified["valid"])
        self.assertTrue(verified["factor_pack_current"])
        tampered = deepcopy(first)
        tampered["line_items"][0]["kg_co2e"] = "5.999"
        check = call(self.core, {"action": "verify_result", "result": tampered})["data"]
        self.assertFalse(check["valid"])
        self.assertFalse(check["audit_hash_valid"])
        tampered_notary = deepcopy(first)
        tampered_notary["notary_payload"]["context"] = "evil"
        check = call(self.core, {"action": "verify_result",
                                 "result": tampered_notary})["data"]
        self.assertTrue(check["audit_hash_valid"])
        self.assertFalse(check["notary_payload_valid"])
        self.assertFalse(check["derived_payloads_valid"])
        self.assertFalse(check["valid"])
        tampered_offset = deepcopy(first)
        tampered_offset["offset_weave"]["buy_offset_args"]["mass_g"] = 999999
        check = call(self.core, {"action": "verify_result",
                                 "result": tampered_offset})["data"]
        self.assertTrue(check["audit_hash_valid"])
        self.assertFalse(check["offset_weave_valid"])
        self.assertFalse(check["valid"])

        # A content-intact historical result stays valid after a pack bump;
        # currency is a separate signal, not part of integrity validity.
        current_pack = core_module.FACTOR_PACK_SHA256
        try:
            core_module.FACTOR_PACK_SHA256 = "f" * 64
            stale = call(self.core, {"action": "verify_result",
                                     "result": first})["data"]
        finally:
            core_module.FACTOR_PACK_SHA256 = current_pack
        self.assertTrue(stale["valid"])
        self.assertTrue(stale["audit_hash_valid"])
        self.assertTrue(stale["derived_payloads_valid"])
        self.assertFalse(stale["factor_pack_current"])

    # GH9 — every rollup conserves; tampering fails loud.
    def test_GH9_conservation_and_tampered_rollup_fails_loud(self):
        result = self.calculate([natural_gas(), grid()])
        self.assertEqual(result["grand_total"]["kg_co2e"], "355.054")
        self.core.assert_conservation(result)
        tampered = deepcopy(result)
        tampered["scope_totals_kg_co2e"]["scope_1"] = "5.313"
        with self.assertRaisesRegex(AssertionError, "GH9 conservation drift"):
            self.core.assert_conservation(tampered)
        verify = call(self.core, {"action": "verify_result", "result": tampered})["data"]
        self.assertFalse(verify["conservation_valid"])

        tiny = self.calculate([
            natural_gas("0.0001", id="tiny-1"),
            natural_gas("0.0001", id="tiny-2"),
        ])
        self.assertEqual([line["kg_co2e"] for line in tiny["line_items"]],
                         ["0.001", "0.001"])
        self.assertEqual(tiny["grand_total"]["kg_co2e"], "0.002")
        self.assertEqual(
            sum((Decimal(value)
                 for value in tiny["gas_breakdown_kg_co2e"].values()),
                Decimal("0")), Decimal("0.002"))
        self.core.assert_conservation(tiny)
        tampered_gas = deepcopy(tiny)
        tampered_gas["gas_breakdown_kg_co2e"]["co2"] = "0.001"
        with self.assertRaisesRegex(AssertionError, "GH9 gas rollup drift"):
            self.core.assert_conservation(tampered_gas)

    def test_scope3_starter_categories_refrigerant_and_esrs_shape(self):
        activities = [
            {"activity_type": "purchased_goods_spend", "quantity": "10",
             "unit": "usd", "region": "US", "year": 2026},
            {"activity_type": "waste_landfilled_mixed_msw", "quantity": "1",
             "unit": "short_ton", "region": "US", "year": 2025},
            {"activity_type": "business_travel_passenger_car", "quantity": "10",
             "unit": "vehicle_mile", "region": "US", "year": 2025},
        ]
        result = self.calculate(activities)
        self.assertEqual(result["scope_totals_kg_co2e"]["scope_3"], "586.986")
        rollups = result["category_rollups_kg_co2e"]["scope_3"]
        self.assertEqual(rollups["category_1_purchased_goods_and_services"], "4.000")
        self.assertEqual(rollups["category_5_waste_generated_in_operations"], "580.000")
        self.assertEqual(rollups["category_6_business_travel"], "2.986")
        self.assertEqual(len(rollups), 15)
        self.assertEqual(result["esrs_e1"]["gross_scope_3"], "0.586986")
        refrigerant = self.calculate([{
            "activity_type": "refrigerant_hfc_134a", "quantity": "1", "unit": "kg",
            "region": "GLOBAL", "year": 2021,
        }])
        self.assertEqual(refrigerant["grand_total"]["kg_co2e"], "1526.000")

    def test_offset_weave_is_exact_integer_grams_and_dry_run_first(self):
        result = self.calculate([natural_gas()], {"offset_buyer": "buyer-7"})
        weave = result["offset_weave"]
        self.assertTrue(weave["dry_run_ready"])
        self.assertTrue(weave["commit_ready"])
        self.assertEqual(weave["buy_offset_args"]["mass_g"], 5312)
        self.assertIs(weave["buy_offset_args"]["dry_run"], True)
        self.assertEqual(weave["source"]["audit_sha256"], result["audit_sha256"])
        partial = self.calculate([natural_gas(), {"activity_type": "unknown",
                                 "quantity": "1", "unit": "kg", "region": "US",
                                 "year": 2025}], {"offset_buyer": "buyer-7"})
        self.assertTrue(partial["offset_weave"]["dry_run_ready"])
        self.assertFalse(partial["offset_weave"]["commit_ready"])
        self.assertEqual(partial["offset_weave"]["basis"],
                         "determinate_subtotal_only")
        invalid_id = call(self.core, {
            "action": "calculate_inventory", "activities": [natural_gas()],
            "options": {"offset_buyer": "buyer-7",
                        "offset_purchase_id": {"a": 1, "b": 2}},
        })
        self.assertEqual(invalid_id["status"], "error")
        self.assertEqual(invalid_id["error_type"], "ValidationError")
        self.assertEqual(invalid_id["field"], "options.offset_purchase_id")

    def test_factor_reads_and_fleet_contract(self):
        listed = call(self.core, {"action": "list_factor_packs"})
        self.assertEqual(listed["data"]["factor_count"], len(PACK["factors"]))
        selected = call(self.core, {"action": "get_factor_pack",
                                    "region": "US", "year": 2025})
        self.assertEqual(selected["status"], "ok")
        self.assertIn("epa_2025_stationary_natural_gas", selected["data"]["factors"])
        missing = call(self.core, {"action": "get_factor_pack",
                                   "region": "US", "year": 1900})
        self.assertEqual(missing["status"], "error")
        for payload in ({}, {"action": "nope"}, "bad", 42):
            response = call(self.core, payload)
            self.assertEqual(response["status"], "error")
        described = self.core.describe()
        healthy = asyncio.run(self.core.health())
        self.assertEqual(described["version"], healthy["version"])
        self.assertEqual(healthy["version"], "0.1.0")
        self.assertEqual(healthy["checks"]["factor_pack_sha256"],
                         FACTOR_PACK_SHA256)


if __name__ == "__main__":
    unittest.main()
