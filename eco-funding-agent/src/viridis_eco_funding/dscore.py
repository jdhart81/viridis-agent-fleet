"""D-Score (Hart; MEE manuscript MEE-26-04-332; data: Zenodo 10.5281/zenodo.19543988).

    D = 0.30 T + 0.25 P + 0.25 F + 0.20 S

T is rarefaction-corrected taxonomic richness, P productivity (NDVI), F functional /
structural diversity (canopy height and structure) and S spectral diversity, each
normalized to [0, 1] against a tropical-forest reference maximum.

The taxonomic component can be computed here from raw citizen-science counts with the
manuscript's power-law rarefaction (reproduces Table 2 of the manuscript; see
tests/test_dscore_golden.py). P, F and S are accepted as normalized values, because the
manuscript's reference maxima for them are product-specific; their source must be given.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ._decimal import ONE, ZERO, pinned, power, sqrt
from .constants import DSCORE_WEIGHTS, SAMPLING_SIGMA_COEFFICIENT, Z_95


@pinned
def rarefied_taxonomic_ratio(species_observed: int, observations: int, z: Decimal,
                             reference_species: Decimal, reference_observations: Decimal) -> Decimal:
    """S_rare / S_trop_rare before clipping.

    S_rare = c N_ref^z with c = S_obs / N_obs^z, and S_trop_rare = c_trop N_ref^z with
    c_trop = S_ref / N_ref_trop^z. N_ref cancels, leaving
    (S_obs / S_ref) * (N_ref_trop / N_obs)^z.
    """
    return (Decimal(species_observed) / reference_species) * power(
        reference_observations / Decimal(observations), z)


@pinned
def taxonomic_component(spec: dict[str, Any]) -> dict[str, Any]:
    """Return {value, sigma, ...} for the T component from a normalized spec."""
    if spec["mode"] == "normalized":
        return {
            "value": spec["value"],
            "sigma": spec["sigma"],
            "sigma_basis": spec["sigma_basis"],
            "formula": "T supplied, normalized to [0, 1]",
            "source": spec["source"],
        }

    def t_at(z: Decimal) -> Decimal:
        ratio = rarefied_taxonomic_ratio(spec["species_observed"], spec["observations"], z,
                                         spec["reference_species"], spec["reference_observations"])
        return min(ONE, ratio)

    value = t_at(spec["z"])
    z_low, z_high = spec["z_range"]
    sigma_z = abs(t_at(z_high) - t_at(z_low)) / (2 * Z_95)
    sigma_sampling = SAMPLING_SIGMA_COEFFICIENT / sqrt(Decimal(spec["species_observed"]))
    sigma = min(ONE, sqrt(sigma_z * sigma_z + sigma_sampling * sigma_sampling))
    return {
        "value": value,
        "sigma": sigma,
        "sigma_basis": "rarefaction z-range treated as a 95% interval, combined in quadrature "
                       "with sampling term 0.5/sqrt(S_obs)",
        "formula": "T = min(1, (S_obs/S_ref) * (N_ref/N_obs)^z)",
        "source": spec["source"],
        "detail": {
            "species_observed": spec["species_observed"],
            "observations": spec["observations"],
            "z": spec["z"],
            "z_range": [z_low, z_high],
            "reference_species": spec["reference_species"],
            "reference_observations": spec["reference_observations"],
            "sigma_from_z_range": sigma_z,
            "sigma_from_sampling": sigma_sampling,
        },
    }


@pinned
def normalized_component(spec: dict[str, Any], label: str) -> dict[str, Any]:
    return {
        "value": spec["value"],
        "sigma": spec["sigma"],
        "sigma_basis": spec["sigma_basis"],
        "formula": f"{label} supplied, normalized to [0, 1]",
        "source": spec["source"],
    }


@pinned
def d_score(components: dict[str, dict[str, Any]]) -> tuple[Decimal, Decimal]:
    """Weighted sum and its standard uncertainty (components assumed independent)."""
    value = ZERO
    variance = ZERO
    for name, weight in DSCORE_WEIGHTS.items():
        comp = components[name]
        value += weight * comp["value"]
        variance += (weight * comp["sigma"]) ** 2
    return value, sqrt(variance)
