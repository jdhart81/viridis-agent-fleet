# Official A2A Python SDK interoperability receipt

**Date:** 2026-07-25

**SDK:** `a2a-sdk==1.1.2`

**Result:** PASS without a wallet, settlement, tool execution, or production
task write

## Outcome

The released official A2A Python SDK can consume the Viridis A2A 1.0 seller
surface through its normal Agent Card resolver, HTTP+JSON transport, protobuf
message types, and client factory. This closes a buyer-runtime compatibility
gap that the existing handcrafted JSON handler tests did not cover. No
protocol defect was found.

## Live read-only discovery

The official `A2ACardResolver` fetched and parsed
`https://mcp.viridisconservation.com/.well-known/agent-card.json`.

| Field | Parsed value |
|---|---|
| agent | `Viridis Carbon and Compliance Commerce Agent` |
| interface | `https://mcp.viridisconservation.com/a2a` |
| binding | `HTTP+JSON` |
| protocol version | `1.0` |
| skills | `5` |
| required extension | `https://github.com/google-a2a/a2a-x402/v0.1` |

This operation was one public GET. It created no seller task or other
production state.

## Isolated full client-to-seller proof

The same SDK ran against an in-memory Starlette application built from the
production `gateway/a2a_commerce.py` handlers. It resolved the generated Agent
Card, selected HTTP+JSON, constructed the official protobuf message types,
activated the x402 extension, and sent this structured input:

```json
{
  "skillId": "regulatory-radar.scan_regulations",
  "input": {"jurisdiction": "EU", "sector": "energy"}
}
```

The returned event proved:

| Gate | Result |
|---|---|
| A2A task state | `TASK_STATE_INPUT_REQUIRED` |
| payment state | `payment-required` |
| x402 version | `2` |
| scheme / network | `exact` / `eip155:8453` |
| asset | official Base USDC |
| tool executions | `0` |
| local durable saves | `1` |
| production writes | `0` |
| signatures / settlements | `0 / 0` |

The seller produced the requirements from its real price, schema, and x402-v2
builder. The tool remained behind the settle-before-serve boundary.

## Buyer artifact

- `scripts/a2a_quote_client.py` defaults to read-only Agent Card discovery.
- Explicit `--request-quote` creates exactly one unpaid durable task.
- The script has no private-key import, payment signing, submission, or paid
  retry.
- `docs/integrations/A2A_PYTHON_SDK_QUICKSTART.md` provides copyable install
  and operation instructions.
- Offline regressions cover card selection, protobuf-to-JSON quote extraction,
  and the default read-only posture.

The default live command passed against production:

```bash
uv run --no-project --with "a2a-sdk==1.1.2" \
  python scripts/a2a_quote_client.py
```

## Commercial boundary

This is independent client implementation proof, not independent demand. It
created no purchase, external payer, completed job, repeat purchase, or
revenue.

Live money truth remains 6 strict settlements, 4 self, 2 external, 2 distinct
external payers, 0 repeat external purchases, 260,000 atomic USDC ($0.26)
external revenue, and $0 MRR. The next business gate remains a third
independent payer or the first genuine repeat external purchase.
