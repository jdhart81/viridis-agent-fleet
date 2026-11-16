# io.github.jdhart81/agent-arbitration

[![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-arbitration)](https://mcptry.com/servers/io.github.jdhart81/agent-arbitration)

Dispute-resolution oracle for A2A escrows: deterministic, evidence-weighted, machine-verifiable rulings that close the DISPUTED -> resolved loop.

| | |
|---|---|
| Registry name | `io.github.jdhart81/agent-arbitration` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/arbitration/mcp` |
| Version | 0.2.1 |
| Tools | 8 |
| Source | [`agent-arbitration-agent/`](../../agent-arbitration-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-agent-arbitration": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/arbitration/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-agent-arbitration https://mcp.viridisconservation.com/arbitration/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `file_case`

File a dispute over an escrow. Opens the evidence window. Parties must be distinct; amount is in minor currency units (cents).

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `amount_minor` | integer | yes | Disputed amount in minor units (cents), a whole number. |
| `claimant` | string | yes | Agent id of the party bringing the dispute. |
| `escrow_id` | string | yes | The disputed escrow's id, from the escrow server. |
| `respondent` | string | yes | Agent id of the other party. Must differ from the claimant. |

### `submit_evidence`

Submit evidence while the case is open. kind: delivery_proof (weight 3), log (2), or statement (1). Only the named parties may submit.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `case_id` | string | yes | The case id returned by file_case. |
| `content` | string | no | The evidence itself, or a reference or hash pointing to it. |
| `kind` | string | yes | Evidence type: delivery_proof (weight 3), log (2) or statement (1). |
| `party` | string | yes | Agent id of the submitting party; must be the claimant or respondent. |

### `set_trust_scores`

Attach trust-oracle reputation scores (party -> [0,1]) as ruling inputs.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `case_id` | string | yes | The case id returned by file_case. |
| `scores` | object | yes | Trust scores by party, each between 0 and 1, for example {"agent-a": 0.8}. |

### `rule`

Issue the deterministic ruling: allocates 100% of the disputed amount from evidence weights + trust scores, and emits an escrow instruction (release/refund). Exactly-once — re-ruling returns the existing ruling.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `case_id` | string | yes | The case id returned by file_case. |

### `verify_ruling`

Recompute the ruling from its cited evidence + trust inputs and check it matches the stored allocation (machine-checkable justice).

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `case_id` | string | yes | The case id returned by file_case. |

### `get_case`

Fetch the full case record, including any ruling.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `case_id` | string | yes | The case id returned by file_case. |

### `list_cases`

List cases, optionally filtered by state (FILED|EVIDENCE_OPEN|RULED).

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `state` | string | no | Optional filter: FILED, EVIDENCE_OPEN or RULED. |

### `describe_agent`

Describe this agent: name, version, purpose, every action it supports and the inputs each one takes. Read-only and free; call it first to learn how to use this server.

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
  "name": "agent-arbitration-agent",
  "version": "0.2.0",
  "description": "Deterministic, machine-verifiable dispute resolution for A2A escrows (closes DISPUTED -> resolved).",
  "capabilities": [
    "file_case",
    "submit_evidence",
    "set_trust_scores",
    "rule",
    "verify_ruling",
    "get_case",
    "list_cases"
  ],
  "inputs": {
    "action": "str",
    "case_id": "str",
    "escrow_id": "str",
    "claimant": "str",
    "respondent": "str",
    "amount_minor": "int",
    "party": "str",
    "kind": "delivery_proof|log|statement",
    "scores": "dict[party, 0..1]"
  },
  "outputs": {
    "status": "str (ok|error)",
    "data": "dict"
  },
  "a2a_role": "arbitration"
}
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

This server is one of the fleet's shared rails, so on the hosted endpoint a tool that changes records needs a caller credential (`Authorization: Bearer <token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns HTTP 401 and nothing changes. Read-only tools never need one. To get a credential, email <justin@viridisconservation.com>, or self-host from the source folder, where no credential applies.

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`agent-arbitration-agent/`](../../agent-arbitration-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-16T23:45:07Z).*
