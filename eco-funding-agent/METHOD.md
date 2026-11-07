# Method: `vef-method/0.1.0`

This document gives every formula the code computes, with units, inputs, uncertainty propagation and sources. The code is the reference implementation: [`src/viridis_eco_funding`](src/viridis_eco_funding). Each formula below names the module that computes it. Changing any formula, constant or default changes results, and requires a new method version (`tests/test_docs_and_vocabulary.py::test_method_version_pin`).

Status labels used in every output:

| Status | Meaning |
| --- | --- |
| `published method` | Taken from a published or submitted method (D-Score, rarefaction, ECA). |
| `v0.1 method convention` | A choice made for this package, documented and parameterized, and not yet validated (soil index, soil weight, K). |
| `input` | A value supplied by the caller. |
| `conjecture` | Derived from the intelligence bound. |

## 1. Data richness

### 1.1 D-Score (`dscore.py`)

    D = 0.30 T + 0.25 P + 0.25 F + 0.20 S                       [dimensionless, 0-1]

- **T**: rarefaction-corrected taxonomic richness from citizen-science counts.
- **P**: productivity (peak-season NDVI).
- **F**: functional and structural diversity (canopy height and structure).
- **S**: spectral diversity.

Each component is normalized to [0, 1] against a tropical-forest reference maximum. The weights and the definition come from Hart's D-Score manuscript [1], which was validated on 10 NEON sites in 8 biomes. Spearman rho was 0.867 against canopy height, 0.855 against LAI, and 0.770 against rarefied richness. Site rankings did not change for any rarefaction exponent z in [0.20, 0.40].

**T from raw counts.** The manuscript's power-law rarefaction [1, Zenodo deposit `rarefaction_model.py`] is S_rare = c N_ref^z, with c = S_obs / N_obs^z. Normalizing against the tropical reference S_trop_rare = c_trop N_ref^z (c_trop calibrated to 5 500 species at 100 000 observations), the reference effort N_ref cancels:

    T = min(1, (S_obs / 5500) * (100000 / N_obs)^z),   z = 0.30

`tests/test_dscore_golden.py` reproduces the published T values for all ten Run 7 sites to three decimals. It also reproduces every composite D in Table 2 to within half a unit in the last published digit.

**P, F, S** are accepted as normalized values with a stated source. The manuscript's reference maxima for these are specific to each data product, so the package does not invent them.

**Uncertainty.** Components are treated as independent:

    sigma_D = sqrt( sum_i (w_i sigma_i)^2 )

For T computed from counts, sigma_T combines two terms in quadrature. The first treats the plausible z range [0.20, 0.40] as a 95 % interval: |T(0.40) - T(0.20)| / (2 x 1.96). The second is a sampling term, 0.5 / sqrt(S_obs), carried over from the original `dscore` package. A component supplied without a sigma gets the declared default of 0.05, and the output flags it (`sigma_basis: "default"` plus a warning).

### 1.2 Soil index (`soil.py`), v0.1 convention

GSIP soil properties [6] are given in GSIP canonical units (SoilGrids 2.0 basis [11]). Each is mapped to [0, 1] by a piecewise-linear response, and G is the unweighted mean of the indicators supplied:

| Indicator | Response |
| --- | --- |
| SOC (g/kg) | linear 0 -> 1 over 0-40 g/kg |
| pH | 0 at <= 4.0, rising to 1 over 4.0-6.0, 1 over 6.0-7.5, falling to 0 at 9.0 |
| bulk density (kg/dm^3) | 1 at <= 1.30, falling to 0 at 1.80 |
| CEC (cmol(+)/kg) | linear 0 -> 1 over 0-25 |
| total N (g/kg) | linear 0 -> 1 over 0-3 |

sigma_G is supplied, or defaults to 0.10.

### 1.3 Data richness D* (`valuation.py`)

    D* = (1 - w_soil) D + w_soil G          (D* = D when no soil data is supplied)
    sigma_D* = sqrt( ((1 - w_soil) sigma_D)^2 + (w_soil sigma_G)^2 )

The default w_soil = 0.20 is a v0.1 choice. The rationale is that most terrestrial species diversity is estimated to live in soil (Anthony, Bender & van der Heijden 2023 [10]). Set `weights.soil = 0` to reproduce the published four-component D-Score exactly.

## 2. Verified habitat and connectivity (`connectivity.py`)

Only patches flagged `verified: true` are scored. A link counts only when both of its ends are verified. Unverified habitat is listed in the output and never scored.

**Patch attribute:** a_i = area_i x condition_i [ha], with condition in [0, 1] (default 1).

**Link probability** p_ij comes from one of three sources:
- an explicit probability in (0, 1];
- a gap distance d (m) passed through HDFM's movement kernel [5], p = exp(-alpha d / s), with alpha = 2 and s = 1000 m by default;
- `hdfm_linked: true`, a minimum-width corridor confirmed by the dfm-core corridor check, which gives p = 1.

