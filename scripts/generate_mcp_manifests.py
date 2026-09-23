#!/usr/bin/env python3
"""
Generate MCP publish packages for fleet agents.

For each agent, imports its adapters/mcp_server.py (with a stdlib FastMCP shim
injected, so no MCP SDK is needed), introspects the registered tools, and
writes deploy/mcp-publish-github/<agent>/:

    server.json   — MCP registry manifest (remote/streamable-http template)
    tools.json    — one JSON-Schema tool definition per action

Schemas are generated FROM THE CODE, so they cannot drift from the adapter.
Re-run after any adapter change:  python3 scripts/generate_mcp_manifests.py

Publishing itself is a human step — see each package's DEPLOY.md. This script
never touches the network.
"""
import inspect
import json
import subprocess
import sys
import typing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "deploy" / "mcp-publish-github"
LEGACY_OUT = ROOT / "deploy" / "mcp-publish"
PUBLIC_BASE = "https://mcp.viridisconservation.com"
REPOSITORY = "https://github.com/jdhart81/viridis-agent-fleet"
SMITHERY_OUT = ROOT / "deploy" / "smithery"

AGENTS = {
    # agent dir                      registry short-name        remote path
    "agent-identity-registry-agent": ("agent-identity-registry", "identity"),
    "agent-trust-oracle-agent":      ("agent-trust-oracle",      "trust"),
    "agent-escrow-agent":            ("agent-escrow",            "escrow"),
    "agent-metering-agent":          ("agent-metering",          "metering"),
    "agent-arbitration-agent":       ("agent-arbitration",       "arbitration"),
    "agent-compute-ledger-agent":    ("agent-compute-ledger",    "compute-ledger"),
    "smartscale-agent":              ("smartscale",              "smartscale"),
    "protogen-agent":                ("protogen",                "protogen"),
    "regulatory-radar-agent":        ("regulatory-radar",        "regulatory-radar"),
    "narrative-engine-agent":        ("narrative-engine",        "narrative-engine"),
    "agent-covenant-agent":          ("agent-covenant",          "covenant"),
    "agent-hive-orchestrator-agent": ("agent-hive-orchestrator", "hive"),
    "agent-provenance-agent":        ("agent-provenance",        "provenance"),
    "agent-offset-clearinghouse-agent": ("agent-offset-clearinghouse", "offsets"),
    "agent-erc8004-bridge-agent":       ("agent-erc8004-bridge",       "erc8004"),
    "agent-surety-agent":               ("agent-surety",               "surety"),
    "agent-notary-agent":               ("agent-notary",               "notary"),
    "wavefunction-search-agent":        ("wavefunction-search",        "wavefunction"),
    "taxcredit-engine-agent":           ("taxcredit-engine",           "taxcredit-engine"),
    "ghg-ledger-agent":                 ("ghg-ledger",                 "ghg-ledger"),
    "quantity-takeoff-agent":            ("quantity-takeoff",          "quantity-takeoff"),
    "disclosure-compiler-agent":         ("disclosure-compiler",       "disclosure-compiler"),
    "agent-verified-relay-agent":        ("agent-verified-relay",      "verified"),
    "verdigraph-brain-agent":            ("verdigraph-brain",          "verdigraph"),
    "neurogenesis-agent":                ("neurogenesis",              "neurogenesis"),
    "green-router-agent":                ("green-router",              "green-router"),
    "viridisos":                         ("viridisos",                 "viridisos"),
    "security-preflight-agent":          ("security-preflight",        "security-preflight"),
    # Revenue infrastructure is an auxiliary MCP surface: it is published and
    # aggregated like an agent, but does not increase healthz's hosted-agent
    # count (same convention as the /payments surface).
    "subscriptions-agent":              ("subscriptions",              "subscriptions"),
}

