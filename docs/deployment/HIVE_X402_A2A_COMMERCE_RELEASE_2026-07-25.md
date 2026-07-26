# Hive x402 and A2A commerce release

**Released:** 2026-07-25 MDT / 2026-07-26 UTC

**Outcome:** Live and public

**Money moved:** None

## Product outcome

The Agent Hive Orchestrator is now directly purchasable by autonomous buyers
through both public commerce surfaces:

- HTTP x402 v2:
  `POST https://mcp.viridisconservation.com/x402/hive/solve`;
- A2A 1.0:
  skill `hive.solve` at
  `https://mcp.viridisconservation.com/a2a/message:send`.

The fleet now advertises six paid routes: the existing five-step deterministic
carbon/compliance chain plus the separate reviewed Hive product.

Hive remains exactly $5.00, or 5,000,000 atomic Base USDC. It is explicitly
excluded from the one-cent introductory schedule because a solve carries real
provider and sub-hire settlement costs.

## Fail-before-pay controls

The MCP-only validator was not sufficient for HTTP/A2A commerce because those
surfaces intentionally execute through the post-settlement ungated core. The
release adds an agent-owned, side-effect-free paid preflight hook that both
commerce surfaces call before creating a quote and again immediately before
settlement.

The fixed public profile enforces:

- `budget_minor=500`;
- `depth=0`;
- `fee_bps=0`;
- at most four non-empty subtasks;
- redundancy from one through three;
- bounded prompt composition;
- finite review threshold in `(0,1]`;
- integer seed; and
- configured solver-provider readiness.

Validation or provider-readiness refusal creates no payment task, calls no
facilitator, opens no escrow, mutates no Hive job, and returns no payment
header. A provider disappearing between an A2A quote and submitted payment is
rechecked before settlement.

The existing settlement order remains unchanged:

`preflight -> quote -> verify -> settle -> persist receipt -> execute`.

Payment replays remain exactly-once and never execute a second solve.

## Economics

The previously released cost envelope is unchanged:

- list price: $5.00;
- maximum solver settlements: $3.00;
- conservative provider API ceiling: below $0.18;
- minimum contribution margin: at least $1.82, or 36.4%, before fixed
  infrastructure, taxes, refunds, and payment fees.

No live model request or paid smoke was used for this release.

## Verification

- focused Hive/x402/A2A tests: 80 passed;
- gateway suite: 436 passed;
- full local fleet: 1,509 passed, 0 failed, 34/34 suites;
- full production-source fleet with narrow provider readiness:
  1,509 passed, 0 failed, 34/34 suites;
- isolated candidate image: health OK, six A2A skills, exact 5,000,000-atomic
  unpaid Hive challenge;
- public cache-busted smoke: 27 agents, six x402 routes, six A2A skills,
  exact Hive amount, and invalid budget returns HTTP 400 with no payment
  header;
- provider calls: zero;
- money moved: none.

## Production and recovery

Production image:

`sha256:7830f28236d8e081681ca425dcc27f5423c8a0f894f1d8e355ffe1bd3f3cf416`

Rollback tag:

`viridis-stable:prev-2026-07-25-hive-commerce`

Rollback image:

`sha256:19e9c3fbc9be23410d66cfa71950b454a4e285ebe47c13e8b971b829a3cccac9`

Authoritative pre-release database backup:

- container:
  `/data/backups/viridis_state-20260726T005556Z-hive-commerce-safe.db`;
- SHA-256:
  `c8a3501767e0522e6d8487967a60c9b6d648d151aded14c28036221573c39c7a`;
- integrity: `ok`;
- rows: 33;
- off-droplet:
  `production-backups/2026-07-25/viridis_state-pre-hive-commerce-safe-20260726T005556Z.db`;
- current-code compatibility: all 33 rows load, zero errors.

A raw filesystem copy made before the transactional backup was rejected as
authoritative: it was internally valid but contained only 32 rows because the
live SQLite database uses WAL mode. The accepted backup was created with
SQLite's transactional backup API and independently verified off the droplet.

The live database remains integrity `ok` with 33 rows. Disk remained 25% used
with 18 GB free. Only the gateway container was recreated; Caddy and Agent
Market were not restarted.

## Revenue boundary

Release verification left strict commercial truth unchanged:

- seven strict settlements;
- four self settlements;
- three external settlements from three distinct external payers;
- zero repeat external purchases;
- 270,000 atomic USDC, or $0.27, external revenue;
- zero Hive settlements and zero Hive jobs;
- zero active subscriptions and $0 MRR.

This release creates buyer access and protects margin. It is not proof of
demand, repeat purchase, or subscription revenue.
