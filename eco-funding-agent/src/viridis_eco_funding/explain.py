"""Human- and agent-readable explanations of a valuation and of the method."""

from __future__ import annotations

from typing import Any

from ._decimal import pinned
from .canonical import to_canonical_data
from .constants import (
    CONJECTURE_LABEL,
    DEFAULT_AREA_RELATIVE_UNCERTAINTY,
    DEFAULT_COMPONENT_SIGMA,
    DEFAULT_NPP_RELATIVE_UNCERTAINTY,
    DEFAULT_SOIL_SIGMA,
    DEFAULT_SOIL_WEIGHT,
    DEFAULT_TEMPERATURE_SIGMA_K,
    DSCORE_WEIGHTS,
    HDFM_KERNEL_ALPHA,
    HDFM_KERNEL_SCALE_M,
    METHOD_VERSION,
    POOL_SCHEMA,
    RAREFACTION_REFERENCE_OBSERVATIONS,
    RAREFACTION_REFERENCE_SPECIES,
    RAREFACTION_Z,
    RAREFACTION_Z_RANGE,
    RECEIPT_VERSION,
    SITE_SCHEMA,
)
from .valuation import value_site

ORDER = [
    "component_T", "component_P", "component_F", "component_S", "d_score", "soil_index",
    "data_richness", "verified_area_ha", "eca_ha", "connectivity_fraction", "complexity_score",
    "npp_power_w", "stated_bound_bits_per_s", "complexity_capacity_bits_per_s",
    "bound_utilization", "compute_parity_w_at_300k",
]

LIMITS_SUMMARY = [
    "Not a price, market value or financial forecast; an ecological complexity measure.",
    "The D-Score was validated on 10 NEON sites (rank correlations 0.77-0.87); weights are a "
    "published choice, not estimated per site.",
    "ECA measures structural connectivity of verified habitat; it does not show that species "
    "actually move or exchange genes.",
    "The soil index and its 0.20 weight are v0.1 conventions, not calibrated soil-health science.",
    "The intelligence-bound term is a conjecture. Its acquisition (learning-rate) reading has been "
    "challenged; this package uses the maintenance/erasure reading. Values are ceilings many orders "
    "of magnitude above any measured biological information flow.",
    "A receipt proves the calculation can be reproduced from its inputs, not that the inputs are "
    "true. 'verified' habitat flags are only as good as their evidence.",
]


@pinned
def explain_valuation(valuation_or_inputs: Any) -> dict[str, Any]:
    """Explain a valuation result step by step. Accepts a valuation or raw site inputs."""
    data = valuation_or_inputs
    if not (isinstance(data, dict) and "quantities" in data and "method_version" in data):
        data = value_site(data)
    data = to_canonical_data(data)
    steps = []
    for name in ORDER:
        quantity = data["quantities"].get(name)
        if quantity is None:
            continue
        steps.append({
            "quantity": name,
            "formula": quantity["formula"],
            "inputs": quantity["inputs"],
            "value": quantity["value"],
            "units": quantity["units"],
            "uncertainty": quantity["uncertainty"],
            "status": quantity["status"],
            "notes": quantity["notes"],
        })
    # Decide the label from the content itself: a caller-supplied valuation may have had its
    # flag or explanation edited, but any conjecture-status quantity still triggers the label.
    uses_bound = bool(data.get("uses_intelligence_bound")) or any(
        isinstance(q, dict) and q.get("status") == CONJECTURE_LABEL
        for q in data["quantities"].values())
    explanation = str(data.get("explanation", ""))
    if uses_bound and CONJECTURE_LABEL not in explanation:
        explanation += (" The complexity-capacity quantities derive from the intelligence bound, "
                        "which is a conjecture.")
    return {
        "method_version": data["method_version"],
        "site_id": data["site_id"],
        "uses_intelligence_bound": uses_bound,
        "labels": {"intelligence_bound": CONJECTURE_LABEL if uses_bound else "not used"},
        "explanation": explanation,
        "steps": steps,
        "warnings": data.get("warnings", []),
        "limits": LIMITS_SUMMARY,
    }


