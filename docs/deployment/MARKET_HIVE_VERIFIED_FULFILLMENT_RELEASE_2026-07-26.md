# Market-to-Hive Verified Fulfillment Release — 2026-07-26

## Outcome

The production fleet can now fulfill an awarded Agent Market job with the
reviewed Hive only after the private Hub independently verifies the exact
buyer-funded cash escrow. The bridge is live, polls once per hour, and had no
eligible work at activation.

This closes the execution gap between:

1. a signed external buyer work order;
2. an awarded exact-$5 Hive offer;
3. independently verified live escrow custody;
4. one paid, reviewed Hive solve;
5. a content-addressed signed delivery; and
6. later buyer acceptance or dispute.

The bridge does not accept its own delivery, release or refund buyer funds,
attest settlement, or claim usefulness. Buyer acceptance remains the release
boundary.

## Safety and commercial invariants

- The ordinary free tier is unchanged. Market fulfillment uses a separate,
  opaque held-payment authorization bound to one exact work ID, escrow,
  funding receipt, amount, currency, payee, and logical service payload.
- A Hub receipt alone is insufficient. Live custody is rechecked immediately
  before execution.
- Missing, mismatched, test-mode, refunded, released, or otherwise non-funded
  custody fails before the model call.
- Request idempotency prevents a second model call for the same Market job.
- The canonical JSON artifact is persisted before delivery submission.
  Delivery retries reuse the same content digest.
- Hive remains fixed at $5.00 with no model-backed free solve and a minimum
  35% contribution-margin gate. The current audited floor remains $1.82 /
  36.4%.
- Open listings, offers, internal escrows, inbox reads, tests, and self-funded
  work are not counted as demand or revenue.

## Release contents

- `deploy/gateway/market_hive_bridge.py`
- held Market-payment lane in `deploy/gateway/payment_gate.py`
- lifecycle and immutable artifact route wiring in
  `deploy/gateway/viridis_mcp_gateway.py`
- bridge inclusion in `deploy/gateway/Dockerfile`
- root-relative, optional signer and lifecycle env files in
  `deploy/droplet/docker-compose.yml`
- Hive version `0.1.2` and matching local/publication metadata
- focused bridge, gate, gateway, and Hive regression coverage

The lifecycle is enabled with:

- `HIVE_MARKET_LIFECYCLE_ENABLED=1`
- `HIVE_MARKET_LIFECYCLE_INTERVAL_SECONDS=3600`

The hourly cadence avoids creating 288 empty inbox-read events per day while
retaining autonomous fulfillment.

## Verification

### Code and configuration

- Focused bridge/payment checks: **33 passed**
- Gateway suite: **455 passed**
- Hive suite: **58 passed**
- Full local fleet: **1,567 passed, 0 failed, 34/34 suites**
- Full production checkout, with only the provider credential admitted to
  the isolated test environment: **1,567 passed, 0 failed, 34/34 suites**
- Version coherence: **PASS — 27 agents**
- Production compose render: **PASS**
- Signer, lifecycle, and production env files: `0600 root:root`

The production env file is dotenv-compatible but not shell-source-compatible.
The release gate therefore used a one-purpose runner that admitted only
`OPENAI_API_KEY`; it did not load live commerce switches into unit tests.

### Backup and restore

- Online backup:
  `production-backups/2026-07-26/viridis_state-20260726T100319Z.db`
- SHA-256:
  `7f3d99b238355c2d37dbe9f21aa73d3999c729ee3e80c26f6f53aaeb6bba7052`
- Size: `544768` bytes
- SQLite integrity: `ok`
- Persisted core rows: `33`
- Off-droplet copy and manifest: verified
- Local restore drill: integrity `ok`, `33` rows
- Candidate copied-state compatibility and startup smoke: passed

### Images and rollback

- Promoted gateway:
  `sha256:514c8590235f2fabb4a32c2a9b1b1e2924c8a1929ef40fe3f3b210bd01c13109`
- Rollback tag:
  `viridis-stable:prev-2026-07-26-market-hive-bridge-v011`
- Rollback digest:
  `sha256:5585e63f37cbfc1bb2b0ac16c3f3542c3f8b2fd3e2577a7df6086a0a09635c56`

The first compose invocation derived the unintended project name `droplet`
and created a separate container with a new empty volume. The existing
`viridis-fleet` gateway remained healthy and untouched. The accidental
container, network, and empty volume were removed, and the actual replacement
was performed with explicit project name `viridis-fleet`.

## Live production evidence

- Docker health: `healthy`
- Public gateway health: `ok`
- Mount: existing `viridis-fleet_gateway_state:/data`
- Mount errors: none
- Hive version: `0.1.2`
- Hive rails: wired
- Hive solvers: `3`
- Provider ready: true
- Bridge enabled: true
- Bridge cadence: 3,600 seconds
- Bridge runs: `1`
- Bridge errors: none
- Bridge jobs / artifacts: `0 / 0`
- Market payment holds: `0`
- Hub verified work fundings / volume: `0 / $0`
- Agent Market messages: `0`
- Agent Market work funding receipts: `0`
- Unknown artifact digest: HTTP `404`
- Recent gateway log errors: none

Activation performed one signed empty-inbox read, increasing Market events to
28. It did not create a message, offer, job, funding receipt, model call,
artifact, delivery, settlement, or money movement.

## Commercial truth after release

- HTTP x402 settlements: `7`
- Self settlements: `4`
- External settlements: `3`
- Distinct external payers: `3`
- External revenue: `$0.27`
- Repeat external purchases: `0`
- Verified-funded Agent Market jobs: `0`
- Paid Hive jobs: `0`
- Independently useful paid Market deliveries: `0`
- Active subscriptions / MRR: `0 / $0`

The next proof is not more supply-side machinery. It is one independently
funded external Agent Market Hive job that delivers useful work, followed by a
buyer-signed acceptance and then a repeat purchase. Until that occurs, the
fleet has a verified commerce mechanism but not repeatable Agent Market
revenue.
