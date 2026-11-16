# io.github.jdhart81/agent-covenant

Machine-checkable authority leases for agents: scoped, budgeted, expiring, revocable, audited. Deny-by-default power of attorney for the agent economy.

| | |
|---|---|
| Registry name | `io.github.jdhart81/agent-covenant` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/covenant/mcp` |
| Version | 0.1.2 |
| Tools | 7 |
| Source | [`agent-covenant-agent/`](../../agent-covenant-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-agent-covenant": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/covenant/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-agent-covenant https://mcp.viridisconservation.com/covenant/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `grant_covenant`

Grant an agent a covenant: an explicit lease of authority. scopes support wildcards ('payments.*', '*'); budget_minor is the total spend ceiling in minor units; expires_at is ISO-8601. Returns the covenant_id.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent receiving (or, when listing, bound by) the covenant. |
| `budget_minor` | integer | yes | Total spend ceiling in minor units (cents). |
| `expires_at` | string | yes | When the covenant ends, ISO-8601. |
| `principal` | string | yes | Id of the party granting authority. |
| `scopes` | array of string | yes | Allowed actions, wildcards supported, for example ["payments.*"]. |

### `check_act`

Check (and if allowed, record) a proposed act against a covenant. Deny-by-default. Idempotent on act_id — retries never double-consume budget. Every check lands on the audit chain.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `act_id` | string | yes | Your id for this act; a retry with the same act_id never double-spends. |
| `amount_minor` | integer | no | Spend for this act in minor units. Default 0. |
| `covenant_id` | string | yes | The covenant id returned by grant_covenant. |
| `scope` | string | yes | The action being attempted, for example payments.send. |

### `revoke_covenant`

Revoke a covenant immediately and terminally. All subsequent checks deny.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `covenant_id` | string | yes | The covenant id returned by grant_covenant. |
| `reason` | string | no | Optional. A short note of why, kept on the record. |

### `covenant_status`

Current state, consumed/remaining budget, and check count.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `covenant_id` | string | yes | The covenant id returned by grant_covenant. |

### `verify_audit`

Verify the tamper-evident audit chain of allowed/denied acts.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `covenant_id` | string | yes | The covenant id returned by grant_covenant. |

### `list_covenants`

List covenants, optionally filtered by state (ACTIVE|REVOKED|EXPIRED) and/or the bound agent.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | no | Id of the agent receiving (or, when listing, bound by) the covenant. |
| `state` | string | no | Optional filter: ACTIVE, REVOKED or EXPIRED. |

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
  "name": "agent-covenant-agent",
  "version": "0.1.1",
  "description": "Machine-checkable authority leases for agents: scoped, budgeted, expiring, revocable, audited. Deny-by-default.",
  "capabilities": [
    "grant",
    "check_act",
    "revoke",
    "status",
    "verify_audit",
    "list"
  ],
  "inputs": {
    "action": "str",
    "covenant_id": "str",
    "principal": "str",
    "agent_id": "str",
    "scopes": "list[str] (wildcards: 'x.*', '*')",
    "budget_minor": "int >= 0",
    "expires_at": "ISO-8601",
    "act_id": "str",
    "scope": "str",
    "amount_minor": "int >= 0"
  },
  "outputs": {
    "status": "str (ok|error)",
    "data": "dict"
  },
  "a2a_role": "authority"
}
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

This server is one of the fleet's shared rails, so on the hosted endpoint a tool that changes records needs a caller credential (`Authorization: Bearer <token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns HTTP 401 and nothing changes. Read-only tools never need one. To get a credential, email <justin@viridisconservation.com>, or self-host from the source folder, where no credential applies.

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`agent-covenant-agent/`](../../agent-covenant-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
