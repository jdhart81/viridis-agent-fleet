"""FC1: every calculation engine publishes one request that computes.

The same request appears in the MCP tool description, in describe(), and beside
any failed or empty calculation, so an agent holding only the tool description
can reach a determinate result on its next call.
"""
import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

FLEET = Path(__file__).resolve().parents[2]
ENGINES = {
    "ghg-ledger-agent": ("calculate_inventory", "calculate_inventory", "inventory_status",
                         {"activities": [{"type": "electricity", "amount": 250000, "unit": "kWh",
                                          "location": "Texas", "year": 2025}], "options": {}}),
    "quantity-takeoff-agent": ("calculate_takeoff", "calculate_takeoff", "takeoff_status",
                               {"items": [{"type": "concrete slab", "length": 20, "width": 30,
                                           "thickness": 4}], "options": {}}),
    "disclosure-compiler-agent": ("compile_disclosure", "compile_disclosure", "draft_status",
                                  {"framework": "SB 253", "company_facts": {"name": "Acme Corp"}}),
    "taxcredit-engine-agent": ("calculate", "calculate_tax_credit", "calculation_status",
                               {"credit": "48E", "facts": {"project_cost": 2400000,
                                                           "capacity_mw": 1.5}}),
}
PROBE = r'''
import asyncio, json, sys, inspect
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from src import core
import adapters.mcp_server as adapter
action, tool, naive = sys.argv[3], sys.argv[4], json.loads(sys.argv[5])
engine = core.build()
run = lambda req: asyncio.run(engine.process(req))
fn = getattr(adapter, tool)
fn = getattr(fn, "fn", fn)
doc = inspect.getdoc(inspect.unwrap(fn)) or ""
print(json.dumps({
    "example": core.EXAMPLE_REQUEST,
    "good": run({"action": action, **core.EXAMPLE_REQUEST}),
    "bad": run({"action": action, **naive}),
    "broken": run({"action": action}),
    "other": run({"action": "verify_result", "result": {}}),
    "describe": engine.describe(),
    "doc": doc,
}, default=str))
'''


@pytest.fixture(scope="module", params=sorted(ENGINES))
def probe(request):
    agent = request.param
    action, tool, status_key, naive = ENGINES[agent]
    out = subprocess.run([sys.executable, "-c", PROBE, str(FLEET / agent), str(FLEET),
                          action, tool, json.dumps(naive)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]
    return agent, status_key, json.loads(out.stdout)


def test_published_example_computes_with_no_help_needed(probe):
    agent, status_key, got = probe
    assert got["good"]["status"] == "ok", agent
    assert got["good"]["data"][status_key] not in ("indeterminate", None), agent
    assert "first_call_help" not in got["good"], agent


def test_a_naive_or_malformed_call_is_handed_the_working_example(probe):
    agent, status_key, got = probe
    for kind in ("bad", "broken"):
        help_ = got[kind].get("first_call_help")
        assert help_ and help_["example_request"] == got["example"], (agent, kind)
        assert help_["discover_with"], agent
    # the help never enters audited data, and other actions are untouched
    assert "first_call_help" not in json.dumps(got["bad"].get("data", {})), agent
    assert "first_call_help" not in got["other"], agent


def test_tool_description_and_describe_carry_the_same_example(probe):
    agent, _, got = probe
    assert got["describe"]["example_request"] == got["example"], agent
    marker = "Example arguments: "
    assert marker in got["doc"], agent
    assert json.loads(got["doc"].split(marker, 1)[1]) == got["example"], agent
