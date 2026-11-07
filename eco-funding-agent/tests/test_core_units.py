"""Unit tests for connectivity, soil, canonical JSON, decimal helpers and input validation."""

from __future__ import annotations

from decimal import Decimal, localcontext

import pytest
from conftest import clone

from viridis_eco_funding import SiteInputError, value_site
from viridis_eco_funding._decimal import CONTEXT, round_sig, to_decimal
from viridis_eco_funding.canonical import canonical_dumps, format_decimal, loads_decimal, to_plain_json
from viridis_eco_funding.connectivity import equivalent_connected_area
from viridis_eco_funding.inputs import normalize_site_inputs
from viridis_eco_funding.soil import indicator_score


def habitat(patches, links=(), **extra):
    site = {"site_id": "t", "habitat": {"patches": list(patches), "links": list(links), **extra},
            "biodiversity": {k: {"value": 0.5} for k in ("taxonomic", "productivity", "functional", "spectral")}}
    return normalize_site_inputs(site)["habitat"]


# --- connectivity ---------------------------------------------------------------------
def test_eca_two_patches_known_values():
    a = {"id": "a", "area_ha": 4, "verified": True}
    b = {"id": "b", "area_ha": 9, "verified": True}
    with localcontext(CONTEXT):
        assert equivalent_connected_area(habitat([a, b]))["eca_ha"] == Decimal(97).sqrt()
    full = equivalent_connected_area(habitat([a, b], [{"from": "a", "to": "b", "hdfm_linked": True}]))
    assert full["eca_ha"] == 13
    half = equivalent_connected_area(habitat([a, b], [{"from": "a", "to": "b", "probability": 0.5}]))
    with localcontext(CONTEXT):
        assert half["eca_ha"] == Decimal(16 + 81 + 2 * 36 * Decimal("0.5")).sqrt()


def test_eca_uses_best_path_through_stepping_stone():
    patches = [{"id": x, "area_ha": 1, "verified": True} for x in "abc"]
    links = [{"from": "a", "to": "b", "probability": 0.9}, {"from": "b", "to": "c", "probability": 0.9},
             {"from": "a", "to": "c", "probability": 0.5}]
    result = equivalent_connected_area(habitat(patches, links))
    # p*_ac = max(0.5, 0.81) = 0.81
    with localcontext(CONTEXT):
        expected = Decimal(3 + 2 * (Decimal("0.9") + Decimal("0.9") + Decimal("0.81"))).sqrt()
    assert result["eca_ha"] == expected


def test_distance_kernel_matches_hdfm_form():
    patches = [{"id": "a", "area_ha": 1, "verified": True}, {"id": "b", "area_ha": 1, "verified": True}]
    result = equivalent_connected_area(habitat(patches, [{"from": "a", "to": "b", "distance_m": 500}]))
    with localcontext(CONTEXT):
        assert result["links_used"][0]["probability"] == Decimal(-1).exp()  # exp(-2 * 500 / 1000)


def test_unverified_endpoints_are_ignored_and_reported():
    patches = [{"id": "a", "area_ha": 1, "verified": True}, {"id": "b", "area_ha": 5}]
    result = equivalent_connected_area(habitat(patches, [{"from": "a", "to": "b", "hdfm_linked": True}]))
    assert result["eca_ha"] == 1 and result["unverified_patch_ids"] == ["b"]
    assert result["links_ignored"][0]["reason"].startswith("an endpoint")


def test_no_verified_patches_scores_zero(woodland_site):
    site = clone(woodland_site)
    for patch in site["habitat"]["patches"]:
        patch["verified"] = False
    result = value_site(site)
    assert result["quantities"]["complexity_score"]["value"] == 0
    assert result["quantities"]["complexity_capacity_bits_per_s"]["value"] == 0
    assert any("no verified patches" in w for w in result["warnings"])


# --- soil -----------------------------------------------------------------------------
@pytest.mark.parametrize("name,value,expected", [
    ("soc_g_per_kg", "20", "0.5"), ("soc_g_per_kg", "80", "1"),
    ("ph", "3.5", "0"), ("ph", "5", "0.5"), ("ph", "7", "1"), ("ph", "8.25", "0.5"), ("ph", "9.5", "0"),
    ("bd_kg_per_dm3", "1.2", "1"), ("bd_kg_per_dm3", "1.55", "0.5"), ("bd_kg_per_dm3", "2", "0"),
    ("cec_cmol_per_kg", "12.5", "0.5"), ("n_g_per_kg", "1.5", "0.5"),
])
def test_soil_curves(name, value, expected):
    assert indicator_score(name, Decimal(value)) == Decimal(expected)


def test_soil_weight_zero_reproduces_dscore(woodland_site):
    site = clone(woodland_site)
    site["weights"] = {"soil": 0}
    q = value_site(site)["quantities"]
    assert q["data_richness"]["value"] == q["d_score"]["value"]


# --- canonical JSON and decimals ----------------------------------------------------------
@pytest.mark.parametrize("value,text", [
    ("0", "0"), ("-0.0", "0"), ("1.500", "1.5"), ("100", "100"), ("1E+2", "100"),
    ("0.0000001", "0.0000001"), ("0.00000001", "1E-8"), ("1E+21", "1E+21"),
    ("123456789012345678901", "123456789012345678901"), ("-2.5E-30", "-2.5E-30"),
])
def test_format_decimal(value, text):
    assert format_decimal(Decimal(value)) == text


