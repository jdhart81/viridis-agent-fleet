# io.github.jdhart81/ghg-ledger

[![mcptry](https://mcptry.com/badge/io.github.jdhart81/ghg-ledger)](https://mcptry.com/servers/io.github.jdhart81/ghg-ledger)

Deterministic auditable Scope 1, 2, and 3 greenhouse-gas inventory engine

| | |
|---|---|
| Registry name | `io.github.jdhart81/ghg-ledger` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/ghg-ledger/mcp` |
| Version | 0.1.1 |
| Tools | 6 |
| Source | [`ghg-ledger-agent/`](../../ghg-ledger-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-ghg-ledger": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/ghg-ledger/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-ghg-ledger https://mcp.viridisconservation.com/ghg-ledger/mcp`

ChatGPT: published app [Viridis GHG Ledger](https://chatgpt.com/plugins/plugin_asdk_app_6aebb509f8d8819196202a14ab8627b5). Open it in ChatGPT and add it; no connector setup or developer mode.

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `calculate_inventory`

Calculate an auditable GHG inventory from explicit activity records. Returns per-line gas/CO2e results, Scope 1/2/3 and category rollups, dual Scope 2 reporting, indeterminate lines, factor lineage, notary payload, and …

*read-only; $1.00 per call after the free daily calls (x402 catalog); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `activities` | array or object or string | no | The activities to inventory: a list of {activity_type, quantity, unit, region, year}. One object or a JSON string is also accepted. |
| `options` | object | no | Optional. Settings, for example factor_year_policy or offset_buyer. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |

### `classify_activity`

Suggest scope and Scope 3 category from the bundled deterministic map. No inference is used; unknown activity types return no suggestion.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `activity` | object | yes | One activity: {activity_type, quantity, unit, region, year}. |

### `list_factor_packs`

List the bundled pack version/digest, supported regions and years, activity types, GWP set, and explicit MVP coverage.

*read-only; structured output*

No inputs.

### `get_factor_pack`

Return factors, GWP values, conversions, sources, and pack SHA for one exact bundled region/year. No nearest-region or nearest-year substitution.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `region` | string | yes | Region code, for example US, US-CAMX or UK; see list_factor_packs. |
| `year` | integer | yes | Factor year, for example 2023; see list_factor_packs. |

### `verify_result`

Recompute a prior inventory's audit hash and conservation checks. Pass the prior result object as JSON; tampering or stale factor lineage is flagged.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `result_json` | string | yes | The full calculate_inventory result, as a JSON string, unchanged. |

### `describe_agent`

Return fleet-standard capabilities, version, pack digest, and pricing.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-16):

```json
{
  "name": "calculate_inventory",
  "arguments": {
    "activities": [
      {
        "activity_type": "purchased_electricity",
        "id": "office-electricity",
        "quantity": "12000",
        "region": "US",
        "unit": "kWh",
        "year": 2023
      },
      {
        "activity_type": "stationary_combustion_diesel",
        "id": "backup-generator",
        "quantity": "400",
        "region": "US",
        "unit": "gallons",
        "year": 2025
      }
    ],
    "options": {}
  }
}
```

Response (shortened):

```json
{
  "status": "ok",
  "data": {
    "inventory_status": "complete_for_supplied_activities",
    "organization_id": null,
    "reporting_period": null,
    "organizational_boundary": null,
    "inputs": {
      "activities": [
        {
          "id": "office-electricity",
          "activity_type": "purchased_electricity",
          "quantity": "12000",
          "unit": "kWh",
          "region": "US",
          "year": 2023
        },
        {
          "id": "backup-generator",
          "activity_type": "stationary_combustion_diesel",
          "quantity": "400",
          "unit": "gallons",
          "region": "US",
          "year": 2025
        }
      ],
      "options": {}
    },
    "input_sha256": "226244ddd6106f0e4e0cde81430cbb2a430a48e12174ffb91df345a0716bdfc3",
    "line_items": [
      {
        "id": "office-electricity",
        "status": "determinate",
        "activity_type": "purchased_electricity",
        "input": {
          "quantity": "12000",
          "unit": "kWh",
          "region": "US",
          "year": 2023
        },
  …
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`ghg-ledger-agent/`](../../ghg-ledger-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-16T23:45:07Z).*
