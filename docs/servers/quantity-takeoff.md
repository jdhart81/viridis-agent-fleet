# io.github.jdhart81/quantity-takeoff

Deterministic, auditable construction material takeoff engine

| | |
|---|---|
| Registry name | `io.github.jdhart81/quantity-takeoff` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/quantity-takeoff/mcp` |
| Version | 0.1.1 |
| Tools | 7 |
| Source | [`quantity-takeoff-agent/`](../../quantity-takeoff-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-quantity-takeoff": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/quantity-takeoff/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-quantity-takeoff https://mcp.viridisconservation.com/quantity-takeoff/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `calculate_takeoff`

Calculate an auditable material takeoff from explicit geometry or a supported SmartScale/ProtoGen measurement payload. Returns net, explicit waste-adjusted, and conservative purchase quantities. This is a planning …

*read-only; $0.50 per call after the free daily calls (x402 catalog); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `items` | array or object or string | no | The items to quantify: a list of {id, assembly, unit_system, dimensions}. One item or a JSON string is also accepted. |
| `options` | object | no | Optional. Extra settings for this call, as an object. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |

### `list_assemblies`

List supported assemblies, required dimensions, formulas, waste defaults, and the current material-pack digest.

*read-only; structured output*

No inputs.

### `get_assembly`

Return one assembly's formula, required dimensions, material factors, purchase increment, sources, and material-pack lineage.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `assembly_type` | string | yes | Assembly id, for example concrete_slab; see list_assemblies. |

### `list_material_pack`

List the bundled material pack version, digest, coverage, shapes, rebar sizes, roof pitches, and explicit unsupported policy.

*read-only; structured output*

No inputs.

### `get_material_pack`

Return the bundled factors, densities, coverages, waste defaults, purchase increments, unit conversions, sources, and raw-pack SHA.

*read-only; structured output*

No inputs.

### `verify_result`

Recompute a takeoff audit hash, notary payload, pack currency, and QT9 unit-resolved conservation. Pass the prior result object as JSON.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `result_json` | string | yes | The full calculate_takeoff result, as a JSON string, unchanged. |

### `describe_agent`

Return fleet-standard capabilities, version, pack digest, disclaimer, composition role, and pricing.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-15):

```json
{
  "name": "calculate_takeoff",
  "arguments": {
    "items": [
      {
        "assembly": "concrete_slab",
        "dimensions": {
          "length": {
            "unit": "ft",
            "value": "20"
          },
          "thickness": {
            "unit": "in",
            "value": "4"
          },
          "width": {
            "unit": "ft",
            "value": "30"
          }
        },
        "id": "slab-1",
        "unit_system": "imperial"
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
    "takeoff_status": "complete_for_supplied_items",
    "project_id": null,
    "revision_id": null,
    "inputs": {
      "items": [
        {
          "id": "slab-1",
          "assembly": "concrete_slab",
          "unit_system": "imperial",
          "dimensions": {
            "length": {
              "value": "20",
              "unit": "ft"
            },
            "width": {
              "value": "30",
              "unit": "ft"
            },
            "thickness": {
              "value": "4",
              "unit": "in"
            }
          }
        }
      ],
      "options": {}
    },
    "input_sha256": "930c5cf2c5af6f1745cdbd060fcf3468208467d9e51298dc18c8e2b9c16928b0",
    "line_items": [
      {
        "id": "slab-1:ready_mix_concrete",
        "item_id": "slab-1",
        "status": "determinate",
        "assembly": "concrete_slab",
        "trade": "concrete",
        "material": "ready_mix_concrete",
        "net_qty": "7.407",
  …
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`quantity-takeoff-agent/`](../../quantity-takeoff-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
