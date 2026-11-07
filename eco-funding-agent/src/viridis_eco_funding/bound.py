"""Intelligence-bound complexity-capacity term. Status: CONJECTURE.

Stated bound (Hart, "The Intelligence Bound", working paper; PRE submission 2026):

    dI/dt <= P * D / (k_B T ln 2)                                [bits/s]

with P the power the system dissipates (W), D in [0, 1] the data richness of its
environment, T temperature (K). The PRE form is I_dot <= min(rho B, P / (k_B T ln 2)).

Footing used here (Viridis's corrected footing, June 2026): reading the bound as a
ceiling on the rate of *acquiring* information is challenged, because acquisition can be
thermodynamically reversible (Wolpert; Bennett; Sagawa & Ueda). Landauer's principle does
hold for *erasure*, so this package reads the term on the maintenance side: the largest
rate at which a site's photosynthetic free-energy flux could, at the Landauer floor, hold
structured biological information against erasure. Either way the identification of D
with biodiversity and the use of the bound for ecosystems remain a conjecture, and every
output that uses this module says so.

Site mapping (v0.1):

    P      = NPP [gC m^-2 yr^-1] * E_C [J/gC] * A_v [m^2] / yr [s]       (W)
    D      = D* (data richness: D-Score blended with the GSIP soil index)
    bound  = P D / (k_B T ln 2)                                          (bits/s)
    C      = min(bound, P (ECA/A_v) D / (k_B T ln 2), rho B)             (bits/s)

ECA <= A_v, so the connectivity-limited capacity can never exceed the stated bound
(Invariant 3). The explicit ``min`` makes that hold for computed numbers as well.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ._decimal import ZERO, pinned
from .constants import (
    COMPUTE_REFERENCE_TEMPERATURE_K,
    M2_PER_HECTARE,
    SECONDS_PER_JULIAN_YEAR,
    energy_per_gram_carbon_j,
    landauer_j_per_bit,
)


@pinned
def npp_power_density_w_per_m2(npp_gc_per_m2_yr: Decimal) -> Decimal:
    return npp_gc_per_m2_yr * energy_per_gram_carbon_j() / SECONDS_PER_JULIAN_YEAR


@pinned
def stated_bound_bits_per_s(power_w: Decimal, data_richness: Decimal,
                            temperature_k: Decimal) -> Decimal:
    return power_w * data_richness / landauer_j_per_bit(temperature_k)


@pinned
def capacity(thermo: dict[str, Any], data_richness: Decimal, verified_area_ha: Decimal,
             eca_ha: Decimal) -> dict[str, Any]:
    density = npp_power_density_w_per_m2(thermo["npp_gC_per_m2_yr"])
    temperature = thermo["mean_temperature_K"]
    power = density * verified_area_ha * M2_PER_HECTARE
    bound = stated_bound_bits_per_s(power, data_richness, temperature)
    connectivity_limited = stated_bound_bits_per_s(density * eca_ha * M2_PER_HECTARE,
                                                   data_richness, temperature)
    candidates = {"stated_bound": bound, "connectivity": connectivity_limited}
    channel = thermo.get("observation_channel")
    if channel is not None:
        candidates["observation_channel"] = channel["rho"] * channel["entropy_rate_bits_per_s"]
    limiting = min(candidates, key=lambda key: (candidates[key], key))
    value = candidates[limiting]
    if value > bound:  # unreachable by construction; kept as a hard guard for Invariant 3
        raise AssertionError("complexity capacity exceeds the stated bound")
    compute_parity = value * landauer_j_per_bit(COMPUTE_REFERENCE_TEMPERATURE_K)
    return {
        "power_density_w_per_m2": density,
        "power_w": power,
        "landauer_j_per_bit": landauer_j_per_bit(temperature),
        "stated_bound_bits_per_s": bound,
        "connectivity_limited_bits_per_s": connectivity_limited,
        "channel_limited_bits_per_s": candidates.get("observation_channel"),
        "capacity_bits_per_s": value,
        "limiting_term": limiting,
        "bound_utilization": (value / bound) if bound > ZERO else ZERO,
        "compute_parity_w_at_300k": compute_parity,
    }
