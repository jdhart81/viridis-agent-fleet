# io.github.jdhart81/agent-hive-orchestrator

[![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-hive-orchestrator)](https://mcptry.com/servers/io.github.jdhart81/agent-hive-orchestrator)

Deterministic nested hive-mind orchestration: hire, cross-review, synthesize, and settle N solver agents through the A2A rails

| | |
|---|---|
| Registry name | `io.github.jdhart81/agent-hive-orchestrator` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/hive/mcp` |
| Version | 0.1.5 |
| Tools | 6 |
| Source | [`agent-hive-orchestrator-agent/`](../../agent-hive-orchestrator-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-agent-hive-orchestrator": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/hive/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-agent-hive-orchestrator https://mcp.viridisconservation.com/hive/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `solve`

Open and run a hive job in one call: hire solvers through the rails (covenant -> escrow -> meter), force reviewer!=author cross-review, synthesize only what survives review, settle every escrow exactly-once, and return …

*changes records; may need a caller credential (see below); $5.00 per call after the free daily calls (x402 catalog); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `accept_threshold` | number | no | Optional. Minimum review score, 0 to 1, for a contribution to count. |
| `budget_minor` | integer | yes | Total budget for hired solvers in minor units (cents). |
| `covenant_id` | string | no | Optional. A covenant that authorizes the spend. |
| `depth` | integer | no | Optional. How many levels of sub-decomposition to allow. Default 0. |
| `fee_bps` | integer | no | Optional. Fee in basis points on each escrow. Default 0. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |
| `problem` | string | yes | The problem to solve, in plain words. |
| `redundancy` | integer | no | Optional. Solvers hired per subtask, for cross-review. Default 2. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |
| `seed` | integer | no | Optional. Seed for deterministic planning, so a rerun gives the same plan. |
| `subtasks` | array | no | Optional. Your own split of the problem into subtasks. |

### `job_status`

Return job state, plan hash, and live budget conservation books.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `job_id` | string | yes | The job id returned by solve. |

### `audit_job`

Return the full content-addressed lineage of a completed job: plan, hires (including refused ones with reasons), contributions, reviews, settlements, rail calls (with simulated flags), and synthesis.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `job_id` | string | yes | The job id returned by solve. |

### `verify_audit`

Recompute the audit digest from a presented lineage (never trusts the embedded hash) and report whether it matches a job this hive ran.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `audit_json` | string | yes | The lineage from audit_job, as a JSON string, unchanged. |

### `list_solvers`

List the registered solver pool: id, kind (worker|hive), price, capabilities.

*read-only; structured output*

No inputs.

### `describe_agent`

Return fleet-standard capabilities, actions, invariants, and pricing.

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
  "name": "agent-hive-orchestrator-agent",
  "version": "0.1.4",
  "description": "Deterministic nested hive-mind orchestration: hire N solvers through covenant/escrow/meter, adversarial cross-review, honest synthesis, carbon-accounted, content-addressed audit.",
  "capabilities": [
    "hive-orchestration",
    "nested-composition",
    "adversarial-review",
    "a2a-settlement",
    "bits-per-joule-telemetry"
  ],
  "actions": [
    "open_job",
    "run_job",
    "solve",
    "job_status",
    "audit_job",
    "verify_audit",
    "list_solvers"
  ],
  "invariants": [
    "H1-budget-conservation",
    "H2-deny-by-default",
    "H3-determinism",
    "H4-reviewer-not-author",
    "H5-settlement-closure",
    "H6-emergence-honesty",
    "H7-thermodynamic-accounting",
    "H8-fail-safe",
    "H9-recompute-in-verify",
    "H10-standalone-honesty"
  ],
  "rails_mode": "wired",
  "pricing": {
    "model": "premium per solve; sub-hires settle through escrow at solver list price",
    "free_per_day": 0,
    "usd_per_solve": 5.0,
    "free_scope": "no free model-backed execution; read-only tools and unpaid preflight remain free",
    "service_price_minor": 500,
    "currency": "USD",
  …
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

This server is one of the fleet's shared rails, so on the hosted endpoint a tool that changes records needs a caller credential (`Authorization: Bearer <token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns HTTP 401 and nothing changes. Read-only tools never need one. To get a credential, email <justin@viridisconservation.com>, or self-host from the source folder, where no credential applies.

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`agent-hive-orchestrator-agent/`](../../agent-hive-orchestrator-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
