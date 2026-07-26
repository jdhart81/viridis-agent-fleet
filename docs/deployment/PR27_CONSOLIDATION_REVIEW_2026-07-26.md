# PR #27 consolidation review

**Reviewed:** 2026-07-26  
**Candidate:** draft PR #27, `release/market-hive-verified-fulfillment-20260726`  
**Candidate commit before this receipt:** `ab2a0c6d287577c2bf28f1563d71162c729d9889`  
**Decision:** Approval-ready as the single consolidation candidate; no merge,
close, or Registry publication is authorized by this review.

## Recommendation

Approve PR #27 as the one main-based source candidate. After PR #27 merges,
close PRs #20–#25 as superseded. Do not merge PR #27, close the older drafts,
or publish new Registry versions until Justin explicitly says:
`authorize consolidation`.

## Current dependency graph

All seven PRs are open, draft, and mergeable. Public `main` remains
`5dd8e9f033ad010c755fe8aadac1cec72aab3d59`.

| PR | Base | Head | Head commit |
|---|---|---|---|
| #20 | `main` | `agent/hive-x402-a2a-commerce` | `e661bb73930272a8281b8e4bbbb7fd10aa283877` |
| #21 | `main` | `agent/market-usefulness-feedback` | `8847c220dadbf7775633e5a041f1370c6ffea2f6` |
| #22 | #20 | `agent/executable-repeat-continuation-stack` | `2025ecd36581a9ef2300946df1da5644f47170cb` |
| #23 | #22 | `agent/hive-cost-coverage` | `eb940d7e2f05e93eb8ecb5c774f06be592503b89` |
| #24 | #21 | `agent/market-hive-discovery` | `4d274d9d541a92f695bf408f57680073264706d0` |
| #25 | #23 | `agent/repeat-purchase-contract` | `08697f5affb5a9e33b58a181f58a1412e97c6b40` |
| #27 | `main` | `release/market-hive-verified-fulfillment-20260726` | `ab2a0c6d287577c2bf28f1563d71162c729d9889` |

The stacked dependency lanes are `#20 → #22 → #23 → #25` and
`#21 → #24`. PR #27 descends directly from `main`.

## File coverage

The six dependency PRs change 46 unique files relative to their own bases.
All 46 are represented in PR #27's 85-file diff from `main`.

| Source PR | Files | Byte-exact in #27 | Later implementation in #27 | Missing |
|---|---:|---:|---:|---:|
| #20 | 18 | 2 | 16 | 0 |
| #21 | 16 | 6 | 10 | 0 |
| #22 | 7 | 1 | 6 | 0 |
| #23 | 12 | 8 | 4 | 0 |
| #24 | 4 | 0 | 4 | 0 |
| #25 | 7 | 4 | 3 | 0 |
| **Unique total** | **46** | — | — | **0** |

“Later implementation” means the path is present in #27 but changed again by
the verified-funding, seller-identity, bounded-worker, fulfillment, or paid
completion durability work. It is not treated as equivalent based on filename
alone; the semantic checks below cover those changes.

## Semantic coverage

- #20's Hive A2A full-price, preflight, provider-readiness, six-front-door,
  x402-price, and fixed-margin tests remain in #27.
- #21's usefulness, operator-receipt, security, and independent-verification
  tests remain in #27.
- #22's executable continuation retains `input_schema`, `input_example`,
  `required_buyer_inputs`, the MCP endpoint, the authoritative fresh unpaid
  HTTP-402 quote source, and the no-auto-execution rule.
- #23's cost-coverage metadata and margin tests remain. The payment gate is
  superseded by the later held-payment and durable-before-ack implementation.
- #24's Hive discovery test is strengthened into purchase-route coverage for
  both x402 and verified cash escrow, including exact
  `payee_id=viridis:hive`. Additional tests pin bind-once seller
  authorization and signed-profile preservation.
- #25's fixed-price Hive repeat-purchase contract test remains exact.
- PR #27 additionally fails closed if the final paid-completion snapshot
  cannot be saved. It returns `durable_completion_failed`, preserves the last
  durable `EXECUTING` hold, and refuses replay without running billable work a
  second time.

## Verification

| Gate | Result |
|---|---:|
| Agent Market unit suite at #27 head | 46 passed |
| Hive unit suite at #27 head | 58 passed |
| Portable public gateway suites at #27 head | 90 passed |
| GitHub `security-baseline` at #27 head | passed |
| Canonical full fleet | 1,568 passed, 0 failed, 34/34 suites |
| Production-checkout full fleet | 1,568 passed, 0 failed, 34/34 suites |
| Canonical and production deployment subset | 586 passed |
| Production local + Registry + live coherence | 27 agents, passed |

The portable gateway run includes A2A commerce, Hermes access, Hub kernel,
Market→Hive bridge, held-payment durability, and x402 v2.

Thirteen public gateway files were also attempted together. Five cannot
collect because they directly import private fleet packages absent from the
publication checkout. Of the remaining eight, 92 tests passed and nine
failed only where two tests expected private layout: the security-plane test
imports private `request_limits` and fleet adapters, while Wave 9 expects the
private-root `scripts/x402_demo_client.py`. Removing those two
layout-dependent files yields the clean 90-test portable gate above. These
are publication packaging assumptions, not candidate logic regressions; the
same surfaces pass in the 1,568-test canonical and production-checkout gates.

## Production alignment

The durability change at `ab2a0c6` is deployed and restart-verified on image
`sha256:8e13c5b6dc8919dcaef5a3aff9b739e44f847d5c16130835584ebfbca9195fb8`.
Rollback image
`sha256:514c8590235f2fabb4a32c2a9b1b1e2924c8a1929ef40fe3f3b210bd01c13109`
and the integrity-green 34-row transactional backup are verified. The live
gateway is healthy, Hive has three provider-ready solvers, and Market holds,
bridge jobs, and artifacts remain zero.

## Commercial truth

This review created no offer, job, payment, model call, delivery, settlement,
subscription, message, or money movement.

- 7 HTTP x402 settlements: 4 self and 3 external;
- 3 distinct external payers;
- $0.27 external revenue;
- 0 repeat purchases;
- 0 verified-funded Market jobs;
- 0 paid Hive jobs;
- 0 independently useful paid Market deliveries; and
- 0 active subscriptions / $0 MRR.

The next commercial proof is an independently funded external Hive job,
buyer-controlled acceptance, and a repeat purchase. Source consolidation is
necessary distribution work, but it is not demand or revenue.
