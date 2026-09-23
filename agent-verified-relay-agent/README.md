# Viridis Verified — agent-verified-relay-agent

Wrap any MCP server with consequences.

The agent economy has payments (x402) and identity (ERC-8004). What it lacks
is *evidence with teeth*: proof of what was asked, what was delivered, and a
neutral chain a dispute can be settled from. Viridis Verified relays
`tools/call` to any registered third-party MCP server and notarizes every
exchange into a tamper-evident receipt chain — request hash, response hash,
outcome, latency — metered and billable per call.

```
register_service(url, provider)          -> vsvc-… (content-addressed, idempotent)
call_verified(service_id, tool, call_id) -> result + receipt (hash-chained)
verify_receipts(service_id)              -> full chain + fee ledger recomputation
```

Receipts compose with the rest of the Viridis rails: surety underwriting
(`price_bond`, model uw-v1) prices a bond behind a provider from its receipt
history; arbitration rules from receipts; trust decays or compounds on them.

Ten invariants (V1–V10), one test each — see `src/core.py`. Stdlib-only core.

Part of the [Viridis Agent Fleet](https://mcp.viridisconservation.com) —
usage stats at `/stats`, fleet health at `/healthz`.
