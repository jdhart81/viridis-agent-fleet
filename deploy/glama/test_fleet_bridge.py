"""Release-contract tests for the Glama/public aggregate bridge."""

import json
import sys
import types

import fleet_bridge as bridge


def test_private_bearer_forwarding_is_opt_in(monkeypatch):
    monkeypatch.delenv("VIRIDIS_ACCOUNT_KEY", raising=False)
    assert bridge.upstream_headers() is None

    monkeypatch.setenv("VIRIDIS_ACCOUNT_KEY", "vir_acct_private_test")
    assert bridge.upstream_headers() == {
        "Authorization": "Bearer vir_acct_private_test"
    }


def test_malformed_private_bearer_falls_back_to_anonymous(monkeypatch):
    monkeypatch.setenv("VIRIDIS_ACCOUNT_KEY", "bad token")
    assert bridge.upstream_headers() is None
    monkeypatch.setenv("VIRIDIS_ACCOUNT_KEY", "x" * 257)
    assert bridge.upstream_headers() is None


def test_subscription_surface_is_bundled_and_namespaced(monkeypatch):
    manifest = bridge.load_manifest()
    assert "subscriptions" in manifest
    names = {tool["name"] for tool in manifest["subscriptions"]}
    assert {
        "list_plans",
        "create_checkout_link",
        "subscription_status",
        "mrr_summary",
    }.issubset(names)

    class Tool:
        def __init__(self, **kwargs):
            vars(self).update(kwargs)

    mcp_shim = types.ModuleType("mcp")
    mcp_shim.types = types.SimpleNamespace(Tool=Tool)
    monkeypatch.setitem(sys.modules, "mcp", mcp_shim)

    tools, routes = bridge.build_tool_index({
        "subscriptions": manifest["subscriptions"]
    })
    fq_names = {tool.name for tool in tools}
    assert "subscriptions__list_plans" in fq_names
    assert routes["subscriptions__mrr_summary"] == (
        "subscriptions", "mrr_summary"
    )
    description = next(
        tool.description for tool in tools
        if tool.name == "subscriptions__list_plans"
    )
    assert "B2B monthly seats" in description


def test_quantity_takeoff_surface_is_bundled_and_namespaced(monkeypatch):
    manifest = bridge.load_manifest()
    assert "quantity-takeoff" in manifest
    names = {tool["name"] for tool in manifest["quantity-takeoff"]}
    assert {
        "calculate_takeoff",
        "list_assemblies",
        "get_material_pack",
        "verify_result",
    }.issubset(names)

    class Tool:
        def __init__(self, **kwargs):
            vars(self).update(kwargs)

    mcp_shim = types.ModuleType("mcp")
    mcp_shim.types = types.SimpleNamespace(Tool=Tool)
    monkeypatch.setitem(sys.modules, "mcp", mcp_shim)

    tools, routes = bridge.build_tool_index({
        "quantity-takeoff": manifest["quantity-takeoff"]
    })
    fq_names = {tool.name for tool in tools}
    assert "quantity-takeoff__calculate_takeoff" in fq_names
    assert routes["quantity-takeoff__verify_result"] == (
        "quantity-takeoff", "verify_result"
    )
    description = next(
        tool.description for tool in tools
        if tool.name == "quantity-takeoff__calculate_takeoff"
    )
    assert "construction material takeoffs" in description


def test_manifest_never_contains_a_bearer_secret():
    raw = json.dumps(bridge.load_manifest()).lower()
    assert "viridis_account_key" not in raw
    assert "authorization" not in raw
    assert "account_key" not in raw
