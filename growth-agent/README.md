# Viridis growth agent

Separate, default-off distribution worker for the public x402 fleet. It reads
live `/healthz` plus the public Agent Market catalog, selects only targets that pass the platform-policy allowlist
and cooldown, and commits an immutable `outbound_log` attempt before calling
any posting API. An isolated OpenAI Agents SDK harness can improve phrasing
with `gpt-5.6-terra`; deterministic fleet facts remain authoritative.

It never imports the gateway, never reads `STRIPE_*` variables, and must run
with a dedicated environment containing only `GROWTH_*` credentials. The
OpenAI key is never passed to posting adapters. The model cannot add targets,
post, move money, change prices, or bypass policy.

## Model guardrails

- `GROWTH_OPENAI_ENABLED=0` is a separate fail-closed model kill switch.
- The only permitted model is `gpt-5.6-terra`, with no reasoning effort,
  low verbosity, and at most 700 output tokens per run.
- `GROWTH_OPENAI_MONTHLY_BUDGET_USD=20.00` is a hard monthly stop. Calls reserve
  five cents before execution; unavailable or invalid model output falls back
  to the existing deterministic template.
- Exact route names, prices, intro pricing, conversion proof, live open-work
  identifiers/budgets, and live URLs
  are validated after generation. Any invented or missing dollar amount makes
  the generated copy ineligible for posting.
- Model usage and estimated cost are written to the append-only SQLite log.

Policy-cleared live targets are owned Smithery listings and one factual
discovery file in `jdhart81/viridis-agent-fleet`. Smithery uses its official
metadata API with `GROWTH_SMITHERY_API_KEY`. GitHub uses the official Contents
API with a repository-only GitHub App. The worker signs a short-lived JWT
from a read-only private-key mount and automatically mints one-hour
installation tokens; there is no recurring PAT rotation. It can update only
`docs/LIVE_AGENT_SUITE.md` on `main`; it has no issue, PR, star, follow, or
third-party write capability. Missing target credentials make that target
ineligible instead of starving other channels.

Each send stores the target route's conversion counters before posting. Later
health reads correlate only that route's new external settlements, distinct
payers, atomic revenue, and first-settlement receipt to the newest eligible
attempt. Durable high-water marks prevent one settlement from being credited
to multiple older posts for the same route. Suite-wide owned content uses the
total bucket and is explicitly logged as correlation, never causal proof.

## Dry run

```sh
GROWTH_STATE_DB=/tmp/viridis-growth.sqlite3 python3 main.py
```

The default kill switch is off, so that command performs no network read or
send. Programmatic dry-run tests call `GrowthAgent.run_once(dry_run=True)` with
a live or fake fleet snapshot and never call a posting adapter. Set
`GROWTH_AGENT_DRY_RUN=1` with both kill switches enabled for a real model call
that records its cost but does not post.

## Production isolation

Build separately from the gateway:

```sh
docker build -f growth-agent/Dockerfile -t viridis-growth-agent .
```

Run with a dedicated state volume and growth-only env file. Do not pass the
gateway `.env` or any Stripe credential to this container.

The included `docker-compose.yml` is intentionally separate from
`deploy/droplet/docker-compose.yml`. Copy `.env.example` to an independently
permissioned `.env`, then run Compose from this directory. It defaults OFF and
does not share the gateway environment or state volume.

`GROWTH_AGENT_ENABLED=1` does not override target policy. The current CDP
Discord target remains blocked until CDP staff installs/authorizes the Viridis
bot; Discord user-account automation is never supported.