@pinned
def describe_method() -> dict[str, Any]:
    """Static description of the method, constants, defaults, invariants and citations."""
    return to_canonical_data({
        "method_version": METHOD_VERSION,
        "schemas": {"site": SITE_SCHEMA, "receipt": RECEIPT_VERSION, "pool": POOL_SCHEMA},
        "explanation": (
            "viridis-eco-funding values a site's ecological complexity as K = D* x ECA "
            "(complexity-hectares): data richness D* (the published D-Score, optionally blended "
            "with a GSIP soil index) times the equivalent connected area of verified habitat "
            "(Saura et al. 2011, links from HDFM). An optional complexity-capacity term applies "
            "the intelligence bound dI/dt <= P D / (k_B T ln 2) to the site's photosynthetic "
            "power. The intelligence bound is a conjecture and every output that uses it says so. "
            "Outputs are reproducible receipts and pool simulations; no money is held, moved or "
            "released by this software."),
        "formulas": {
            "taxonomic": "T = min(1, (S_obs / S_ref) * (N_ref / N_obs)^z)",
            "d_score": "D = 0.30 T + 0.25 P + 0.25 F + 0.20 S",
            "soil_index": "G = mean of GSIP indicator scores",
            "data_richness": "D* = (1 - w_soil) D + w_soil G   (D* = D without soil data)",
            "link_probability": "p = exp(-alpha d / s) | supplied p | 1 for an HDFM-linked corridor",
            "eca": "ECA = sqrt(sum_i sum_j a_i a_j p*_ij)",
            "complexity_score": "K = D* x ECA   [complexity-ha]",
            "npp_power": "P = NPP x E_C x A_v / yr   [W]",
            "stated_bound": "B = P D* / (k_B T ln 2)   [bits/s]   (conjecture)",
            "complexity_capacity": "C = min(B, P (ECA / A_v) D* / (k_B T ln 2), rho B_obs)   (conjecture)",
            "compute_parity": "W_eq = C k_B (300 K) ln 2   [W]   (conjecture)",
        },
        "statuses": {
            "published method": "D-Score (MEE submission), rarefaction, ECA",
            "v0.1 method convention": "soil index, soil weight, K = D* x ECA",
            "input": "values supplied by the caller",
            CONJECTURE_LABEL: "anything derived from the intelligence bound",
        },
        "parameters": {
            "dscore_weights": dict(DSCORE_WEIGHTS),
            "rarefaction_z": RAREFACTION_Z,
            "rarefaction_z_range": list(RAREFACTION_Z_RANGE),
            "rarefaction_reference_species": RAREFACTION_REFERENCE_SPECIES,
            "rarefaction_reference_observations": RAREFACTION_REFERENCE_OBSERVATIONS,
            "hdfm_kernel_alpha": HDFM_KERNEL_ALPHA,
            "hdfm_kernel_scale_m": HDFM_KERNEL_SCALE_M,
            "boltzmann_J_per_K": "1.380649e-23 (exact)",
            "energy_per_gram_carbon_J": "2.803e6 / (6 x 12.011)",
        },
        "declared_defaults": {
            "component_sigma": DEFAULT_COMPONENT_SIGMA,
            "area_relative_uncertainty": DEFAULT_AREA_RELATIVE_UNCERTAINTY,
            "npp_relative_uncertainty": DEFAULT_NPP_RELATIVE_UNCERTAINTY,
            "temperature_sigma_K": DEFAULT_TEMPERATURE_SIGMA_K,
            "soil_sigma": DEFAULT_SOIL_SIGMA,
            "soil_weight": DEFAULT_SOIL_WEIGHT,
        },
        "invariants": [
            "I1 determinism: same inputs and method version give byte-identical results and receipts",
            "I2 monotonicity: more verified habitat or connectivity never lowers the complexity score",
            "I3 bound respected: complexity capacity never exceeds the stated bound",
            "I4 conservation: pool releases + remaining balance = total pledges; no release without a met milestone",
            "I5 no money movement: no payment SDKs, private keys, wallets or token minting",
            "I6 read-only externally: only public GET reads; nothing is written to any service",
            "I7 honest labels: outputs that use the intelligence bound say 'conjecture'",
        ],
        "citations": [
            "Hart, J. D. (2026). D-Score: a composite, open-data biodiversity index validated across a "
            "multi-biome gradient using NEON sites. Manuscript MEE-26-04-332, Methods in Ecology and "
            "Evolution (submitted). Data: https://doi.org/10.5281/zenodo.19543988",
            "Hart, J. D. (2026). The Intelligence Bound: a formally verified thermodynamic limit on "
            "mutual information creation rate. Submitted to Physical Review E. (Its Lean 4 "
            "formalization certifies the reasoning under its stated assumptions, not empirical "
            "magnitudes; applied to ecosystems the bound remains a conjecture.)",
            "Hart, J. D. The Intelligence Bound: a universal thermodynamic limit on learning unifying "
            "artificial and biological systems. Working paper, Viridis LLC.",
            "Hart, J. D. (2026). A thermodynamic speed limit on planetary restoration. "
            "https://doi.org/10.5281/zenodo.20479012",
            "Landauer, R. (1961). IBM J. Res. Dev. 5, 183-191.",
            "Wolpert, D. H. (2019). The stochastic thermodynamics of computation. J. Phys. A 52, 193001.",
            "Saura, S. & Pascual-Hortal, L. (2007). Landscape and Urban Planning 83, 91-103.",
            "Saura, S. et al. (2011). Ecological Indicators 11, 407-416.",
            "Parkes, D., Newell, G. & Cheal, D. (2003). Ecol. Manag. Restor. 4, S29-S38.",
            "Anthony, M. A., Bender, S. F. & van der Heijden, M. G. A. (2023). PNAS 120, e2304663120.",
            "Poggio, L. et al. (2021). SoilGrids 2.0. SOIL 7, 217-240.",
        ],
        "limits": LIMITS_SUMMARY,
    })
