"""TS1-TS4: the calculate_inventory schema describes an activity without rejecting one."""
import asyncio
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent)]

try:
    from adapters import mcp_server as adapter
    from fleet_utils.mcp_compat import field
    HAVE_MCP = hasattr(adapter.mcp, "list_tools")
except Exception:  # pragma: no cover
    HAVE_MCP = False

from src import core  # noqa: E402

ITEM = {"id": "e", "activity_type": "purchased_electricity", "quantity": "100",
        "unit": "kWh", "region": "US", "year": 2023}


def call(arguments):
    out = asyncio.run(adapter.mcp.call_tool("calculate_inventory", arguments))
    text = out.content[0].text if hasattr(out, "content") else out[0][0].text
    return json.loads(text)


@unittest.skipUnless(HAVE_MCP, "needs the MCP SDK")
class TypedSchema(unittest.TestCase):
    def schema(self):
        tools = asyncio.run(adapter.mcp.list_tools())
        tool = next(t for t in tools if t.name == "calculate_inventory")
        return field(tool, "inputSchema")

    def test_ts3_schema_names_every_field_type_and_region_from_the_pack(self):
        schema = self.schema()
        text = json.dumps(schema)
        activity = schema["$defs"]["Activity"]
        self.assertEqual(set(activity["properties"]),
                         {"id", "activity_type", "quantity", "unit", "region", "year",
                          "mobile_source_class"})
        self.assertNotIn("required", activity)                       # TS1
        self.assertIsNot(activity.get("additionalProperties"), False)
        for value in {f["activity_type"] for f in core.PACK["factors"].values()} | \
                {f["region"] for f in core.PACK["factors"].values()}:
            self.assertIn(value, text)
        for prop in activity["properties"].values():
            self.assertTrue(prop.get("description"))

    def test_ts2_the_engine_receives_exactly_what_was_sent(self):
        direct = asyncio.run(core.build().process(
            {"action": "calculate_inventory", "activities": [ITEM], "options": {}}))
        via = call({"activities": [ITEM]})
        self.assertEqual(via["data"]["audit_sha256"], direct["data"]["audit_sha256"])
        self.assertEqual(via["data"]["inputs"]["activities"], [ITEM])
        extra = call({"activities": [{**ITEM, "site": "HQ", "market_factor": None}]})
        self.assertEqual(extra["data"]["inputs"]["activities"][0]["site"], "HQ")
        self.assertIn("market_factor", extra["data"]["inputs"]["activities"][0])

    def test_shapes_a_host_sends_all_compute(self):
        want = call({"activities": [ITEM]})["data"]["grand_total"]["kg_co2e"]
        for arguments in ({"activities": ITEM}, {"activities": json.dumps([ITEM])},
                          {"activities": [{**ITEM, "quantity": 100}]},
                          {"activities": [{**ITEM, "quantity": 100.0, "year": "2023"}]}):
            got = call(arguments)
            self.assertEqual(got["status"], "ok", arguments)
            self.assertEqual(got["data"]["grand_total"]["kg_co2e"], want, arguments)

    def test_ts1_a_wrong_request_reaches_the_engine_and_gets_help(self):
        for arguments in ({}, {"activities": [{"activity_type": "jet_fuel", "quantity": 1,
                                                "unit": "kg", "region": "US", "year": 2025}]},
                          {"activities": [{"type": "electricity", "amount": 5}]}):
            got = call(arguments)
            self.assertIn("first_call_help", got, arguments)
        unknown = call({"activities": [{"activity_type": "jet_fuel", "quantity": 1,
                                        "unit": "kg", "region": "US", "year": 2025}]})
        self.assertIn("bundled activity types", unknown["data"]["indeterminate"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
