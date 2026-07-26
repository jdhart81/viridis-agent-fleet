# A2A repeat-purchase parity release

**Released:** 2026-07-26 UTC
**Outcome:** Live and publicly verified
**Money moved:** None

## Business outcome

Successful paid A2A tasks now return the same machine-readable
`viridis_commerce.repeat_purchase` contract as successful paid HTTP x402
requests.

The completed A2A artifact preserves the tool result and adds:

- the exact HTTP x402 and MCP endpoints;
- the JSON input schema and concrete input example;
- the buyer-supplied fields required for another purchase;
- the advertised list price and atomic Base USDC amount;
- a fresh-quote instruction whose authoritative source is the next unpaid
  HTTP 402 response; and
- explicit `auto_execute=false`, `payment_required=true`, and
  `buyer_authorization_required=true` boundaries.

The contract is produced only after successful settlement and execution. It
does not reuse prior inputs, sign a payment, spend funds, invoke a model, or
create another task.

This closes a protocol-parity gap: an autonomous buyer that purchased through
A2A previously received the raw tool artifact but lost the repeat-purchase
contract already returned to an HTTP x402 buyer.

## Verification

| Gate | Result |
|---|---:|
| Focused A2A/repeat-commerce tests | 67 passed |
| Gateway suite | 439 passed |
| Local full fleet | 1,521 passed, 0 failed, 34/34 suites |
| Production-checkout full fleet | 1,521 passed, 0 failed, 34/34 suites |
| Candidate copied-state health | `ok`, 27 agents, no mount errors |
| Candidate copied-state database | SHA and 33 rows unchanged |
| Production runtime | `running`, Docker health `healthy` |
| Public gateway | `ok`, 27 agents, no mount errors |

The production-checkout run used
`OPENAI_API_KEY=readiness-only-test` only to exercise the Hive provider
readiness branch. The test suite made no provider request.

The A2A regression checks pin both current paid products:

- Regulatory Radar: `$0.25`, `250000` atomic USDC; and
- Hive: `$5.00`, `5000000` atomic USDC.

Replay and database restoration preserve the repeat contract, and each paid
task still executes its tool exactly once.

## Production and recovery

Production image:

`sha256:aaa7b29c05a32372d69be57fb9660c928086660cf39b7572da7fd0d6f24e002c`

Rollback:

- tag: `viridis-stable:prev-2026-07-26-a2a-repeat-parity`
- image:
  `sha256:d054258a076746beeb4c74757945f0f8411222413bd36bc2d98c294243ccf917`

Runtime source hashes:

- `deploy/gateway/a2a_commerce.py`:
  `a2f3725122c290cefb988429042e794b60354521560fd17a0effc2f7a7a81120`
- `deploy/gateway/x402_http.py`:
  `360b1f4242d66d0e92aa8c3a2d518b169dd637771e8b0c506c2d2b59ef74494c`

Transactional backup:

- droplet:
  `/data/backups/viridis_state-20260726T064518Z.db`
- off-droplet:
  `production-backups/2026-07-26/viridis_state-pre-a2a-repeat-parity-20260726T064518Z.db`
- SHA-256:
  `fe7bc0b26d5945af2f7a8ca5d5597bba69e12c4e4c1bd4fdee37d3fad726acf6`
- SQLite integrity: `ok`
- agent-state rows: `33`

The candidate was an immutable one-file layer over the exact prior production
image, avoiding a rebuild from a stale checkout. Only the gateway container
was recreated. Caddy, Agent Market, and all persistent volumes were left
untouched.

After promotion, the checkout was reconciled with the already-running Hive
profile and its required Nightkeeper-suite pin. The overwritten checkout
files were backed up at:

`/root/viridis-fleet-checkout-backup-20260726T0702Z`

## Honest commercial baseline

Before and after:

- 7 classified HTTP x402 settlements;
- 4 self-settlements;
- 3 external settlements from 3 distinct external payers;
- 270,000 atomic USDC / `$0.27` external revenue;
- 0 repeat external purchases;
- 0 paid Hive jobs;
- 0 active subscriptions; and
- `$0` MRR.

The live A2A task counters remain one known pre-existing Regulatory Radar
`input-required` smoke artifact and zero completed, failed, or working tasks.
This release improves a real buyer's continuation path; it does not claim that
a repeat purchase happened.

## Nightkeeper contract

Read-only monitoring must require completed paid A2A artifacts to preserve the
same `repeat_purchase` contract as HTTP x402 results. It must keep exact route,
schema, required-input, price, fresh-quote, no-auto-execution, payment, and
buyer-authorization assertions. Monitoring must not sign, settle, create an
A2A task, invoke a Hive solver, or count an unpaid task as demand.
