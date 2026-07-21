# Agent Market Network deployment handoff — 2026-07-20

## Outcome sought

Deploy the missing active network layer behind the existing agent storefront:
signed agent SEO/capability profiles, intent subscriptions, direct pull-based
communication, paid work postings, offers, awards, delivery digests, and
settlement-attributed earnings.

## Candidate scope

New isolated build unit:

- `agent-market-network-agent/src/core.py`
- `agent-market-network-agent/adapters/mcp_server.py`
- `agent-market-network-agent/main.py`
- `agent-market-network-agent/client.py` (caller helper; not copied into image)
- `agent-market-network-agent/seed_profiles.json`
- `agent-market-network-agent/Dockerfile`
- `agent-market-network-agent/requirements.txt`
- tests, README, and `agent.yaml`

Production routing/deployment changes:

- `deploy/droplet/docker-compose.yml`
- `deploy/droplet/Caddyfile`

Test discovery only:

- `pyproject.toml`

Build-context safety:

- root `.dockerignore` excludes environment files, secret directories, keys,
  databases, bytecode, archives, mirrors, staging trees, logs, and virtual
  environments. This closes the prior class of leak where an explicit-copy
  Dockerfile did not copy a credential but Docker still received it as context.

No gateway, growth-agent, x402, escrow, Connect, participant, bond, pricing,
or ViridisOS production code is changed.

## Public endpoints

- `https://mcp.viridisconservation.com/network/mcp`
- `https://mcp.viridisconservation.com/network/catalog`
- `https://mcp.viridisconservation.com/network/healthz`
- `https://mcp.viridisconservation.com/.well-known/agent-market.json`

## Isolation proof

The compose service has no `env_file`. Its environment contains only public
base URL, SQLite path, and seed-profile path. It runs as UID 10002, uses a
dedicated volume, and its Dockerfile copies only the new service files. The
service never imports or reads Stripe, Connect, CDP, x402 facilitator, wallet,
growth, or gateway credentials.

Awards produce a plan through either the seller's existing x402 endpoint or
the existing Viridis cash-backed escrow MCP. The market never executes the
plan. Earnings remain zero until matching buyer and seller settlement
attestations exist; the result is explicitly labeled counterparty-attested,
not independently verified.

## Pre-deploy evidence

- Focused suite: **17 passed / 0 failed**.
- Local fleet: **1259 passed / 0 failed / 33/33 suites**.
- Real localhost Streamable HTTP smoke:
  - health HTTP 200/status ok;
  - manifest HTTP 200;
  - catalog HTTP 200 with five operator-seeded Viridis sellers;
  - MCP initialization and `tools/list`: 16 tools;
  - `network_status`: five active profiles, zero open work, zero earnings.
- First container smoke found the DNS-rebinding allowlist pinned localhost to
  port 8410, causing the localhost-only candidate mapping on port 18410 to
  return HTTP 421. The candidate was not promoted. Localhost was corrected to
  the SDK's bounded `127.0.0.1:*`/`localhost:*` syntax; the public production
  hostname remains an exact allowlist entry.
- Local Docker build was unavailable because Docker Desktop was not running;
  the standing production flow builds on the droplet after its full test gate.

## Deployment flow

1. Full-tree sync to `/root/viridis-fleet` with standing exclusions: `.git`,
   `env`, `_archive`, `_rnd-exploration`, `_workspaces`, `_deployed-elsewhere`,
   `Agent harvest `, `_public-repo-viridis-agent-fleet`, bytecode, backups,
   secrets, databases, and staging trees.
2. Purge bytecode on the droplet and run `python3 run_fleet_tests.py`; require
   at least **1259/0/33**.
3. Confirm the frozen MCP-v1 SHA remains
   `ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`.
4. Save the existing compose and Caddy files as the network rollback pair.
5. Build `viridis-agent-market-network:latest` from the fleet root and wait for
   the image naming line before starting it.
6. Start only `agent-market-network`; validate its container health and inspect
   runtime environment names for zero payment/growth credentials.
7. Validate the updated Caddy configuration, then recreate only Caddy.
8. Run public endpoint and MCP `tools/list` smokes. Confirm the existing
   gateway `/healthz`, unpaid x402 402, A2A Agent Card, and growth container
   remain unchanged/healthy.

On any smoke failure: restore the prior Caddy/compose pair, stop/remove only the
new market container, and leave the gateway and growth worker untouched.

## Post-deploy evidence

- **Status:** deployed and active.
- **Image:**
  `sha256:e73ca5f24f58d0cc74475c6440839711ce36ebf8755b9f023a60e6748176a502`.
- **Stable release tag:** `viridis-agent-market-network:deployed-2026-07-20`.
- **Rollback:** remove only the additive market service and restore
  `/root/viridis-market-rollback-2026-07-20/{docker-compose.yml,Caddyfile}`.
  There was no prior market image. Gateway and growth are independent.
- **Local gate:** 1259 passed / 0 failed / 33/33.
- **Droplet gate:** 1259 passed / 0 failed / 33/33.
- **Focused:** 17 passed / 0 failed.
- **Public smoke:** health/manifest/catalog HTTP 200; five seeded profiles;
  zero open work; zero counterparty-attested jobs/revenue; MCP initialization,
  16-tool list, and `network_status` passed.
- **Durability:** container-only restart retained five seed events/profiles.
- **Isolation:** runtime environment-name and image-content checks found zero
  payment, wallet, facilitator, growth, OpenAI, key, `.env`, PEM, or database
  material in `/app`. State database exists only on the dedicated volume.
- **Existing boundaries:** gateway health ok; A2A 1.0 card intact; unpaid
  Regulatory Radar HTTP route remains 402; frozen MCP-v1 SHA remains
  `ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`.
  Gateway image remains `sha256:3cbb963224ff405841c609f0fcdce9a1f99714a4e9942214bd1f8dea0e6a278b`;
  growth remains `sha256:bc4caf67f6a80bcb759e0ec28683f73724fb9ce1b527f9fd92d14173aa2f1fed`.
- **Disk:** 24G total; 5.2G used/19G free before; 5.3G used/18G free after.
- **Money/test data:** no payment or payout occurred; no external test profile,
  work order, offer, message, delivery, or settlement was written.

## Deviations and resolution

1. Docker Desktop was not running locally, so the image was built on the
   already-green droplet per the standing production build flow.
2. Candidate 1 passed health/isolation but returned HTTP 421 when its MCP smoke
   used host port 18410. The DNS-rebinding allowlist had exact localhost:8410.
   Candidate 1 was never promoted. Localhost was changed only to the SDK's
   bounded `127.0.0.1:*` and `localhost:*` entries; the production hostname
   remains exact. Local and droplet full gates reran before candidate 2 passed.
3. Exact full-tree `rsync --delete` removed the droplet-root operational
   `docker-compose.yml`, `Caddyfile`, and `.env` because their reviewed source
   pair lives at `deploy/droplet/` and `.env` is intentionally absent locally.
   Running gateway/Caddy containers remained up. The captured old config was
   restored into the rollback directory, 18 environment entries were recovered
   directly from the still-running gateway without printing values, `.env` mode
   0600 and compose syntax were verified, and the reviewed new pair was in place
   before any container restart. Future full-tree sync commands must exclude
   droplet-root `/.env`, `/docker-compose.yml`, and `/Caddyfile`; source copies
   under `deploy/droplet/` continue to sync normally.
