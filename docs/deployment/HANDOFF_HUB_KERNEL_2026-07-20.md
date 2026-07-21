# Viridis Hub Kernel deployment handoff — 2026-07-20

**Status:** deployed and verified in production
**Authorization:** Justin: “build and deploy it”
**Goal:** one trusted agent-market transaction that compounds discovery,
identity, verified payment, delivery evidence, reputation, distribution, and
mission accounting without adding a money rail.

## What changed

### Independent settlement verification

- `deploy/gateway/hub_kernel.py` is a new gateway composition module.
- The market sends a canonical event over the private Docker network, signed
  with `HMAC-SHA256(timestamp + "." + body)` using `HUB_EVENT_SECRET`.
- Caddy returns `404` for public `/internal/*`; the market reaches the gateway
  directly at `http://gateway:8402/internal/hub/events`.
- x402 settlements verify either against the gateway's durable settle-before-
  serve receipt or, for outside sellers, an exact successful Base-mainnet USDC
  `Transfer` log to the awarded `payee_address`.
- cash settlements verify custody funding, exact award terms, a RELEASED
  escrow, and either same-party revenue recognition or a Stripe Connect
  `transfer_id`. A bare manual `executed:true` is not independent evidence.
- Test-mode cash cannot count as production earnings by default.
- One transaction reference can complete at most one work order.

The Hub contains no buyer signer and creates no money movement. Stripe Checkout
and the existing Connect rail remain the only hosted cash primitives; x402
remains the existing settle-before-serve USDC rail.

### Market completion and evidence

- Production runs with `MARKET_HUB_REQUIRED=1`; matching buyer and seller
  attestations alone no longer complete a new job.
- Successful completion becomes `INDEPENDENTLY_VERIFIED`, with the Hub receipt
  persisted in the market SQLite database.
- fixed-price x402 offers must equal the seller's published route price. Custom
  job amounts use `viridis_cash_escrow`; a fixed endpoint can no longer be used
  as evidence for an arbitrary larger award.
- `submit_delivery` accepts optional signed `compute_evidence` and optional
  existing `notary_commitment_id` / `verified_receipt_id` proofs.
- Measured compute evidence is physically validated by Compute Ledger and emits
  an x402-C receipt. Evidence is optional and never inferred.

### Identity, reputation, and mission

- Hub-verified counterparties receive namespaced fleet identities
  (`market:<agent_id>`) so untrusted public identity writes cannot overwrite an
  existing record.
- Seller `delivered` and buyer `success` outcomes enter Trust Oracle exactly
  once, followed by content-addressed trust attestations.
- Optional Notary and Verified Relay references must bind the accepted delivery
  digest or the event fails closed.
- Mission accounting reports measured x402-C evidence when supplied. The
  conservation allocation remains **0** rather than inventing an unratified
  revenue percentage; this wave changes no prices or pledges.

### Distribution and discovery

- `/agents`, `/quickstart`, `/llms.txt`, `/healthz`, `/`, and the ARD manifest
  link the public Agent Market catalog and MCP endpoint.
- The isolated growth worker reads the public market catalog and includes up to
  three exact live job IDs and budgets in grounded outbound copy. Model output
  is rejected if it alters a job ID, budget, route price, or live URL.
- Official MCP Registry source manifest added at
  `deploy/mcp-publish-github/agent-market-network-agent/server.json` for
  `io.github.jdhart81/agent-market-network` v0.2.0.

## Security and legal boundaries

- The market receives **no** Stripe, CDP, facilitator, wallet, OpenAI, growth,
  or gateway-admin credential. Its sole service credential is the Hub event
  HMAC secret.
- The growth worker still receives no money credential and cannot sign, settle,
  award, or accept market work.
- non-Connect third-party cash payouts remain behind the existing legal/manual
  fallback and cannot become independently verified merely from a boolean.
- MCP-v1 x402 (`deploy/gateway/x402_rail.py`) is byte-frozen and unchanged.
- no price, participant, escrow-core, Connect CR1–CR7, bond, or payment-rail
  logic changed.

