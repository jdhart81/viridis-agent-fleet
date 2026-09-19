import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_quantaoptima_boundary_is_fail_closed():
    policy = json.loads((ROOT / "policy.json").read_text())
    assert policy["reviewed_source_commit"] == "7abfc6a"
    assert policy["reviewed_candidate_version"] == "0.4.1"
    assert policy["candidate_release_status"] == "unreleased"
    assert policy["fleet_role"] == "external_optional_dependency"
    assert policy["hosted_by_fleet"] is False
    assert policy["listed_as_paid_fleet_route"] is False
    assert policy["public_sales_enabled"] is False
    assert policy["production_fulfillment_verified"] is False
    assert policy["external_action_authority"] == "none"


def test_quantaoptima_boundary_has_no_checkout_and_retires_unsafe_paths():
    policy_text = (ROOT / "policy.json").read_text()
    readme = (ROOT / "README.md").read_text()
    assert "buy.stripe.com" not in policy_text + readme
    assert "mcp_server.server" in policy_text + readme
    assert "SETUP_MCP.sh" in policy_text + readme
    assert "does not prove execution" in (policy_text + readme).lower()
