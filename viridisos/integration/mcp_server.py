"""Phase 3c (staging) — the ViridisOS MCP server.

Wraps the unified tool surface + the live modules as an MCP (JSON-RPC 2.0) server. `handle_rpc` is a
pure function (request dict -> response dict) so it is testable without sockets; `main()` is the stdio
loop for the actual server.

STAGING POSTURE: signer is the dev HmacSigner behind TrustRoot, resolver is the live canon index.
The mark is therefore NOT yet externally unforgeable — swap TrustRoot's signer to the K3 signer for a
production authority (see PHASE3_SPEC.md §3c / HANDOFF_NOTES.md). Modules resolve LIVE/BLOCKED against
the real canon: restoration/afforestation/harmonization READY, mutualist BLOCKED until SRPT publishes.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from viridis_platform import build_platform, catalog_status
from runtime.module import CertifyBlocked
from certification.standard import STANDARD
from integration.trust_root import TrustRoot
from integration.mark import verify_mark
from integration.certifier_bridge import certificate_to_envelope, conservation_validator
from integration import mcp_tools

# --- one shared root for the whole server (signs modules' certs AND the stateless tools) ---
ROOT = TrustRoot()
REGISTRY, CERTIFIER = build_platform(signer=ROOT)

# --- tool manifest: the 4 stateless unified tools + the module/certify tools ---
_MODULE_TOOLS = [
    {"name": "viridis_list_modules",
     "description": "List ViridisOS modules and their LIVE/BLOCKED state (A-1 against the live canon).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "viridis_certify",
     "description": "Certify a subject with a module -> a certificate (409/error if the module is BLOCKED).",
     "input_schema": {"type": "object",
                      "properties": {"module_id": {"type": "string"}, "subject": {"type": "string"},
                                     "inputs": {"type": "object"}},
                      "required": ["module_id", "subject", "inputs"]}},
    {"name": "viridis_certify_envelope",
     "description": "Certify then return a 'Certified by ViridisOS' mark envelope (conservation-claim).",
     "input_schema": {"type": "object",
                      "properties": {"module_id": {"type": "string"}, "subject": {"type": "string"},
                                     "inputs": {"type": "object"}},
                      "required": ["module_id", "subject", "inputs"]}},
]
FULL_MANIFEST = list(mcp_tools.MANIFEST) + _MODULE_TOOLS
_STATELESS = {t["name"] for t in mcp_tools.MANIFEST}


def dispatch_tool(name: str, args: dict) -> dict:
    """Route a tool call. Pure, never raises — returns {"error": ...} on any failure."""
    try:
        if name in _STATELESS:
            return mcp_tools.call_tool(name, args, root=ROOT)
        if name == "viridis_list_modules":
            return {"modules": catalog_status()}
        if name == "viridis_certify":
            module = REGISTRY.get(args["module_id"])
            cert = CERTIFIER.issue(module, subject=args["subject"], inputs=args["inputs"])
            return cert.to_dict()
        if name == "viridis_certify_envelope":
            module = REGISTRY.get(args["module_id"])
            cert = CERTIFIER.issue(module, subject=args["subject"], inputs=args["inputs"])
            return {"envelope": asdict(certificate_to_envelope(cert))}
        return {"error": f"unknown tool: {name}"}
    except CertifyBlocked as e:
        return {"error": f"BLOCKED: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e) or type(e).__name__}


def handle_rpc(req: dict) -> dict:
    """Pure JSON-RPC 2.0 handler for the MCP methods we support."""
    mid = req.get("id")
    method = req.get("method")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "viridisos", "version": "1.0.0", "standard": STANDARD["id"]},
            "capabilities": {"tools": {}}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": FULL_MANIFEST}}
    if method == "tools/call":
        params = req.get("params", {}) or {}
        result = dispatch_tool(params.get("name", ""), params.get("arguments", {}) or {})
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": json.dumps(result)}],
            "isError": "error" in result}}
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def main() -> None:  # pragma: no cover - stdio transport
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        sys.stdout.write(json.dumps(handle_rpc(req)) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