**Best-path probability** p*_ij is the maximum, over all paths from i to j, of the product of link probabilities. p*_ii = 1. It is computed by max-product Dijkstra.

**Equivalent Connected Area** (Saura & Pascual-Hortal 2007 [7]; Saura et al. 2011 [8]):

    ECA = sqrt( sum_i sum_j a_i a_j p*_ij )                       [ha]
    A_v = sum of verified patch areas                             [ha]
    phi = min(1, ECA / A_v)                                       [connectivity fraction]

ECA <= sum a_i <= A_v. Uncertainty: the caller gives a relative area uncertainty u_A (default 0.05). It is treated as fully correlated across patches, so sigma_ECA = u_A x ECA. The ratio phi has no area uncertainty because it cancels. Uncertainty in the link probabilities is **not modeled** in v0.1 (see LIMITS.md).

## 3. Complexity score (headline)

    K = D* x ECA                         [complexity-ha: D-weighted equivalent connected hectares]
    sigma_K^2 = (ECA sigma_D*)^2 + (D* sigma_ECA)^2

K is a habitat-hectares analogue (Parkes, Newell & Cheal 2003 [9]): extent weighted by quality, extended here with connectivity. A 10-ha site of reference-quality habitat with every patch fully connected scores 10 x D*.

**Monotonicity (Invariant 2).** p*_ij is a maximum over paths, so adding a link or raising a link probability can only add paths or improve them. Adding a verified patch, enlarging a patch or improving its condition can only add non-negative terms. So ECA, and with it K at fixed D*, never falls. This also holds for the *computed* numbers. Decimal rounding is monotone, every partial sum with an added term is at least the corresponding partial sum without it, and the max-product Dijkstra finds the maximum over paths of products rounded in sequence.

## 4. Complexity-capacity term (`bound.py`): **conjecture**

### 4.1 The stated bound

Hart's intelligence bound [3] states that a system with power input P, environmental data richness D in [0, 1] and temperature T creates information at a rate

    dI/dt <= P D / (k_B T ln 2)                                    [bits/s]

The Physical Review E submission [2] states it as I_dot(tau) <= min(rho B, P / (k_B T ln 2)): a data-processing term plus a Landauer term, with a conditional Lean 4 formalization.

### 4.2 Footing used here

Landauer's principle [12] sets a minimum dissipation of k_B T ln 2 per bit **erased**. Reading the bound as a ceiling on the rate of **acquiring** information has been challenged, because acquisition can be thermodynamically reversible. Wolpert [13] extends Landauer's analysis to arbitrary computations (see also Bennett; Sagawa & Ueda). Following the corrected footing Viridis adopted in June 2026, this package reads the term on the **maintenance / erasure side**, where Landauer holds. It is the largest rate at which a site's photosynthetic free-energy flux could hold structured biological information against erasure, at the Landauer floor. Two things remain **conjecture** under either reading: identifying D with biodiversity (here D*), and applying the bound to ecosystems. Every output that uses this section carries the label.

### 4.3 Site mapping

    E_C   = 2.803e6 J/mol / (6 x 12.011 g/mol) ~= 3.889e4 J/gC   (glucose-equivalent photosynthate)
    P     = NPP x E_C x A_v x 1e4 / 31 557 600                     [W]      (NPP in gC m^-2 yr^-1)
    B     = P D* / (k_B T ln 2)                                    [bits/s] (stated bound)
    C     = min( B,  P phi D* / (k_B T ln 2),  rho B_obs )          [bits/s] (complexity capacity)
    W_eq  = C x k_B x 300 K x ln 2                                 [W]      (compute parity)

k_B = 1.380649e-23 J/K, exact in the 2019 SI. NPP is the caller's net primary productivity, and T is the site's mean temperature in K. The optional observation-channel term rho B_obs is the PRE paper's data-processing ceiling [2].

**Bound respected (Invariant 3).** phi <= 1, so the connectivity-limited term is at most B. The explicit `min` guarantees C <= B for computed numbers too, and a hard guard raises an error if that ever failed.

**Compute parity** restates C in watts. W_eq is the power at which a room-temperature computer running at the Landauer limit would have the same bit-rate ceiling as the site. It puts conservation and computation on one physical scale, in the spirit of [3]'s shared-budget argument. It is a change of units, not evidence for the conjecture.

**Uncertainty.** To first order, with the terms independent:

    (sigma_B / B)^2 = u_NPP^2 + u_A^2 + (sigma_D*/D*)^2 + (sigma_T/T)^2

The defaults are u_NPP = 0.20 and sigma_T = 1 K. C and W_eq carry the same relative uncertainty unless C is limited by the observation channel; channel parameters are treated as exact.

## 5. Receipts (`receipt.py`, `canonical.py`)

    inputs_sha256 = SHA-256( canonical(normalized inputs) )
    result_sha256 = SHA-256( canonical(result) )
    seal          = SHA-256( canonical({receipt_version, method_version, inputs_sha256, result_sha256, source}) )

