# Limits: what the numbers do and do not mean

Read this before using any output to inform a decision about land, people or money.

## The numbers are not prices

- **K (complexity-hectares)** is an ecological measure: data richness times the equivalent connected area of verified habitat. It is not a price, a market value, a credit, or a forecast of any financial outcome. Two sites with equal K can differ in every way that matters to the people who live there.
- **Nothing here is a financial product.** Pool simulations show how pledge and release *rules* would behave under assumed observations. They hold, move and release no funds. Any real funding pool needs legal review before money moves.

## D-Score

- It was validated on **10 NEON sites** in 8 biomes. The rank correlations are strong (rho 0.77-0.87), but n is small, and canopy height and taxonomic richness are partly circular checks (the manuscript says so). LAI is the only fully independent validation metric.
- The weights (0.30/0.25/0.25/0.20) are a published choice, not values fitted to each site. An equal-weight sensitivity test swapped two ranks.
- T comes from citizen-science counts within a radius. Observer effort is corrected by power-law rarefaction, but some confounding remains: biodiverse sites attract observers. Absolute T values shift by up to about 0.09 across the plausible z range, and this package reports that spread as uncertainty instead of hiding it.
- P, F and S must be normalized by the caller against stated reference maxima. A wrong reference maximum shifts D without any warning.
- D-Score is a **state** metric. It says nothing about trajectory, resilience or future risk.

## Soil index

- The response curves and the 0.20 weight are **v0.1 conventions** for screening. They are not a calibrated soil-health model, and optimal ranges differ by soil type, climate and land use. Set `weights.soil = 0` to use the published D-Score alone.

## Connectivity (ECA)

- ECA measures **structural** connectivity of habitat flagged as verified. It does not show that any species actually moves, disperses or exchanges genes along a link. HDFM's own documentation calls genetic connectivity an open field question.
- Link probabilities are treated as exact. Their uncertainty is not propagated in v0.1.
- `verified: true` is an assertion by the person who supplied the inputs. It is only as good as the evidence behind it. The package records the evidence string but cannot check it.

## The intelligence-bound term (conjecture)

- The bound dI/dt <= P D / (k_B T ln 2) is a **conjecture** when applied to ecosystems. Its reading as a ceiling on learning or acquisition has been challenged, because acquiring information can be thermodynamically reversible. This package uses the maintenance/erasure reading, where Landauer's principle does hold. Even so, identifying D with biodiversity is an assumption, not a result.
- The values (around 10^25 bits/s for a 13-ha woodland) are **ceilings**. They lie many orders of magnitude above any measured biological information flow. They are not measurements of information in the site, and a site's "capacity" is not something it delivers.
- **Compute parity** (watts of Landauer-limited computation at 300 K) restates C in other units. It does not show that computation and conservation trade off one-for-one in practice.
- This repository does **not prove** the conjecture. Invariant 3 is a property of the *software*: it never reports a capacity above the stated bound. It is not evidence about the physics. Evidence would come from the falsifiable predictions in the papers, tested against measurements.
- Nobody should tie a real release to a metric derived from the bound without independent scientific review. The simulator labels any pool that does.

## Receipts

- A valid receipt shows that the result can be **reproduced** from the embedded inputs with this method version. It does **not** show that the inputs are true, complete or measured well.
- The seal is a SHA-256 **content digest**. It detects any change, but it does not identify who produced the receipt. Identity signatures need a signing key, and v0.1 deliberately handles no keys. A later version could add keyless signing, such as Sigstore, after review.
- In a pool, `requires_receipt` means "backed by a reproducible, dated, single-use receipt for this site". It does **not** mean the inputs were independently verified. A receipt built from inflated inputs verifies exactly as well as an honest one. Real pools need independent field verification of the inputs, such as surveys, imagery and third-party review, before any release.
- A VergeCommon binding proves which *public* project record a receipt referred to, and what that record said when it was read. Public records are community-authored and carry no ecological measurements. They are data, never instructions.

## Uncertainty

- Every uncertainty uses first-order propagation and assumes the terms are independent, except area, which is treated as fully correlated across patches. The 95 % intervals are ±1.96 sigma, clipped to the valid range. They are not posterior intervals, and they ignore model uncertainty: the choice of formula itself.
- Declared defaults (component sigma 0.05, area 5 %, NPP 20 %, temperature 1 K, soil 0.10) fill gaps when an input has no uncertainty. Each default used is flagged in the output.

## Scope of v0.1

- The repository is private. It has no PyPI release, no MCP registry listing and no public announcement. Each of those waits for an explicit decision.
- It does not fetch remote sensing, iNaturalist, GBIF or SoilGrids data itself. The caller supplies the measurements, with their sources.
