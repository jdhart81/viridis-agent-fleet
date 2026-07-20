# Mission closure handoff — builds 1–4

**Date:** 2026-07-20

**Status:** deployed, active, and verified

**Scope:** FA-15 bond return, agent-native storefront, owned acquisition channel, campaign attribution

## Outcome

All four requested builds are in production.

1. **FA-15 bond provider return:** a clean provider-return leg now performs a
   real Stripe partial refund against the original collateral Checkout Session
   before it can become `executed:true`. The purpose key is deterministic,
   transient errors remain retryable, and every executed leg must carry a
   `refund_id`, `transfer_id`, or certified `money_primitive_id`.
2. **Agent-native storefront:** `/llms.txt`, `/x402/catalog`, `/agents`, and
   `/quickstart` expose the five-route measure → account → disclose → claim →
   scan workflow, exact prices, active $0.01 intro pricing, and a free dry run.
3. **Policy-cleared acquisition:** the isolated growth worker retains the three
   owned Smithery listings and now updates only
   `jdhart81/viridis-agent-fleet/docs/LIVE_AGENT_SUITE.md` through GitHub's
   Contents API. Its credential is fine-grained to that repository, with
   Contents write and required Metadata read only. It expires 2026-08-19.
4. **Campaign attribution:** pre-send rows now capture route scope plus
   settlement, payer, revenue, and first-settlement baselines. Later observations
   calculate deltas and use a persisted route high-water mark so one settlement
   cannot be credited to multiple posts.

## Evidence

- Local full gate: **1230 passed / 0 failed / 31/31 suites**.
- Droplet full gate: **1230 passed / 0 failed / 31/31 suites**.
- Isolated 25-agent gateway gate: **362 passed**.
- Growth worker gate: **22 passed**.
- Public mirror gates after rebase: **103 gateway + 22 growth passed**.
- Live health: `status: ok`, 25 agents, gateway container healthy.
- Unpaid regulatory-radar front door: HTTP 402 with `PAYMENT-REQUIRED`.
- Machine catalog: five routes; intro pricing enabled.
- Bond health: zero production bond records and explicit Stripe-refund evidence
  semantics; no money moved during this deployment.
- Runtime MCP-v1 SHA:
  `ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`.
- ViridisOS: absent from the candidate, image, and running container.
- First owned GitHub send: attempt
  `558ccecf-782b-45a3-99ce-4197069aa0b1`, content SHA
  `f79d9224be6e50c172c50f16b22f97a58cdcda26e5ca327bacc369ed0dea9b48`,
  commit `9c8637c725a56295c4946b22e04a231c224f0160`.
- The send_attempt row was committed before the API call and carries fleet-wide
  attribution scope `*` with a baseline of one external payer, one external
  settlement, and 250000 atomic external revenue.
- Growth runtime contains zero Stripe, CDP, x402, Coinbase, private-key, or
  payment credential variables.

## Images and rollback

- Gateway image:
  `sha256:bb6f10ea062a1968bb2eab674f67015d82165d9fdac817346752d3a11551b68e`.
- Gateway rollback: `viridis-stable:prev-2026-07-20-closure` →
  `sha256:edabff21fbfc1265ab56d2340b6be332767b9d88fa3291ba15174083ee5ffdac`.
- Growth image:
  `sha256:d983f5f4f547979228bbfb324cf63188bddd29a6d2f1149d8c113fbf4dcb5c15`.
- Growth rollback: `viridis-growth-agent:prev-2026-07-20-closure` →
  `sha256:c7b46c2030401b0f39e48e6edbc2535a3e0dea44facc6e660c1c7d611479394c`.
- Droplet disk before: 24G total, 4.8G used, 19G free (21%).
- Droplet disk after cleanup: 24G total, 5.2G used, 18G free (23%).

## Public delivery

- Reviewed Wave 6–closure release: `e9f0b19`.
- First autonomous owned-file refresh: `9c8637c`.
- Live storefront: https://mcp.viridisconservation.com/agents
- Machine catalog: https://mcp.viridisconservation.com/x402/catalog
- Agent guidance: https://mcp.viridisconservation.com/llms.txt
- Free quickstart: https://mcp.viridisconservation.com/quickstart

## Boundaries retained

No list price changed. The in-band MCP x402 v1 lane stayed byte-frozen. No
participant-spend, ConnectRail CR1–CR7, EscrowCustody EC-series, or FA-I3
manual-fallback logic changed. No live bond or payout was created for a smoke.

## Account-level maintenance

The fine-grained GitHub token expires 2026-08-19 and must be rotated by the
account holder unless it is replaced later with a repository GitHub App. An
unused classic token was generated during setup but was never installed,
copied into production, or used; it should be revoked from GitHub settings.
