# io.github.jdhart81/taxcredit-engine

[![mcptry](https://mcptry.com/badge/io.github.jdhart81/taxcredit-engine)](https://mcptry.com/servers/io.github.jdhart81/taxcredit-engine)

Deterministic auditable US clean-energy tax-credit scenario engine

| | |
|---|---|
| Registry name | `io.github.jdhart81/taxcredit-engine` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/taxcredit-engine/mcp` |
| Version | 0.1.1 |
| Tools | 5 |
| Source | [`taxcredit-engine-agent/`](../../taxcredit-engine-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-taxcredit-engine": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/taxcredit-engine/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-taxcredit-engine https://mcp.viridisconservation.com/taxcredit-engine/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `calculate_tax_credit`

Calculate an auditable tax-credit scenario. credit is 45Q, 45V, 45Y, 48E, or 45X. facts must contain the explicit credit-specific eligibility facts; missing facts return indeterminate. This is not tax or filing advice. …

*read-only; $2.00 per call after the free daily calls (x402 catalog); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `credit` | string | no | Which US clean-energy credit. One of: 45Q, 45V, 45X, 45Y, 48E. |
| `facts` | object | no | The facts for that credit, as an object (dates as YYYY-MM-DD, amounts as numbers or decimal strings, yes/no as true/false). get_rule_pack shows a credit's rules; a missing fact comes back as indeterminate with its name, and the example shows a full 48E request. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |

### `list_rule_packs`

List supported credits and the current bundled rule-pack digest.

*read-only; structured output*

No inputs.

### `get_rule_pack`

Return the bundled rules and official source metadata for one credit.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `credit` | string | yes | Credit id, for example 48E or 45Q; see list_rule_packs. |

### `verify_tax_credit_result`

Verify an engine result's audit_sha256. Pass the prior result object as JSON; any changed amount, fact, rule step, or source digest fails.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `result_json` | string | yes | The full calculate_tax_credit result, as a JSON string, unchanged. |

### `describe_agent`

Return fleet-standard capabilities, version, and pricing.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-16):

```json
{
  "name": "calculate_tax_credit",
  "arguments": {
    "credit": "48E",
    "facts": {
      "claimed_45y": false,
      "construction_begin_date": "2025-01-01",
      "domestic_content_met": true,
      "energy_community": true,
      "foreign_influenced_entity": false,
      "lifecycle_emissions_g_co2e_per_kwh": "0",
      "low_income_allocation_ratio_percent": "0",
      "low_income_allocation_received": false,
      "low_income_bonus_percentage_points": "0",
      "material_assistance_from_pfe": false,
      "nameplate_capacity_mw": "2",
      "placed_in_service_date": "2026-01-01",
      "produced_in_us": true,
      "pwa_met": true,
      "qualified_investment_usd": "1000000",
      "specified_foreign_entity": false,
      "tax_exempt_bond_financing_percent": "0",
      "tax_year": 2026,
      "tax_year_begin_date": "2026-01-01",
      "technology": "geothermal"
    }
  }
}
```

Response (shortened):

```json
{
  "status": "ok",
  "data": {
    "credit": "48E",
    "tax_year": 2026,
    "calculation_status": "eligible",
    "credit_amount_usd": "500000.00",
    "rate": {
      "percentage": "50",
      "rate_class": "increased",
      "low_income_effective_percentage_points": "0",
      "tax_exempt_bond_reduction_percent": "0"
    },
    "tier": "increased",
    "eligibility_flags": [
      {
        "id": "48E-US",
        "status": "pass",
        "detail": "facility/production is in US"
      },
      {
        "id": "48E-EMISSIONS",
        "status": "pass",
        "detail": "greenhouse-gas emissions rate must be no greater than zero"
      },
      {
        "id": "48E-PLACED",
        "status": "pass",
        "detail": "qualified facility/property placed in service after 2024"
      },
      {
        "id": "48E-ENTITY",
        "status": "pass",
        "detail": "PFE entity restriction applied according to tax-year begin date"
      },
      {
        "id": "48E-PFE",
        "status": "pass",
        "detail": "post-2025 construction has no modeled material assistance from PFE"
      },
  …
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`taxcredit-engine-agent/`](../../taxcredit-engine-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-16T23:45:07Z).*
