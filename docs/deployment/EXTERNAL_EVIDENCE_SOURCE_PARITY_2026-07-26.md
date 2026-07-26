# External x402 evidence source parity

**Prepared:** 2026-07-26

**Production state:** live and restart-verified

**Repository state:** stacked draft candidate; depends on draft PR #27

**Money moved:** none

## Why

An external x402 corpus maintainer captured the Viridis GHG Ledger unpaid
preflight twice and reported a byte-identical `PAYMENT-REQUIRED` header. Their
fixture was merged as
[`smartflowproai-lang/x402-endpoint-validator#14`](https://github.com/smartflowproai-lang/x402-endpoint-validator/pull/14).

The useful contract is not another seller-authored receipt. It is an immutable
pointer to externally hosted fixture bytes, the external repository's merge
commit, and the fixture SHA-256.

## Public contract

`/.well-known/x402` exposes `independent_evidence` with:

- `classification: external_fixture_pointer_index`;
- `index_posture: seller_published_pointer_only`;
- `authoritative_for_payment: false`;
- `revenue_signal: false`; and
- `verification_required: true`.

The index pins:

| Route | Evidence posture | Merge | SHA-256 |
|---|---|---|---|
| `regulatory-radar/scan_regulations` | settled flow confirmed | `0920d50db53cbf59f20052c6c656f17f881c4b41` | `0dbd36a0cb2cfa3ebf7a3575acc5550bfe2208d640fa2508574454365a7834fe` |
| `ghg-ledger/calculate_inventory` | unpaid preflight only | `45b006b42a60562101a43ffc293447793900d095` | `8cd884c016b19c2131207365e523677a9384b8463fb45eb0ca826a89497b7d40` |

### Drift disclosure

The Regulatory Radar row is now explicitly
`fixture_state: historical_capture_drift_detected`. Tom Smart's first daily
comparison found an additive jurisdiction-schema widening on 2026-07-26
against the 2026-07-24 capture. Payment terms were unchanged. A fresh external
capture and merge were requested; the dated fixture must not be interpreted as
current-state evidence while that replacement is pending.

GHG Ledger remained byte-identical on its 2026-07-26 comparison. These are
dated observations, not perpetual freshness claims.

The quickstart now explains what an agent can verify before payment and why
seller counters are not buyer, settlement, or revenue proof.

The seat renderer also no longer describes a configured zero-percent
allocation as a pledge. Positive configured values remain exact pledge
disclosures and never claim completed retirement.

## Production evidence

- live image:
  `sha256:94c22d625c0bb8fa8469bf113f0d21779459c6b69e8a5e3069c297e77283b254`;
- rollback image:
  `sha256:d7ff374e482b81cf97faa0943fb7d4783f02f0c281ace6ccda9727ca99e938ec`;
- backup SHA-256:
  `9675cc5f437b6c5b603f298b5c9af7bdcd24af9d3bbac5f838d36f3bdd7f98de`;
- SQLite integrity and scratch restore: passed;
- copied-state candidate: healthy with 34 namespaces;
- Hive: wired, three solvers, provider ready;
- seller lifecycle during candidate smoke: disabled;
- local and production-checkout fleet gates:
  `1,571 passed, 0 failed, 34/34 suites`;
- local and production deployment gates: `589 passed`;
- live MCP gate: 27 agents plus subscriptions, 210 tools;
- local + Registry + live coherence: passed; and
- controlled restart marker `esc_000036`: survived with valid audit chain.

The exact external-verifier closeout is recorded at:

`https://github.com/smartflowproai-lang/x402-endpoint-validator/pull/14#issuecomment-5084314596`

## Commercial boundary

This is trust and source-parity work, not a revenue event.

- external x402 settlements: 3;
- external revenue: $0.27;
- repeat external purchases: 0;
- paid Hive settlements: 0;
- completed A2A tasks: 0;
- active subscriptions / MRR: 0 / $0;
- independently verified funded Market work: 0; and
- Market-Hive jobs / artifacts: 0 / 0.

## Merge boundary

This candidate is intentionally stacked on draft PR #27 because it modifies
the production stack introduced there. It does not modify PR #27, merge it,
close PRs #20-#25, publish a Registry version, or authorize consolidation.
