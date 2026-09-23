"""Offline publication contract for the disclosure-compiler MCP surface."""

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = (
    ROOT / "deploy" / "mcp-publish-github" / "disclosure-compiler-agent"
)
BRIDGE_PATH = ROOT / "deploy" / "glama" / "fleet_bridge.py"
OFFLINE_GENERATOR = ROOT / "scripts" / "generate_mcp_manifests.py"
LIVE_GENERATOR = ROOT / "scripts" / "generate_live_glama_manifest.py"
GLAMA = ROOT / "deploy" / "glama" / "fleet_manifest.json"
SMITHERY = (
    ROOT / "deploy" / "smithery" / "disclosure-compiler-agent" / "listing.json"
)
VERSION_COHERENCE = ROOT / "deploy" / "check_version_coherence.py"


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_official_registry_manifest_targets_intended_live_surface():
    server = _json(PACKAGE / "server.json")
    assert server["name"] == "io.github.jdhart81/disclosure-compiler"
    assert server["version"] == "0.1.0"
    assert server["repository"] == {
        "url": "https://github.com/jdhart81/viridis-agent-fleet",
        "source": "github",
    }
    assert server["remotes"] == [{
        "type": "streamable-http",
        "url": (
            "https://mcp.viridisconservation.com/"
            "disclosure-compiler/mcp"
        ),
    }]


def test_tool_schemas_match_the_five_tool_contract():
    package = _json(PACKAGE / "tools.json")
    assert package["server"] == "disclosure-compiler-agent"
    assert package["tool_count"] == 5 == len(package["tools"])
    assert {tool["name"] for tool in package["tools"]} == {
        "compile_disclosure",
        "list_frameworks",
        "get_framework",
        "verify_result",
        "describe_agent",
    }
    compile_schema = next(
        tool["inputSchema"] for tool in package["tools"]
        if tool["name"] == "compile_disclosure"
    )
    assert compile_schema["required"] == ["framework", "company_facts"]
    assert compile_schema["properties"]["ghg_result"]["type"] == "object"
    assert compile_schema["properties"]["options"]["type"] == "object"


def test_glama_bridge_has_disclosure_role_and_namespace_contract(monkeypatch):
    bridge = _load(BRIDGE_PATH, "disclosure_fleet_bridge")
    assert bridge.ROLE["disclosure-compiler"] == (
        "deterministic cited compliance disclosure drafts "
        "(ESRS E1/SEC/IFRS S2/TNFD)"
    )

    class Tool:
        def __init__(self, **kwargs):
            vars(self).update(kwargs)

    import sys
    import types

    mcp_shim = types.ModuleType("mcp")
    mcp_shim.types = types.SimpleNamespace(Tool=Tool)
    monkeypatch.setitem(sys.modules, "mcp", mcp_shim)
    packaged = _json(PACKAGE / "tools.json")["tools"]
    tools, routes = bridge.build_tool_index({
        "disclosure-compiler": packaged,
    })
    names = {tool.name for tool in tools}
    assert "disclosure-compiler__compile_disclosure" in names
    assert routes["disclosure-compiler__verify_result"] == (
        "disclosure-compiler", "verify_result"
    )
    description = next(
        tool.description for tool in tools
        if tool.name == "disclosure-compiler__compile_disclosure"
    )
    assert "deterministic cited compliance disclosure drafts" in description


def test_offline_generator_knows_the_disclosure_surface():
    generator = _load(OFFLINE_GENERATOR, "disclosure_offline_generator")
    assert generator.AGENTS["disclosure-compiler-agent"] == (
        "disclosure-compiler", "disclosure-compiler"
    )
    assert len(generator.OFFICIAL_DESCRIPTIONS[
        "disclosure-compiler-agent"
    ]) <= 100
    assert generator.SMITHERY["disclosure-compiler-agent"] == _json(SMITHERY)
    assert "disclosure-compiler-agent" in generator.PRESERVE_OFFICIAL_DEPLOY


def test_generator_preserves_reviewed_disclosure_deploy(tmp_path):
    generator = _load(OFFLINE_GENERATOR, "deploy_preserving_generator")
    pkg = tmp_path / "disclosure-compiler-agent"
    pkg.mkdir()
    deploy = pkg / "DEPLOY.md"
    deploy.write_text("reviewed distribution handoff\n")
    generator.write_official_deploy(
        pkg,
        "disclosure-compiler-agent",
        "disclosure-compiler",
        "disclosure-compiler",
    )
    assert deploy.read_text() == "reviewed distribution handoff\n"


def test_live_generator_is_fail_closed_until_28_agent_release():
    source = LIVE_GENERATOR.read_text()
    assert 'default=28' in source
    assert 'agents.get("disclosure-compiler", {}).get("version")' in source
    assert 'manifest.get("disclosure-compiler")' in source


def test_released_glama_manifest_matches_disclosure_package():
    package = _json(PACKAGE / "tools.json")
    glama = _json(GLAMA)
    assert len(glama) == 29
    assert sum(len(tools) for tools in glama.values()) == 216
    assert {tool["name"] for tool in glama["disclosure-compiler"]} == {
        tool["name"] for tool in package["tools"]
    }


def test_publish_package_contains_no_secret_or_card_surface():
    raw = (PACKAGE / "server.json").read_text()
    raw += (PACKAGE / "tools.json").read_text()
    lowered = raw.lower()
    assert "sk_live_" not in lowered
    assert "sk_test_" not in lowered
    assert "card_number" not in lowered
    assert "account_key" not in lowered


def test_handoff_documents_exact_registry_targets_and_safe_fresh_clone():
    deploy = (PACKAGE / "DEPLOY.md").read_text()
    assert "io.github.jdhart81/disclosure-compiler" in deploy
    assert "hartjustin6/disclosure-compiler" in deploy
    assert (
        "python3 scripts/generate_live_glama_manifest.py --expected-count 21"
        in deploy
    )
    assert "/private/tmp/viridis-agent-fleet-disclosure-20260713" in deploy
    assert "Do not reuse `_public-repo-viridis-agent-fleet`" in deploy


def test_smithery_scaffold_is_public_and_states_exact_pricing():
    listing = _json(SMITHERY)
    assert listing["slug"] == "hartjustin6/disclosure-compiler"
    assert listing["visibility"] == "public"
    assert listing["remote_url"].endswith("/disclosure-compiler/mcp")
    assert "10 free disclosure drafts/day" in listing["pricing"]
    assert "$2.00 per draft" in listing["pricing"]
    assert "redeem_payment" in listing["pricing"]
    assert "Stripe Price IDs" in listing["pricing"]


def test_version_coherence_maps_registry_name_to_live_mount():
    module = _load(VERSION_COHERENCE, "disclosure_version_coherence")
    assert module.NAME_TO_MOUNT["disclosure-compiler"] == "disclosure-compiler"
