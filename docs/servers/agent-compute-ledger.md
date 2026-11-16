# io.github.jdhart81/agent-compute-ledger

Compute-is-carbon cost/energy ledger for agent work: joules, gCO2e, and Landauer-limit efficiency per unit of agent cognition, with content-addressed attestations.

| | |
|---|---|
| Registry name | `io.github.jdhart81/agent-compute-ledger` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/compute-ledger/mcp` |
| Version | 0.3.0+h1115 |
| Tools | 13 |
| Source | [`agent-compute-ledger-agent/`](../../agent-compute-ledger-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-agent-compute-ledger": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/compute-ledger/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-agent-compute-ledger https://mcp.viridisconservation.com/compute-ledger/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `record_work`

Record a unit of agent compute work. energy_j = power_w * duration_s; carbon_g follows from grid intensity. If bit_ops is declared, the entry is validated against the Landauer floor (bit_ops * kB * T * ln2) — physically …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent whose compute or inventory is recorded or read. |
| `bit_ops` | number | no | Optional. Irreversible bit operations performed; when given, the entry is checked against the Landauer floor. |
| `duration_s` | number | yes | How long the work ran, in seconds. |
| `entry_id` | string | yes | Your id for this work entry; recording it again is idempotent. |
| `grid_intensity_g_per_kwh` | number | no | Grid carbon intensity in grams CO2e per kWh. Default 400. |
| `power_w` | number | yes | Average power draw in watts. |
| `price_minor_per_kwh` | number | no | Optional. Electricity price in minor units per kWh, for cost. |
| `task` | string | no | Optional. A short label for the work. |
| `temperature_k` | number | no | Operating temperature in kelvin. Default 300. |

### `footprint`

Aggregate footprint for an agent: total J, kWh, gCO2e, cost, and mean Landauer efficiency. Totals are exact sums of the ledger entries.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent whose compute or inventory is recorded or read. |

### `attest`

Issue a content-addressed attestation for a ledger entry (verifiable green-compute / energy claim).

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `entry_id` | string | yes | Your id for this work entry; recording it again is idempotent. |

### `verify_attestation`

Verify an attestation by recomputing the entry hash.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `attestation` | object | yes | The attestation object returned by attest, unchanged. |

### `verify_chain`

Verify the tamper-evident hash chain of an agent's ledger.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent whose compute or inventory is recorded or read. |

### `list_entries`

List all ledger entries for an agent.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent whose compute or inventory is recorded or read. |

### `carbon_receipt`

Emit an x402-C carbon receipt for a recorded work entry — the physically-grounded {version, g_co2e, energy_j, method, landauer_*, ...} object an x402 machine-payment receipt can carry. method is 'landauer-floor' when …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `entry_id` | string | yes | Your id for this work entry; recording it again is idempotent. |
| `offset_ref` | string | no | Optional. A clearinghouse purchase_id whose retirement covers this entry. |

### `intelligence_bound`

Thermodynamic ceiling on information processing for a power budget. Returns the Landauer ceiling P / (k_B*T*ln 2) on irreversible bit operations per second (established physics), the Intelligence Bound min(rho*B, P / …

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `bandwidth_bits_per_s` | number | no | Optional. Available information bandwidth in bits per second. |
| `measured_bits_per_s` | number | no | Optional. Measured processing rate in bits per second, to compare. |
| `power_w` | number | yes | Average power draw in watts. |
| `temperature_k` | number | no | Operating temperature in kelvin. Default 300. |

### `record_inventory`

Record an audited GHG inventory in a separate append-only chain. mass_g is exact integer grams; content and factor-pack digests are bare lowercase SHA-256 hex. Idempotent on inventory_id.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent whose compute or inventory is recorded or read. |
| `content_digest` | string | yes | SHA-256 of the inventory content, lowercase hex without prefix. |
| `factor_pack_digest` | string | yes | SHA-256 of the factor pack, lowercase hex. |
| `factor_pack_version` | string | yes | Version of the emission factor pack used. |
| `inventory_id` | string | yes | Id of the GHG inventory, for example from ghg-ledger. |
| `mass_g` | integer | yes | Inventory total in whole grams CO2e. |
| `source_ids` | array | no | Optional. Ids of the factor sources the inventory used. |

### `get_inventory`

Fetch one immutable inventory record by inventory_id.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `inventory_id` | string | yes | Id of the GHG inventory, for example from ghg-ledger. |

### `list_inventories`

List the separate GHG inventory chain for an agent.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent whose compute or inventory is recorded or read. |

### `verify_inventory_chain`

Verify an agent's inventory hash chain independently of compute work.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent whose compute or inventory is recorded or read. |

### `describe_agent`

Describe this agent: name, version, purpose, every action it supports and the inputs each one takes. Read-only and free; call it first to learn how to use this server.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-15):

```json
{
  "name": "intelligence_bound",
  "arguments": {
    "power_w": 100
  }
}
```

Response (shortened):

```json
{
  "status": "ok",
  "data": {
    "formula": "I_dot <= min(rho*B, P / (k_B * T * ln 2))",
    "inputs": {
      "power_w": 100.0,
      "temperature_k": 300.0,
      "bandwidth_bits_per_s": null
    },
    "landauer_j_per_bit": 2.870978885078724e-21,
    "landauer_bits_per_s": 3.4831325482652564e+22,
    "bound_bits_per_s": 3.4831325482652564e+22,
    "binding_term": "power",
    "note": "The bound counts irreversible bit operations (erasures) at temperature T. Today's processors dissipate many orders of magnitude more energy per operation than k_B*T*ln 2, so real workloads sit far below the bound; reversible computation is not limited by this term.",
    "status": "The Landauer term (k_B*T*ln 2 per irreversible bit) is established physics. The Intelligence Bound, min(rho*B, P/(k_B*T*ln 2)), is Viridis's working conjecture, not a proved law.",
    "reference": "J. Hart, The Intelligence Bound (manuscript in preparation)",
    "next": [
      "record_work: log a measured workload with Landauer validation",
      "carbon_receipt: emit an x402-C carbon receipt for that work"
    ]
  },
  "error": null,
  "timestamp": "2026-11-15T23:15:26.519395+00:00"
}
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

This server is one of the fleet's shared rails, so on the hosted endpoint a tool that changes records needs a caller credential (`Authorization: Bearer <token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns HTTP 401 and nothing changes. Read-only tools never need one. To get a credential, email <justin@viridisconservation.com>, or self-host from the source folder, where no credential applies.

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`agent-compute-ledger-agent/`](../../agent-compute-ledger-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
