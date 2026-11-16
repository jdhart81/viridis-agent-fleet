# io.github.jdhart81/green-router

Carbon-accounted agent compute: free honest footprint quotes and carbon-ranked routing; paid certificates backed by REAL verified offset retirement through the fleet's own clearinghouse (Verra provenance, x402-C verifiable).

| | |
|---|---|
| Registry name | `io.github.jdhart81/green-router` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/green-router/mcp` |
| Version | 0.1.1 |
| Tools | 6 |
| Source | [`green-router-agent/`](../../green-router-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-green-router": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/green-router/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-green-router https://mcp.viridisconservation.com/green-router/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `quote_footprint`

FREE: honest energy/carbon footprint for an agent workload — {backend_id? (frontier_cloud | efficient_cloud | local_small), total_tokens, output_tokens, calls?, success_score?, grid_gco2e_per_kwh?, pue?, custom_backend? …

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `workload` | object | yes | The workload: {backend_id?, total_tokens, output_tokens, calls?, success_score?, grid_gco2e_per_kwh?, pue?, custom_backend?}. |

### `green_route`

FREE: rank compute backends by carbon for this workload — the greenest eligible path and the gCO2e saved per call. Carbon only (GR6); pair with /neurogenesis/mcp route_task for quality-floor routing.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `allowed_backends` | array | no | Optional. Backend ids to choose from; default all. |
| `workload` | object | yes | The workload: {backend_id?, total_tokens, output_tokens, calls?, success_score?, grid_gco2e_per_kwh?, pue?, custom_backend?}. |

### `certify`

PAID ($0.50 after free tier): compute the workload footprint, then RETIRE the required verified offset mass through the fleet's own clearinghouse — Verra provenance rides into the certificate; no retirement, no …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |
| `workload` | object | yes | The workload: {backend_id?, total_tokens, output_tokens, calls?, success_score?, grid_gco2e_per_kwh?, pue?, custom_backend?}. |

### `verify_green_certificate`

FREE forever (GR5): recompute a certificate's footprint from its stored workload, compare against the certified numbers, and surface the clearinghouse purchase_id for the independent x402-C verify_retirement check on …

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `certificate_id` | string | yes | The certificate id returned by certify. |

### `list_green_certificates`

FREE: the certificate ledger — counts, total grams retired, total clearinghouse cost (honest books, GR8).

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `limit` | integer | no | Optional. The most items to return. |

### `describe_agent`

Return capabilities and input contract.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-15):

```json
{
  "name": "quote_footprint",
  "arguments": {
    "workload": {
      "backend_id": "efficient_cloud",
      "output_tokens": 2000,
      "total_tokens": 10000
    }
  }
}
```

Response (shortened):

```json
{
  "status": "ok",
  "data": {
    "backend_id": "efficient_cloud",
    "calls": 1,
    "per_call": {
      "it_energy_joules": 2880.0,
      "facility_energy_joules": 4492.8,
      "carbon_gco2e": 0.55536,
      "useful_bits": 20000.0
    },
    "total": {
      "facility_energy_joules": 4492.8,
      "carbon_gco2e": 0.55536,
      "useful_bits": 20000.0
    },
    "retirement_required_g": 1,
    "assumptions": {
      "backend_energy": {
        "id": "efficient_cloud",
        "wh_per_1k_tokens": 0.08,
        "note": "Smaller hosted model, ~4x more efficient per token than frontier."
      },
      "grid": {
        "gco2e_per_kwh": 445.0,
        "source": "IEA global average electricity carbon intensity, 2024"
      },
      "facility_pue": {
        "pue": 1.56,
        "source": "Uptime Institute Global Data Center Survey 2024"
      },
      "safety_factor": 1.2,
      "honesty": "estimates from disclosed per-query energy figures, not telemetry; retirement mass is ceil(gCO2e x safety_factor)"
    },
    "physics_context": {
      "landauer_joules_per_bit_at_300K": 2.870978885078724e-21,
      "note": "dI/dt <= P*D/(kB*T*ln2): the Landauer floor is the yardstick, not a proximity claim — the gap IS the finding"
    },
    "next_steps": {
      "certify": "call certify with the same workload — the fleet's own clearinghouse retires 1 g of Verra-provenance verified offsets and you receive a machine-verifiable certificate",
  …
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

This server is one of the fleet's shared rails, so on the hosted endpoint a tool that changes records needs a caller credential (`Authorization: Bearer <token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns HTTP 401 and nothing changes. Read-only tools never need one. To get a credential, email <justin@viridisconservation.com>, or self-host from the source folder, where no credential applies.

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`green-router-agent/`](../../green-router-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
