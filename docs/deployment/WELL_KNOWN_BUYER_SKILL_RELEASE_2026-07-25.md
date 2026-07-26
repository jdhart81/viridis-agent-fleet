# Domain-discoverable buyer skill release — 2026-07-25

## Outcome

Viridis now publishes its keyless buyer procedure directly from the seller
domain using Hermes's supported well-known skill convention:

- index:
  `https://mcp.viridisconservation.com/.well-known/skills/index.json`
- skill:
  `https://mcp.viridisconservation.com/.well-known/skills/viridis-paid-tools/SKILL.md`

An agent no longer needs prior knowledge of a raw GitHub URL. It can discover
the seller-domain skill, inspect it, and install it:

```bash
hermes skills search https://mcp.viridisconservation.com \
  --source well-known
hermes skills install \
  well-known:https://mcp.viridisconservation.com/.well-known/skills/viridis-paid-tools \
  --yes
```

Installation contains no wallet credential and moves no money. The skill still
requires a caller-owned signer, the exact live 402, exactly one paid attempt,
and a fresh spend mandate for every follow-on route. It treats
`funding_status: UNVERIFIED` as unfunded inventory.

The live-client verification found and corrected one documentation defect:
Hermes Agent 0.19.0 rejects the newer `--now` spelling. Its supported
noninteractive confirmation flag is `--yes`; a new Hermes session loads the
installed skill when an existing session does not reload it.

## Why this was the next conversion step

The public skill already existed, but a buyer needed to know its raw repository
path. The hosted README and quickstart received limited direct traffic, while
the domain is already the authoritative service-discovery surface. Publishing
the standard domain index removes that hidden prerequisite without opening a
duplicate community listing, sending a cold message, or manufacturing a paid
call.

## Production proof

| Gate | Result |
|---|---|
| Skill validator | Pass |
| Focused buyer/runtime tests | 11 passed |
| Gateway suite | 419 passed |
| Full isolated fleet | 1,434 passed, 0 failed, 33/33 suites |
| Candidate database | integrity `ok`, 32 rows |
| Candidate restart | Pass |
| Candidate MCP surface | 26 agents + 1 infrastructure mount, 204 tools |
| Production MCP surface | byte-identical to candidate, 204 tools |
| Production database | integrity `ok`, 32 rows |
| Public skill content type | `text/markdown; charset=utf-8` |
| Public skill SHA-256 | `3fafbd5bf5d52c2da39b5e55106bfc5123cffc929a2ecfc6aeadfbeaff24f36b` |
| Gateway logs after cutover | no traceback, error, or exception |

The candidate was derived from the exact running image, not the stale droplet
checkout. The reviewed overlay changed only:

- `deploy/gateway/viridis_mcp_gateway.py`
- `deploy/gateway/quickstart.html`
- `deploy/gateway/llms.txt`
- `integrations/viridis-paid-tools/SKILL.md`

## Images and rollback

- live image:
  `sha256:54c432d9670df6152373565a82d365e241016a57fb10f423260079ab6b4eb1a5`
- live container:
  `bfc4c58c468078195c0d5a0c2a9f247e1d010fedebbfeafd3faa580c8f4039ce`
- retained candidate tag:
  `viridis-stable:well-known-skill-candidate-2026-07-25`
- retained rollback tag:
  `viridis-stable:prev-2026-07-25-well-known-skill`
- rollback image:
  `sha256:ea896b4be108beeb5a8695367f42fd34952c4fd5546b2e63cc50542bc5e40e97`

Only the gateway was recreated. Agent Market
`0947fce026dc`, growth worker `982eb594f36b`, and Caddy `5d5ecdd94bb2`
remained running.

The isolated candidate container was removed after promotion. Its temporary
environment file and copied state databases were deleted from the droplet;
candidate and rollback images were retained.

## Backup proof

Both off-droplet backups have SHA-256
`73ba1d08686127f6783aaa12f3cd66b23a7e260c9ce8c1b7c61de4353512b810`,
SQLite integrity `ok`, and 32 state rows:

- `/Users/justinhart/Documents/Viridis Production Backups/2026-07-25/viridis_state-pre-well-known-skill-20260725.db`
- `/Users/justinhart/Documents/Viridis Production Backups/2026-07-25/viridis_state-post-well-known-skill-20260725.db`

## Public-source publication

Public source and install documentation merged in
[`jdhart81/viridis-agent-fleet#11`](https://github.com/jdhart81/viridis-agent-fleet/pull/11)
at commit `7e4f0cd50947d41a427296261584983db266177f`.

- PR security run:
  `https://github.com/jdhart81/viridis-agent-fleet/actions/runs/30173507107`
- post-merge `main` security run:
  `https://github.com/jdhart81/viridis-agent-fleet/actions/runs/30173526878`

The public mirror intentionally omits most private fleet agent directories.
Its scoped buyer/discovery tests passed 4/4, skill validation passed, Python
compile and diff checks passed, and the workflow pinning/registry-wrapper
tests passed 4/4. The complete runtime and fleet gates ran in the full
production source workspace.

## Honest commercial boundary

The release did not create a customer or transaction. Live truth after
cutover remains:

- 6 versioned x402 settlements;
- 4 self-settlements;
- 2 external settlements;
- 2 distinct external payers;
- 0 repeat external purchases;
- 260,000 atomic USDC ($0.26) external revenue;
- 0 active subscriptions and $0 MRR;
- 1 internal A2A task waiting for input, with 0 externally completed tasks.

The next business gate is still a third independent payer or the first genuine
repeat external purchase.
