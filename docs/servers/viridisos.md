# io.github.jdhart81/viridisos

ViridisOS: theorem-backed conservation certification and the fleet's trust root.

| | |
|---|---|
| Registry name | `io.github.jdhart81/viridisos` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/viridisos/mcp` |
| Version | 1.0.0+h1115 |
| Tools | 7 |
| Source | [`viridisos/`](../../viridisos/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-viridisos": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/viridisos/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-viridisos https://mcp.viridisconservation.com/viridisos/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `viridis_list_modules`

List ViridisOS modules and their LIVE/BLOCKED state (A-1 against the live canon).

*read-only; structured output*

No inputs.

### `viridis_certify`

Certify a subject (parcel/portfolio) with a module -> a certificate. Errors if the module's backing theorem is not gate-passed (BLOCKED).

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `inputs` | object | yes | The module's inputs, as an object. |
| `module_id` | string | yes | The certification module id. |
| `subject` | string | yes | What is certified, for example a parcel or portfolio id. |

### `viridis_certify_envelope`

Certify then return a 'Certified by ViridisOS' mark envelope (profile conservation-claim).

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `inputs` | object | yes | The module's inputs, as an object. |
| `module_id` | string | yes | The certification module id. |
| `subject` | string | yes | What is certified, for example a parcel or portfolio id. |

### `viridis_verify_mark`

Verify a 'Certified by ViridisOS' envelope against the shared trust root.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `envelope` | object | yes | The 'Certified by ViridisOS' envelope, unchanged. |
| `profile` | string | no | Optional. The profile to verify against. |

### `viridis_bind_did`

Derive the canonical did:viridis identity for an agent (fleet R1 formula) under the shared root.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent. |
| `pubkey` | string | yes | The agent's public key. |

### `viridis_agent_attestation`

Issue a mark-stamped agent-attestation envelope under the shared trust root.

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `event` | object | yes | The event to attest, as an object. |

### `viridis_compute_toll`

Compute the unified Viridis protocol margin (the take) + pass-through card cost for a settlement.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `amount_minor` | integer | yes | Settlement amount in minor units (cents). |
| `payee_tier` | string | yes | new, connect_onboarded or connect_verified. |

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-15):

```json
{
  "name": "viridis_list_modules",
  "arguments": {}
}
```

Response (shortened):

```json
{
  "modules": [
    {
      "id": "mutualist",
      "name": "Mutualist — natural-capital risk-premium pricing",
      "line": "Valuation & Finance",
      "backing_doi": "10.5281/zenodo.SRPT-PENDING",
      "lean_module": "SymbioticRiskPremium",
      "state": "BLOCKED"
    },
    {
      "id": "restoration",
      "name": "Restoration — nucleation planting design (Θ go/no-go + n*)",
      "line": "Restoration",
      "backing_doi": "10.5281/zenodo.20982979",
      "lean_module": "ForestNucleation",
      "state": "READY"
    },
    {
      "id": "afforestation",
      "name": "Afforestation — cubic optimal-seeding law + site-prep lever",
      "line": "Restoration",
      "backing_doi": "10.5281/zenodo.21168224",
      "lean_module": "AfforestationStewardship",
      "state": "READY"
    },
    {
      "id": "harmonization",
      "name": "Harmonization — thermodynamic shadow-price coordination",
      "line": "Governance / OS Modules",
      "backing_doi": "10.5281/zenodo.21168212",
      "lean_module": "GaianHarmonization",
      "state": "READY"
    }
  ]
}
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`viridisos/`](../../viridisos/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
