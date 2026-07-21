# Agent Market Smithery distribution handoff — 2026-07-20

**Status:** deployed and verified  
**Authorization:** Justin approved public Smithery publication and continuation  
**Scope:** one owned registry listing plus the isolated growth worker only

## Outcome

`hartjustin6/agent-market-network` is public on Smithery. Release
`d7ddb407-24e8-4aaf-8bdc-dfd32da4b7d0` completed successfully and Smithery
scanned all 16 live MCP tools at
`https://mcp.viridisconservation.com/network/mcp`.

The listing links the public source and live Agent Market catalog. Its current
description is generated from live route prices, intro pricing, external
settlement telemetry, and exact open-work IDs/budgets.

## Autonomous maintenance

The isolated growth worker adds one target:

- `smithery-agent-market-network`
- owned name `hartjustin6/agent-market-network`
- suite-wide attribution scope `*`
- homepage `https://mcp.viridisconservation.com/network/catalog`
- 30-day cooldown

The Smithery adapter continues to reject every namespace outside
`hartjustin6/*`. It now also rejects every homepage except the owned Viridis
agent-suite and Agent Market catalog surfaces.

The first live cycle wrote append-only row 16 (`send_attempt`) before row 17
(`send_result`) and succeeded:

- attempt: `c8b9ff86-b32f-4e75-a80b-d5f4d34572cb`
- timestamp: `2026-07-21T05:23:06.188840+00:00`
- content SHA-256:
  `aa27eac756c19370aab5f40d33777a56677370ca960a2b0359f952a124e9e08c`
- model: `gpt-5.6-terra`
- call cost: `$0.010180`
- monthly model spend after call: `$0.071417 / $20.00`

## Gates and deployment

- focused growth suite: **28 passed / 0 failed**
- local fleet: **1272 passed / 0 failed / 33/33**
- droplet fleet: **1272 passed / 0 failed / 33/33**
- candidate no-send smoke selected `smithery-agent-market-network`, rendered
  1002 grounded characters, and reported `send_attempted:false`
- live growth image:
  `sha256:4dbe5042f2697d73c5493d3691073559baa1eb87fd4976c6b75f4d93141a2dd6`
- deployed tag: `viridis-growth-agent:deployed-2026-07-20-market-distribution`
- rollback tag: `viridis-growth-agent:prev-2026-07-20-market-distribution`
  -> `sha256:380820a46e6656c68b83ee8f221005ee7df88fdaab388a676ff1c2c756bf237b`
- disk before/after: 24G total, 5.3G used, 18G available (23%)

Gateway and Agent Market stayed healthy. Three paid jobs remain open; no offer,
market completion, Hub verification, or money movement occurred during this
release. Existing x402 telemetry remains one external settlement from one
external payer.

## Transport deviation contained before build

The pre-build inspection found local `.env.openai.local` was not matched by the
old exact-name Docker ignore. The first sync transported that duplicate and
deleted the separately managed growth `.env` and GitHub App key from the source
tree. The running container stayed healthy and preserved both operational
values.

No candidate image had been built. The growth-only `.env` and GitHub App key
were recovered from the running isolated container without printing values and
restored at mode 0600. The transported duplicate was removed; its Mac original
remains intact. Root `.dockerignore` now blocks `.env*` and `**/.env*`, the sync
uses matching protections, and a regression test pins both patterns. Final
candidate context was 56.37 kB and image inspection found no environment or key
file.

## Frozen boundaries

No gateway, Agent Market, Hub, price, payment rail, x402, Connect, escrow, bond,
participant, or legal-fallback behavior changed. The growth container still has
no Stripe, CDP, x402 signer, Hub, market-HMAC, or gateway-admin credential.
