"""Tests for fleet_utils.starters (invariants S1 to S7 in the module docstring).

Each adapter is loaded in its own subprocess (they share the module names
``adapters`` and ``src``) and inspected through a real in-memory MCP client,
so what is checked is what a host receives on initialize, prompts/list and
prompts/get.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from fleet_utils import starters  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
AGENTS = {"ghg-ledger": "ghg-ledger-agent",
          "regulatory-radar": "regulatory-radar-agent",
          "disclosure-compiler": "disclosure-compiler-agent"}
SAMPLE_ARGS = {
    "footprint_from_bills": {"electricity_kwh": "12000", "year": "2025",
                             "electricity_region": "US-NYUP",
                             "natural_gas_therms": "800", "organization": "Acme"},
    "which_climate_rules_apply": {"jurisdiction": "california", "sector": "energy"},
    "what_changed_since_last_time": {"jurisdiction": "california", "cursor": "7"},
    "sb253_first_draft": {"company": "Acme", "reporting_year": "2025",
                          "electricity_kwh": "12000"},
}

PROBE = r"""
import asyncio, json, sys
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from adapters import mcp_server as adapter
from fleet_utils.mcp_compat import connect, field
from fleet_utils.starters import apply_starters
samples = json.loads(sys.argv[3])

async def main():
    out = {}
    async with connect(adapter.mcp) as client:
        inst = getattr(client, "instructions", None)  # SDK 2.x Client
        if inst is None:  # SDK 1.x ClientSession keeps the initialize result
            init = getattr(client, "_initialize_result", None) or getattr(client, "initialize_result", None)
            inst = field(init, "instructions") if init is not None else None
        out["instructions"] = inst
        tools = await client.list_tools()
        out["tools"] = sorted(
            (field(t, "name"), json.dumps(field(t, "inputSchema"), sort_keys=True),
             json.dumps(field(t, "annotations").model_dump() if field(t, "annotations") else None, sort_keys=True))
            for t in field(tools, "tools"))
        prompts = await client.list_prompts()
        out["prompts"] = [{"name": field(p, "name"), "title": field(p, "title"),
                           "description": field(p, "description"),
                           "args": [(field(a, "name"), field(a, "required"))
                                    for a in (field(p, "arguments") or [])]}
                          for p in field(prompts, "prompts")]
        out["rendered"] = {}
        for p in out["prompts"]:
            got = await client.get_prompt(p["name"], samples[p["name"]])
            msgs = field(got, "messages")
            out["rendered"][p["name"]] = [(field(m, "role"), field(field(m, "content"), "text")) for m in msgs]
    out["second_apply"] = apply_starters(adapter.mcp, sys.argv[4])
    print(json.dumps(out))

