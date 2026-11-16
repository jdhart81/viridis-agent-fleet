# io.github.jdhart81/agent-escrow

Trustless escrow & settlement for agent-to-agent (A2A) transactions. Funds sit in escrow until delivery is verified, then release or refund — with an exactly-once state machine and a tamper-evident audit chain.

| | |
|---|---|
| Registry name | `io.github.jdhart81/agent-escrow` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/escrow/mcp` |
| Version | 0.1.4 |
| Tools | 9 |
| Source | [`agent-escrow-agent/`](../../agent-escrow-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-agent-escrow": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/escrow/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-agent-escrow https://mcp.viridisconservation.com/escrow/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `open_escrow`

Open an escrow between payer and payee. amount_minor is a positive integer in minor units (cents). The platform fee is computed and FROZEN at open (ceil bps). Returns the escrow_id (state OPEN). RETRY-SAFE: pass …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `amount_minor` | integer | yes | Escrow amount in minor units (cents), a positive whole number. |
| `currency` | string | no | ISO 4217 currency code, for example USD. |
| `deadline` | string | no | Optional. Delivery deadline, ISO-8601. |
| `fee_bps` | integer | no | Optional. Platform fee in basis points; fixed when the escrow opens. |
| `open_ref` | string | no | Optional but recommended. Your job id; repeating it returns the same escrow. |
| `payee` | string | yes | Agent id of the party paid on release. |
| `payer` | string | yes | Agent id of the party paying into escrow. |
| `terms` | string | no | Optional. The agreed deliverable, in words or as a reference. |

### `fund_escrow`

Mark an OPEN escrow as FUNDED (idempotent). payment_ref links the payment-rail transaction.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `escrow_id` | string | yes | The escrow id returned by open_escrow. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |

### `release_escrow`

Release a FUNDED/DISPUTED escrow to the payee (exactly-once — a repeat release returns the existing terminal record, never a double payout).

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `delivery_proof` | string | no | Optional. Proof of delivery, for example the notary's delivery_proof. |
| `escrow_id` | string | yes | The escrow id returned by open_escrow. |

### `refund_escrow`

Refund an OPEN/FUNDED/DISPUTED escrow to the payer (exactly-once). Refunding an OPEN escrow is a cancel.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `escrow_id` | string | yes | The escrow id returned by open_escrow. |
| `reason` | string | no | Optional. A short note of why, kept on the record. |

### `dispute_escrow`

Move a FUNDED escrow to DISPUTED. An arbiter (agent-arbitration-agent) then resolves it to release or refund.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `escrow_id` | string | yes | The escrow id returned by open_escrow. |
| `reason` | string | no | Optional. A short note of why, kept on the record. |

### `escrow_status`

Current record for an escrow.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `escrow_id` | string | yes | The escrow id returned by open_escrow. |

### `list_escrows`

List escrows, optionally filtered by state (OPEN|FUNDED|RELEASED|REFUNDED|DISPUTED).

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `state` | string | no | Optional filter: OPEN, FUNDED, RELEASED, REFUNDED or DISPUTED. |

### `verify_audit`

Validate the tamper-evident audit hash chain for an escrow.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `escrow_id` | string | yes | The escrow id returned by open_escrow. |

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
  "name": "agent-escrow-agent",
  "version": "0.1.3",
  "description": "Trustless escrow & settlement for agent-to-agent transactions.",
  "capabilities": [
    "open",
    "fund",
    "release",
    "refund",
    "dispute",
    "status",
    "list",
    "verify_audit"
  ],
  "inputs": {
    "action": "str",
    "payer": "str",
    "payee": "str",
    "amount_minor": "int",
    "currency": "str (optional)",
    "escrow_id": "str (for state ops)"
  },
  "outputs": {
    "status": "str (ok|error)",
    "data": "dict",
    "error": "str (optional)"
  },
  "a2a_role": "settlement"
}
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

This server is one of the fleet's shared rails, so on the hosted endpoint a tool that changes records needs a caller credential (`Authorization: Bearer <token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns HTTP 401 and nothing changes. Read-only tools never need one. To get a credential, email <justin@viridisconservation.com>, or self-host from the source folder, where no credential applies.

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`agent-escrow-agent/`](../../agent-escrow-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
