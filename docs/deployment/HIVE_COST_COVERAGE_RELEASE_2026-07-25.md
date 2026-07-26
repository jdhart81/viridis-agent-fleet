# Hive API-cost coverage release

**Released:** 2026-07-26 UTC
**Outcome:** Live and publicly verified
**Money moved:** None

## Business outcome

Every provider-backed Hive solve now requires paid backing. The prior
three-free-solve allowance was bounded, but it could still create OpenAI cost
for a caller that never converted.

The current owned contract is:

- $5.00 per model-backed solve;
- zero provider-backed execution free calls;
- free read-only tools and unpaid quote/preflight;
- at most $3.00 in solver settlements;
- conservative provider API ceiling below $0.18;
- minimum contribution margin $1.82 / 36.4% before fixed infrastructure; and
- a machine-enforced 35% contribution-margin floor at gateway boot.

An unsupported model or future cost/profile change that falls below the margin
floor fails closed instead of mounting a sellable Hive.

## Verification

| Gate | Result |
|---|---:|
| Focused Hive/payment/x402/A2A | 225 passed |
| Hive package | 42 passed |
| Gateway | 437 passed |
| Full fleet | 1,518 passed, 0 failed, 34/34 suites |
| Production-copy health | `ok`, no mount errors |
| Production-copy state | 33 rows, sequence sum 1,689 |
| Provider-backed free solves | 0 |
| Actual / required margin | 3,640 / 3,500 bps |
| Public health | `ok`, Hive free execution 0 |

No provider request, paid smoke, customer job, signature, settlement, or
outbound message was created.

## Production and recovery

Production image:

`sha256:5f89c39145a48191d170f5ea49d94220a37862c574edc7ff2e8b4266bedebe87`

Rollback:

- tag: `viridis-stable:prev-2026-07-25-hive-cost-coverage`
- image:
  `sha256:ea5b2093edde340cc2fb43eea621a6389907a0ac403dd7c8328e6b4e000895be`

Transactional state backup:

- path:
  `/root/viridis-hive-cost-coverage-20260725/viridis_state.pre_hive_cost_coverage.sqlite3`
- SHA-256:
  `fe7bc0b26d5945af2f7a8ca5d5597bba69e12c4e4c1bd4fdee37d3fad726acf6`

Secret-excluded build context:

- SHA-256:
  `984fb04300c779822105023d06df9cd50ad7b1d95de9c0f354804888e6c50a12`

Transferred amd64 image archive:

- SHA-256:
  `431a8668c163e2c0902685ce18ae30989351104248942e4d431cd3a627cb5e1d`

Runtime source:

- Hive adapter:
  `81cecd206df5d092a94fc388e8f80a0e3cc3cd44073e95cd79c09a1ff307a0b6`
- payment gate:
  `1c99998c95f1d06d43fee943f0f8c25b80ca879f581c8593997536e498d08c6c`

Only the gateway was recreated during promotion. Agent Market and Caddy
retained their containers.

## Build incident and corrective action

The first candidate build was attempted on the 1 GB production droplet,
following an obsolete runbook instruction. Docker build exhausted host
availability: SSH banner exchange and public HTTPS timed out. No image was
promoted and the live container was never recreated.

A soft reboot did not clear the stalled host. DigitalOcean power-cycle action
`3311799416` completed at `2026-07-26T04:12:47Z`. The unchanged production
image restarted healthy with all 33 state rows and commercial counters intact.

The candidate was then built off-host for `linux/amd64`, exported, checksummed,
transferred, and loaded. A resource-limited copied-state container passed
before promotion. The deployment runbook now forbids gateway builds on the
1 GB production droplet.

## Honest commercial baseline

Before and after:

- 3 external settlements;
- 3 distinct external payers;
- 270,000 atomic USDC / $0.27 external revenue;
- 0 repeat external purchases;
- 0 Hive jobs; and
- $0 MRR.

This release protects unit economics. It does not claim a new customer.
