"""Invariant 2 - Monotonicity: adding verified habitat or connectivity never lowers the
complexity score, all else equal. Checked on the computed (rounded) outputs over
thousands of seeded random sites, for every kind of habitat/connectivity addition."""

from __future__ import annotations

from decimal import Decimal

import pytest
from conftest import clone, random_site

from viridis_eco_funding import value_site


def k(site) -> Decimal:
    return value_site(site)["quantities"]["complexity_score"]["value"]


def eca(site) -> Decimal:
    return value_site(site)["quantities"]["eca_ha"]["value"]


def capacity(site) -> Decimal:
    q = value_site(site)["quantities"]
    return q["complexity_capacity_bits_per_s"]["value"]


def _mutations(rng, site):
    """Yield (name, mutated_site) pairs, each adding habitat or connectivity only."""
    patches = site["habitat"]["patches"]
    links = site["habitat"]["links"]
    ids = [p["id"] for p in patches]

    m = clone(site)
    m["habitat"]["patches"].append({"id": "zz-new", "area_ha": round(rng.uniform(0.05, 40), 2),
                                    "verified": True, "condition": round(rng.uniform(0, 1), 2)})
    if rng.random() < 0.7 and ids:
        m["habitat"]["links"].append({"from": "zz-new", "to": rng.choice(ids),
                                      "probability": round(rng.uniform(0.01, 1), 3)})
    yield "add verified patch", m

    i = rng.randrange(len(patches))
    m = clone(site)
    m["habitat"]["patches"][i]["area_ha"] = round(patches[i]["area_ha"] + rng.uniform(0.01, 20), 2)
    yield "enlarge patch", m

    m = clone(site)
    m["habitat"]["patches"][i]["condition"] = min(1.0, round(patches[i]["condition"] + rng.uniform(0, 0.5), 2))
    yield "improve condition", m

    unverified = [n for n, p in enumerate(patches) if not p["verified"]]
    if unverified:
        m = clone(site)
        m["habitat"]["patches"][rng.choice(unverified)]["verified"] = True
        yield "verify existing patch", m

    linked = {tuple(sorted((link["from"], link["to"]))) for link in links}
    free = [(a, b) for x, a in enumerate(ids) for b in ids[x + 1:] if (a, b) not in linked]
    if free:
        a, b = rng.choice(free)
        for mode in ("probability", "distance_m", "hdfm_linked"):
            m = clone(site)
            link = {"from": a, "to": b}
            link[mode] = {"probability": round(rng.uniform(0.01, 1), 3),
                          "distance_m": round(rng.uniform(0, 3000), 1),
                          "hdfm_linked": True}[mode]
            m["habitat"]["links"].append(link)
            yield f"add {mode} link", m

    if links:
        j = rng.randrange(len(links))
        m = clone(site)
        link = m["habitat"]["links"][j]
        if "probability" in link:
            link["probability"] = min(1.0, round(link["probability"] + rng.uniform(0, 0.5), 3))
            yield "raise link probability", m
        elif "distance_m" in link:
            link["distance_m"] = round(link["distance_m"] * rng.uniform(0, 1), 1)
            yield "shorten gap distance", m
        else:
            yield "unchanged hdfm link", m


def test_additions_never_lower_score(rng):
    checked = 0
    for _ in range(400):
        site = random_site(rng, channel=False)
        base_k, base_eca, base_cap = k(site), eca(site), capacity(site)
        for name, mutated in _mutations(rng, site):
            assert k(mutated) >= base_k, name
            assert eca(mutated) >= base_eca, name
            # capacity is C = P (ECA/A_v) D*/(k_B T ln2): also monotone without a channel cap
            assert capacity(mutated) >= base_cap, name
            checked += 1
    assert checked > 2000


def test_unverified_habitat_changes_nothing(rng):
    for _ in range(200):
        site = random_site(rng)
        base = value_site(site)["quantities"]["complexity_score"]["value"]
        m = clone(site)
        m["habitat"]["patches"].append({"id": "zz-unverified", "area_ha": 99.0, "verified": False})
        m["habitat"]["links"].append({"from": "zz-unverified", "to": site["habitat"]["patches"][0]["id"],
                                      "hdfm_linked": True})
        assert value_site(m)["quantities"]["complexity_score"]["value"] == base


@pytest.mark.parametrize("area", ["0.01", "1", "123.45", "9999999"])
def test_single_patch_eca_equals_area_times_condition(woodland_site, area):
    site = clone(woodland_site)
    site["habitat"] = {"patches": [{"id": "only", "area_ha": area, "verified": True,
                                    "condition": "0.5"}]}
    assert eca(site) == Decimal(area) * Decimal("0.5")
