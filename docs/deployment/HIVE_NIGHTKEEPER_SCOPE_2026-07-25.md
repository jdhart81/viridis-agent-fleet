# Hive Nightkeeper scope and conversion-control refresh

**Activated:** 2026-07-25 MDT / 2026-07-26 UTC

**Money moved:** None

## Outcome

The live Agent Hive Orchestrator is now covered by three operating layers:

1. `run_fleet_tests.py` treats
   `agent-hive-orchestrator-agent` as a required suite. If its test directory
   disappears, the fleet/Nightkeeper gate fails instead of silently shrinking.
2. The N70 Cross-Pollination Queue and current Morning Brief explicitly require
   read-only Hive commerce checks.
3. Both active distribution automations understand the live Hive contract and
   the current commercial goal.

## Nightkeeper contract

Nightkeeper must pin and monitor:

- x402 route `/x402/hive/solve`;
- A2A skill `hive.solve`;
- fixed price $5.00 / 5,000,000 atomic Base USDC;
- zero provider-backed execution free calls; read-only tools and unpaid
  quote/preflight remain free;
- contribution-margin floor at least 35%;
- exclusion from one-cent introductory pricing;
- paid preflight before quote or task creation;
- paid preflight recheck immediately before settlement;
- refusal before payment, facilitator, model, escrow, or job mutation when
  cost bounds or provider readiness fail;
- `rails_mode=wired`;
- three registered solvers;
- provider readiness;
- Hive jobs and settlements reported separately.

Monitoring must never sign a payment, invoke a live provider, create a Hive
job, or manufacture a customer task.

For every `next_paid_routes` offer, Nightkeeper must also pin the executable
continuation contract: `mcp_endpoint`, `description`, `input_schema`,
`input_example`, `required_buyer_inputs`, and `quote`. The quote must require a
fresh unpaid HTTP 402 preflight and name `next_route_unpaid_http_402` as the
authoritative source. The catalog's list price is informative, not authority
to spend.

## Conversion-control refresh

The active `viridis-daily-flywheel-distribution` and
`viridis-community-reply-monitor` automations previously targeted payer gates
that live telemetry had already passed. Their prompts now prioritize:

- the first genuine repeat external purchase;
- the first paid result independently judged useful;
- repeatable MRR after those two proofs.

A fourth distinct payer is welcome but does not substitute for repeat or
usefulness. Both automations fail closed against synthetic payments, friendly
test traffic, fake reviews, synthetic Hive jobs, unauthorized Discord
automation, unsolicited follow-ups, and margin leakage.

## Verification

Local required-suite pin:

- focused contract test: 1 passed;
- full fleet: 1,510 passed, 0 failed, 0 errors;
- suites: 34/34 clean;
- Hive suite: 42 passed;
- gateway suite: 436 passed;
- scripts suite: 10 passed.

Live read-only evidence at `2026-07-26T01:36:10Z`:

- gateway health: `ok`;
- mount errors: none;
- hosted agents: 27 healthy;
- Hive: wired rails, three solvers, provider ready, zero jobs;
- x402 catalog: six routes;
- Hive amount: 5,000,000 atomic Base USDC;
- A2A Agent Card: six skills including `hive.solve`;
- A2A tasks: one input-required, zero working, zero completed, zero failed;
- Hive settlements: zero;
- Hive external revenue: zero.

The single input-required task was traced read-only through pickle opcode
inspection, without deserializing or mutating production state. It is
Regulatory Radar task `151bd125-e2f2-4ee2-b073-be0b103b2c77`, created
`2026-07-20T22:48:55.245215+00:00` by message
`smoke-challenge-20260720` for
`regulatory-radar.scan_regulations`. It is a known fleet smoke artifact, not
Hive interest or an unidentified external buyer.

No paid route, model provider, facilitator, signature, escrow, customer job,
or outbound message was invoked for this verification.

## Commercial boundary

Live strict HTTP x402 truth remains:

- seven settlements total;
- four self settlements;
- three external settlements;
- three distinct external payers;
- zero repeat external purchases;
- 270,000 atomic USDC / $0.27 external revenue;
- zero Hive settlements and zero Hive jobs;
- zero active subscriptions and $0 MRR.

The unpaid A2A input-required task is the known 2026-07-20 Regulatory Radar
smoke challenge. It is not a paid job, completed delivery, Hive task, external
buyer, repeat purchase, or revenue.
