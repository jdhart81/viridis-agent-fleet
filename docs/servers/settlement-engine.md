# io.github.jdhart81/settlement-engine

Progressive-settlement engine that reports what an officially published series has already decided and settles outcome contracts on it with recomputable evidence

| | |
|---|---|
| Registry name | `io.github.jdhart81/settlement-engine` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/settlement-engine/mcp` |
| Version | 0.1.0 |
| Tools | 12 |
| Source | [`settlement-engine-agent/`](../../settlement-engine-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-settlement-engine": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/settlement-engine/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-settlement-engine https://mcp.viridisconservation.com/settlement-engine/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `register_series`

FREE: declare a progressively published series. aggregate: mean (prices), sum (totals), share (survival/success 0/1 per slot), last (closing value). n_expected: number of observation slots in the period. …

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `aggregate` | string | yes | mean, sum, share or last. |
| `meta` | object | no | Optional. Extra description of the series. |
| `n_expected` | integer | yes | Number of observation slots in the period. |
| `name` | string | yes | Name of the series. |
| `period_end` | string | yes | Period end, ISO-8601. |
| `period_start` | string | yes | Period start, ISO-8601. |
| `source` | string | yes | Where observations are published. |
| `strikes` | array | no | Optional. Values of interest for the aggregate. |
| `unit` | string | yes | Unit of one observation, for example USD or percent. |
| `value_max` | number | no | Optional. Highest physically possible value of one observation. |
| `value_min` | number | no | Optional. Lowest physically possible value of one observation. |

### `ingest`

FREE: append observations [{slot, value, source_url, source_sha256 (64 hex of the source document), observed_at}]. A re-posted slot replaces the value and is logged as a revision (S7). Each observation is hashed (S4).

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `observations` | array of object | yes | [{slot, value, source_url, source_sha256, observed_at}]. |
| `series_id` | string | yes | The series id returned by register_series. |

### `period_status`

FREE: published share, published aggregate, remaining slots, and per strike the required remainder, the decided flag (arithmetic + declared bounds only) and a labelled model estimate kept separate from the facts (S1).

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `series_id` | string | yes | The series id returned by register_series. |

### `required_remainder`

FREE: what the remaining slots must average / sum to / hit for the aggregate to reach the strike, plus decided.

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `series_id` | string | yes | The series id returned by register_series. |
| `strike` | number | yes | The strike value. |

### `decided_strikes`

FREE: every strike across registered series that is decided by the published part alone.

*changes records; structured output*

No inputs.

### `explain`

FREE: deterministic plain-language reading of a series (no LLM in the serving path).

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `series_id` | string | yes | The series id returned by register_series. |

### `list_series`

FREE: registered series cards.

*changes records; structured output*

No inputs.

### `compile_contract`

PAID: compile a Verified Outcome Contract v0 — a series, a strike, a settlement rule (above | at_or_above | below | at_or_below) and a closing time, content-addressed; the contract_id is the sha256 of its canonical form.

*changes records; $1.00 per call after the free daily calls (x402 catalog); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `closes_at` | string | yes | When the contract closes, ISO-8601. |
| `parties` | object | no | Optional. The parties, as an object. |
| `rule` | string | yes | above, at_or_above, below or at_or_below. |
| `series_id` | string | yes | The series id returned by register_series. |
| `strike` | number | yes | The strike value. |
| `terms` | string | no | Optional. Contract terms in words. |

### `get_contract`

FREE: a compiled contract and its settlement ids.

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `contract_id` | string | yes | The contract id returned by compile_contract. |

### `settle_contract`

PAID: evaluate a contract against the ledger at an explicit time: YES / NO / UNDECIDED with the exact arithmetic and every observation hash used. A decided strike settles before closure; an incomplete, undecided series …

*changes records; $1.00 per call after the free daily calls (x402 catalog); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `contract_id` | string | yes | The contract id returned by compile_contract. |
| `now` | string | yes | The evaluation time, ISO-8601. |

### `verify_settlement`

FREE: recompute a settlement from its stored evidence (hash, aggregate, result each checked separately).

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `settlement` | object | no | A settlement object; give this or settlement_id. |
| `settlement_id` | string | no | A settlement id; give this or the settlement object. |

### `describe_agent`

FREE: actions, invariants S1–S10 and limits.

*changes records; structured output*

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
  "ok": true,
  "name": "settlement-engine-agent",
  "version": "0.1.0",
  "model_version": "remainder-v0-trailing-normal",
  "actions": {
    "free": [
      "register_series",
      "ingest",
      "period_status",
      "required_remainder",
      "decided_strikes",
      "explain",
      "verify_settlement",
      "list_series",
      "get_contract",
      "describe"
    ],
    "paid": [
      "compile_contract",
      "settle_contract"
    ]
  },
  "invariants": [
    "S1 facts/model separate",
    "S2 deterministic",
    "S3 no trading/keys/network",
    "S4 observations are evidence",
    "S5 decided means decided",
    "S6 never raises",
    "S7 revisions visible",
    "S8 settlement recomputable",
    "S9 bounded",
    "S10 closure declared"
  ],
  "limits": {
    "max_series": 2000,
    "max_slots": 50000,
    "max_strikes": 64,
    "max_contracts": 20000
  …
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`settlement-engine-agent/`](../../settlement-engine-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
