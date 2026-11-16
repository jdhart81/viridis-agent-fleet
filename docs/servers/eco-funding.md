# io.github.jdhart81/eco-funding

[![mcptry](https://mcptry.com/badge/io.github.jdhart81/eco-funding)](https://mcptry.com/servers/io.github.jdhart81/eco-funding)

Ecological complexity valuation for agents and people: D-Score x equivalent connected area of verified habitat (HDFM links, GSIP soil) -> sealed, re-runnable receipts, plus pledge-pool simulation with milestone and outcome-linked release rules. Read-only; no money movement; the intelligence-bound capacity term is labelled conjecture.

| | |
|---|---|
| Registry name | `io.github.jdhart81/eco-funding` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/eco-funding/mcp` |
| Version | 0.1.1 |
| Tools | 5 |
| Source | [`eco-funding-agent/`](../../eco-funding-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-eco-funding": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/eco-funding/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-eco-funding https://mcp.viridisconservation.com/eco-funding/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `value_site`

Value a site's ecological complexity (schema vef-site/0.1: D-Score components, habitat patches and links, optional GSIP soil indicators, optional NPP and temperature). Produces a sealed, reproducible receipt in which …

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `bind_vergecommon` | boolean | no | Optional. Bind the receipt to the site's VergeCommon public record. |
| `site` | object | yes | The site description, schema vef-site/0.1 (see describe_method for the fields). |

### `explain_valuation`

Explain a valuation step by step: each quantity's formula, inputs, value, units, uncertainty and status (published method, v0.1 convention, input, or conjecture), plus limits. Accepts a valuation (receipt.result) or raw …

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `valuation_or_site` | object | yes | A valuation (receipt.result from value_site) or raw site inputs. |

### `verify_receipt`

Re-run a valuation receipt offline and check its input, result and seal digests; valid only if reproduced byte for byte. refetch_source=true also reads the bound VergeCommon public record (GET only). Shows …

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `receipt` | object | yes | A value_site receipt, unchanged. |
| `refetch_source` | boolean | no | Optional. Also re-read the bound VergeCommon record (read only). |

### `simulate_pool`

Simulate a pledge pool (schema vef-pool/0.1) under milestone and outcome-linked release rules, given dated receipts or hypothetical readings per period. Integer accounting: releases + remaining = pledges; nothing …

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `observations` | array | no | Optional. Dated receipts or hypothetical readings per period. |
| `pool` | object | yes | The pledge pool definition, schema vef-pool/0.1. |

### `describe_method`

Describe the method: formulas, constants, declared defaults, statuses, the seven invariants, citations and limits. Call first. Free rail.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-15):

```json
{
  "name": "describe_method",
  "arguments": {}
}
```

Response (shortened):

```json
{
  "status": "ok",
  "action": "describe_method",
  "agent": "viridis-eco-funding",
  "result": {
    "citations": [
      "Hart, J. D. (2026). D-Score: a composite, open-data biodiversity index validated across a multi-biome gradient using NEON sites. Manuscript MEE-26-04-332, Methods in Ecology and Evolution (submitted). Data: https://doi.org/10.5281/zenodo.19543988",
      "Hart, J. D. (2026). The Intelligence Bound: a formally verified thermodynamic limit on mutual information creation rate. Submitted to Physical Review E. (Its Lean 4 formalization certifies the reasoning under its stated assumptions, not empirical magnitudes; applied to ecosystems the bound remains a conjecture.)",
      "Hart, J. D. The Intelligence Bound: a universal thermodynamic limit on learning unifying artificial and biological systems. Working paper, Viridis LLC.",
      "Hart, J. D. (2026). A thermodynamic speed limit on planetary restoration. https://doi.org/10.5281/zenodo.20479012",
      "Landauer, R. (1961). IBM J. Res. Dev. 5, 183-191.",
      "Wolpert, D. H. (2019). The stochastic thermodynamics of computation. J. Phys. A 52, 193001.",
      "Saura, S. & Pascual-Hortal, L. (2007). Landscape and Urban Planning 83, 91-103.",
      "Saura, S. et al. (2011). Ecological Indicators 11, 407-416.",
      "Parkes, D., Newell, G. & Cheal, D. (2003). Ecol. Manag. Restor. 4, S29-S38.",
      "Anthony, M. A., Bender, S. F. & van der Heijden, M. G. A. (2023). PNAS 120, e2304663120.",
      "Poggio, L. et al. (2021). SoilGrids 2.0. SOIL 7, 217-240."
    ],
    "declared_defaults": {
      "area_relative_uncertainty": 0.05,
      "component_sigma": 0.05,
      "npp_relative_uncertainty": 0.2,
      "soil_sigma": 0.1,
      "soil_weight": 0.2,
      "temperature_sigma_K": 1
    },
    "explanation": "viridis-eco-funding values a site's ecological complexity as K = D* x ECA (complexity-hectares): data richness D* (the published D-Score, optionally blended with a GSIP soil index) times the equivalent connected area of verified habitat (Saura et al. 2011, links from HDFM). An optional complexity-capacity term applies the intelligence bound dI/dt <= P D / (k_B T ln 2) to the site's photosynthetic power. The intelligence bound is a conjecture and every output that uses it says so. Outputs are reproducible receipts and pool simulations; no money is held, moved or released by this software.",
    "formulas": {
      "complexity_capacity": "C = min(B, P (ECA / A_v) D* / (k_B T ln 2), rho B_obs)   (conjecture)",
      "complexity_score": "K = D* x ECA   [complexity-ha]",
      "compute_parity": "W_eq = C k_B (300 K) ln 2   [W]   (conjecture)",
      "d_score": "D = 0.30 T + 0.25 P + 0.25 F + 0.20 S",
      "data_richness": "D* = (1 - w_soil) D + w_soil G   (D* = D without soil data)",
      "eca": "ECA = sqrt(sum_i sum_j a_i a_j p*_ij)",
      "link_probability": "p = exp(-alpha d / s) | supplied p | 1 for an HDFM-linked corridor",
      "npp_power": "P = NPP x E_C x A_v / yr   [W]",
      "soil_index": "G = mean of GSIP indicator scores",
      "stated_bound": "B = P D* / (k_B T ln 2)   [bits/s]   (conjecture)",
      "taxonomic": "T = min(1, (S_obs / S_ref) * (N_ref / N_obs)^z)"
    },
  …
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`eco-funding-agent/`](../../eco-funding-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
