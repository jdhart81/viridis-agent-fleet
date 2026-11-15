"""TS1-TS4 across the priced tools: each tool's schema tells a host what to
send, names values read from the agent's own data, and never rejects a request
the engine could answer with help."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

FLEET = Path(__file__).resolve().parents[2]
RUN = r"""
import asyncio, json, sys
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from adapters import mcp_server as adapter
from fleet_utils.mcp_compat import field
request = json.loads(sys.stdin.read())
tools = asyncio.run(adapter.mcp.list_tools())
tool = next(t for t in tools if t.name == request["tool"])
out = {"schema": field(tool, "inputSchema"), "calls": []}
for arguments in request["calls"]:
    res = asyncio.run(adapter.mcp.call_tool(request["tool"], arguments))
    text = res.content[0].text if hasattr(res, "content") else res[0][0].text
    out["calls"].append(json.loads(text))
print(json.dumps(out, default=str))
"""


def adapter(agent, tool, calls=()):
    pytest.importorskip("mcp")
    out = subprocess.run([sys.executable, "-c", RUN, str(FLEET / agent), str(FLEET)],
                         input=json.dumps({"tool": tool, "calls": list(calls)}),
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def described(schema, name):
    prop = schema["properties"][name]
    assert prop.get("description"), name
    return prop["description"]


def test_disclosure_schema_names_frameworks_and_fact_keys_from_the_pack():
    pack = json.loads((FLEET / "disclosure-compiler-agent/data/framework_packs.v0.1.0.json").read_text())
    got = adapter("disclosure-compiler-agent", "compile_disclosure", [{}])
    schema = got["schema"]
    for framework in pack["frameworks"]:
        assert framework in described(schema, "framework")
        assert framework in described(schema, "company_facts")
    assert "organizational_boundary" in described(schema, "company_facts")
    assert "calculate_inventory" in described(schema, "ghg_result")
    assert "applicability" in described(schema, "options")
    assert not schema.get("required")
    assert "first_call_help" in got["calls"][0]                        # TS1


def test_tax_credit_schema_names_the_bundled_credits():
    got = adapter("taxcredit-engine-agent", "calculate_tax_credit", [{}])
    for credit in ("45Q", "45V", "45Y", "48E", "45X"):
        assert credit in described(got["schema"], "credit")
    assert described(got["schema"], "facts")
    assert "first_call_help" in got["calls"][0]


def test_radar_schema_names_jurisdictions_and_sectors():
    got = adapter("regulatory-radar-agent", "scan_regulations",
                  [{"jurisdiction": "california", "sector": "energy"}])
    for value in ("eu", "uk", "us", "california", "global"):
        assert value in described(got["schema"], "jurisdiction")
    for value in ("energy", "forestry", "financial_services"):
        assert value in described(got["schema"], "sector")
    assert described(got["schema"], "query")
    body = got["calls"][0]
    assert body.get("data", body)["total_regulations"] > 0


def test_takeoff_schema_describes_an_item_and_accepts_one_item_or_a_string():
    pack = json.loads((FLEET / "quantity-takeoff-agent/data/material_pack.v0.1.0.json").read_text())
    item = {"id": "slab-1", "assembly": "concrete_slab", "unit_system": "imperial",
            "dimensions": {"length": {"value": "20", "unit": "ft"},
                           "width": {"value": "30", "unit": "ft"},
                           "thickness": {"value": "4", "unit": "in"}}}
    got = adapter("quantity-takeoff-agent", "calculate_takeoff",
                  [{"items": [item]}, {"items": item}, {"items": json.dumps([item])}, {}])
    model = got["schema"]["$defs"]["TakeoffItem"]
    assert "required" not in model and model.get("additionalProperties") is not False
    for assembly in pack["assemblies"]:
        assert assembly in model["properties"]["assembly"]["description"]
    listed, single, text, empty = got["calls"]
    assert listed["status"] == "ok"
    assert single["data"]["audit_sha256"] == listed["data"]["audit_sha256"]   # TS2
    assert text["data"]["audit_sha256"] == listed["data"]["audit_sha256"]
    assert listed["data"]["inputs"]["items"] == [item]
    assert "first_call_help" in empty
