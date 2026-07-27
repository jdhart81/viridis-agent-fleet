# Viridis Security Preflight release — 2026-07-27

## Outcome

Viridis Security Preflight v1.0.0 is deployed as the Fleet's seventh paid
x402/A2A route and 28th hosted MCP agent:

- MCP: `https://mcp.viridisconservation.com/security-preflight/mcp`
- x402: `https://mcp.viridisconservation.com/x402/security-preflight/security_preflight`
- public receipts:
  `https://mcp.viridisconservation.com/security-preflight/receipts/{receipt_id}`
- Agent Market:
  `https://mcp.viridisconservation.com/network/catalog`

List price is $1.00 per scan with zero free calls. The existing Fleet-wide
one-time new-wallet introduction can quote $0.01.

## Product boundary

The service evaluates only caller-supplied MCP metadata:

- endpoint and authentication declarations;
- JSON Schema closure;
- high-impact tool approval requirements;
- allow/deny policy conflicts; and
- static prompt-injection indicators.

It never fetches URLs, executes tools, stores raw manifests/policies/samples,
or tests a deployed runtime. Its receipt is evidence of bounded static
coverage, not a certification that an agent is secure or vulnerability-free.

Each result includes a 30-day Ed25519-signed
`viridis-security-receipt-v1`. The private key exists only in the Fleet
gateway environment; Agent Market receives only the public verification key.
The public-key SHA-256 is
`f4814e4634295083316fda3fdaebe0df19717b0135608b76a44cb566211bcf4a`.

Payment does not prove Agent Market profile ownership or import consent.
Receipt import is a separate explicit action. Because ViridisNorth LLC
operates the issuer and seeded Viridis profiles, related imports are labeled
`COMMON_CONTROL_RELATED`, not independent verification.

## Revenue design

The product creates a low-friction paid entry into Viridis Security:

1. $1 automated preflight;
2. signed receipt that can improve transparent Agent Market discovery; and
3. an explicit $99 starting offer for a reviewed developer evidence pack.

The evidence-pack purchase is not automated. No funnel step fabricates profile
ownership, buyer consent, independent evidence, or revenue.

## Verification

The exact release passed:

- 119 focused Security Preflight, gateway, and Agent Market tests;
- 463 complete gateway tests;
- 593 gateway, droplet, and persistence tests;
- 1,551 full-fleet tests, 0 failures, 0 errors, 34/34 suites;
- local version coherence for all 28 agents;
- copied-production-state candidate health;
- valid request -> HTTP 402 without execution;
- invalid request -> HTTP 400 with `payment_required:false`;
- MCP initialize -> HTTP 200;
- signed receipt import -> accepted once;
- duplicate receipt import -> replay-safe, imported count remains one; and
- related-party classification -> `COMMON_CONTROL_RELATED`.

The production host has 961 MB RAM and no swap. Repeating the complete suite
there was OOM-killed with exit 137, so the production gate used the exact
locally tested archive and image, copied-state candidate containers, and
public post-deployment probes. No test failure was hidden by that resource
limit.

## Deployment and rollback

Live images:

- gateway:
  `sha256:1251bbedb89a41ebfb7c438324dd513ca81309b371b3425aa39865cfdf7a8e92`
- Agent Market:
  `sha256:cfbde1943466d5949290f550bbd2d8464ee09f56dfb89005057831838a4a48ec`

Rollback tags:

- `viridis-stable:rollback-security-preflight-20260727`
- `viridis-agent-market-network:rollback-security-preflight-20260727`

Pre-deploy database backups passed SQLite integrity checks and scratch restore:

- gateway SHA-256:
  `e6d33916553384986eeb0d39f5e2f8ae80a903d7540fbe20f001fdaa41a51560`
- Agent Market SHA-256:
  `939dc03a3879ad965532202b204be91b0d78a5a4d8450be0cbbb48fe5440749c`

Verified off-host copies exist. The source-only release delta SHA-256 is
`03273a57a44d7dd858a6181d84addecd602916fda1a5f4db3c5a53e23885ed5b`.

The first Compose invocation used the compose-file directory as its project
root, creating an isolated `droplet-*` project with fresh empty volumes. The
original `viridis-fleet-*` services and state remained intact. Those disposable
resources were removed, and the release was recreated under the existing
`viridis-fleet` project with the root Fleet env file explicitly loaded. Both
final services are healthy on the intended persistent volumes.

## Public proof and money truth

Post-deployment public checks confirm:

- gateway and Agent Market health HTTP 200;
- signer required and ready;
- seven paid routes;
- Security Preflight price $1.00 and free calls 0;
- 12 Agent Market profiles, including active
  `viridis-security-preflight`;
- valid unpaid request HTTP 402 with `PAYMENT-REQUIRED`;
- malformed request HTTP 400 before payment;
- missing receipt HTTP 404;
- MCP initialize HTTP 200; and
- Security Preflight present on the agents, quickstart, deck, and llms
  surfaces.

Pre/post external settlement telemetry is unchanged at four external
settlements and 280,000 atomic USDC ($0.28) across the Fleet.
Security Preflight has zero external settlements and **$0 revenue** at release.

The official MCP Registry accepted the v1.0.0 manifest at validation. A direct
publish attempt was rejected before publication because the local Registry JWT
had expired. The repository's pinned GitHub OIDC publisher is allowlisted for
`security-preflight-agent`; that workflow is the no-long-lived-secret
publication path after this source release merges.
