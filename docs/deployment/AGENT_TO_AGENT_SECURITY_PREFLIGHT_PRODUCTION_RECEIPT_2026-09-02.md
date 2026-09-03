# Agent-to-Agent Security Preflight production receipt

**Pacific authorization date:** 2026-09-02

**Promotion run:** `20260903T031632Z`
**Outcome:** `PROMOTED / RESTART_VERIFIED / PUBLIC_QUOTE_VERIFIED`

## Promoted surface

The production gateway now presents Security Preflight as the default first
paid MCP purchase, with a one-cent ceiling and a Coinbase Payments MCP direct
x402 recipe. The promotion changed only:

- `gateway/quickstart.html`
- `gateway/llms.txt`
- `integrations/viridis-paid-tools/SKILL.md`

Promoted source SHA-256 values:

- quickstart: `31ef166e908953e6d5e4817cca4491d719d8504b744fc81050abfb7d73c0dd84`
- machine guide: `b3b3d231312cd13e4cac81cc3218532da7bf160c105096d8d42696e5f374c6bc`
- paid-tools skill: `356f55602fde20056075a416cb6d2dbb23ce2d2c65e0e5c2e0d41a8c4f3dedf3`

## Runtime evidence

- Previous image: `sha256:aad054a5019daaf2a64ceca3a74c503494776eeabb2af28f845957cb37955d8b`
- Promoted image: `sha256:b4515d26cc232a4e4619d18b01036f392ef9c6f61494bd925391dfe2509a9784`
- Copied-state rehearsal passed, including first boot and restart.
- Production first boot and restart passed.
- State integrity remained healthy with 35 rows.
- Rollback stayed armed and was not invoked.
- State backup: `/root/viridis-candidates/agent-to-agent-security-preflight-20260902/promotion-runs/20260903T031632Z/backups/viridis_state-20260903T031633Z.db`
- Rollback image tag: `viridis-stable:rollback-agent-to-agent-security-preflight-20260902`

The public Security Preflight endpoint returned an exact x402 HTTP 402 quote
for 10,000 atomic units of Base USDC, equal to $0.01. The verification did not
fund a wallet, sign a payment, execute a paid tool call, or create a settlement.

## Verification scope

Focused gateway, adoption, and buyer-client checks passed: `33 passed`.

The broader local fleet run reported `2189 passed / 5 failed / 36 of 37 suites
clean`. The five failures are historical August candidate-bundle tests whose
builders bind mutable current source paths to old immutable content hashes.
They do not exercise the exact-image promotion path used here. Their sealed
hashes were not weakened or rewritten.

## Commercial boundary

This receipt proves technical activation and a publicly reachable unpaid quote.
It does not prove a new external buyer, paid delivery, settlement, repeat use,
subscription, MRR, or product-market adoption. The next flywheel event is one
external agent completing a paid Security Preflight call and receiving a useful
result plus settlement receipt.
