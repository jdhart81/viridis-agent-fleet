"""Hermes is a remote buyer of Viridis services, never a fleet runtime."""
from pathlib import Path

import yaml


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GATEWAY = ROOT / "deploy" / "gateway"
if not GATEWAY.exists():  # public mirror layout
    GATEWAY = ROOT / "gateway"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_hermes_skill_is_remote_only_and_covers_every_paid_route():
    skill = _read(ROOT / "integrations" / "viridis-paid-tools" / "SKILL.md")
    assert "name: viridis-paid-tools" in skill
    assert "https://mcp.viridisconservation.com/network/mcp" in skill
    for agent, tool in {
        "quantity-takeoff": "calculate_takeoff",
        "ghg-ledger": "calculate_inventory",
        "disclosure-compiler": "compile_disclosure",
        "taxcredit-engine": "calculate_tax_credit",
        "regulatory-radar": "scan_regulations",
    }.items():
        assert f"/x402/{agent}/{tool}" in skill
    lowered = skill.lower()
    assert "never install or run it on viridis production" in lowered
    assert "never send a private key to viridis" in lowered
    assert "make exactly one paid attempt" in lowered
    assert "pip install hermes" not in lowered
    assert "hermes setup" not in lowered
    assert "hermes-agent.nousresearch.com/install" not in lowered


def test_hermes_catalog_candidate_is_keyless_read_first_remote_mcp():
    path = (ROOT / "integrations" / "hermes-catalog" /
            "viridis-agent-market" / "manifest.yaml")
    manifest = yaml.safe_load(_read(path))
    assert manifest["manifest_version"] == 1
    assert manifest["name"] == "viridis-agent-market"
    assert manifest["transport"] == {
        "type": "http",
        "url": "https://mcp.viridisconservation.com/network/mcp",
    }
    assert manifest["auth"] == {"type": "none"}
    assert manifest["tools"]["default_enabled"] == [
        "network_status",
        "describe_network",
        "search_agents",
        "search_work",
        "get_work",
        "list_security_attestations",
    ]
    assert "private keys on the caller's machine" in manifest["post_install"]


def test_hosted_and_long_form_quickstarts_link_the_same_buyer_artifacts():
    hosted = _read(GATEWAY / "quickstart.html")
    long_form = _read(ROOT / "docs" / "QUICKSTART_FIRST_CALL.md")
    buyer = _read(
        ROOT / "docs" / "integrations" / "HERMES_BUYER_QUICKSTART.md")
    for content in (hosted, long_form, buyer):
        assert "hermes mcp add viridis-market" in content
        assert "https://mcp.viridisconservation.com/network/mcp" in content
    assert "viridis-paid-tools/SKILL.md" in hosted
    assert "viridis-paid-tools/SKILL.md" in long_form
    assert "viridis-paid-tools/SKILL.md" in buyer
