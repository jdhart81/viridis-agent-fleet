"""U1 / V1 / hint fixes found while self-testing for the Claude directory (2026-11-03).

U1 unit names are case-insensitive; the audited input keeps the caller's spelling.
V1 verify_result accepts calculate_inventory's full {"status","data"} envelope.
H1 classify_activity is a pure lookup (readOnlyHint=True).
"""
import asyncio
import json
from pathlib import Path

from src.core import build


def call(core, payload):
    return asyncio.run(core.process(payload))


def inv(unit):
    return call(build(), {"action": "calculate_inventory", "activities": [
        {"activity_type": "purchased_electricity", "quantity": 1000, "unit": unit,
         "region": "US", "year": 2023}]})


def test_u1_kwh_any_case_is_computed_and_equal():
    lower, mixed, upper = inv("kwh"), inv("kWh"), inv("KWH")
    for r in (lower, mixed, upper):
        assert r["status"] == "ok", r
        assert r["data"]["inventory_status"] != "indeterminate", r["data"].get("indeterminate")
    tot = lambda r: r["data"]["scope_totals_kg_co2e"]
    assert tot(lower) == tot(mixed) == tot(upper)
    assert float(tot(mixed)["scope_2_location_based"]) > 0
    # the caller's spelling is preserved in the audited inputs
    assert mixed["data"]["inputs"]["activities"][0]["unit"] == "kWh"


def test_u1_unknown_unit_still_indeterminate():
    r = inv("furlongs")
    assert r["data"]["indeterminate"], r


def test_v1_verify_accepts_envelope_and_inner_data():
    r = inv("kWh")
    core = build()
    for payload in (r, r["data"]):
        v = call(core, {"action": "verify_result", "result": payload})
        assert v["status"] == "ok" and v["data"]["valid"] is True, v


def test_v1_tampered_envelope_is_invalid():
    r = inv("kWh")
    r["data"]["scope_totals_kg_co2e"]["scope_2_location_based"] = "1.000"
    v = call(build(), {"action": "verify_result", "result": r})
    assert v["data"]["valid"] is False


def test_v1_mcp_tool_verifies_its_own_output():
    from adapters import mcp_server
    out = asyncio.run(mcp_server.calculate_inventory([
        {"activity_type": "purchased_electricity", "quantity": 1000, "unit": "kWh",
         "region": "US", "year": 2023}]))
    body = json.loads(asyncio.run(mcp_server.verify_result(out)))
    assert body["data"]["valid"] is True, body


def test_h1_classify_is_read_only():
    from adapters import mcp_server
    if hasattr(mcp_server.mcp, "list_tools"):   # real MCP SDK
        anns = {t.name: t.annotations for t in asyncio.run(mcp_server.mcp.list_tools())}
        a = anns["classify_activity"]
        a = a if isinstance(a, dict) else a.model_dump(by_alias=True, exclude_none=True)
        assert a["readOnlyHint"] is True and a["destructiveHint"] is False
    else:                                        # stdlib shim: check the declaration
        src = Path(mcp_server.__file__).read_text()
        assert "@mcp.tool(annotations=_READ)\nasync def classify_activity" in src
