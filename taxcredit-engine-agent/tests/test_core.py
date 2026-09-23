"""TC1-TC9 invariant tests; stdlib unittest so the agent tests anywhere."""

import asyncio
import hashlib
import json
import unittest

from src.core import RULE_PACK_SHA256, VERSION, build


def run(payload):
    return asyncio.run(build().process(payload))


EVIDENCE = hashlib.sha256(b"verified 45VH2-GREET report").hexdigest()


def h2(emissions="0.44", **overrides):
    facts = {
        "tax_year": 2026,
        "tax_year_begin_date": "2026-01-01",
        "kg_hydrogen": "1000",
        "lifecycle_kg_co2e_per_kg_h2": emissions,
        "greet_version": "45VH2-GREET-2025",
        "evidence_digest": EVIDENCE,
        "pwa_met": True,
        "produced_in_us": True,
        "construction_begin_date": "2026-01-01",
        "placed_in_service_date": "2026-01-01",
        "section_45q_claimed_for_facility": False,
        "tax_exempt_bond_financing_percent": "0",
    }
    facts.update(overrides)
    return facts


def electricity(**overrides):
    facts = {
        "tax_year": 2026,
        "tax_year_begin_date": "2026-01-01",
        "lifecycle_emissions_g_co2e_per_kwh": "0",
        "placed_in_service_date": "2026-01-01",
        "construction_begin_date": "2025-01-01",
        "produced_in_us": True,
        "nameplate_capacity_mw": "2",
        "pwa_met": True,
        "specified_foreign_entity": False,
        "foreign_influenced_entity": False,
        "material_assistance_from_pfe": False,
        "technology": "geothermal",
        "tax_exempt_bond_financing_percent": "0",
    }
    facts.update(overrides)
    return facts


def component(component_type="battery_cell", **overrides):
    facts = {
        "tax_year": 2026,
        "tax_year_begin_date": "2026-01-01",
        "component_type": component_type,
        "quantity": "100",
        "produced_in_us": True,
        "sold_to_unrelated_person": True,
        "related_party_election": False,
        "substantially_transformed": True,
        "meets_component_definition": True,
        "claimed_48c": False,
        "specified_foreign_entity": False,
        "foreign_influenced_entity": False,
        "material_assistance_from_pfe": False,
    }
    facts.update(overrides)
    return facts