asyncio.run(main())
"""


def probe(key):
    agent_dir = ROOT / AGENTS[key]
    res = subprocess.run([sys.executable, "-c", PROBE, str(agent_dir), str(ROOT),
                          json.dumps(SAMPLE_ARGS), key],
                         capture_output=True, text=True, cwd=str(agent_dir), timeout=120)
    assert res.returncode == 0, res.stderr[-3000:]
    return json.loads(res.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module", params=sorted(AGENTS))
def seen(request):
    return request.param, probe(request.param)


def test_instructions_reach_the_client(seen):
    key, out = seen
    assert out["instructions"] == starters.INSTRUCTIONS[key]
    assert len(out["instructions"]) < 1200                                  # S7


def test_prompts_listed_and_render_text_only(seen):
    key, out = seen
    names = [p["name"] for p in out["prompts"]]
    assert names == [s["name"] for s in starters.PROMPTS[key]]
    assert len(set(names)) == len(names)                                    # S7
    for p in out["prompts"]:
        assert p["name"].replace("_", "").isalnum() and p["name"].islower()
        assert p["title"] and len(p["description"]) < 200
        rendered = out["rendered"][p["name"]]
        assert len(rendered) == 1 and rendered[0][0] == "user"              # S2
        assert rendered[0][1].strip()


def test_prompts_name_only_real_tools(seen):                                # S3
    key, out = seen
    tool_names = {t[0] for t in out["tools"]}
    for spec in starters.PROMPTS[key]:
        for tool in spec["tools"]:
            assert tool in tool_names, tool
            assert tool in out["rendered"][spec["name"]][0][1] or tool == "list_factor_packs"
    for word in ("calculate_inventory", "scan_regulations", "watch_changes",
                 "compile_disclosure", "verify_result", "list_factor_packs",
                 "assess_compliance", "list_frameworks"):
        if word in starters.INSTRUCTIONS[key]:
            own = word in tool_names
            sibling = word in {"calculate_inventory", "compile_disclosure"}
            assert own or sibling, word


def test_no_price_or_payment_wording_in_prompts():                          # S4
    for key, specs in starters.PROMPTS.items():
        for spec in specs:
            text = spec["fn"](**SAMPLE_ARGS[spec["name"]]) + spec["description"]
            for banned in ("$", "USDC", "x402", "seat", "pay ", "price", "free"):
                assert banned not in text, (spec["name"], banned)
    for key, text in starters.INSTRUCTIONS.items():
        for banned in ("$", "USDC", "x402", "seat", "price"):
            assert banned not in text, (key, banned)


def test_tools_unchanged_by_starters(seen):                                 # S1
    key, out = seen
    agent_dir = ROOT / AGENTS[key]
    script = (
        "import asyncio, json, sys\n"
        "sys.path[:0] = [sys.argv[1], sys.argv[2]]\n"
        "import fleet_utils.starters as s\n"
        "s.apply_starters = lambda server, key: 0\n"
        "from adapters import mcp_server as adapter\n"
        "from fleet_utils.mcp_compat import connect, field\n"
        "async def main():\n"
        "    async with connect(adapter.mcp) as client:\n"
        "        tools = await client.list_tools()\n"
        "        print(json.dumps(sorted((field(t, 'name'), json.dumps(field(t, 'inputSchema'), sort_keys=True),"
        " json.dumps(field(t, 'annotations').model_dump() if field(t, 'annotations') else None, sort_keys=True))"
        " for t in field(tools, 'tools'))))\n"
        "asyncio.run(main())\n")
    res = subprocess.run([sys.executable, "-c", script, str(agent_dir), str(ROOT)],
                         capture_output=True, text=True, cwd=str(agent_dir), timeout=120)
    assert res.returncode == 0, res.stderr[-3000:]
    before = [tuple(t) for t in json.loads(res.stdout.strip().splitlines()[-1])]
    assert before == [tuple(t) for t in out["tools"]]


def test_idempotent(seen):                                                  # S6
    _, out = seen
    assert out["second_apply"] == 0


def test_shim_and_unknown_key_are_noops():                                  # S5
    class Shim:
        def tool(self, *a, **k):
            return lambda fn: fn
    assert starters.apply_starters(Shim(), "ghg-ledger") == 0
    assert starters.apply_starters(object(), "ghg-ledger") == 0

    class HasPrompt:
        def prompt(self, **k):
            raise AssertionError("must not register for an unknown key")
    assert starters.apply_starters(HasPrompt(), "no-such-agent") == 0


def test_rendered_texts_carry_the_users_numbers():
    text = starters._footprint_from_bills("12000", "2025", "US-NYUP", "800", "Acme")
    assert "12000 kWh" in text and "US-NYUP" in text and "800 therm" in text
    assert "Acme" in text and "2025" in text
    default = starters._footprint_from_bills("5", "2025")
    assert "region US," in default and "natural gas" not in default
    draft = starters._sb253_first_draft("Acme", "2025", "12000")
    assert "US-CAMX" in draft and "ca-sb253" in draft and "filing" in draft
    assert "since=7" in starters._what_changed("california", "7")
    assert "since=0" in starters._what_changed("california")
