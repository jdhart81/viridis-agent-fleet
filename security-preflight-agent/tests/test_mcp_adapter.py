import asyncio
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_adapter():
    for name in list(sys.modules):
        if (name == "src" or name.startswith("src.")
                or name == "adapters" or name.startswith("adapters.")):
            sys.modules.pop(name, None)
    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location(
        "security_preflight_test_adapter",
        ROOT / "adapters" / "mcp_server.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_adapter_exports_paid_and_read_tools():
    mcp_server = _load_adapter()
    assert callable(mcp_server.security_preflight)
    assert callable(mcp_server.get_security_receipt)


def test_adapter_accepts_optional_profile_binding():
    mcp_server = _load_adapter()
    result = json.loads(asyncio.run(mcp_server.security_preflight(
        agent_id="profile-bound-agent",
        subject_profile_sha256="b" * 64,
        manifest={
            "endpoint": "https://example.com/mcp",
            "auth": "bearer",
            "tools": [],
        },
    )))
    assert result["market_import"]["eligible"] is True
    assert "profile-sha256:" + "b" * 64 in result["receipt"]["coverage"]


def test_adapter_validation_envelope():
    mcp_server = _load_adapter()
    result = json.loads(asyncio.run(mcp_server.security_preflight(
        agent_id="INVALID ID",
        manifest={},
    )))
    assert result["status"] == "error"
    assert result["field"] == "agent_id"