def test_canonical_rules():
    assert canonical_dumps({"b": [1, Decimal("2.0")], "a": None, "c": "é"}) == '{"a":null,"b":[1,2],"c":"\\u00e9"}'
    with pytest.raises(TypeError):
        canonical_dumps({"x": 1.5})
    with pytest.raises(TypeError):
        canonical_dumps({1: "x"})
    with pytest.raises(ValueError):
        loads_decimal('{"x": NaN}')
    assert to_plain_json({"x": Decimal("2.5E+25")}) == {"x": 2.5e25}


def test_decimal_helpers():
    assert round_sig(Decimal("123456"), 2) == Decimal("1.2E+5")
    assert to_decimal(0.1) == Decimal("0.1")
    for bad in (True, float("nan"), float("inf"), [1], "abc"):
        with pytest.raises(ValueError):
            to_decimal(bad)


# --- input validation -------------------------------------------------------------------
BAD = [
    (lambda s: s.pop("site_id"), "site_id"),
    (lambda s: s.update(extra=1), "unknown key"),
    (lambda s: s.update(schema="vef-site/9"), "schema"),
    (lambda s: s["biodiversity"].pop("spectral"), "missing component"),
    (lambda s: s["biodiversity"]["productivity"].update(value=1.2), "<= 1"),
    (lambda s: s["biodiversity"]["productivity"].pop("value"), "normalized value"),
    (lambda s: s["habitat"]["patches"][0].update(area_ha=0), "> 0"),
    (lambda s: s["habitat"]["patches"].append(dict(s["habitat"]["patches"][0])), "duplicate patch"),
    (lambda s: s["habitat"]["links"].append({"from": "core-north", "to": "nope", "probability": 1}), "unknown patch"),
    (lambda s: s["habitat"]["links"].append({"from": "core-north", "to": "core-north", "probability": 1}), "different"),
    (lambda s: s["habitat"]["links"].append({"from": "core-south", "to": "hedgerow-link", "probability": 1}), "duplicate link"),
    (lambda s: s["habitat"]["links"].append({"from": "core-north", "to": "core-south"}), "exactly one"),
    (lambda s: s["habitat"]["links"].append({"from": "core-north", "to": "core-south", "hdfm_linked": False}), "must be true"),
    (lambda s: s["habitat"]["patches"][0].update(verified="yes"), "true or false"),
    (lambda s: s["thermodynamics"].update(mean_temperature_K=20), ">= 150"),
    (lambda s: s.update(soil={"sigma": 0.1}), "at least one"),
    (lambda s: s.update(vergecommon={"coop_id": "not-a-uuid", "project_id": "x"}), "UUID"),
    (lambda s: s["biodiversity"]["taxonomic"].update(z=0.5), "inside z_range"),
    (lambda s: s["biodiversity"]["taxonomic"].update(observations=True), "integer"),
    (lambda s: s["biodiversity"]["productivity"].update(sigma_basis="default"), "requires"),
    (lambda s: s["biodiversity"]["productivity"].update(mode="rarefaction"), "mode"),
]


@pytest.mark.parametrize("mutate,message", BAD)
def test_invalid_inputs_are_rejected_with_named_field(woodland_site, mutate, message):
    site = clone(woodland_site)
    mutate(site)
    with pytest.raises(SiteInputError, match=message):
        value_site(site)


def test_defaults_are_written_out_and_flagged(woodland_site):
    site = clone(woodland_site)
    del site["biodiversity"]["productivity"]["sigma"]
    del site["habitat"]["area_relative_uncertainty"]
    del site["thermodynamics"]["npp_relative_uncertainty"]
    normalized = normalize_site_inputs(site)
    assert normalized["biodiversity"]["productivity"]["sigma_basis"] == "default"
    assert normalized["habitat"]["area_uncertainty_basis"] == "default"
    assert normalized["thermodynamics"]["npp_uncertainty_basis"] == "default"
    warnings = value_site(site)["warnings"]
    assert sum("declared default" in w for w in warnings) == 3


def test_every_quantity_states_formula_units_inputs_uncertainty(woodland_site):
    for name, q in value_site(woodland_site)["quantities"].items():
        assert set(q) >= {"value", "units", "formula", "inputs", "uncertainty", "status"}, name
        assert q["units"] and q["formula"] and q["uncertainty"]["basis"], name
        lo, hi = q["uncertainty"]["ci95"]
        assert lo <= q["value"] <= hi, name


@pytest.mark.parametrize("value", ["1e999999999", "1e-400", 10**400, "1e301", "-1e-301"])
def test_out_of_range_magnitudes_are_value_errors(woodland_site, value):
    site = clone(woodland_site)
    site["habitat"]["patches"][0]["area_ha"] = value
    with pytest.raises(SiteInputError):
        value_site(site)


def test_publish_flushes_subnormal_range_to_zero():
    from viridis_eco_funding._decimal import publish
    assert publish(Decimal("3E-313")) == 0
    assert publish(Decimal("1E-300")) == Decimal("1E-300")
    assert publish(Decimal("123.4567890123456")) == Decimal("123.456789012")


def test_cli_reports_arithmetic_errors_cleanly(tmp_path, capsys):
    from viridis_eco_funding.cli import main
    bad = tmp_path / "site.json"
    bad.write_text('{"site_id": "x", "habitat": {"patches": [{"id": "a", "area_ha": 1e999}]}}')
    assert main(["value", str(bad)]) == 2
    assert "error" in capsys.readouterr().err
