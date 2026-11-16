# io.github.jdhart81/agent-identity-registry

The passport + directory of the agent-to-agent economy: verifiable agent identity (content-addressed DIDs), capability advertising, and capability-based discovery. Supply-side complement to intent routing.

| | |
|---|---|
| Registry name | `io.github.jdhart81/agent-identity-registry` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/identity/mcp` |
| Version | 0.1.2 |
| Tools | 6 |
| Source | [`agent-identity-registry-agent/`](../../agent-identity-registry-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-agent-identity-registry": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/identity/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-agent-identity-registry https://mcp.viridisconservation.com/identity/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `register_agent`

Register (or idempotently update) an agent identity. Returns a deterministic content-addressed DID. capabilities is a non-empty list of lowercase capability tags other agents can discover you by.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Your stable id for the agent. |
| `capabilities` | array of string | yes | Lowercase capability tags, for example ["ghg-inventory"]. |
| `endpoint` | string | no | Optional. The agent's MCP or HTTP endpoint URL. |
| `name` | string | no | Optional. Display name. |
| `pricing` | object | no | Optional. Pricing the agent advertises, as an object. |
| `pubkey` | string | no | Optional. The agent's public key, for signed actions. |
| `reputation_hint` | number | no | Optional. Starting reputation between 0 and 1. Default 0.5. |

### `resolve_agent`

Resolve an identity by agent_id or DID to its full public registration.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | no | Your stable id for the agent. |
| `did` | string | no | The agent's DID; give this or agent_id. |

### `discover_agents`

Find ACTIVE agents matching ALL requested capabilities (AND semantics), deterministically ordered by match count then reputation.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `capabilities` | array of string | yes | Lowercase capability tags, for example ["ghg-inventory"]. |
| `limit` | integer | no | Optional. The most agents to return. Default 25. |

### `revoke_agent`

Revoke an identity: it disappears from discovery (terminal) but its record is retained for auditability.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | no | Your stable id for the agent. |
| `did` | string | no | The agent's DID; give this or agent_id. |

### `list_registrations`

List registrations, optionally filtered by status (ACTIVE|REVOKED).

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `status` | string | no | Optional filter: ACTIVE or REVOKED. |

### `describe_agent`

Describe this agent: name, version, purpose, every action it supports and the inputs each one takes. Read-only and free; call it first to learn how to use this server.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-15):

```json
{
  "name": "describe_agent",
  "arguments": {}
}
```

Response (shortened):

```json
{
  "name": "agent-identity-registry-agent",
  "version": "0.1.1",
  "description": "Verifiable agent identity (DIDs) + capability advertising & discovery.",
  "capabilities": [
    "register",
    "resolve",
    "discover",
    "revoke",
    "list"
  ],
  "inputs": {
    "action": "str",
    "agent_id": "str",
    "capabilities": "list[str]",
    "endpoint": "str",
    "pubkey": "str",
    "pricing": "dict"
  },
  "outputs": {
    "status": "str (ok|error)",
    "data": "dict"
  },
  "a2a_role": "identity"
}
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

This server is one of the fleet's shared rails, so on the hosted endpoint a tool that changes records needs a caller credential (`Authorization: Bearer <token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns HTTP 401 and nothing changes. Read-only tools never need one. To get a credential, email <justin@viridisconservation.com>, or self-host from the source folder, where no credential applies.

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`agent-identity-registry-agent/`](../../agent-identity-registry-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
