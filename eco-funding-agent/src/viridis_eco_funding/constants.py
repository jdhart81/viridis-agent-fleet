"""Physical constants, published method parameters and declared defaults.

Every constant carries its source. Changing any value here changes valuation results and
therefore requires a METHOD_VERSION bump (see tests/test_method_version.py).
"""

from __future__ import annotations

from decimal import Decimal

from ._decimal import pinned

METHOD_VERSION = "vef-method/0.1.0"
RECEIPT_VERSION = "vef-receipt/0.1"
SITE_SCHEMA = "vef-site/0.1"
POOL_SCHEMA = "vef-pool/0.1"

CONJECTURE_LABEL = "conjecture"

# --- Physical constants -------------------------------------------------------------
BOLTZMANN_J_PER_K = Decimal("1.380649E-23")
"""k_B, exact by definition in the 2019 SI redefinition (BIPM SI Brochure, 9th ed.)."""

SECONDS_PER_JULIAN_YEAR = Decimal(31_557_600)
"""365.25 d x 86 400 s (IAU Julian year)."""

GLUCOSE_COMBUSTION_J_PER_MOL = Decimal(2_803_000)
"""Standard enthalpy of combustion of solid alpha-D-glucose, approx. 2.803 MJ/mol
(NIST Chemistry WebBook). Used as the free energy stored per unit of photosynthate."""

CARBON_MOLAR_MASS_G_PER_MOL = Decimal("12.011")
"""IUPAC conventional atomic weight of carbon."""

CARBONS_PER_GLUCOSE = Decimal(6)

M2_PER_HECTARE = Decimal(10_000)

COMPUTE_REFERENCE_TEMPERATURE_K = Decimal(300)
"""Reference temperature for the compute-parity restatement (room-temperature hardware)."""

Z_95 = Decimal("1.96")
"""Two-sided 95 % normal quantile used for every reported interval."""


@pinned
def ln2() -> Decimal:
    return Decimal(2).ln()


@pinned
def energy_per_gram_carbon_j() -> Decimal:
    """Free energy per gram of fixed carbon, glucose-equivalent basis (~3.89e4 J/gC)."""
    return GLUCOSE_COMBUSTION_J_PER_MOL / (CARBONS_PER_GLUCOSE * CARBON_MOLAR_MASS_G_PER_MOL)


# --- D-Score (Hart, MEE manuscript MEE-26-04-332; Zenodo 10.5281/zenodo.19543988) ---------
DSCORE_WEIGHTS = {
    "taxonomic": Decimal("0.30"),
    "productivity": Decimal("0.25"),
    "functional": Decimal("0.25"),
    "spectral": Decimal("0.20"),
}
"""D = 0.30 T + 0.25 P + 0.25 F + 0.20 S, all components normalized to [0, 1]."""

RAREFACTION_Z = Decimal("0.30")
RAREFACTION_Z_RANGE = (Decimal("0.20"), Decimal("0.40"))
"""Default accumulation exponent and its ecologically plausible range (manuscript sec. 3.3)."""

RAREFACTION_REFERENCE_SPECIES = Decimal(5500)
RAREFACTION_REFERENCE_OBSERVATIONS = Decimal(100_000)
"""Tropical-forest calibration: 5 500 species at 100 000 observations
(rarefaction_model.py in the Zenodo deposit)."""

# --- HDFM movement kernel (jdhart81/hdfm-framework, hdfm/entropy.py) ---------------------
HDFM_KERNEL_ALPHA = Decimal(2)
HDFM_KERNEL_SCALE_M = Decimal(1000)
"""p_ij = exp(-alpha * d_ij / s): the dispersal kernel used by HDFM's movement entropy."""

# --- Declared defaults (used only when an input omits its own uncertainty) ---------------
DEFAULT_COMPONENT_SIGMA = Decimal("0.05")
DEFAULT_AREA_RELATIVE_UNCERTAINTY = Decimal("0.05")
DEFAULT_NPP_RELATIVE_UNCERTAINTY = Decimal("0.20")
DEFAULT_TEMPERATURE_SIGMA_K = Decimal("1.0")
DEFAULT_SOIL_SIGMA = Decimal("0.10")
DEFAULT_SOIL_WEIGHT = Decimal("0.20")
"""v0.1 method choice, not from the D-Score manuscript: belowground (GSIP) share of data
richness when soil indicators are supplied. Rationale: most described and estimated
species diversity lives in soil (Anthony, Bender & van der Heijden 2023, PNAS). Set
weights.soil = 0 to reproduce the published four-component D-Score exactly."""

SAMPLING_SIGMA_COEFFICIENT = Decimal("0.5")
"""sigma_sampling = 0.5 / sqrt(S_obs): sample-size heuristic carried over from the
original dscore package (species.py)."""


@pinned
def landauer_j_per_bit(temperature_k: Decimal) -> Decimal:
    """k_B T ln 2: minimum heat dissipated per bit erased (Landauer 1961)."""
    return BOLTZMANN_J_PER_K * temperature_k * ln2()