## Environment

Production gateway and market share one new random 32+ byte value:

```text
HUB_EVENT_SECRET=<random; never committed or printed>
HUB_KERNEL_REQUIRED=1
MARKET_HUB_REQUIRED=1
MARKET_HUB_URL=http://gateway:8402/internal/hub/events
```

Optional, defaulted and fail-closed:

```text
BASE_RPC_URL=https://mainnet.base.org
HUB_ALLOW_TEST_SETTLEMENTS=0
GROWTH_MARKET_CATALOG_URL=https://mcp.viridisconservation.com/network/catalog
```

## Verification

- Local full fleet: **1269 passed / 0 failed / 33/33 suites**.
- Droplet full fleet: **1269 passed / 0 failed / 33/33 suites**.
- Focused: market **20**, growth **25**, Hub Kernel **5**, gateway **381**.
- Tests cover HMAC tamper/staleness, exact x402 amount and route, reused receipt
  refusal, cash Connect proof, manual-boolean refusal, durable replay, independent
  market completion, retry after verifier failure, fixed-price enforcement,
  signed compute/proof persistence, and exact growth job-budget grounding.

## Production cutover

- Gateway image:
  `sha256:3fccd2c23ba2a792e779c3a7ee393bed024a5d75cabfbc3303561ca23fbca8cd`
  (`viridis-stable:deployed-2026-07-20-hub`).
- Market image:
  `sha256:392d373015354f3bc10016103fd92896f86288d1b37493ded2f0c8d494139576`
  (`viridis-agent-market-network:deployed-2026-07-20-hub`).
- Growth image:
  `sha256:380820a46e6656c68b83ee8f221005ee7df88fdaab388a676ff1c2c756bf237b`
  (`viridis-growth-agent:deployed-2026-07-20-hub`).
- Rollback tags preserve the preceding images as
  `viridis-stable:prev-2026-07-20-hub`,
  `viridis-agent-market-network:prev-2026-07-20-hub`, and
  `viridis-growth-agent:prev-2026-07-20-hub`.
- Gateway and market are healthy; growth is running with zero restarts. Public
  health is `ok`, Hub Kernel is enabled, and market health is `ok` at v0.2.0
  with Hub verification required/configured.
- Production market state survived recreation: 6 profiles and all 3 open paid
  jobs remain. Five seller profiles advertise exact existing x402 routes and
  the Viridis settlement address.
- Public `/internal/hub/events` returns `404`. An HMAC-authenticated private
  malformed-event smoke reached the Hub and returned `400 bad_event`,
  `verified:false`, leaving verified settlements at zero.
- The market runtime exposes no Stripe, CDP, x402 signer, OpenAI, growth, or RPC
  credential. The growth runtime exposes no Stripe, CDP, x402, Hub, or RPC
  credential.
- The market MCP endpoint and well-known manifest return 200. `/agents`,
  `/quickstart`, and `/llms.txt` all link the live market catalog.
- Frozen MCP-v1 x402 SHA is still
  `ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`.
- Existing HTTP x402 remains live: Regulatory Radar returned 402 with a v2
  `PAYMENT-REQUIRED` challenge at the active first-wallet amount of 10000
  atomic USDC. No payment was made during this deployment.
- The first growth candidate correctly failed closed when the combined route
  and live-job copy exceeded Discord's limit. It was rolled back immediately;
  no send occurred. The local candidate was then corrected, a five-route plus
  three-job regression was added, both full gates were rerun, and a real-data
  dry-run rendered all three exact jobs in 1002 characters with
  `send_attempted:false`. The corrected worker is live; its first cycle found
  only cooldown- or policy-blocked targets and made no duplicate post.
- Droplet disk before and after: 24G total, 5.3G used, 18G available (23%).
- No money moved, no test profile/job was created, and no payment rail, price,
  Connect, escrow, bond, participant, or FA-I3 fallback logic changed.
