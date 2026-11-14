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


# ---- NC1: a request the engine cannot attempt is refused before any charge ----
NC_PROBE = r'''
import asyncio, json, sys
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from src import core
engine = core.build() if hasattr(core, "build") else None
if engine is None or not hasattr(engine, "_paid_preflight"):
    name = [n for n in dir(core) if n.endswith("Core")][0]
    engine = getattr(core, name)()
action, key = sys.argv[3], sys.argv[4]
calls = []
original = type(engine).process
async def wrapped(payload):                      # what a gateway puts on the instance
    calls.append(payload)
    return {"status": "ok", "wrapped": True}
engine.process = wrapped
run = lambda p: asyncio.run(engine._paid_preflight(p))
example = dict(getattr(core, "EXAMPLE_REQUEST", {}) or {})
print(json.dumps({
    "missing": run({"action": action}),
    "wrong_type": run({"action": action, key: "a sentence, not the expected shape"} if key != "jurisdiction" else {"action": action, key: "  "}),
    "with_payment_ref": run({"action": action, "payment_ref": "x", "request_id": "r"}),
    "other_action": run({"action": "describe"}),
    "not_a_dict": run("nope"),
    "example": run({"action": action, **example}) if example else "no-example",
    "instance_wrapper_calls": len(calls),
}, default=str))
'''
NC_TOOLS = {
    "ghg-ledger-agent": ("calculate_inventory", "activities"),
    "quantity-takeoff-agent": ("calculate_takeoff", "items"),
    "disclosure-compiler-agent": ("compile_disclosure", "company_facts"),
    "taxcredit-engine-agent": ("calculate", "facts"),
    "regulatory-radar-agent": ("monitor_changes", "jurisdiction"),
}


@pytest.fixture(scope="module", params=sorted(NC_TOOLS))
def nc(request):
    agent = request.param
    action, key = NC_TOOLS[agent]
    done = subprocess.run(
        [sys.executable, "-c", NC_PROBE, str(FLEET / agent), str(FLEET), action, key],
        capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-800:]
    return agent, json.loads(done.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("case", ["missing", "wrong_type", "with_payment_ref"])
def test_nc1_unusable_request_is_refused_before_charge_with_help(nc, case):
    agent, got = nc
    answer = got[case]
    assert isinstance(answer, dict), f"{agent} {case}: not refused"
    assert answer["status"] == "error" and "first_call_help" in answer


def test_nc1_usable_requests_and_other_actions_take_the_normal_path(nc):
    _agent, got = nc
    assert got["other_action"] is None and got["not_a_dict"] is None
    assert got["example"] in (None, "no-example")


def test_nc1_preflight_never_runs_the_instance_wrapper(nc):
    """The gateway wraps process on the instance with the payment gate and the
    sealer; the admission check must not pass through either."""
    _agent, got = nc
    assert got["instance_wrapper_calls"] == 0
