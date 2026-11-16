# io.github.jdhart81/agent-surety

[![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-surety)](https://mcptry.com/servers/io.github.jdhart81/agent-surety)

Counterparty risk transfer for the agent economy: bonds behind promises, ruling-gated slashing, conservation-checked balances, tamper-evident audit. The trust oracle scores counterparties; surety BACKS them.

| | |
|---|---|
| Registry name | `io.github.jdhart81/agent-surety` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/surety/mcp` |
| Version | 0.2.1 |
| Tools | 10 |
| Source | [`agent-surety-agent/`](../../agent-surety-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-agent-surety": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/surety/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-agent-surety https://mcp.viridisconservation.com/surety/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `post_bond`

Post a surety bond behind an agent's promises. principal is a positive integer in minor units; expires_at is the ISO-8601 coverage window end. The bond fee (2% default) is computed and frozen at post.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `coverage` | string | no | Optional. What the bond covers, in words. |
| `currency` | string | no | ISO 4217 currency code, for example USD. |
| `expires_at` | string | yes | End of the coverage window, ISO-8601. |
| `principal` | integer | yes | Bond stake in minor units (cents), a positive whole number. |
| `principal_agent` | string | yes | Id of the agent whose promises the bond covers. |

### `activate_bond`

Mark a POSTED bond ACTIVE (idempotent). funding_ref links the payment rail transaction that funded the stake.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `bond_id` | string | yes | The bond id returned by post_bond. |
| `funding_ref` | string | no | Optional. The payment that funded the stake. |

### `file_claim`

File a claim against an ACTIVE bond. Claims pay out ONLY when an arbitration ruling upholds them (see slash_bond).

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `amount_minor` | integer | yes | Claimed amount in minor units (cents). |
| `bond_id` | string | yes | The bond id returned by post_bond. |
| `claimant` | string | yes | Id of the party filing the claim. |
| `reason` | string | no | Optional. A short note of why, kept on the record. |

### `slash_bond`

Execute an arbitration ruling against a claim. Requires the ruling's case id + content hash from agent-arbitration — no ruling, no slash; a given ruling pays at most once. Payout caps at the bond's available balance …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `bond_id` | string | yes | The bond id returned by post_bond. |
| `claim_id` | string | yes | The claim id returned by file_claim. |
| `ruling_case_id` | string | yes | The arbitration case id. |
| `ruling_hash` | string | yes | The arbitration ruling's content hash. |
| `upheld` | boolean | no | True if the ruling upholds the claim. Default true. |

### `release_bond`

Release the remaining stake to the principal after the coverage window elapses — refused while any claim is still open.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `bond_id` | string | yes | The bond id returned by post_bond. |

### `bond_status`

Current record for a bond (state, balances, claims, audit head).

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `bond_id` | string | yes | The bond id returned by post_bond. |

### `list_bonds`

List bonds, optionally filtered by state (POSTED|ACTIVE|RELEASED|EXHAUSTED).

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `state` | string | no | Optional filter: POSTED, ACTIVE, RELEASED or EXHAUSTED. |

### `verify_audit`

Validate the tamper-evident audit hash chain for a bond.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `bond_id` | string | yes | The bond id returned by post_bond. |

### `price_bond`

Underwrite a surety bond: deterministic actuarial premium quote from a counterparty's track record (attestations, notarized deliveries, completed bonds lower the rate; slashes raise it or decline outright). Integer-only …

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `attestations` | integer | no | Optional. Trust attestations the counterparty holds. |
| `bonds_completed` | integer | no | Optional. Bonds released without a claim. |
| `coverage_minor` | integer | yes | Coverage amount in minor units (cents). |
| `duration_days` | integer | yes | Coverage length in days. |
| `slashed_minor` | integer | no | Optional. Total slashed, in minor units. |
| `slashes` | integer | no | Optional. Times the counterparty's bonds were slashed. |
| `successful_deliveries` | integer | no | Optional. Notarized deliveries completed. |

### `describe_agent`

Return capabilities and input contract.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-16):

```json
{
  "name": "price_bond",
  "arguments": {
    "coverage_minor": 100000,
    "duration_days": 30
  }
}
```

Response (shortened):

```json
{
  "status": "ok",
  "data": {
    "decision": "quote",
    "coverage_minor": 100000,
    "duration_days": 30,
    "history": {
      "attestations": 0,
      "successful_deliveries": 0,
      "bonds_completed": 0,
      "slashes": 0,
      "slashed_minor": 0
    },
    "model": "uw-v1",
    "premium_minor": 494,
    "multiplier_ppm": 3000000,
    "base_rate_bps_per_year": 200,
    "effective_rate_bps_per_year": 601,
    "quote_hash": "bc9fc2dd85782d006a50ff73871dff15f0f60e8a19b5c07098448e8a033ade7a"
  },
  "error": null,
  "timestamp": "2026-11-16T23:44:52.299283+00:00",
  "_orc": {
    "orc": "0.1",
    "profile": "viridis.fleet/auto",
    "issuer": {
      "id": "did:web:viridisconservation.com",
      "name": "Viridis LLC"
    },
    "subject": {
      "agent": "surety",
      "tool": "price_bond"
    },
    "output": {
      "result": {
        "status": "ok",
        "data": {
          "decision": "quote",
          "coverage_minor": 100000,
          "duration_days": 30,
  …
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

This server is one of the fleet's shared rails, so on the hosted endpoint a tool that changes records needs a caller credential (`Authorization: Bearer <token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns HTTP 401 and nothing changes. Read-only tools never need one. To get a credential, email <justin@viridisconservation.com>, or self-host from the source folder, where no credential applies.

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`agent-surety-agent/`](../../agent-surety-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-16T23:45:07Z).*
