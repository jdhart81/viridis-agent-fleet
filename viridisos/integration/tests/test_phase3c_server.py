"""Phase 3c staging acceptance — the ViridisOS MCP server (handle_rpc over the live canon).

Run from the ViridisOS package root:
    python3 integration/tests/test_phase3c_server.py
Pure stdlib. Proves the server serves the unified tools + live modules, and A-1 blocks Mutualist.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from integration.mcp_server import handle_rpc, ROOT, FULL_MANIFEST
from integration.mark import verify_mark, Envelope
from integration.certifier_bridge import conservation_validator

_PASS = 0; _FAIL = 0
def check(name, cond):
    global _PASS, _FAIL
    if cond: _PASS += 1
    else: _FAIL += 1; print(f"  FAIL: {name}")

def rpc(method, **params):
    return handle_rpc({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params if params else {}})

def call(name, **args):
    r = rpc("tools/call", name=name, arguments=args)
    return json.loads(r["result"]["content"][0]["text"]), r["result"]["isError"]


def s_initialize():
    r = rpc("initialize")
    check("initialize returns serverInfo", r["result"]["serverInfo"]["name"] == "viridisos")

def s_tools_list():
    r = rpc("tools/list")
    names = {t["name"] for t in r["result"]["tools"]}
    check("tools/list >= 7 tools", len(names) >= 7)
    check("has stateless + module tools",
          {"viridis_bind_did", "viridis_compute_toll", "viridis_certify",
           "viridis_certify_envelope", "viridis_list_modules"} <= names)

def s_list_modules_states():
    data, err = call("viridis_list_modules")
    states = {m["id"]: m["state"] for m in data["modules"]}
    check("mutualist BLOCKED (A-1)", states.get("mutualist") == "BLOCKED")
    check("restoration READY", states.get("restoration") == "READY")
    check("3 live modules READY",
          sum(1 for m in ("restoration", "afforestation", "harmonization") if states.get(m) == "READY") == 3)

def s_certify_live_module():
    data, err = call("viridis_certify", module_id="restoration", subject="corridor-9",
                     inputs={"sigma": 3.0, "delta_mu": 1.5})
    check("certify restoration ok (no error)", err is False)
    check("certificate has id + values", "certificate_id" in data and "claim" in data)

def s_certify_blocked_module():
    data, err = call("viridis_certify", module_id="mutualist", subject="p",
                     inputs={"x": 1.0})
    check("certify mutualist is error (BLOCKED)", err is True and "error" in data)

def s_certify_envelope_verifies():
    data, err = call("viridis_certify_envelope", module_id="afforestation", subject="stand-4",
                     inputs={"sigma": 2.0, "delta_mu": 1.0})
    check("envelope returned", err is False and "envelope" in data)
    e = data["envelope"]
    env = Envelope(e["payload"], e["profile"], e["root_id"], e["key_id"], e["signature"], e["mark"])
    check("server envelope verifies under server root",
          verify_mark(ROOT, env, conservation_validator) is True)

def s_stateless_tool_through_server():
    data, err = call("viridis_bind_did", agent_id="weaver", pubkey="PK")
    check("bind_did via server", str(data.get("did", "")).startswith("did:viridis:"))

def s_unknown_method():
    r = rpc("bogus/method")
    check("unknown method -> JSON-RPC error", "error" in r and r["error"]["code"] == -32601)


TESTS = [
    s_initialize, s_tools_list, s_list_modules_states, s_certify_live_module,
    s_certify_blocked_module, s_certify_envelope_verifies, s_stateless_tool_through_server,
    s_unknown_method,
]

if __name__ == "__main__":
    for t in TESTS:
        try: t()
        except Exception as e:  # noqa: BLE001
            _FAIL += 1; print(f"  FAIL: {t.__name__} ({type(e).__name__}: {e})")
    print(f"{_PASS} passed, {_FAIL} failed")
    sys.exit(0 if _FAIL == 0 else 1)
