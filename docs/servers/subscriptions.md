# io.github.jdhart81/subscriptions

[![mcptry](https://mcptry.com/badge/io.github.jdhart81/subscriptions)](https://mcptry.com/servers/io.github.jdhart81/subscriptions)

Verified monthly-seat catalog, account attribution, quota, overage, and MRR infrastructure.

| | |
|---|---|
| Registry name | `io.github.jdhart81/subscriptions` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/subscriptions/mcp` |
| Version | 0.1.2 |
| Tools | 10 |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-subscriptions": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/subscriptions/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-subscriptions https://mcp.viridisconservation.com/subscriptions/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `list_plans`

List the versioned monthly-seat catalog, exact prices/coverage, catalog SHA-256, readiness flags, and pending owner-confirmation notice.

*read-only; structured output*

No inputs.

### `get_plan`

Get one exact monthly plan and its versioned catalog lineage.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `plan_id` | string | yes | Plan id, for example starter-seat; see list_plans. |

### `create_account`

Create a free account for bearer attribution. The full account key is returned once; only its SHA-256 and last four characters are retained.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `account_ref` | string | yes | Your reference for the account, for example an email address. |

### `create_checkout_link`

Prepare a Stripe-hosted subscription Checkout URL. It never charges a card. Draft plans, missing owner approval, unavailable covered agents, or missing recurring Price IDs fail closed without creating a session.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `account_ref` | string | yes | Your reference for the account, for example an email address. |
| `plan_id` | string | yes | Plan id, for example starter-seat; see list_plans. |

### `record_subscription`

Pull-verify a Stripe session/subscription and idempotently activate its exact subscription period. A newly created account receives its key once.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `stripe_session_or_sub_id` | string | yes | The Stripe Checkout session id or subscription id. |

### `subscription_status`

Return bearer-owned subscription lifecycle and current-period quota. The account key is always masked in output.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | The account id. Send the account key as the bearer token. |

### `customer_portal_link`

Return a bearer-owned Stripe-hosted billing-portal URL. The human manages or cancels there; this tool never moves money.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | The account id. Send the account key as the bearer token. |

### `usage_summary`

Return bearer-owned, period-resolved included and overage usage with exact catalog lineage and conservation totals.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | The account id. Send the account key as the bearer token. |

### `mrr_summary`

Return aggregate active live-mode subscription count, MRR minor units, and plan mix. No account or Stripe identifiers are exposed.

*read-only; structured output*

No inputs.

### `describe_agent`

Return the fleet-standard version, catalog digest, security posture, lifecycle policy, and capabilities.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-16):

```json
{
  "name": "describe_agent",
  "arguments": {}
}
```

Response (shortened):

```json
{
  "name": "subscriptions-agent",
  "version": "0.1.1",
  "description": "Deterministic account, verified monthly-seat, quota, overage, and MRR infrastructure.",
  "capabilities": [
    "list_plans",
    "get_plan",
    "create_account",
    "create_checkout_link",
    "record_subscription",
    "subscription_status",
    "customer_portal_link",
    "usage_summary",
    "mrr_summary",
    "retention_summary"
  ],
  "security": {
    "account_auth": "bearer account_key",
    "stored_key": "sha256 + last4 only",
    "stripe_secret_handling": "none",
    "money_movement": "Stripe-hosted human action only"
  },
  "entitlement": {
    "past_due_grace": "none",
    "period": "[current_period_start,current_period_end)",
    "error_path": "existing per-call freemium"
  },
  "plan_catalog": {
    "version": "0.4.0",
    "sha256": "8f4149acf0c4176b1ee88e392087abc96a1e2b694c7d03fa2394d6223e0c47f9"
  },
  "a2a_role": "subscription-entitlement-infrastructure"
}
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

This server is one of the fleet's shared rails, so on the hosted endpoint a tool that changes records needs a caller credential (`Authorization: Bearer <token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns HTTP 401 and nothing changes. Read-only tools never need one. To get a credential, email <justin@viridisconservation.com>, or self-host from the source folder, where no credential applies.

## Hosted service and this repository

This server is operated by Viridis; its hosted adapter is not in this repository. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-16T23:45:07Z).*
