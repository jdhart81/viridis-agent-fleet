"""Invariant 7 - Honest labels: every output that uses the intelligence bound carries
"conjecture" in its explanation field (valuations, explanations, receipt verification,
pool simulations, method description and MCP tool results)."""

from __future__ import annotations

import asyncio
import json

import pytest
from conftest import clone, random_site

from viridis_eco_funding import (
    describe_method,
    explain_valuation,
    make_receipt,
    simulate_pool,
    value_site,
    verify_receipt,
)


def test_every_valuation_using_the_bound_is_labelled(rng):
    for _ in range(300):
        site = random_site(rng, thermo=rng.random() < 0.7)
        result = value_site(site)
        uses = "thermodynamics" in site
        assert result["uses_intelligence_bound"] is uses
        if uses:
            assert "conjecture" in result["explanation"]
            assert result["labels"]["intelligence_bound"] == "conjecture"
            for name in ("stated_bound_bits_per_s", "complexity_capacity_bits_per_s",
                         "bound_utilization", "compute_parity_w_at_300k"):
                assert result["quantities"][name]["status"] == "conjecture"
                assert "conjecture" in result["quantities"][name]["notes"] or name == "bound_utilization"
        else:
            assert result["labels"]["intelligence_bound"] == "not used"
            assert "stated_bound_bits_per_s" not in result["quantities"]


def test_explain_and_verify_carry_the_label(woodland_site):
    assert "conjecture" in explain_valuation(woodland_site)["explanation"]
    assert "conjecture" in verify_receipt(make_receipt(woodland_site))["explanation"]
    assert "conjecture" in describe_method()["explanation"]


def test_pool_using_bound_metric_is_labelled(woodland_site):
    pool = {"pool_id": "p", "horizon_periods": 1,
            "pledges": [{"id": "a", "pledger": "x", "amount_minor": 100}],
            "rules": [{"id": "c", "type": "milestone", "metric": "complexity_capacity_bits_per_s",
                       "comparator": ">=", "threshold": 1, "release_bps": 100}]}
    sim = simulate_pool(pool, [])
    assert sim["uses_intelligence_bound"] is True
    assert "conjecture" in sim["explanation"]


def test_no_conjecture_claimed_where_bound_is_absent(woodland_site):
    site = clone(woodland_site)
    del site["thermodynamics"]
    result = value_site(site)
    assert result["uses_intelligence_bound"] is False
    assert "conjecture" not in result["explanation"]


def test_mcp_outputs_carry_the_label(woodland_site):
    pytest.importorskip("mcp.server.mcpserver", reason="standalone vef-mcp server needs mcp 2.x")
    from viridis_eco_funding.mcp_server import build_server

    server = build_server()

    async def call(name, args):
        result = await server.call_tool(name, args)
        return json.loads(result.content[0].text)

    out = asyncio.run(call("value_site", {"site": woodland_site}))
    assert "conjecture" in out["explanation"]
    assert "conjecture" in asyncio.run(call("explain_valuation",
                                            {"valuation_or_site": woodland_site}))["explanation"]
    assert "conjecture" in asyncio.run(call("verify_receipt",
                                            {"receipt": out["receipt"]}))["explanation"]
    assert "conjecture" in asyncio.run(call("describe_method", {}))["explanation"]


def test_explain_label_cannot_be_stripped_by_editing_the_valuation(woodland_site):
    """Review finding: the label is derived from content, not the caller's flag."""
    valuation = value_site(woodland_site)
    valuation["uses_intelligence_bound"] = False
    valuation["explanation"] = "Site value explained."
    valuation["labels"] = {"intelligence_bound": "not used"}
    out = explain_valuation(valuation)
    assert out["uses_intelligence_bound"] is True
    assert "conjecture" in out["explanation"]
    assert out["labels"]["intelligence_bound"] == "conjecture"


def test_failed_verification_still_labels_claimed_bound(woodland_site):
    from viridis_eco_funding.canonical import to_plain_json
    receipt = to_plain_json(make_receipt(woodland_site))
    receipt["method_version"] = "vef-method/9.9.9"
    report = verify_receipt(receipt)
    assert report["valid"] is False and "conjecture" in report["explanation"]


def test_receipt_top_level_explanation_is_labelled(woodland_site):
    assert "conjecture" in make_receipt(woodland_site)["explanation"]