SMITHERY = {
    "quantity-takeoff-agent": {
        "slug": "hartjustin6/quantity-takeoff",
        "display_name": "Viridis Quantity Takeoff",
        "description": ("Deterministic construction material takeoffs with "
                        "locked waste factors, conservative purchase rounding, "
                        "and notary-ready audit hashes."),
        "repository": REPOSITORY,
        "homepage": PUBLIC_BASE,
        "remote_url": f"{PUBLIC_BASE}/quantity-takeoff/mcp",
        "visibility": "public",
        "pricing": ("10 free takeoffs/day, then $0.50 per takeoff via "
                    "redeem_payment. B2B construction seats are planned."),
    },
    "subscriptions-agent": {
        "slug": "hartjustin6/subscriptions",
        "display_name": "Viridis B2B Subscriptions",
        "description": ("Monthly-seat account attribution, deterministic "
                        "entitlements, included quota, exact overage, and MRR."),
        "repository": REPOSITORY,
        "homepage": PUBLIC_BASE,
        "remote_url": f"{PUBLIC_BASE}/subscriptions/mcp",
        "visibility": "public",
        "pricing": ("Draft catalog: $99-$249/month with 1,000 included calls, "
                    "then the covered agent's per-call rate. Checkout remains "
                    "disabled until owner approval and recurring Stripe Price IDs."),
        "publish_note": ("Do not publish a claim that Checkout is active while "
                         "every catalog Price ID is still null."),
    },
    "disclosure-compiler-agent": {
        "slug": "hartjustin6/disclosure-compiler",
        "display_name": "Viridis Disclosure Compiler",
        "description": (
            "Deterministic, cited ESRS E1, IFRS S2, TNFD, and "
            "non-presumptive SEC climate-rule disclosure drafts with "
            "verified GHG lineage and notary-ready audit hashes."
        ),
        "repository": REPOSITORY,
        "homepage": PUBLIC_BASE,
        "remote_url": f"{PUBLIC_BASE}/disclosure-compiler/mcp",
        "visibility": "public",
        "pricing": (
            "10 free disclosure drafts/day, then $2.00 per draft via "
            "redeem_payment. B2B energy, climate, and compliance seats "
            "become coverage-ready with this service; Checkout still "
            "depends on separately approved Stripe Price IDs."
        ),
    },
}

OFFICIAL_DESCRIPTIONS = {
    "security-preflight-agent": (
        "Evidence-bounded static agent security checks with signed redacted receipts."
    ),
    "quantity-takeoff-agent": (
        "Auditable construction takeoffs with locked waste and conservative purchase rounding."
    ),
    "disclosure-compiler-agent": (
        "Deterministic cited disclosure drafts with verified GHG lineage and audit hashes."
    ),
    "verdigraph-brain-agent": (
        "Verifiable cognition: any agent file to a deterministic "
        "content-addressed brain_id."
    ),
}
OFFICIAL_SHORT_NAMES = {
    # Preserve the already-published canonical identity; the local directory
    # name is not the registry product name.
    "verdigraph-brain-agent": "verdigraph",
}
LEGACY_SCHEMA_OVERRIDES = {
    "verdigraph-brain-agent": (
        "https://static.modelcontextprotocol.io/schemas/2025-09-29/"
        "server.schema.json"),
}

# This release carries a detailed, audit-reviewed distribution handoff with
# the Smithery copy, Glama live-regeneration gate, and safe fresh-clone plan.
# A fleet-wide schema regeneration must not replace it with the generic note.
PRESERVE_OFFICIAL_DEPLOY = {"disclosure-compiler-agent"}

_TYPE_MAP = {str: "string", float: "number", int: "integer", bool: "boolean",
             dict: "object", list: "array"}


def _json_type(annotation):
    origin = typing.get_origin(annotation)
    if origin is typing.Union:  # Optional[X]
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return _json_type(args[0]) if args else "string"
    if origin in (list, typing.List):
        return "array"
    if origin in (dict, typing.Dict):
        return "object"
    return _TYPE_MAP.get(annotation, "string")


def _is_optional(param):
    return param.default is not inspect.Parameter.empty


