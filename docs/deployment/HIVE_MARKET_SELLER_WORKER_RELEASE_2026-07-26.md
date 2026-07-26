# Hive Agent Market seller worker release — 2026-07-26

## Outcome

The production gateway now contains a bounded one-shot seller worker for the
$5 reviewed Hive. It is **read-only by default, unscheduled, and apply-disabled**.

The worker reads Agent Market inventory and full work records, then emits an
eligibility decision and exact refusal reason. It does not treat an open job
as funded demand or revenue.

## Eligibility contract

Every condition must pass:

- buyer id is present, external, and not Viridis-controlled;
- required capabilities are a non-empty subset of the Hive's exact public
  capabilities;
- currency is USD;
- budget covers the fixed `500`-minor-unit price;
- `viridis_cash_escrow` is allowed;
- the existing 35% contribution-margin floor still passes;
- the OpenAI-backed solver pool is ready;
- at least one hour remains before delivery;
- the Hive has not already offered;
- the problem statement is present and within the public prompt bound.

No fuzzy capability inference, internal buyer, undersized budget, x402-only
custom job, unready provider, duplicate offer, or short delivery window can
pass.

## Apply boundary

`--apply` is insufficient by itself. The process also requires
`HIVE_MARKET_APPLY=1` and the caller-held
`VIRIDIS_AGENT_MARKET_PRIVATE_KEY_B64`.

One invocation may submit at most one deterministic offer:

- seller: `viridis-hive-orchestrator`;
- amount: `$5.00`;
- rail: `viridis_cash_escrow`;
- endpoint: `https://mcp.viridisconservation.com/payments/mcp`;
- payee: `viridis:hive`;
- delivery promise: one hour.

The worker cannot open or fund escrow, confirm funding, call a model, submit a
delivery, attest settlement, or move money. If an offer is later awarded,
Agent Market still blocks model execution and delivery until the private Hub
verifies exact live custody funding.

## Verification

| Gate | Result |
|---|---:|
| Hive suite | 58 passed |
| Gateway suite | 448 passed |
| Full fleet, local | 1,560 passed, 0 failed, 34/34 |
| Full fleet, production checkout | 1,560 passed, 0 failed, 34/34 |
| Exact candidate-image read-only smoke | `eligible_count=0`, `send_attempted=false` |
| Promoted-image read-only smoke | `eligible_count=0`, `send_attempted=false` |
| Public gateway health | `ok`, no mount errors |
| Hive readiness | wired rails, 3 solvers, provider ready |
| Hive release coherence | core + agent manifest + both registry manifests at v0.1.1 |
| Public Agent Market health | `ok`, v0.7.1 |

Both live smokes rejected all three current work records as
`common_control_or_invalid_buyer`. No signer was loaded and no write tool was
called.

## Production and rollback

- Live gateway image:
  `sha256:5585e63f37cbfc1bb2b0ac16c3f3542c3f8b2fd3e2577a7df6086a0a09635c56`
- Intermediate v0.1.0 worker image:
  `sha256:6681e20c5ca0da09d511ce8811f01310a344ff1cc3c9e29663ee57bd2dfaf9e0`
- Immediate rollback tag:
  `viridis-stable:prev-2026-07-26-hive-seller-v010`
- Rollback image:
  `viridis-stable:prev-2026-07-26-hive-market-seller`
- Rollback digest:
  `sha256:13599a51a508c67991e36e5f8e1755d2c4c25794da06c49fae5575bb80efcac4`
- Pre-restart gateway database:
  `production-backups/2026-07-26/viridis_state-pre-hive-market-seller-20260726T0924Z.db`
- Database SHA-256:
  `fe7bc0b26d5945af2f7a8ca5d5597bba69e12c4e4c1bd4fdee37d3fad726acf6`
- Database integrity: `ok`

The signer remains root-only at
`/root/viridis-fleet/private/hive-market-signer.env`. It is not injected into
the long-running gateway. A future apply run must mount it explicitly into
the isolated one-shot process.

## Commercial truth

This release created no work, offer, message, model call, escrow, funding
claim, delivery, settlement, or payment.

Current truth remains:

- 3 external HTTP settlements;
- 3 distinct external payers;
- `$0.27` external revenue;
- 0 repeat external purchases;
- 0 paid Hive jobs;
- 0 Agent Market offers, deliveries, or settlements;
- 0 active subscriptions / `$0` MRR.

The next trigger is external inventory that passes every worker gate. Until
then, keeping the worker read-only and unscheduled is the truthful posture.
