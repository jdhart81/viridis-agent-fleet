"""FH1: a first request with missing inputs reaches the engine and gets help.

Before this, the MCP layer rejected such a request with a schema error that
named a field and linked to a validation library's documentation. The engine's
own first_call_help (a request that computes) was never seen by the callers who
needed it most.

FH1 calling a priced tool over MCP with no arguments, or with only unknown
    arguments, returns the engine's JSON answer with first_call_help; it is not
    an MCP schema error.
FH2 a complete request still computes exactly as before.
FH3 the tool's schema still names every input; none is marked required that the
    engine can explain the absence of.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

FLEET = Path(__file__).resolve().parents[2]
TOOLS = {
    "ghg-ledger-agent": ("calculate_inventory", ["activities"]),
    "quantity-takeoff-agent": ("calculate_takeoff", ["items"]),
    "disclosure-compiler-agent": ("compile_disclosure", ["framework", "company_facts"]),
    "taxcredit-engine-agent": ("calculate_tax_credit", ["credit", "facts"]),
    "regulatory-radar-agent": ("monitor_changes", ["jurisdiction"]),
}
PROBE = r'''
import asyncio, json, sys
sys.path[:0] = [sys.argv[1], sys.argv[2]]
import adapters.mcp_server as adapter
tool = sys.argv[3]

def text(result):
    if isinstance(result, tuple):
        result = result[0]
    blocks = getattr(result, "content", result)
    return blocks[0].text

async def call(arguments):
    try:
        return {"text": text(await adapter.mcp.call_tool(tool, arguments))}
    except Exception as exc:
        return {"raised": repr(exc)[:300]}

async def main():
    tools = {t.name: t for t in await adapter.mcp.list_tools()}
    schema = tools[tool].inputSchema
    example = None
    try:
        from src import core
        example = getattr(core, "EXAMPLE_REQUEST", None)
    except Exception:
        pass
    out = {"empty": await call({}),
           "unknown_only": await call({"description": "a plain-language request"}),
           "schema": schema}
    if example is not None:
        out["example"] = await call(example)
    print(json.dumps(out, default=str))

asyncio.run(main())
'''


@pytest.fixture(scope="module", params=sorted(TOOLS))
def probe(request):
    agent = request.param
    tool, inputs = TOOLS[agent]
    done = subprocess.run(
        [sys.executable, "-c", PROBE, str(FLEET / agent), str(FLEET), tool],
        capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-800:]
    return agent, tool, inputs, json.loads(done.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("case", ["empty", "unknown_only"])
def test_fh1_missing_inputs_reach_the_engine_and_get_help(probe, case):
    agent, tool, _inputs, got = probe
    answer = got[case]
    assert "raised" not in answer, f"{agent}.{tool} {case}: {answer}"
    assert "validation error" not in answer["text"] and "pydantic" not in answer["text"]
    body = json.loads(answer["text"])
    assert "first_call_help" in body, f"{agent}.{tool} {case} gave no help"
    assert body.get("status") in ("error", "ok", "success")


def test_fh2_a_complete_request_still_computes(probe):
    agent, tool, _inputs, got = probe
    if "example" not in got:
        pytest.skip("engine publishes no EXAMPLE_REQUEST")
    assert "raised" not in got["example"], got["example"]
    body = json.loads(got["example"]["text"])
    assert body.get("status") in ("ok", "success") and "first_call_help" not in body


def test_fh3_schema_names_every_input_and_requires_none_of_them(probe):
    _agent, _tool, inputs, got = probe
    schema = got["schema"]
    for name in inputs:
        assert name in schema["properties"]
        assert name not in schema.get("required", [])