def introspect_agent(agent_dir: str) -> dict:
    """Runs in a SUBPROCESS per agent (src.core namespace collision)."""
    code = f'''
import inspect, json, sys, types, typing
# --- inject FastMCP shim so adapters import without the MCP SDK ---
shim_pkg = types.ModuleType("mcp"); shim_srv = types.ModuleType("mcp.server")
shim_fast = types.ModuleType("mcp.server.fastmcp")
class FastMCP:
    def __init__(self, name, **kw): self.name, self.description, self.tools = name, (kw.get("description") or kw.get("instructions") or ""), {{}}
    def tool(self, *a, **k):
        def deco(fn):
            fn.__viridis_structured_output__ = bool(k.get("structured_output"))
            self.tools[fn.__name__] = fn
            return fn
        return deco
    def run(self): pass
shim_fast.FastMCP = FastMCP
shim_pkg.server = shim_srv; shim_srv.fastmcp = shim_fast
sys.modules["mcp"] = shim_pkg; sys.modules["mcp.server"] = shim_srv
sys.modules["mcp.server.fastmcp"] = shim_fast
sys.modules["fastmcp"] = shim_fast
sys.path.insert(0, {str(ROOT / agent_dir)!r})
import importlib.util
spec = importlib.util.spec_from_file_location("adapter", {str(ROOT / agent_dir / "adapters" / "mcp_server.py")!r})
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
server = mod.mcp
_TYPE_MAP = {{str: "string", float: "number", int: "integer", bool: "boolean", dict: "object", list: "array"}}
def _json_type(ann):
    origin = typing.get_origin(ann)
    if origin is typing.Union:
        args = [a for a in typing.get_args(ann) if a is not type(None)]
        return _json_type(args[0]) if args else "string"
    if origin in (list, typing.List): return "array"
    if origin in (dict, typing.Dict): return "object"
    return _TYPE_MAP.get(ann, "string")
tools = []
for name, fn in server.tools.items():
    sig = inspect.signature(fn)
    props, required = {{}}, []
    for pname, p in sig.parameters.items():
        ann = p.annotation if p.annotation is not inspect.Parameter.empty else str
        props[pname] = {{"type": _json_type(ann)}}
        if p.default is inspect.Parameter.empty: required.append(pname)
        else:
            d = p.default
            if d is not None: props[pname]["default"] = d
    tool = {{"name": name,
             "description": inspect.getdoc(fn) or "",
             "inputSchema": {{"type": "object", "properties": props,
                              "required": required}}}}
    if getattr(fn, "__viridis_structured_output__", False):
        tool["outputSchema"] = {{
            "properties": {{
                "status": {{"title": "Status", "type": "string"}},
                "data": {{"default": None, "title": "Data"}},
                "result": {{"default": None, "title": "Result"}},
                "error": {{"default": None, "title": "Error"}},
                "error_type": {{"anyOf": [{{"type": "string"}}, {{"type": "null"}}],
                               "default": None, "title": "Error Type"}},
                "field": {{"anyOf": [{{"type": "string"}}, {{"type": "null"}}],
                          "default": None, "title": "Field"}},
                "constraint": {{"anyOf": [{{"type": "string"}}, {{"type": "null"}}],
                               "default": None, "title": "Constraint"}},
                "message": {{"anyOf": [{{"type": "string"}}, {{"type": "null"}}],
                            "default": None, "title": "Message"}},
                "timestamp": {{"anyOf": [{{"type": "string"}}, {{"type": "null"}}],
                              "default": None, "title": "Timestamp"}},
            }},
            "required": ["status"],
            "title": "FleetToolResult",
            "type": "object",
        }}
    tools.append(tool)
print(json.dumps({{"server_name": server.name,
                   "server_description": getattr(server, "description", ""),
                   "tools": tools}}))
'''
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{agent_dir}: {r.stderr[-800:]}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def agent_version(agent_dir: str) -> str:
    for line in (ROOT / agent_dir / "agent.yaml").read_text().splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip().strip('"')
    return "0.1.0"


