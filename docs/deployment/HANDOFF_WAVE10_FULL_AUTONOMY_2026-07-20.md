# Wave 10 handoff — full autonomy closure

**Date:** 2026-07-20
**Status:** deployed; isolated Wave 10 gateway live, intro pricing active, isolated Smithery growth worker active, FA-06 production exposure quantified
**Ratification:** Justin's Wave 10 prompt

## Result

Wave 10 closes every cleanly classified recurring execution gap found in the
audited scope and ships outbound as an isolated, auditable worker rather than
another CEO queue.

- Same-account Weave events remain autonomous. A narrowly scoped WV8 restore
  migration durably closes old persisted instructions only when their scope is
  exactly `same_account_allocation` or they match the exact pre-WV4 fixed
  EnergyAI-to-Viridis schema observed in production. It removes the obsolete
  human action field and never touches an external/manual leg.
- Weave now accepts an optional external restoration payee. A pull-verified,
  payouts-enabled payee is transferred through the existing ConnectRail with
  purpose key `weave-restoration:<event_id>`. A non-onboarded/incomplete payee
  gets the existing certified fallback and onboarding guidance. Transient
  Stripe errors fail closed and leave the event retryable.
- Bond slash-claimant payments already met FA-A3: Connect auto-execution,
  purpose-key idempotency, and manual fallback only when not onboarded. Bond
  core was not modified.
- `ParticipantBridge.execute_ruling` now composes a durable cash-backed ruling
  into the existing custody settlement surface immediately. Refund rulings
  issue the origin refund; release rulings inherit Connect/manual CR7 exactly
  as custody defines it. Internal-ledger rulings never call custody.
- The growth worker is a separate build and Compose project. It derives copy
  from live route, price, intro, and conversion telemetry; chooses only
  policy-cleared targets outside cooldown; writes an immutable SQLite
  `send_attempt` before the posting API; records results; and reweights targets
  from later external-settlement observations.

The complete gap ledger is
`docs/deployment/AUTONOMY_GAP_LEDGER_2026-07-20.md`.

## Legal disposition

The reviewed Stripe and FinCEN primary sources support automatic execution on
the Connect rail, but do not support the categorical claim that the product
name alone eliminates every platform obligation. Connect supplies the
licensed transfer/payout infrastructure and connected-account screening;
Viridis can still remain merchant of record and retain transaction/platform
responsibilities. Therefore:

1. eligible Connect transfers remain automatic and exactly once;
2. genuinely non-Connect third-party disbursements retain CR7; and
3. a one-time counsel review of the actual agreements/funds flow remains, not
   a per-transfer approval queue.

See `docs/legal/STRIPE_CONNECT_RESIDUAL_LICENSING_RESEARCH_2026-07-20.md`.

## Growth-agent isolation and policy

Build independently:

```sh
docker build -f growth-agent/Dockerfile -t viridis-growth-agent:latest .
docker compose -f growth-agent/docker-compose.yml config
docker compose -f growth-agent/docker-compose.yml up -d
```

The worker has no gateway import, no gateway state volume, no gateway env file,
and reads only `GROWTH_DISCORD_BOT_TOKEN`, `GROWTH_GITHUB_TOKEN`, and
`GROWTH_SMITHERY_API_KEY` as credentials. The image is standard-library only.
Owned Smithery listings are the first policy-cleared autonomous live targets.

Environment:

```text
GROWTH_AGENT_ENABLED=0                 # fail-closed default
GROWTH_AGENT_INTERVAL_SECONDS=86400
GROWTH_FLEET_HEALTH_URL=https://mcp.viridisconservation.com/healthz
GROWTH_STATE_DB=/state/viridis_growth.sqlite3
GROWTH_FEEDBACK_WINDOW_DAYS=7
GROWTH_TARGETS_PATH=/app/targets.json
GROWTH_DISCORD_BOT_TOKEN=              # bot token only; never a user token
GROWTH_GITHUB_TOKEN=                   # fine-grained, first-party repo only
GROWTH_SMITHERY_API_KEY=               # owned hartjustin6 listings only
```

`GROWTH_AGENT_ENABLED=1` never overrides target policy. As shipped, CDP
Discord is not cleared because Discord forbids user-account automation and
Viridis cannot install a bot in CDP's server. CDP staff must authorize the bot
for the exact channel, or the target remains skipped. Third-party GitHub
promotion is likewise disabled unless a repository's contribution policy or
maintainer invitation explicitly accepts it. See
`docs/deployment/GROWTH_AGENT_PLATFORM_ALLOWLIST_2026-07-20.md`.

## Verification evidence

- Production baseline before edits: **1156 passed / 0 failed / 29/29**.
- Local focused Weave/participant/bond gate: **46 passed**.
- Local growth-agent gate: **13 passed**.
- Droplet growth-agent gate: **13 passed**; live-state dry-run selected an
  owned Smithery target, generated current content, and made no posting call.
