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
| `regulatory-radar/scan_regulations` | current unpaid preflight with dated settlement reference | `811fef6b037cfeb71a890cac97bb822f0efcf03a` | `f667444013029bc98e229b0d3021426d8bf18d13afe3007db419a213d0e290b5` |
| `ghg-ledger/calculate_inventory` | unpaid preflight only | `45b006b42a60562101a43ffc293447793900d095` | `8cd884c016b19c2131207365e523677a9384b8463fb45eb0ca826a89497b7d40` |

### Drift disclosure

Tom Smart's first daily comparison found an additive jurisdiction-schema
widening on 2026-07-26 against the 2026-07-24 capture. Viridis temporarily
marked that pin `historical_capture_drift_detected`.

The replacement was merged in external PR #15 and independently verified:
its SHA-256 is
`f667444013029bc98e229b0d3021426d8bf18d13afe3007db419a213d0e290b5`,
and its 3,172-byte `PAYMENT-REQUIRED` header was byte-identical to a fresh live
unpaid preflight. The new fixture is explicitly `capture_method:
unpaid_preflight`; it does not inherit settlement provenance. The paid-flow
claim remains attached to merge
`0920d50db53cbf59f20052c6c656f17f881c4b41`, where it was earned. Payment
terms were byte-identical across both captures.

GHG Ledger remained byte-identical on its 2026-07-26 comparison. These are
dated observations, not perpetual freshness claims.

The quickstart now explains what an agent can verify before payment and why
seller counters are not buyer, settlement, or revenue proof.

The seat renderer also no longer describes a configured zero-percent
allocation as a pledge. Positive configured values remain exact pledge
disclosures and never claim completed retirement.

## Production evidence

- live image:
  `sha256:32be1995fb23a9187ed1ac803eb35a5696606f498983fc422af75b4f96dba588`;
- rollback image:
  `sha256:4261247a9094cf1e5d6789cf4122e1ed4e4cf1786a3ed3a2e7610d4e86f5257a`;
- backup SHA-256:
  `9d1a151d6191d9985eac4f45501edce67c422ac9e827917671d768b124ac7c51`;
- SQLite integrity and scratch restore: passed;
- copied-state candidate: healthy with 34 namespaces;
- Hive: wired, three solvers, provider ready;
- seller lifecycle during candidate smoke: disabled;
- local and production-checkout fleet gates:
  `1,571 passed, 0 failed, 34/34 suites`;
- local and production deployment gates: `589 passed`;
- live MCP gate: 27 agents plus subscriptions, 210 tools;
- local + Registry + live coherence: passed; and
- controlled restart marker `esc_000038`: survived with valid audit chain.

The exact external-verifier closeout is recorded at:

`https://github.com/smartflowproai-lang/x402-endpoint-validator/pull/14#issuecomment-5084314596`

The drift report and accepted recapture path are recorded at:

`https://github.com/smartflowproai-lang/x402-endpoint-validator/pull/14#issuecomment-5084362469`

`https://github.com/smartflowproai-lang/x402-endpoint-validator/pull/14#issuecomment-5084378709`

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
