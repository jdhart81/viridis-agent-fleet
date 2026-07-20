# Agent Commerce Flywheel Handoff — 2026-07-20

## Outcome

The release is deployed. Viridis now exposes the five paid carbon/compliance
tools as an A2A 1.0 commerce agent, ships a bounded buyer/router SDK for
agent-to-agent purchasing, and runs the isolated growth worker with
repository-scoped GitHub App authentication instead of an expiring PAT.

The gateway uses the existing x402-v2 verifier, facilitator client,
settle-before-serve ordering, persisted replay ledger, kill switches, and Base
mainnet USDC configuration. No payment or money-movement rail was added.

## Deployment evidence

| Gate | Result |
|---|---|
| Local full fleet | 1242 passed / 0 failed / 32/32 |
| Droplet full fleet | 1242 passed / 0 failed / 32/32 |
| Gateway suite | 376 passed |
| Growth suite | 23 passed |
| Buyer/router suite | 6 passed |
| Gateway image | `sha256:3cbb963224ff405841c609f0fcdce9a1f99714a4e9942214bd1f8dea0e6a278b` |
| Gateway rollback | `viridis-stable:prev-2026-07-20-commerce` -> `sha256:bb6f10ea062a1968bb2eab674f67015d82165d9fdac817346752d3a11551b68e` |
| Growth image | `sha256:bc4caf67f6a80bcb759e0ec28683f73724fb9ce1b527f9fd92d14173aa2f1fed` |
| Growth rollback | `viridis-growth-agent:prev-2026-07-20-commerce` -> `sha256:d983f5f4f547979228bbfb324cf63188bddd29a6d2f1149d8c113fbf4dcb5c15` |
| Droplet disk | 24G total, 5.3G used before build; 5.5G after cleanup; 18G free |

The production build context excluded `.git`, the public mirror, archives,
staging trees, bytecode, environment files, PEM files, secrets, databases,
and ViridisOS. Exact post-sync hashes matched the reviewed local files.

## A2A seller surface

Live routes:

- `GET /.well-known/agent-card.json`
- `POST /a2a/message:send`
- `GET /a2a/tasks/{id}`

The Agent Card declares A2A protocol version 1.0, HTTP+JSON, five skills, and
the required extension URI
`https://github.com/google-a2a/a2a-x402/v0.1`. Each skill derives its price,
atomic amount, description, and JSON schema from the existing x402 catalog.

An initial message persists a `TASK_STATE_INPUT_REQUIRED` task and the exact
payment requirement. A follow-up on the same task supplies the caller-signed
x402 payload. Only a successful verify and settle can execute the tool. The
settlement identifier is written to the existing durable replay ledger before
execution; a replay returns the stored task without executing again.

Production smokes passed:

- Agent Card: version 1.0, five skills, required A2A-x402 extension.
- Missing extension: HTTP 400, no execution.
- Valid unpaid message: durable payment-required task at 10000 atomic USDC,
  reflecting the active first-wallet intro offer.
- Task polling: returned the identical input-required task.
- Existing unpaid HTTP x402 route: still HTTP 402.
- Health: status `ok`, A2A enabled, 25 agents green.

No paid A2A call was made during deployment.

## Buyer/router SDK

`scripts/viridis_market_router.py` provides discovery ranking plus a bounded
purchase client. A `SpendMandate` limits purpose, total and per-call atomic
spend, networks, payees, resource prefixes, expiry, latency, and seller trust.
Private, loopback, reserved, and non-HTTPS seller URLs are refused. The client
can quote without signing; execution requires a caller-injected signer and a
payment receipt. The SDK stores no private key, wallet seed, or signing secret.

## Growth authentication

GitHub App `Viridis Growth Publisher`:

- App ID: `4350532`
- Installation ID: `147900092`
- Installation: only `jdhart81/viridis-agent-fleet`
- Permission: Contents read/write; required Metadata read-only
- Production key mount: `/root/viridis-growth/secrets/viridis-growth.pem` to
  `/run/secrets/viridis-growth.pem`, read-only to UID 10001

The worker signs a short-lived app JWT, asks GitHub for a token restricted to
the one repository and Contents write, caches it only in memory, and refreshes
before expiry. A live read-only smoke minted a token and returned HTTP 200 for
the approved repository. The old `GROWTH_GITHUB_TOKEN` variable is absent.

The worker's first post-cutover cycle selected no target because every cleared
owned target was still on cooldown, so it correctly made no network send.

## Credential incident and safe state

While validating production configuration, a compose rendering command
expanded the prior OpenAI API key into tool output. The growth worker was
stopped immediately; the key was removed from its environment; and the worker
was restarted with `GROWTH_OPENAI_ENABLED=0`. Runtime verification shows the
OpenAI key is empty, the PAT is absent, and Stripe/CDP/x402 credential variables
are absent. Deterministic grounded copy remains active.

Required account action: revoke the exposed OpenAI project key in the OpenAI
Platform and create a replacement before re-enabling LLM phrasing. The current
release intentionally fails safe without it.

The local top-level `env/` credential folder was also inadvertently included
in the SSH-protected full-tree source transport and isolated Docker build
context. The gateway Dockerfile enumerates its `COPY` inputs and did not copy
that folder; a container check confirmed `/fleet/env` is absent. The two
droplet copies were deleted immediately, and the original local files were
changed from world-readable to owner-only permissions. Future transports must
exclude the top-level `env/` directory explicitly.

## Frozen boundaries

- Frozen in-band MCP x402-v1 SHA:
  `ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`.
- No price changes.
- No Connect, escrow, participant, bond, refund, or legal-gate changes.
- No ViridisOS files in the production candidate.
- Existing external telemetry remains one payer, one settlement, 250000 atomic.

## Primary references

- A2A 1.0 specification: <https://a2a-protocol.org/latest/specification/>
- A2A-x402 extension: <https://github.com/google-agentic-commerce/a2a-x402>
- GitHub App JWT authentication: <https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app>
- GitHub installation access tokens: <https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app>
