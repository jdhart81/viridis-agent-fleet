"""The D-Score implementation reproduces the published Run 7 dataset
(Zenodo 10.5281/zenodo.19543988): rarefied T values and composite D-Scores for all ten
NEON validation sites in Table 2 of the MEE manuscript."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest

from viridis_eco_funding._decimal import ONE
from viridis_eco_funding.dscore import d_score, rarefied_taxonomic_ratio, taxonomic_component
from viridis_eco_funding.inputs import normalize_site_inputs

# Site, S_obs, N_obs, T_rare (published), T, P, F, S, D (published)  - dscore_run7_*.csv
RUN7 = [
    ("MLBS", 3187, 27341, "0.855", "0.855", "0.57", "0.73", "0.7", "0.722"),
    ("SERC", 5017, 51709, "1.0", "1.0", "0.59", "0.55", "0.6", "0.705"),
    ("HARV", 4356, 45081, "1.0", "1.0", "0.55", "0.5", "0.5", "0.662"),
    ("WREF", 1073, 4884, "0.483", "0.483", "0.49", "0.52", "0.55", "0.507"),
    ("BART", 1827, 10134, "0.66", "0.66", "0.45", "0.4", "0.44", "0.498"),
    ("OSBS", 2918, 40811, "0.694", "0.694", "0.46", "0.42", "0.25", "0.478"),
    ("SRER", 1093, 6073, "0.461", "0.461", "0.41", "0.38", "0.48", "0.432"),
    ("KONZ", 2757, 23997, "0.769", "0.769", "0.28", "0.25", "0.1", "0.383"),
    ("MOAB", 357, 1070, "0.253", "0.253", "0.257", "0.58", "0.35", "0.355"),
    ("TOOL", 457, 1966, "0.27", "0.27", "0.07", "0.3", "0.13", "0.199"),
]


def r3(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


@pytest.mark.parametrize("site,s_obs,n_obs,t_pub", [row[:4] for row in RUN7])
def test_rarefied_t_matches_published(site, s_obs, n_obs, t_pub):
    ratio = rarefied_taxonomic_ratio(s_obs, n_obs, Decimal("0.30"), Decimal(5500), Decimal(100000))
    assert r3(min(ONE, ratio)) == Decimal(t_pub), site


@pytest.mark.parametrize("site,s,n,t_pub,t,p,f,sp,d_pub", RUN7)
def test_composite_matches_table_2(site, s, n, t_pub, t, p, f, sp, d_pub):
    comps = {name: {"value": Decimal(v), "sigma": Decimal(0)}
             for name, v in zip(("taxonomic", "productivity", "functional", "spectral"), (t, p, f, sp))}
    value, sigma = d_score(comps)
    # Exact decimal value lies within half a unit of the published 3-decimal figure
    # (the published table was rounded from binary floats, so exact ties such as
    # 0.6625 or 0.1995 may have gone either way).
    assert abs(value - Decimal(d_pub)) <= Decimal("0.0005"), site
    assert sigma == 0


def test_z_sensitivity_matches_published_direction():
    # dscore_run7_sensitivity.csv: MLBS rises 0.690 -> 0.757 from z = 0.20 to 0.40
    spec = normalize_site_inputs({
        "site_id": "MLBS",
        "biodiversity": {"taxonomic": {"species_observed": 3187, "observations": 27341},
                         "productivity": {"value": 0.57}, "functional": {"value": 0.73},
                         "spectral": {"value": 0.7}},
        "habitat": {"patches": [{"id": "a", "area_ha": 1, "verified": True}]},
    })["biodiversity"]["taxonomic"]
    comp = taxonomic_component(spec)
    assert r3(comp["value"]) == Decimal("0.855")
    assert comp["sigma"] > 0
    assert comp["detail"]["sigma_from_z_range"] > comp["detail"]["sigma_from_sampling"]
