# Repeat-commerce release

**Released:** 2026-07-25T19:39Z
**Outcome:** Deployed, restart-verified, and active
**Money moved:** None

## Business outcome

Every successful paid HTTP x402 result from a listed Viridis carbon or
compliance route now carries a machine-readable `viridis_commerce` object.
It names compatible next paid routes with their exact endpoint, method, price,
atomic USDC amount, and workflow reason.

The continuation contract is intentionally non-custodial:

- `auto_execute` is `false`;
- `payment_required` is `true`;
- `buyer_authorization_required` is `true`; and
- no follow-on payment is signed, initiated, or executed.

The same workflow graph is published in each live discovery entry as
`next_paid_routes`. A buyer agent can therefore decide what to buy next
without Viridis manufacturing another transaction.

`/healthz` now reports `repeat_external_purchases` per route and fleet-wide.
The counter includes only versioned external settlements with a known payer
wallet. Anonymous or unclassified records cannot manufacture a repeat.

## Honest commercial baseline

The release itself did not create revenue or a buyer:

| Signal | Before | After restart |
|---|---:|---:|
| Settlements | 6 | 6 |
| Self settlements | 4 | 4 |
| External settlements | 2 | 2 |
| Distinct external payers | 2 | 2 |
| Repeat external purchases | not yet surfaced | 0 |
| External revenue | 260,000 atomic USDC ($0.26) | unchanged |
| Active subscriptions / MRR | 0 / $0 | unchanged |

The business objective remains a third independent payer or the first
verified repeat external purchase.

## Verification

| Gate | Result |
|---|---:|
| Focused x402 and A2A tests | 60 passed |
| Full isolated fleet | 1,434 passed, 0 failed, 33/33 suites |
| Candidate database integrity | `ok`, 32 state rows |
| Offline snapshot compatibility | Pass, no adapter-load errors |
| Candidate restart | Pass |
| Production database integrity | `ok`, 32 state rows |
| Public MCP surface | 26 agents + 1 infrastructure mount, 204 tools |
| Post-restart MCP surface | byte-identical 204-tool manifest |
| Unpaid x402 behavior | HTTP 402; no continuation object |

Successful-payment response behavior is covered with a mock facilitator. No
production paid smoke was used because that would manufacture a transaction.

## Production and rollback proof

The droplet checkout was stale relative to the healthy running image, so it
was not used as a build source. The candidate was derived from the exact live
image and replaced only:

- `deploy/gateway/x402_http.py`
- `deploy/gateway/payment_gate.py`
- the two corresponding regression files

Production:

- image:
  `sha256:ea896b4be108beeb5a8695367f42fd34952c4fd5546b2e63cc50542bc5e40e97`
- gateway container:
  `113dc52d006174fa920279fed85a68c14d948d6fd7a427c711b3f6b5b2c19984`
- `x402_http.py`:
  `6ebb14a1708e5ca43f87242673b812506f8ecb069aaa5dde0a88f4672483da0e`
- `payment_gate.py`:
  `0597c04891046d1d49206120998b071a4e1e748d81740cecdacb4661bb513de0`

Rollback:

- tag: `viridis-stable:prev-2026-07-25-repeat-commerce`
- image:
  `sha256:21f5c2a62006ca993e9d38e3ba6af8cd49d179db124c406dfb6dd7be085c7d8c`

The Growth Agent, Agent Market, and Caddy retained their existing containers.
Disk remained 25% used with 18 GB free.

## Recovery evidence

- backup:
  `viridis_state-post-repeat-commerce-20260725.db`
- SHA-256:
  `73ba1d08686127f6783aaa12f3cd66b23a7e260c9ce8c1b7c61de4353512b810`
- SQLite integrity: `ok`
- agent-state rows: 32
- durable off-droplet copy:
  `/Users/justinhart/Documents/Viridis Production Backups/2026-07-25/`
- independent readback checksum and integrity verification: Pass

The isolated candidate already exercised the same byte-identical database
backup as a scratch restore and survived a restart.

## Boundaries

This release did not change list prices, intro pricing, facilitator behavior,
settlement order, payment credentials, custody, signatures, external
messaging, Olas publication, or the frozen x402 v1 rail. It improves the
conversion path after a real purchase; it does not count infrastructure as
revenue.

## Post-release discovery evidence

Coinbase's public merchant lookup still returns all five Viridis resources.
Its objective quality fields match the honest boundary:

- Regulatory Radar has two calls from two unique payers and is the only route
  with arm's-length external revenue in Viridis state.
- GHG Ledger, Disclosure Compiler, and Quantity Takeoff each show one older
  seed call; Tax Credit Engine shows one Bazaar call absent from the current
  versioned Viridis external-settlement ledger. Those are inventory/indexing
  signals, not additional customer revenue.

Coinbase Bazaar semantic search currently ranks Regulatory Radar first for the
buyer intent `energy climate compliance regulation`. The installable public
buyer skill now uses that official free search path, then requires the exact
live unpaid challenge before any payment.

The current Bazaar entry predates the latest strict Regulatory Radar fixture.
Coinbase's official Bazaar documentation confirms that catalog updates happen
only after a successful settlement and provides no separate registration or
refresh operation. Viridis did not manufacture a paid call to force reindexing.

Public repository traffic for the available 14-day window reports 983 clones
from 221 unique cloners but only seven browser views and no referrer rows.
This is consistent with registry or agent automation and is not adoption or
revenue proof.

Public-source publication is merged in
[`jdhart81/viridis-agent-fleet#10`](https://github.com/jdhart81/viridis-agent-fleet/pull/10)
at commit `c4f3aac2ac5446b2d573342e037f2457da628b05`. The post-merge
`Security baseline` push workflow passed in
[run 30172569648](https://github.com/jdhart81/viridis-agent-fleet/actions/runs/30172569648).
The published `main` buyer skill contains the free Coinbase
`discovery/search` path, reads `viridis_commerce.next_paid_routes`, and
refuses to interpret `funding_status: UNVERIFIED` as funded demand.
