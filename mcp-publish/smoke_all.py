#!/usr/bin/env python3
"""
Smoke tests for the MCP publish packages.

For each agent, imports its adapters/mcp_server.py exactly as an MCP runtime
would (FastMCP shim injected if the SDK is absent), invokes a real tool with a
happy-path payload, and asserts on the JSON result. Run before every publish:

    python3 deploy/mcp-publish/smoke_all.py            # all agents
    python3 deploy/mcp-publish/smoke_all.py smartscale-agent   # one agent

Exits non-zero on any failure.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# agent dir -> list of (tool, kwargs, expected substrings in output)
CASES = {
    "agent-identity-registry-agent": [
        ("register_agent", {"agent_id": "smoke-cad", "capabilities": ["cad"]}, ['"status": "ok"']),
        ("discover_agents", {"capabilities": ["cad"]}, ["smoke-cad"]),
    ],
    "agent-trust-oracle-agent": [
        ("score_agent", {"agent_id": "unknown-x"}, ['"prior": true', "0.5"]),
    ],
    "agent-escrow-agent": [
        ("open_escrow", {"payer": "a", "payee": "b", "amount_minor": 1000}, ["OPEN"]),
    ],
    "agent-metering-agent": [
        ("create_meter", {"provider": "p", "consumer": "c", "unit": "call",
                          "price_minor_per_unit": 100}, ["mtr-"]),
    ],
    "agent-arbitration-agent": [
        ("file_case", {"escrow_id": "e", "claimant": "a", "respondent": "b",
                       "amount_minor": 100}, ["case-", "EVIDENCE_OPEN"]),
    ],
    "agent-compute-ledger-agent": [
        ("record_work", {"agent_id": "a", "entry_id": "e1", "power_w": 100.0,
                         "duration_s": 60.0}, ["energy_j", "carbon_g"]),
    ],
    "smartscale-agent": [
        ("scale_objects_from_credit_card",
         {"image_id": "i", "credit_card_pixel_width": 856.0,
          "objects": [{"name": "box", "pixel_width": 1712.0, "pixel_height": 856.0}]},
         ["171.2"]),
    ],
    "protogen-agent": [
        ("create_cad_workspace", {"project_name": "smoke", "owner_agent": "smoke",
                                  "design_goal": "bracket"}, ["workspace_id"]),
    ],
    "regulatory-radar-agent": [
        ("scan_regulations", {"jurisdiction": "EU"}, ["regulations"]),
    ],
    "narrative-engine-agent": [
        ("translate_narrative", {"agent_output": {"biodiversity_score": 0.82},
                                 "audience_type": "grant_funder",
                                 "format_type": "grant_proposal"}, ["success"]),
    ],
    "agent-covenant-agent": [
        ("grant_covenant", {"principal": "j", "agent_id": "w", "scopes": ["x.*"],
                            "budget_minor": 100,
                            "expires_at": "2099-01-01T00:00:00+00:00"}, ["cov-"]),
    ],
    "agent-provenance-agent": [
        ("register_genesis", {"agent_id": "smoke-agent"},
         ["cert_hash", '"founding_cohort": true']),
    ],
    "agent-offset-clearinghouse-agent": [
        ("list_credit", {"issuer": "viridis", "project_id": "p", "mass_g": 1000,
                         "price_minor_per_kg": 500,
                         "verification_ref": "dscore:x"}, ["crd-"]),
    ],
}


def smoke(agent_dir: str) -> bool:
    cases = CASES[agent_dir]
    code = f'''
import json, sys, types, warnings
warnings.filterwarnings("ignore")
shim_pkg = types.ModuleType("mcp"); shim_srv = types.ModuleType("mcp.server")
shim_fast = types.ModuleType("mcp.server.fastmcp")
class FastMCP:
    def __init__(self, name, **kw): self.name, self.tools = name, {{}}
    def tool(self, *a, **k):
        def deco(fn): self.tools[fn.__name__] = fn; return fn
        return deco
    def run(self): pass
shim_fast.FastMCP = FastMCP
shim_pkg.server = shim_srv; shim_srv.fastmcp = shim_fast
try:
    import mcp  # real SDK present? use it via normal import in the adapter
except ImportError:
    sys.modules["mcp"] = shim_pkg; sys.modules["mcp.server"] = shim_srv
    sys.modules["mcp.server.fastmcp"] = shim_fast; sys.modules["fastmcp"] = shim_fast
sys.path.insert(0, {str(ROOT / agent_dir)!r})
import importlib.util
spec = importlib.util.spec_from_file_location("adapter", {str(ROOT / agent_dir / "adapters" / "mcp_server.py")!r})
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
tools = getattr(mod.mcp, "tools", None)
if tools is None:  # real FastMCP: fall back to module-level functions
    tools = {{name: getattr(mod, name) for name in {json.dumps([c[0] for c in cases])}}}
failures = []
import asyncio, inspect
for tool, kwargs, expects in {json.dumps(cases)}:
    out = tools[tool](**kwargs)
    if inspect.iscoroutine(out):
        out = asyncio.run(out)
    for e in expects:
        if e not in out:
            failures.append(f"{{tool}}: expected {{e!r}} in output")
print(json.dumps({{"failures": failures}}))
'''
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ✗ {agent_dir}: adapter crashed\n{r.stderr[-400:]}")
        return False
    failures = json.loads(r.stdout.strip().splitlines()[-1])["failures"]
    if failures:
        print(f"  ✗ {agent_dir}: {failures}")
        return False
    print(f"  ✓ {agent_dir}: {len(cases)} tool call(s) OK")
    return True


if __name__ == "__main__":
    targets = sys.argv[1:] or list(CASES)
    results = [smoke(t) for t in targets]
    print(f"\n{sum(results)}/{len(results)} publish packages smoke-clean")
    sys.exit(0 if all(results) else 1)
