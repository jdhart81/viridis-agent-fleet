# Agent-to-Agent Paid MCP Flywheel

**Date:** 2026-09-02
**Status:** `PRODUCTION_PROMOTED / GITHUB_PUBLISHED /
LIVE_UNPAID_QUOTE_VERIFIED`

## The one loop

An external buyer agent is about to connect to an unfamiliar MCP server or a
new manifest version. It discovers Viridis Security Preflight, sends the
caller-owned manifest and authority policy, accepts a fresh x402 quote under
its own spending limit, receives a signed result receipt, records whether the
result was useful, and buys another preflight for the next server or version.

`discover -> quote -> pay -> result -> buyer possession -> usefulness -> next version -> repeat`

This is the only near-term flywheel. Human consulting, Upwork, monthly seats,
new fleet agents, and the broad carbon chain are outside this activation test.

## Why Security Preflight is the wedge

- The buyer is another agent or agent runtime, not a human procurement funnel.
- The trigger repeats naturally whenever an MCP server, manifest, schema, or
  authority policy changes.
- The input is bounded JSON that the buyer already controls.
- The output is immediately usable as a connect, hold, or review signal.
- The route already supports x402 v2, a one-cent eligible first call, a signed
  input-redacted receipt, exactly-once feedback, and later paid repeats.
- It does not require Viridis to invent a live regulatory-data claim.

## Current break in the loop

Security Preflight is technically available but is not the public default.
The quickstart and buyer skill historically sent the first purchase to
Regulatory Radar. Coinbase Bazaar currently shows only four historical Viridis
routes and does not return Viridis for the reviewed buyer-intent queries, so a
buyer agent cannot yet rely on semantic discovery of this wedge.

Coinbase's current MCP path removes most wallet integration friction:
Payments MCP can inspect and pay direct x402 endpoints under buyer-configured
limits, and Bazaar MCP exposes `search_resources` plus `proxy_tool_call` for
indexed resources. The remaining distribution problem is getting the exact
Security Preflight route into the buyer agent's context and then earning the
first independent paid call. A self-payment is not demand and must not be used
to manufacture this proof.

## Activation contract

### Trigger

> Before connecting to this MCP server, screen its manifest and tool authority
> policy and return the signed Viridis receipt.

### Paid route

`POST https://mcp.viridisconservation.com/x402/security-preflight/security_preflight`

### First-call price boundary

- normal list price: `$1.00 USDC`;
- eligible new-wallet intro ceiling: `$0.01 USDC`;
- authority: the exact live unpaid HTTP 402, never cached copy; and
- buyer control: per-call budget, no automatic future purchase.

### Acceptance event

Count a delivered result only when the paid response is HTTP 200, includes
`PAYMENT-RESPONSE`, and includes `viridis_delivery` with a result digest. Count
usefulness only from the one-time buyer feedback token. Count repeat demand
only when the buyer independently authorizes and settles a later preflight.

## Distribution sequence

1. Make Security Preflight the first route in `/quickstart`, `/llms.txt`, the
   published buyer skill, and agent-facing examples.
2. Publish one Coinbase Payments MCP recipe that calls the direct endpoint;
   do not require the custom Python client as the first integration.
3. Ensure the live 402 carries complete Bazaar discovery metadata for the POST
   body and result schema.
4. Obtain one independent buyer-agent call from an operator who already has a
   funded x402 wallet and a real MCP manifest to screen.
5. Ask for exactly-once usefulness feedback from the returned token.
6. Re-run only when that buyer has a new server or manifest version. Do not
   schedule or auto-pay without a fresh buyer mandate.

## Scorecard

Track only:

1. distinct external agents that fetched a live Security Preflight quote;
2. distinct external paying wallets;
3. verified paid-result deliveries;
4. useful or partially useful buyer-possession feedback;
5. independently authorized repeat preflights; and
6. revenue from those calls.

Do not count Registry publication, Bazaar listing, views, dry-runs, test
wallets, self-settlements, or seller-generated feedback as adoption.

## Release gates

- Local copy changes may be tested without external effect.
- GitHub publication requires its own push authorization.
- Production quickstart or gateway changes require a rollback-bound promotion
  authorization.
- Any message to an external agent operator requires exact outreach approval.
- Any paid bootstrap call requires an independent buyer and that buyer's own
  explicit spending mandate.

## Local and live verification

- focused gateway, adoption, and buyer-client tests: `33 passed`;
- live route: `security-preflight/security_preflight`;
- live response: HTTP `402`;
- scheme/network: `exact` / `eip155:8453`;
- asset: official Base-mainnet USDC
  `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`;
- fresh quoted amount: `10000` atomic USDC / `$0.01`;
- receiver: `0xfEf2e570b645EB720Ee6c589d27450810982f329`;
- wallet loaded: no;
- signature created: no;
- payment attempted: no; and
- paid tool executed: no.