Canonical JSON uses sorted keys, no whitespace, ASCII, NFC-normalized strings and normalized decimals, and it never contains binary floats. All arithmetic runs on Python `Decimal` at 40 significant digits, under one pinned context with half-even rounding. Every entry point pins that context, so the caller's own decimal settings cannot change a single byte. The correctly rounded `ln`, `exp` and `sqrt` mean results do not depend on the platform's math library.

Inputs are quantized to 15 significant digits, and any non-zero input must have a magnitude between 1e-300 and 1e300. Published values are rounded to 12 significant digits, and anything smaller than 1e-300 in magnitude is published as 0 (both steps are monotone). Together these keep every number inside the normal range of IEEE-754 doubles, so a receipt passed through plain JSON (for example via an MCP client) still verifies byte for byte. The receipt shape is exact: unknown top-level fields, an edited explanation, or any change to the seal's algorithm or kind fail verification. The seal is a content digest, **not an identity signature** (see LIMITS.md).

## 6. Pool simulation (`pool/`)

A pool has pledges (integer minor units of a label such as "USD") and rules. For pledge k and rule r at period t:

    effective_bps_r(t) = release_bps_r                    (milestone, once met: latched)
                       = release_bps_r x progress_r(t)    (outcome-linked; progress = clamp((v - baseline)/(target - baseline), 0, 1), ratchet)
    entitled_kr(t)     = floor( amount_k x effective_bps_r(t) / 10000 )   for pledges active at t
    release_kr(t)      = entitled_kr(t) - entitled_kr(t-1)  >= 0

sum_r release_bps_r <= 10 000. Every amount is an integer, and entitlements never decrease, so at every period released + remaining = pledged to date (Invariant 4). Nothing is released without a met rule, and the simulator checks both at runtime.

Every v0.1 metric is better when higher, so rules can only reward improvement. Milestone comparators are `>=` or `>`, and an outcome-linked target must exceed its baseline. A rule with `requires_receipt: true` needs the pool to declare `site_id` and a `calendar` (start date and period length in months). It counts a reading only when the receipt meets four conditions: it passes `verify_receipt`; it is for the pool's `site_id`; its `observed_at` date falls inside the observation's period; and it has not already been used in the pool. So a receipt cannot be counted for another site, replayed, or moved to a later period.

## References

1. Hart, J. D. (2026). *D-Score: a composite, open-data biodiversity index validated across a multi-biome gradient using NEON sites.* Manuscript MEE-26-04-332, submitted to *Methods in Ecology and Evolution*. Data and rarefaction code: https://doi.org/10.5281/zenodo.19543988 (CC BY 4.0).
2. Hart, J. D. (2026). *The Intelligence Bound: a formally verified thermodynamic limit on mutual information creation rate.* Submitted to *Physical Review E*, March 2026. Lean 4 formalization archived on Zenodo; it certifies the reasoning under its stated assumptions, not the empirical magnitudes.
3. Hart, J. D. *The Intelligence Bound: a universal thermodynamic limit on learning unifying artificial and biological systems.* Working paper, Viridis LLC.
4. Hart, J. D. (2026). *A thermodynamic speed limit on planetary restoration: machine-checked foundations from the second law to the intelligence bound.* https://doi.org/10.5281/zenodo.20479012. See also *Thermodynamic slack decomposition of the intelligence bound*, https://doi.org/10.5281/zenodo.20320324 (preprint).
5. Viridis LLC. *Dendritic Forest Management (HDFM) framework and dfm-core 0.3.0.* https://github.com/jdhart81/hdfm-framework (movement kernel: `hdfm/entropy.py`).
6. Global Soil Intelligence Project (GSIP). https://github.com/global-soil-intelligence/gsip (canonical soil units).
7. Saura, S. & Pascual-Hortal, L. (2007). A new habitat availability index to integrate connectivity in landscape conservation planning. *Landscape and Urban Planning* 83, 91-103.
8. Saura, S., Estreguil, C., Mouton, C. & Rodriguez-Freire, M. (2011). Network analysis to assess landscape connectivity trends: application to European forests (1990-2000). *Ecological Indicators* 11, 407-416.
9. Parkes, D., Newell, G. & Cheal, D. (2003). Assessing the quality of native vegetation: the 'habitat hectares' approach. *Ecological Management & Restoration* 4, S29-S38.
10. Anthony, M. A., Bender, S. F. & van der Heijden, M. G. A. (2023). Enumerating soil biodiversity. *PNAS* 120, e2304663120.
11. Poggio, L. et al. (2021). SoilGrids 2.0: producing soil information for the globe with quantified spatial uncertainty. *SOIL* 7, 217-240.
12. Landauer, R. (1961). Irreversibility and heat generation in the computing process. *IBM Journal of Research and Development* 5, 183-191.
13. Wolpert, D. H. (2019). The stochastic thermodynamics of computation. *Journal of Physics A* 52, 193001; and Wolpert, D. H. (2015), *Extending Landauer's bound from bit erasure to arbitrary computation*, arXiv:1508.05319.
