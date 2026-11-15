# io.github.jdhart81/agent-metering

Usage metering + SLA accounting for agent services: the meter behind the x402/HTTP-402 micropayment idiom. Counts the work honestly so escrow knows how much to settle and trust knows whether promises were kept.

| | |
|---|---|
| Registry name | `io.github.jdhart81/agent-metering` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/metering/mcp` |
| Version | 0.2.0 |
| Tools | 11 |
| Source | [`agent-metering-agent/`](../../agent-metering-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-agent-metering": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/metering/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-agent-metering https://mcp.viridisconservation.com/metering/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `create_meter`

Create a usage meter between a provider and a consumer agent. unit: what is being counted (call, token, kwh, ...). Price is in minor currency units (cents) per unit. Returns the meter_id.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `consumer` | string | yes | Agent id of the party consuming it. |
| `currency` | string | no | ISO 4217 currency code, for example USD. |
| `price_minor_per_unit` | number | yes | Price per unit in minor units (cents). |
| `provider` | string | yes | Agent id of the party providing the service. |
| `sla_target` | number | no | Target success rate between 0 and 1. Default 0.99. |
| `unit` | string | yes | What is counted, for example call, token or kwh. |

### `record_usage`

Record a usage event. Idempotent on event_id (safe to retry — never double-billed). outcome is 'ok' or 'error' and feeds the SLA report.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `event_id` | string | yes | Your id for this usage event; recording it again never double-bills. |
| `metadata` | object | no | Optional. Extra key-value data stored with the record. |
| `meter_id` | string | yes | The meter id returned by create_meter. |
| `outcome` | string | no | ok or error. Feeds the SLA report. |
| `quantity` | number | yes | Units used in this event. |

### `usage_summary`

Totals for a meter: event count, total quantity, accrued minor units.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `meter_id` | string | yes | The meter id returned by create_meter. |

### `sla_report`

Pure SLA report: success_rate vs sla_target, breach flag. No mutation.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `meter_id` | string | yes | The meter id returned by create_meter. |

### `close_period`

Freeze all open events into an immutable invoice (exactly-once). The invoice amount is what agent-escrow-agent should settle.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `meter_id` | string | yes | The meter id returned by create_meter. |

### `verify_chain`

Verify the tamper-evident event hash chain for a meter.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `meter_id` | string | yes | The meter id returned by create_meter. |

### `list_meters`

List all meters with event/invoice counts.

*read-only; structured output*

No inputs.

### `list_events`

Read usage events (paginated, read-only). Filter by meter, provider, consumer_class (internal|external|unknown), channel, outcome (ok|error), and ISO date range [since, until). Test-flagged events are excluded unless …

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `channel` | string | no | Optional filter: the channel the events came through. |
| `consumer_class` | string | no | Optional filter: internal, external or unknown. |
| `cursor` | string | no | Optional. The cursor from your previous answer, to fetch the next page. |
| `include_test` | boolean | no | Optional. Include events from meters flagged as test. Default false. |
| `limit` | integer | no | Optional. The most items to return. |
| `meter_id` | string | no | The meter id returned by create_meter. |
| `outcome` | string | no | ok or error. Feeds the SLA report. |
| `provider` | string | no | Agent id of the party providing the service. |
| `since` | string | no | Optional. ISO-8601 timestamp: only items at or after this time. |
| `until` | string | no | Optional. ISO-8601 timestamp: only items before this time. |

### `usage_timeseries`

Usage time series bucketed on each event's recorded_at (UTC; bucket=day|hour), grouped across meters by provider — a real time-series primitive, independent of meter creation times. Includes per-bucket breakdowns by …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `bucket` | string | no | day or hour. |
| `channel` | string | no | Optional filter: the channel the events came through. |
| `consumer_class` | string | no | Optional filter: internal, external or unknown. |
| `include_test` | boolean | no | Optional. Include events from meters flagged as test. Default false. |
| `meter_id` | string | no | The meter id returned by create_meter. |
| `provider` | string | no | Agent id of the party providing the service. |
| `since` | string | no | Optional. ISO-8601 timestamp: only items at or after this time. |
| `until` | string | no | Optional. ISO-8601 timestamp: only items before this time. |

### `flag_meter`

Admin: flag/unflag a meter as test/synthetic so its events are excluded from usage statistics by default. Touches meter metadata only — never events, never the hash chain, never billing accruals. Requires the server's …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `admin_token` | string | yes | The server's admin token. Required for this admin action. |
| `is_test` | boolean | yes | True to flag the meter as test traffic, false to clear it. |
| `meter_id` | string | yes | The meter id returned by create_meter. |
| `note` | string | no | Optional. Why the flag changed. |

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
  "name": "agent-metering-agent",
  "version": "0.2.0",
  "description": "Usage metering + SLA accounting for agent services (the meter behind x402 micropayments).",
  "capabilities": [
    "create_meter",
    "record_usage",
    "usage_summary",
    "sla_report",
    "close_period",
    "verify_chain",
    "list_meters",
    "list_events",
    "usage_timeseries",
    "flag_meter"
  ],
  "inputs": {
    "action": "str",
    "meter_id": "str",
    "event_id": "str",
    "quantity": "number",
    "outcome": "ok|error",
    "provider": "str",
    "consumer": "str",
    "unit": "str",
    "price_minor_per_unit": "number",
    "consumer_class": "internal|external|unknown (trusted writer only)",
    "channel": "str (trusted writer only)",
    "is_test": "bool",
    "include_test": "bool",
    "bucket": "day|hour",
    "cursor": "str",
    "limit": "int"
  },
  "outputs": {
    "status": "str (ok|error)",
    "data": "dict"
  },
  "a2a_role": "metering"
}
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

This server is one of the fleet's shared rails, so on the hosted endpoint a tool that changes records needs a caller credential (`Authorization: Bearer <token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns HTTP 401 and nothing changes. Read-only tools never need one. To get a credential, email <justin@viridisconservation.com>, or self-host from the source folder, where no credential applies.

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`agent-metering-agent/`](../../agent-metering-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