class TaxCreditInvariants(unittest.TestCase):
    def calculate(self, credit, facts):
        result = run({"action": "calculate", "credit": credit, "facts": facts})
        self.assertEqual(result["status"], "ok", result)
        return result["data"]

    def test_tc1_decimal_determinism(self):
        a = self.calculate("45V", h2())["audit_sha256"]
        b = self.calculate("45V", h2())["audit_sha256"]
        self.assertEqual(a, b)
        self.assertEqual(self.calculate("45V", h2())["credit_amount_usd"], "3280.00")

    def test_tc2_45v_exact_boundaries(self):
        cases = [("0.4499", "tier_4", "3.28"),
                 ("0.45", "tier_3", "1.095"),
                 ("1.5", "tier_2", "0.82"),
                 ("2.5", "tier_1", "0.655"),
                 ("4", "tier_1", "0.655")]
        for emissions, tier, rate in cases:
            data = self.calculate("45V", h2(emissions))
            self.assertEqual(data["tier"], tier)
            self.assertEqual(data["rate"]["amount_usd"], rate)
        over = self.calculate("45V", h2("4.0001"))
        self.assertEqual(over["calculation_status"], "ineligible")
        self.assertEqual(over["credit_amount_usd"], "0.00")

    def test_tc3_45q_date_path_pwa_and_threshold(self):
        facts = {
            "tax_year": 2026, "metric_tons": "12500",
            "facility_type": "other_industrial_facility",
            "disposal_path": "utilization", "pwa_met": True,
            "construction_begin_date": "2026-01-01",
            "placed_in_service_date": "2025-07-05",
            "captured_and_disposed_in_us": True,
            "tax_exempt_bond_financing_percent": "0",
        }
        data = self.calculate("45Q", facts)
        self.assertEqual(data["rate"]["amount_usd"], "85")
        self.assertEqual(data["credit_amount_usd"], "1062500.00")
        below = self.calculate("45Q", {**facts, "metric_tons": "12499.99"})
        self.assertEqual(below["calculation_status"], "ineligible")
        legacy = self.calculate("45Q", {**facts,
                                        "placed_in_service_date": "2022-12-31"})
        self.assertEqual(legacy["calculation_status"], "indeterminate")

    def test_tc4_45y_48e_coordination_and_rates(self):
        y = self.calculate("45Y", electricity(
            kwh="1000000", disposition="sold_to_unrelated_person",
            claimed_conflicting_credit=False))
        self.assertEqual(y["credit_amount_usd"], "31000.00")
        e = self.calculate("48E", electricity(
            qualified_investment_usd="1000000", claimed_45y=False,
            domestic_content_met=True, energy_community=True,
            low_income_bonus_percentage_points="0",
            low_income_allocation_received=False,
            low_income_allocation_ratio_percent="0",
            tax_exempt_bond_financing_percent="0"))
        self.assertEqual(e["rate"]["percentage"], "50")
        self.assertEqual(e["credit_amount_usd"], "500000.00")
        conflict = self.calculate("48E", electricity(
            qualified_investment_usd="1000000", claimed_45y=True,
            domestic_content_met=False, energy_community=False,
            low_income_bonus_percentage_points="0",
            low_income_allocation_received=False,
            low_income_allocation_ratio_percent="0",
            tax_exempt_bond_financing_percent="0"))
        self.assertEqual(conflict["calculation_status"], "ineligible")
        bond = self.calculate("48E", electricity(
            qualified_investment_usd="1000000", claimed_45y=False,
            domestic_content_met=False, energy_community=False,
            low_income_bonus_percentage_points="0",
            low_income_allocation_received=False,
            low_income_allocation_ratio_percent="0",
            tax_exempt_bond_financing_percent="50"))
        self.assertEqual(bond["rate"]["tax_exempt_bond_reduction_percent"], "15")
        self.assertEqual(bond["credit_amount_usd"], "255000.00")
        no_allocation = self.calculate("48E", electricity(
            qualified_investment_usd="1000000", claimed_45y=False,
            domestic_content_met=False, energy_community=False,
            low_income_bonus_percentage_points="20",
            low_income_allocation_received=False,
            low_income_allocation_ratio_percent="0",
            tax_exempt_bond_financing_percent="0"))
        self.assertEqual(no_allocation["calculation_status"], "ineligible")
        base_bonus = self.calculate("48E", electricity(
            pwa_met=False, nameplate_capacity_mw="2",
            qualified_investment_usd="1000000", claimed_45y=False,
            domestic_content_met=True, energy_community=True,
            low_income_bonus_percentage_points="0",
            low_income_allocation_received=False,
            low_income_allocation_ratio_percent="0",
            tax_exempt_bond_financing_percent="0"))
        self.assertEqual(base_bonus["rate"]["percentage"], "10")
        self.assertEqual(base_bonus["credit_amount_usd"], "100000.00")

    def test_tc5_45x_component_and_phaseouts(self):
        battery = self.calculate("45X", component())
        self.assertEqual(battery["credit_amount_usd"], "3500.00")
        wind = self.calculate("45X", component("wind_blade", tax_year=2028))
        self.assertEqual(wind["calculation_status"], "ineligible")
        mineral = component("critical_mineral", tax_year=2032)
        mineral.pop("quantity")
        mineral["eligible_production_cost_usd"] = "100000"
        phased = self.calculate("45X", mineral)
        self.assertEqual(phased["rate"]["phaseout_percentage"], "50")
        self.assertEqual(phased["credit_amount_usd"], "5000.00")
        vessel = component("offshore_wind_vessel", tax_year=2027)
        vessel.pop("quantity")
        vessel["eligible_sales_price_usd"] = "2000000"
        self.assertEqual(self.calculate("45X", vessel)["credit_amount_usd"],
                         "200000.00")
        coal = component("metallurgical_coal", tax_year=2030)
        coal.pop("quantity")
        coal["eligible_production_cost_usd"] = "100000"
        self.assertEqual(self.calculate("45X", coal)["calculation_status"],
                         "ineligible")

    def test_tc6_missing_facts_fail_closed(self):
        data = self.calculate("45V", {"tax_year": 2026})
        self.assertEqual(data["calculation_status"], "indeterminate")
        self.assertIsNone(data["credit_amount_usd"])
        self.assertTrue(data["eligibility_flags"])

    def test_tc7_audit_verification_detects_tampering(self):
        data = self.calculate("45V", h2())
        verified = run({"action": "verify_result", "result": data})
        self.assertTrue(verified["data"]["valid"])
        data["credit_amount_usd"] = "999999.00"
        tampered = run({"action": "verify_result", "result": data})
        self.assertFalse(tampered["data"]["valid"])

    def test_tc8_never_raises_and_versions_match(self):
        for bad in (None, [], "x", {}, {"action": "calculate", "credit": "no"}):
            result = asyncio.run(build().process(bad))
            self.assertEqual(result["status"], "error")
        agent = build()
        health = asyncio.run(agent.health())
        self.assertEqual(agent.describe()["version"], health["version"])
        self.assertEqual(health["version"], VERSION)

    def test_tc9_versioned_sources_and_digest(self):
        pack = run({"action": "get_rule_pack", "credit": "45V"})["data"]
        self.assertEqual(pack["rule_pack_sha256"], RULE_PACK_SHA256)
        self.assertGreaterEqual(len(pack["sources"]), 3)
        self.assertTrue(all(s.get("url", "").startswith("https://")
                            for s in pack["sources"] if s["id"] != "builder-spec-2026-07-12"))


if __name__ == "__main__":
    unittest.main()
