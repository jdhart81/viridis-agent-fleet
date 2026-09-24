"""QT1-QT9 invariant and fleet-contract tests for quantity-takeoff-agent."""

import ast
import asyncio
import json
import unittest
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import src.core as core_module
from src.core import MATERIAL_PACK_SHA256, PACK, build


def call(core, payload):
    return asyncio.run(core.process(payload))


def dim(value, unit):
    return {"value": value, "unit": unit}


def slab(**extra):
    item = {
        "id": "slab-1", "assembly": "concrete_slab",
        "unit_system": "imperial",
        "dimensions": {
            "length": dim("20", "ft"), "width": dim("30", "ft"),
            "thickness": dim("4", "in"),
        },
    }
    item.update(extra)
    return item


class QuantityTakeoffInvariants(unittest.TestCase):
    def setUp(self):
        self.core = build()

    def calculate(self, items, options=None):
        response = call(self.core, {"action": "calculate_takeoff", "items": items,
                                    "options": options or {}})
        self.assertEqual(response["status"], "ok", response)
        return response["data"]

    # QT1 — Decimal-only math with distinct exact and purchase quantities.
    def test_QT1_decimal_dual_quantities_and_exact_slab(self):
        result = self.calculate([slab()])
        line = result["line_items"][0]
        self.assertEqual(result["takeoff_status"], "complete_for_supplied_items")
        self.assertEqual(line["operands"]["net_ft3"], "200")
        self.assertEqual(line["net_qty"], "7.407")
        self.assertEqual(line["exact_qty"], "7.778")
        self.assertEqual(line["purchase_qty"], "7.78")
        self.assertNotEqual(line["exact_qty"], line["purchase_qty"])
        tree = ast.parse((Path(__file__).resolve().parents[1] / "src" / "core.py").read_text())
        float_literals = [node.value for node in ast.walk(tree)
                          if isinstance(node, ast.Constant)
                          and isinstance(node.value, float)]
        self.assertEqual(float_literals, [])
        # Boundary JSON numerics normalize immediately to Decimal; no float
        # operation exists in the calculation path.
        numeric = slab()
        numeric["dimensions"]["length"]["value"] = 20.0
        self.assertEqual(self.calculate([numeric])["line_items"][0]["net_qty"], "7.407")

    # QT2 — bundled waste is locked, while an override is explicit and bound.
    def test_QT2_waste_default_and_override_are_explicit(self):
        default_line = self.calculate([slab()])["line_items"][0]
        self.assertEqual(default_line["waste"]["percent"], "5")
        self.assertEqual(default_line["waste"]["basis"], "material_pack_default")
        overridden = slab(waste_override={"percent": "0", "reason": "sealed supplier quote"})
        line = self.calculate([overridden])["line_items"][0]
        self.assertTrue(line["waste"]["overridden"])
        self.assertEqual(line["waste"]["reason"], "sealed supplier quote")
        self.assertEqual(line["waste"]["replaces_default"]["percent"], "5")
        self.assertEqual(line["net_qty"], line["exact_qty"])

    # QT3 — unit system and positive finite geometry are mandatory.
    def test_QT3_geometry_validation_fails_loud(self):
        missing_system = slab()
        missing_system.pop("unit_system")
        response = call(self.core, {"action": "calculate_takeoff",
                                    "items": [missing_system], "options": {}})
        self.assertEqual(response["status"], "error")
        self.assertIn("unit_system must be explicit", response["message"])
        for value in ("0", "-1", "NaN", "Infinity"):
            bad = slab()
            bad["dimensions"]["length"]["value"] = value
            response = call(self.core, {"action": "calculate_takeoff",
                                        "items": [bad], "options": {}})
            self.assertEqual(response["status"], "error", response)

    # QT4 — every constant and conversion resolves to a source-linked pack pin.
    def test_QT4_every_line_is_formula_operand_and_source_auditable(self):
        line = self.calculate([slab()])["line_items"][0]
        self.assertIn("length_ft * width_ft", line["formula"])
        self.assertEqual(line["operands"]["ft3_per_yd3"], "27")
        self.assertEqual(line["weight"]["density_lb_per_yd3"], "4050")
        self.assertIn("aci-ct25-normalweight-concrete", line["source_ids"])
        self.assertIn("nist-sp811-unit-conversions", line["source_ids"])
        used = {source["id"] for source in
                self.calculate([slab()])["material_pack"]["sources_used"]}
        self.assertTrue(set(line["source_ids"]) <= used)
        source_ids = {source["id"] for source in PACK["sources"]}
        for source in PACK["sources"]:
            self.assertTrue(source["url"].startswith("https://"))
        self.assertIn(PACK["unit_conversions_source_id"], source_ids)

    # QT5 — deterministic conversion only, and unitful counts are rejected.
    def test_QT5_unit_integrity_and_metric_conversion(self):
        metric = {
            "assembly": "concrete_slab", "unit_system": "SI",
            "dimensions": {
                "length": dim("6.096", "m"), "width": dim("9.144", "m"),
                "thickness": dim("101.6", "mm"),
            },
        }
        self.assertEqual(self.calculate([metric])["line_items"][0]["net_qty"], "7.407")
        bad = slab()
        bad["dimensions"]["length"]["unit"] = "furlong"
        response = call(self.core, {"action": "calculate_takeoff",
                                    "items": [bad], "options": {}})
        self.assertEqual(response["status"], "error")
        self.assertIn("no bundled conversion", response["message"])
        bad_count = {
            "assembly": "paint", "unit_system": "imperial",
            "dimensions": {"area": dim("100", "ft2"),
                           "coats": {"value": "2", "unit": "ft"}},
        }
        response = call(self.core, {"action": "calculate_takeoff",
                                    "items": [bad_count], "options": {}})
        self.assertEqual(response["status"], "error")
        self.assertIn("unitless", response["message"])

    # QT6 — unsupported or incomplete coverage is excluded, never guessed.
    def test_QT6_unknown_and_missing_factors_are_indeterminate(self):
        unknown = {"id": "x", "assembly": "teleport_pad", "unit_system": "imperial",
                   "dimensions": {"length": dim("1", "ft")}}
        missing = slab()
        missing["id"] = "missing"
        missing["dimensions"].pop("thickness")
        result = self.calculate([slab(), unknown, missing])
        self.assertEqual(result["takeoff_status"], "partial_indeterminate")
        self.assertEqual(len(result["line_items"]), 1)
        self.assertEqual(len(result["indeterminate"]), 2)
        self.assertTrue(all(line["excluded_from_totals"]
                            for line in result["indeterminate"]))
        self.assertIn("assembly not in pack", result["indeterminate"][0]["reason"])
        self.assertIn("missing required dimension", result["indeterminate"][1]["reason"])

    # QT7 — drywall is hand-verifiable and always rounds upward to a sheet.
    def test_QT7_conservative_drywall_purchase_rounding(self):
        item = {"assembly": "drywall", "unit_system": "imperial",
                "dimensions": {"area": dim("1000", "ft2")}}
        line = self.calculate([item])["line_items"][0]
        self.assertEqual(line["net_qty"], "31.250")
        self.assertEqual(line["exact_qty"], "34.375")
        self.assertEqual(line["purchase_qty"], "35")
        self.assertEqual(line["purchase_rounding"]["mode"], "ROUND_CEILING")
        self.assertGreaterEqual(Decimal(line["purchase_qty"]), Decimal(line["exact_qty"]))

    # QT8 — canonical audit/notary output is stable and tamper-evident.
    def test_QT8_reproducible_audit_notary_and_tamper_detection(self):
        options = {"project_id": "job-7", "revision_id": "r1"}
        first = self.calculate([slab()], options)
        second = self.calculate([slab()], options)
        self.assertEqual(first["audit_sha256"], second["audit_sha256"])
        self.assertNotIn("timestamp", json.dumps(first))
        self.assertEqual(first["notary_payload"]["content_digest"],
                         first["audit_sha256"])
        verified = call(self.core, {"action": "verify_result", "result": first})["data"]
        self.assertTrue(verified["valid"])
        tampered = deepcopy(first)
        tampered["line_items"][0]["exact_qty"] = "999.000"
        check = call(self.core, {"action": "verify_result", "result": tampered})["data"]
        self.assertFalse(check["valid"])
        self.assertFalse(check["audit_hash_valid"])
        tampered_notary = deepcopy(first)
        tampered_notary["notary_payload"]["context"] = "evil"
        check = call(self.core, {"action": "verify_result",
                                 "result": tampered_notary})["data"]
        self.assertTrue(check["audit_hash_valid"])
        self.assertFalse(check["notary_payload_valid"])
        current = core_module.MATERIAL_PACK_SHA256
        try:
            core_module.MATERIAL_PACK_SHA256 = "f" * 64
            stale = call(self.core, {"action": "verify_result", "result": first})["data"]
        finally:
            core_module.MATERIAL_PACK_SHA256 = current
        self.assertTrue(stale["valid"])
        self.assertFalse(stale["material_pack_current"])

    # QT9 — assembly, trade, and grand unit-resolved totals reconcile.
    def test_QT9_conservation_and_tampered_rollup_fails_loud(self):
        drywall = {"assembly": "drywall", "unit_system": "imperial",
                   "dimensions": {"area": dim("1000", "ft2")}}
        result = self.calculate([slab(), drywall])
        self.core.assert_conservation(result)
        self.assertEqual(result["grand_rollup"]["totals_by_unit"]["yd3"]["exact_qty"],
                         "7.778")
        self.assertEqual(result["grand_rollup"]["totals_by_unit"]["sheet"]["exact_qty"],
                         "34.375")
        tampered = deepcopy(result)
        tampered["trade_rollups"]["concrete"]["totals_by_unit"]["yd3"]["exact_qty"] = "7.779"
        with self.assertRaisesRegex(AssertionError, "QT9 conservation drift"):
            self.core.assert_conservation(tampered)

    def test_hand_verifiable_roofing_steel_and_rebar(self):
        roofing = {"assembly": "asphalt_shingle", "unit_system": "imperial",
                   "dimensions": {"area": dim("2400", "ft2"), "pitch": "6:12"}}
        roof = self.calculate([roofing])["line_items"][0]
        self.assertEqual(roof["net_qty"], "26.832")
        self.assertEqual(roof["exact_qty"], "29.515")
        self.assertEqual(roof["purchase_qty"], "30")
        steel = {"assembly": "structural_steel", "unit_system": "imperial",
                 "dimensions": {"shape": "W12x26", "length": dim("40", "ft")}}
        steel_line = self.calculate([steel])["line_items"][0]
        self.assertEqual(steel_line["weight"]["net_lb"], "1040.000")
        self.assertEqual(steel_line["weight"]["net_short_ton"], "0.520")
        self.assertEqual(steel_line["net_qty"], "0.520")
        rebar = {"assembly": "rebar_grid", "unit_system": "imperial",
                 "dimensions": {"length": dim("20", "ft"),
                                "width": dim("30", "ft"),
                                "spacing": dim("2", "ft"), "bar_size": "#4"}}
        rebar_line = self.calculate([rebar])["line_items"][0]
        self.assertEqual(rebar_line["net_qty"], "650.000")
        self.assertEqual(rebar_line["weight"]["net_lb"], "434.200")
        self.assertEqual(rebar_line["weight"]["exact_lb"], "455.910")
        self.assertEqual(rebar_line["weight"]["purchase_lb"], "467.600")

    def test_smartscale_and_protogen_payloads_compose_without_guessing(self):
        smartscale = {
            "assembly": "drywall",
            "smartscale": {"status": "ok", "action": "measure",
                           "result": {"objects": [{"id": "wall-a",
                                       "dimensions_mm": {"width": "6096",
                                                         "height": "2438.4"}}]}},
        }
        smart = self.calculate([smartscale])
        self.assertEqual(smart["line_items"][0]["net_qty"], "5.000")
        self.assertEqual(smart["lineage"]["upstream_measurements"],
                         ["smartscale:wall-a"])
        protogen = {
            "assembly": "concrete_slab",
            "dimensions": {"thickness": dim("101.6", "mm")},
            "protogen": {"status": "success", "design": {"id": "cad-1",
                         "dimensions_mm": {"length": "6096", "width": "9144",
                                           "height": "250"}}},
        }
        proto = self.calculate([protogen])
        self.assertEqual(proto["line_items"][0]["net_qty"], "7.407")
        self.assertEqual(proto["lineage"]["upstream_measurements"], ["protogen:cad-1"])
        incomplete = deepcopy(protogen)
        incomplete.pop("dimensions")
        closed = self.calculate([incomplete])
        self.assertEqual(closed["takeoff_status"], "indeterminate")
        self.assertIn("thickness", closed["indeterminate"][0]["reason"])
        ambiguous = deepcopy(smartscale)
        ambiguous["smartscale"]["result"]["objects"].append(
            {"id": "wall-b", "dimensions_mm": {"width": "1", "height": "1"}})
        closed = self.calculate([ambiguous])
        self.assertEqual(closed["takeoff_status"], "indeterminate")
        self.assertIn("exactly one", closed["indeterminate"][0]["reason"])

    def test_all_mvp_assemblies_and_fleet_reads(self):
        items = [
            {"assembly": "concrete_footing", "unit_system": "imperial",
             "dimensions": {"length": dim("10", "ft"), "width": dim("2", "ft"),
                            "depth": dim("1", "ft")}},
            {"assembly": "concrete_wall", "unit_system": "imperial",
             "dimensions": {"length": dim("10", "ft"), "height": dim("8", "ft"),
                            "thickness": dim("8", "in")}},
            {"assembly": "concrete_column", "unit_system": "imperial",
             "dimensions": {"diameter": dim("2", "ft"), "height": dim("10", "ft")}},
            {"assembly": "wood_wall_framing", "unit_system": "imperial",
             "dimensions": {"length": dim("20", "ft"), "height": dim("8", "ft"),
                            "stud_spacing": dim("16", "in"), "corners": "2",
                            "openings": "1"}},
            {"assembly": "sheathing", "unit_system": "imperial",
             "dimensions": {"area": dim("320", "ft2")}},
            {"assembly": "dimensional_lumber", "unit_system": "imperial",
             "dimensions": {"nominal_width": dim("4", "in"),
                            "nominal_thickness": dim("2", "in"),
                            "length": dim("10", "ft"), "pieces": "4"}},
            {"assembly": "cmu_wall", "unit_system": "imperial",
             "dimensions": {"area": dim("100", "ft2")}},
            {"assembly": "brick_veneer", "unit_system": "imperial",
             "dimensions": {"area": dim("100", "ft2")}},
            {"assembly": "excavation", "unit_system": "imperial",
             "dimensions": {"length": dim("10", "ft"), "width": dim("10", "ft"),
                            "depth": dim("3", "ft")}},
            {"assembly": "aggregate_base", "unit_system": "imperial",
             "dimensions": {"length": dim("10", "ft"), "width": dim("10", "ft"),
                            "depth": dim("6", "in")}},
            {"assembly": "paint", "unit_system": "imperial",
             "dimensions": {"area": dim("700", "ft2"), "coats": "2"}},
        ]
        result = self.calculate(items)
        self.assertEqual(result["takeoff_status"], "complete_for_supplied_items")
        self.assertEqual(len(result["line_items"]), len(items) + 1)
        self.assertEqual(result["material_pack"]["sha256"], MATERIAL_PACK_SHA256)
        listed = call(self.core, {"action": "list_assemblies"})
        self.assertEqual(len(listed["data"]["assemblies"]), len(PACK["assemblies"]))
        assembly = call(self.core, {"action": "get_assembly",
                                    "assembly_type": "drywall"})
        self.assertEqual(assembly["status"], "ok")
        pack = call(self.core, {"action": "get_material_pack"})
        self.assertEqual(pack["data"]["sha256"], MATERIAL_PACK_SHA256)
        self.assertEqual(self.core.describe()["version"], "0.1.0")
        self.assertEqual(asyncio.run(self.core.health())["version"], "0.1.0")


if __name__ == "__main__":
    unittest.main()
