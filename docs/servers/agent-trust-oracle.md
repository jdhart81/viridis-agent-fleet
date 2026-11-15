# io.github.jdhart81/agent-trust-oracle

Reputation & tamper-evident trust attestations for the agent-to-agent economy. Answers 'can this agent be trusted with authority?' via a decay-weighted, bounded reputation score and signed attestations.

| | |
|---|---|
| Registry name | `io.github.jdhart81/agent-trust-oracle` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/trust/mcp` |
| Version | 0.1.1 |
| Tools | 6 |
| Source | [`agent-trust-oracle-agent/`](../../agent-trust-oracle-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-agent-trust-oracle": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/trust/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-agent-trust-oracle https://mcp.viridisconservation.com/trust/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `record_outcome`

Record an interaction outcome for an agent. kind: success | delivered | dispute_won | failure | undelivered | dispute_lost | timeout | security_incident (security incidents carry a 3x penalty).

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent. |
| `counterparty` | string | no | Optional. Id of the other party. |
| `kind` | string | yes | success, delivered, dispute_won, failure, undelivered, dispute_lost, timeout or security_incident. |
| `note` | string | no | Optional. A short note. |
| `weight` | number | no | Optional. Weight of this outcome. Default 1. |

### `score_agent`

Get an agent's decay-weighted trust score in [0,1] and tier. Unknown agents get a neutral 0.5 prior — no blind trust, no unfair zero.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent. |

### `attest`

Issue a tamper-evident (hash-chained) trust attestation for an agent.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent. |
| `claim` | string | no | Optional. What the attestation states. Default reputation-snapshot. |

### `verify_attestation`

Verify a previously issued attestation by recomputing its hash.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent. |
| `attestation_id` | string | yes | The attestation id returned by attest. |

### `history`

Full outcome history + attestation count + current score for an agent.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent. |

### `describe_agent`

Describe this agent: name, version, purpose, every action it supports and the inputs each one takes. Read-only and free; call it first to learn how to use this server.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-15):

```json
{
  "name": "score_agent",
  "arguments": {
    "agent_id": "example-agent"
  }
}
```

Response (shortened):

```json
{
  "status": "ok",
  "data": {
    "agent_id": "example-agent",
    "score": 0.5,
    "tier": "NEUTRAL",
    "outcomes": 0,
    "prior": true
  },
  "error": null,
  "timestamp": "2026-11-15T23:15:33.556448+00:00",
  "_orc": {
    "orc": "0.1",
    "profile": "viridis.fleet/auto",
    "issuer": {
      "id": "did:web:viridisconservation.com",
      "name": "Viridis LLC"
    },
    "subject": {
      "agent": "trust",
      "tool": "score"
    },
    "output": {
      "result": {
        "status": "ok",
        "data": {
          "agent_id": "example-agent",
          "score": "0.5",
          "tier": "NEUTRAL",
          "outcomes": 0,
          "prior": true
        },
        "error": null,
        "timestamp": "2026-11-15T23:15:33.556448+00:00"
      },
      "args_sha256": "38a1239263348e34d9f9cff173c4eff14d1288ba425d119570a27a5f34ed70cf",
      "thermo": {
        "method": "modeled-wallclock-v1",
        "wall_ms": 1,
        "power_mw_declared": 15000,
  …
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

This server is one of the fleet's shared rails, so on the hosted endpoint a tool that changes records needs a caller credential (`Authorization: Bearer <token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns HTTP 401 and nothing changes. Read-only tools never need one. To get a credential, email <justin@viridisconservation.com>, or self-host from the source folder, where no credential applies.

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`agent-trust-oracle-agent/`](../../agent-trust-oracle-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
