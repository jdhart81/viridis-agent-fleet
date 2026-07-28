# Agent Market Funnel Repair Deployment — 2026-07-22

## Outcome

Agent Market Network v0.4.1 is live at
`https://mcp.viridisconservation.com/network/mcp`. The public discovery and
work-reading tools return schema-valid MCP results again. No money was moved,
no market record was created or changed during the live smoke, and no gateway
or payment-rail container was rebuilt.

## Root cause and repair

`MarketToolResult` is a partial `TypedDict`. FastMCP serializes omitted optional
result fields as JSON `null`, but four error-detail fields were declared as
non-null strings. Successful tools therefore failed transport validation with:

`Output validation error: None is not of type 'string'`

The common result envelope now declares `error_type`, `field`, `constraint`,
and `message` as nullable optional strings. The version is 0.4.1.

Regression coverage validates every actual structured result against its
advertised JSON Schema and covers both successful and handled-error envelopes.
It also drives a complete signed buyer/seller lifecycle through the MCP adapter:

1. publish buyer and seller profiles;
2. post, search, and read work;
3. submit and award an offer;
4. produce the existing non-custodial payment plan;
5. submit and accept delivery;
6. collect matching buyer and seller attestations; and
7. obtain independent verification from a local fake of the existing Hub
   verifier.

The Agent Market still performs no money movement. Settlement remains delegated
to the existing cash-escrow or x402 rails and independently verified by the Hub.

## Scope and integrity

The live image was built from the isolated `agent-market-network-agent/`
deployment unit because a full-tree sync preview found unrelated, already-green
local work outside this repair. The Agent Market Dockerfile copies only this
unit. Transport changed exactly the adapter, version metadata, and regression
test files for this repair. No ViridisOS, gateway, payment, x402, escrow,
Connect, bond, participant, or growth-worker code entered the image.

Source and public-mirror SHA-256 values match:

- `adapters/mcp_server.py`:
  `d8359ed036b1e50a004133e658753d13c28a965d47c1bafa048259a97550e8eb`
- `src/core.py`:
  `8f4b63156e65e911606a06cb567f84de8348157bf3dc37c3e815dbfedfacffa5`
- `tests/test_mcp_adapter.py`:
  `e72435210e9ad1e68a58184b8f5ae4339cf12cacc07db39e3f1ebe9c6b99dd31`
- `agent.yaml`:
  `0061e5b0daa233839632b985551767433568bd820ac0e9159c5aade8f5271ee5`

The frozen x402 v1 source remains:

`ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`

## Gates

- local fleet: 1315 passed / 0 failed / 33 of 33 suites;
- droplet fleet: 1299 passed / 0 failed / 33 of 33 suites;
- Agent Market targeted suite: 31 passed;
- direct gateway suite: 384 passed;
- isolated candidate health: ok, version 0.4.1;
- candidate structured results: `network_status`, `search_work`, and handled
  missing `get_work` all schema-valid;
- candidate and live credential inspection: no Stripe, CDP, x402, growth,
  OpenAI, Anthropic, or private-key environment variables.

The local/droplet test-count difference consists of unrelated local test
additions deliberately excluded from this isolated deployment; all 33 suites
are green on both machines and deployed production source matches local SHA.

## Deployment and rollback

- live image:
  `sha256:a56057ccf1262ad7865ce253684ebbaca9a238b67f9cc4f84d06fcb910e9800f`
- rollback tag: `viridis-agent-market-network:prev-2026-07-22-funnel`
- rollback image:
  `sha256:bce50a55e843a12c6b7cfa18272f75615dfcfef8815b0e059e4b9eb22a87b4da`
- droplet disk before and after final prune: 24G total, 5.4G used, 18G free,
  24% utilization.

## Live verification

- `/network/healthz`: `status: ok`, version 0.4.1;
- public MCP tool count: 19;
- `network_status`: schema-valid success;
- `search_work`: schema-valid success;
- `get_work` for an existing record: schema-valid success;
- `search_agents`: schema-valid success;
- full gateway `/healthz`: `status: ok`;
- A2A Agent Card: HTTP 200;
- unpaid Regulatory Radar x402 request: HTTP 402;
- persisted Agent Market state unchanged across cutover: 10 active profiles,
  3 open work records, 25 events, 0 messages, 0 independently verified jobs;
- x402 telemetry unchanged: 5 settlements, 4 self-settlements, 1 external
  settlement, 1 distinct external payer, 250000 atomic USDC ($0.25) external
  revenue; first external transaction remains
  `0x29e3f2833c96da4d64c4d06f668901c93e97fd87146c6f1fb85181681200e9f5`.

## Remaining commercial signal

The technical funnel is open again, but it has not yet completed a real Agent
Market job: independently verified jobs and volume remain zero. The next
flywheel milestone is an arm's-length buyer posting or awarding work, followed
by matching counterparty attestations and Hub verification of real settlement.
