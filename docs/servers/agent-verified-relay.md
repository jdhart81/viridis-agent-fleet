# io.github.jdhart81/agent-verified-relay

Viridis Verified: the consequence wrapper for the agent economy. Wraps any third-party MCP server with tamper-evident delivery receipts, metered per-call fees, and dispute-ready evidence — rails revenue that scales with other people's services.

| | |
|---|---|
| Registry name | `io.github.jdhart81/agent-verified-relay` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/verified/mcp` |
| Version | 0.1.0+h1115 |
| Tools | 7 |
| Source | [`agent-verified-relay-agent/`](../../agent-verified-relay-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-agent-verified-relay": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/verified/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-agent-verified-relay https://mcp.viridisconservation.com/verified/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `register_service`

Register a third-party MCP server (https, public FQDN only) under Viridis Verified. Returns a content-addressed service_id; idempotent on (url, provider). fee_minor is the per-verified-call fee in cents.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `description` | string | no | Optional. What the service does. |
| `fee_minor` | integer | no | Per-verified-call fee in minor units (cents). Default 2. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |
| `provider` | string | yes | Id of the service's provider. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |
| `url` | string | yes | The MCP server's https URL (public host only). |

### `call_verified`

Relay a tools/call to a registered MCP service and notarize the exchange: request hash + response hash + outcome land in a tamper-evident receipt chain. Idempotent on call_id (a replay returns the original receipt and …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `arguments` | object | no | Optional. Arguments for the tool, as an object. |
| `call_id` | string | yes | Your id for this call; repeating it returns the original receipt. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |
| `service_id` | string | yes | The service id returned by register_service. |
| `timeout_s` | integer | no | Optional. Seconds to wait for the service. Default 20. |
| `tool` | string | yes | Name of the tool to call on that service. |

### `get_receipt`

Fetch a single delivery receipt by id.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `receipt_id` | string | yes | The receipt id from call_verified. |

### `verify_receipts`

Recompute a service's full receipt hash chain and fee ledger. Any party can audit Viridis Verified from receipts alone.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `service_id` | string | yes | The service id returned by register_service. |

### `list_services`

List registered services with call/fee counters.

*read-only; structured output*

No inputs.

### `service_stats`

Call counts, error counts, and accrued fees for one service.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `service_id` | string | yes | The service id returned by register_service. |

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
  "name": "agent-verified-relay-agent",
  "version": "0.1.0",
  "description": "Viridis Verified — receipted relay wrapping any third-party MCP server with tamper-evident delivery receipts, metered fees, and rails composition (bonds, arbitration, reputation).",
  "capabilities": [
    "register_service",
    "call_verified",
    "get_receipt",
    "verify_receipts",
    "list_services",
    "service_stats"
  ],
  "inputs": {
    "action": "str",
    "url": "https URL (public FQDN)",
    "provider": "str",
    "service_id": "str",
    "tool": "str",
    "arguments": "dict",
    "call_id": "str",
    "fee_minor": "int >= 0",
    "timeout_s": "int 1..30"
  },
  "outputs": {
    "status": "ok|error",
    "data": "per action"
  },
  "a2a_role": "verified-relay"
}
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

This server is one of the fleet's shared rails, so on the hosted endpoint a tool that changes records needs a caller credential (`Authorization: Bearer <token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns HTTP 401 and nothing changes. Read-only tools never need one. To get a credential, email <justin@viridisconservation.com>, or self-host from the source folder, where no credential applies.

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`agent-verified-relay-agent/`](../../agent-verified-relay-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