def write_official_deploy(pkg: Path, agent_dir: str, short: str,
                          remote_path: str) -> None:
    """Write the generic handoff unless this package owns reviewed details."""
    deploy_path = pkg / "DEPLOY.md"
    if agent_dir in PRESERVE_OFFICIAL_DEPLOY:
        if not deploy_path.is_file():
            raise RuntimeError(
                f"{agent_dir}: reviewed DEPLOY.md is required and missing"
            )
        return
    deploy_path.write_text(
        f"# Publish {short}\n\n"
        f"Remote: `{PUBLIC_BASE}/{remote_path}/mcp`\n\n"
        "After the matching gateway build is live and healthy:\n\n"
        "```bash\n"
        f"mcp-publisher validate deploy/mcp-publish-github/{agent_dir}/server.json\n"
        f"mcp-publisher publish deploy/mcp-publish-github/{agent_dir}/server.json\n"
        "```\n\n"
        "Publishing mutates the official registry and requires the owner account; "
        "do not publish before live health and version checks pass.\n"
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    LEGACY_OUT.mkdir(parents=True, exist_ok=True)
    SMITHERY_OUT.mkdir(parents=True, exist_ok=True)
    fleet_manifest = {}
    for agent_dir, (short, remote_path) in AGENTS.items():
        info = introspect_agent(agent_dir)
        fleet_manifest[remote_path] = info["tools"]
        pkg = OUT / agent_dir
        pkg.mkdir(exist_ok=True)
        tools_doc = json.dumps(
            {"server": info["server_name"], "tool_count": len(info["tools"]),
             "tools": info["tools"]}, indent=2) + "\n"
        (pkg / "tools.json").write_text(tools_doc)
        manifest = {
            "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
            "name": (
                "io.github.jdhart81/"
                f"{OFFICIAL_SHORT_NAMES.get(agent_dir, short)}"),
            # Official registry schema caps server descriptions at 100 chars.
            "description": (OFFICIAL_DESCRIPTIONS.get(agent_dir)
                            or info["server_description"][:100]
                            or f"Viridis {short} agent"),
            "version": agent_version(agent_dir),
            "repository": {
                "url": REPOSITORY,
                "source": "github",
            },
            "remotes": [{
                "type": "streamable-http",
                "url": f"{PUBLIC_BASE}/{remote_path}/mcp",
            }],
        }
        server_doc = json.dumps(manifest, indent=2) + "\n"
        (pkg / "server.json").write_text(server_doc)
        legacy_pkg = LEGACY_OUT / agent_dir
        legacy_pkg.mkdir(exist_ok=True)
        (legacy_pkg / "tools.json").write_text(tools_doc)
        legacy_manifest = dict(manifest)
        if agent_dir in LEGACY_SCHEMA_OVERRIDES:
            legacy_manifest["$schema"] = LEGACY_SCHEMA_OVERRIDES[agent_dir]
        (legacy_pkg / "server.json").write_text(
            json.dumps(legacy_manifest, indent=2) + "\n")
        write_official_deploy(pkg, agent_dir, short, remote_path)
        if agent_dir in SMITHERY:
            smithery = SMITHERY[agent_dir]
            smithery_listing = {
                key: value for key, value in smithery.items()
                if key != "publish_note"
            }
            smithery_pkg = SMITHERY_OUT / agent_dir
            smithery_pkg.mkdir(exist_ok=True)
            (smithery_pkg / "listing.json").write_text(
                json.dumps(smithery_listing, indent=2) + "\n")
            (smithery_pkg / "DEPLOY.md").write_text(
                f"# Publish {smithery['slug']} on Smithery\n\n"
                "Use `listing.json` to fill the Smithery admin form after the "
                "remote endpoint is live and version-coherent. Keep pricing "
                "and activation claims exactly aligned with `listing.json`.\n\n"
                + ((smithery.get("publish_note") or "") + "\n\n"
                   if smithery.get("publish_note") else "")
                +
                "The Continue button must be clicked a second time in a separate "
                "action after the form loses focus. Verify the resulting listing "
                "is public and its indexed tool count matches `tools.json`.\n")
        print(
            f"  {agent_dir}: {len(info['tools'])} tools -> "
            f"{pkg.relative_to(ROOT)}/ + {legacy_pkg.relative_to(ROOT)}/"
        )
    glama_manifest = ROOT / "deploy" / "glama" / "fleet_manifest.json"
    glama_manifest.write_text(json.dumps(fleet_manifest, indent=2) + "\n")
    total = sum(len(tools) for tools in fleet_manifest.values())
    print(f"  glama: {len(fleet_manifest)} public surfaces / {total} tools -> "
          f"{glama_manifest.relative_to(ROOT)}")
    print("done")


if __name__ == "__main__":
    main()
