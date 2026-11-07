"""Invariant 3 - Bound respected: the complexity-capacity term never exceeds the stated
thermodynamic bound B = P D* / (k_B T ln 2) for the given inputs."""

from __future__ import annotations

from decimal import Decimal, localcontext

from conftest import clone, random_site

from viridis_eco_funding import value_site
from viridis_eco_funding._decimal import CONTEXT
from viridis_eco_funding.constants import BOLTZMANN_J_PER_K, M2_PER_HECTARE, ln2


def _independent_bound(result, site) -> Decimal:
    """Recompute B from published quantities with an independent formula path."""
    q = result["quantities"]
    with localcontext(CONTEXT):
        density = (Decimal(str(site["thermodynamics"]["npp_gC_per_m2_yr"]))
                   * Decimal(2_803_000) / (6 * Decimal("12.011")) / Decimal(31_557_600))
        power = density * q["verified_area_ha"]["value"] * M2_PER_HECTARE
        temp = Decimal(str(site["thermodynamics"]["mean_temperature_K"]))
        return power * q["data_richness"]["value"] / (BOLTZMANN_J_PER_K * temp * ln2())


def test_capacity_never_exceeds_bound_random(rng):
    for _ in range(1500):
        site = random_site(rng)
        result = value_site(site)
        q = result["quantities"]
        cap = q["complexity_capacity_bits_per_s"]["value"]
        bound = q["stated_bound_bits_per_s"]["value"]
        assert cap <= bound
        assert Decimal(0) <= q["bound_utilization"]["value"] <= Decimal(1)
        # bound itself never exceeds the D = 1 Landauer ceiling P / (k_B T ln 2)
        independent = _independent_bound(result, site)
        assert abs(bound - independent) <= abs(independent) * Decimal("1e-11")


def test_fully_connected_site_reaches_but_does_not_cross_bound(woodland_site):
    site = clone(woodland_site)
    for patch in site["habitat"]["patches"]:
        patch["verified"], patch["condition"] = True, 1.0
    ids = [p["id"] for p in site["habitat"]["patches"]]
    site["habitat"]["links"] = [{"from": a, "to": b, "hdfm_linked": True}
                                for i, a in enumerate(ids) for b in ids[i + 1:]]
    q = value_site(site)["quantities"]
    assert q["complexity_capacity_bits_per_s"]["value"] == q["stated_bound_bits_per_s"]["value"]
    assert q["bound_utilization"]["value"] == 1


def test_observation_channel_can_only_lower_capacity(rng):
    for _ in range(300):
        site = random_site(rng, channel=True)
        without = clone(site)
        del without["thermodynamics"]["observation_channel"]
        with_channel = value_site(site)["quantities"]
        plain = value_site(without)["quantities"]
        assert with_channel["complexity_capacity_bits_per_s"]["value"] <= \
            plain["complexity_capacity_bits_per_s"]["value"]
        assert with_channel["complexity_capacity_bits_per_s"]["value"] <= \
            with_channel["stated_bound_bits_per_s"]["value"]


def test_extreme_inputs(woodland_site):
    for npp, temp in [(0, 150), ("0.0001", 400), (5000, 150), (5000, 400)]:
        site = clone(woodland_site)
        site["thermodynamics"]["npp_gC_per_m2_yr"] = npp
        site["thermodynamics"]["mean_temperature_K"] = temp
        q = value_site(site)["quantities"]
        assert q["complexity_capacity_bits_per_s"]["value"] <= q["stated_bound_bits_per_s"]["value"]
