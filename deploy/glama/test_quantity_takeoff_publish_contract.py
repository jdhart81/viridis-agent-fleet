"""Offline publication contract for the quantity-takeoff MCP surface."""

import json
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "deploy" / "mcp-publish-github" / "quantity-takeoff-agent"
SMITHERY = ROOT / "deploy" / "smithery" / "quantity-takeoff-agent" / "listing.json"
GLAMA = ROOT / "deploy" / "glama" / "fleet_manifest.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def test_official_registry_manifest_targets_live_surface():
    server = _json(PACKAGE / "server.json")
    assert server["name"] == "io.github.jdhart81/quantity-takeoff"
    assert server["version"] == "0.1.0"
    assert server["remotes"] == [{
        "type": "streamable-http",
        "url": "https://mcp.viridisconservation.com/quantity-takeoff/mcp",
    }]


def test_tool_schemas_match_the_seven_tool_contract():
    package = _json(PACKAGE / "tools.json")
    assert package["server"] == "quantity-takeoff-agent"
    assert package["tool_count"] == 7
    assert package["tool_count"] == len(package["tools"])
    assert {tool["name"] for tool in package["tools"]} == {
        "calculate_takeoff",
        "list_assemblies",
        "get_assembly",
        "list_material_pack",
        "get_material_pack",
        "verify_result",
        "describe_agent",
    }


def test_glama_manifest_matches_the_generated_official_tool_package():
    package = _json(PACKAGE / "tools.json")
    glama = _json(GLAMA)
    assert len(glama) == 29
    assert sum(len(tools) for tools in glama.values()) == 216
    assert {tool["name"] for tool in glama["quantity-takeoff"]} == {
        tool["name"] for tool in package["tools"]
    }


def test_smithery_scaffold_is_public_and_states_live_pricing():
    listing = _json(SMITHERY)
    assert listing["slug"] == "hartjustin6/quantity-takeoff"
    assert listing["visibility"] == "public"
    assert listing["remote_url"].endswith("/quantity-takeoff/mcp")
    assert "10 free takeoffs/day" in listing["pricing"]
    assert "$0.50 per takeoff" in listing["pricing"]
    assert "redeem_payment" in listing["pricing"]


def test_version_coherence_maps_registry_name_to_live_mount():
    path = ROOT / "deploy" / "check_version_coherence.py"
    spec = importlib.util.spec_from_file_location("version_coherence", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.NAME_TO_MOUNT["quantity-takeoff"] == "quantity-takeoff"