- Growth image: `sha256:493f85fd55768cf309efbafe1d8f317709ff6183fc3824c6598c3766c2261284`;
  container stable with `GROWTH_AGENT_ENABLED=0` and no payment credentials.
- Dedicated Smithery credential created and installed only in the growth
  worker; a read-only registry request authenticated with HTTP 200. Runtime
  inspection confirmed no Stripe, CDP, or x402 credential variables. The
  protected local transfer file was deleted after installation.
- All ten growth source/config/test files are SHA-identical across local,
  public mirror, and droplet build tree.
- Local gateway: **368 passed**.
- Local full fleet after implementation and bytecode purge:
  **1218 passed / 0 failed / 31/31**.
- Droplet full fleet from the isolated Wave 10 full-test tree after bytecode
  purge and the documented `numpy` dependency install:
  **1218 passed / 0 failed / 31/31**. The isolated gateway build context is
  **368 passed**; the exact FA-09 orchestration/replay set is **3 passed**.
- Frozen v1 file SHA-256 before/after local implementation:
  `ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`.
- Local Docker engine was not running; Compose configuration validated, and
  image build moves to the ordinary droplet build gate.

## Production cutover and one-time activations

Justin selected **ISOLATE WAVE10**. The production candidate was constructed
from the exact Wave 9 droplet tree plus only the Wave 10 Weave/participant
files and associated tests/docs. The Wave 9 Dockerfile SHA remained
`b3ce3567d98fb5282e93c90448fd10555ee9dca48d17ac3fadd4645e6b506168`.
Both filename search and in-image inspection confirmed that no ViridisOS path
or file entered the build context or image.

- Production image:
  `sha256:edabff21fbfc1265ab56d2340b6be332767b9d88fa3291ba15174083ee5ffdac`
- Rollback: `viridis-stable:prev-2026-07-20-wave10` ->
  `sha256:2a84791b0a97466d61ef79a2d495f483a1f4ab4d707d3650c24bf4316e2152d2`
- Frozen x402 MCP-v1 SHA in the image:
  `ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`
- The sole persisted Weave event, `energyai-inv-2026-06-10`, moved from the
  exact legacy pending schema to executed `same_account_allocation` with
  `autonomy_migration: FA-I1-2026-07-20`. Event count stayed one; the
  375-minor share and retirement digest stayed unchanged.

Justin selected **INTRO GO**. Production now has `X402_INTRO_ENABLED=1`. A
fresh Viridis-controlled buyer was added to the self-wallet allowlist before
funding. Its first successful call quoted and settled 10000 atomic USDC:

- intro transaction:
  `0xcfa63199c98b39668323df5130a15af217f88d3d27c236fc69b91db5338b647e`
- same-wallet next call at the unchanged GHG Ledger list price, 1000000 atomic:
  `0x6bd648665d62da96f216e9adfee30b77d692e6a3578447d06403fdd506630b53`

Both receipts have Base status 1. Live telemetry classifies both as self, not
external; the buyer ended with zero USDC and its private key/temp environment
were deleted. The existing arm's-length first-settlement record and external
revenue counters did not change.

Justin selected **GROWTH ON**. Production now has
`GROWTH_AGENT_ENABLED=1` only in the isolated growth Compose project. Runtime
inspection immediately before activation found the scoped Smithery credential
and zero environment names containing Stripe, CDP, or x402. Target resolution
left only owned `hartjustin6/*` Smithery listings eligible; CDP Discord and the
third-party GitHub target remained policy-blocked.

The first live action updated `hartjustin6/disclosure-compiler`:

- attempt timestamp: `2026-07-20T17:33:27.309683+00:00`
- content SHA-256:
  `cf8a4a087a106dabd548e23f088102c80143d869720c268dc0a9f9c06d7d0894`
- result: Smithery `updated: true`
- append-only proof: sequence 1 is `send_attempt`; sequence 2 is the matching
  successful `send_result`, attempt id
  `59b388a7-1056-4a80-a410-8adc5a26c20c`

No recurring review is required. Platform-allowlist changes remain a separate
design decision.

## FA-06 bond provider-return quantification

The separately authorized read-only query found no persisted `bonds` namespace:
0 collateralized bonds, 0 settlement instructions, 0 executed
`same_party_refund` legs, 0 affected providers, and **$0.00** at stake. There is
therefore no evidence of an actual historical non-payment and no evidence of a
historical logging-only payment. The gap is prospective and requires separate
design authorization before the first provider-return settlement. See
`docs/deployment/FA06_BOND_PROVIDER_RETURN_QUANTIFICATION_2026-07-20.md`.

## Explicitly unchanged

- x402 MCP v1 lane (byte-frozen)
- list prices (the separately authorized `x402-intro-v1` flag is now active)
- ConnectRail CR1-CR7 and EscrowCustody EC-series
- bond core/provider-return behavior
- participant internal-earnings spend
- EC10, PG22, refunds, Instant Payouts, and every money primitive
