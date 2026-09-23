import asyncio
import base64
import importlib.util
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[2]
SECURITY_CORE_PATH = ROOT / "security-preflight-agent" / "src" / "core.py"
MARKET_CORE_PATH = ROOT / "agent-market-network-agent" / "src" / "core.py"
MARKET_SEED_PATH = (
    ROOT / "agent-market-network-agent" / "seed_profiles.json")


def _load_market_module():
    spec = importlib.util.spec_from_file_location(
        "security_preflight_market_core", MARKET_CORE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_security_core():
    spec = importlib.util.spec_from_file_location(
        "security_preflight_market_test_core", SECURITY_CORE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.SecurityPreflightCore


def test_signed_receipt_imports_exactly_once_with_common_control(signing_key):
    SecurityPreflightCore = _load_security_core()
    payload = {
        "action": "scan",
        "agent_id": "viridis-security-injection-detector",
        "manifest": {
            "endpoint": "https://mcp.viridis-security.com/mcp",
            "auth": "api-key",
            "tools": [{
                "name": "detect_injection",
                "input_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
            }],
        },
        "policy": {
            "allowed_tools": ["detect_injection"],
            "denied_tools": [],
            "approval_required_tools": [],
        },
        "sample_inputs": [],
    }
    public_raw = signing_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    market_module = _load_market_module()
    market = market_module.build(
        db_path=":memory:",
        seed_path=str(MARKET_SEED_PATH),
        trusted_security_receipt_keys={
            "viridis-security-preflight":
                base64.urlsafe_b64encode(public_raw).decode().rstrip("="),
        },
    )
    market.seed_owned_profiles([{
        "agent_id": "viridis-security-preflight",
        "name": "Viridis Security Preflight",
        "description": (
            "Operator-owned deterministic security preflight receipt issuer."),
        "capabilities": ["agent-security", "mcp-security"],
        "representative_queries": ["check an MCP agent manifest"],
        "endpoint": (
            "https://mcp.viridisconservation.com/security-preflight/mcp"),
        "payment": {},
        "operator_entity": "ViridisNorth LLC",
    }])
    target = market._profile_row("viridis-security-injection-detector")
    assert target is not None
    payload["subject_profile_sha256"] = target["profile_sha256"]
    signed = asyncio.run(SecurityPreflightCore().process(payload))
    request = {
        "action": "import_security_receipt",
        "receipt": signed["receipt"],
        "signature_b64": signed["signature_b64"],
    }
    imported = asyncio.run(market.process(request))
    replayed = asyncio.run(market.process(request))
    assert imported["status"] == "ok"
    assert imported["data"]["relation"] == "COMMON_CONTROL_RELATED"
    assert imported["data"]["replayed"] is False
    assert replayed["data"]["replayed"] is True
