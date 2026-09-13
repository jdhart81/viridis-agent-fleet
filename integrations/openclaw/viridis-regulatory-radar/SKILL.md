---
name: viridis-regulatory-radar
description: Inspect and optionally purchase one bounded Viridis Regulatory Radar x402 v2 scan from OpenClaw. Use when an operator needs an energy or climate regulatory requirement screen, a live unpaid Base USDC quote, or exactly one human-authorized paid scan from buyer-owned facts. Default to no payment; never store signer secrets, auto-subscribe, or follow an upsell automatically.
---

# Viridis Regulatory Radar

Use the live Viridis HTTP contract to screen energy or climate regulatory
requirements. Start unpaid and fail closed if the route or x402 terms differ
from the operator's mandate.

## Collect buyer facts

Require:

- `jurisdiction`, such as `US`, `US-CA`, `california`, or `EU`
- `sector`, such as `energy`, `manufacturing`, or `construction`

Accept an optional focused `query`. Do not infer missing facts from an earlier
purchase or use `CA` for California; `CA` means Canada.

## Inspect without paying

Run the bundled deterministic preflight:

```bash
python3 {baseDir}/scripts/radar_preflight.py \
  --jurisdiction US \
  --sector energy \
  --query "45V clean energy tax credit emissions disclosure"
```

Supply `--payer 0x...` only when a returning buyer wants a wallet-specific
quote. This is a public address used as an `X402-Payer-Address` pricing hint;
it does not authorize payment.

Require all of the following:

- HTTP 402 with a valid `PAYMENT-REQUIRED` header
- x402 version 2 and the `exact` scheme
- Base mainnet, `eip155:8453`
- official Base USDC,
  `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- the exact `regulatory-radar/scan_regulations` resource
- a positive amount at or below the operator's ceiling

Stop on any mismatch. A 402 is a quote, not a purchase or revenue.

## Purchase only with a fresh mandate

Do not pay unless the operator explicitly authorizes all of:

1. `regulatory-radar/scan_regulations`
2. the maximum USDC amount
3. Base mainnet
4. a clear expiry

Use a caller-owned signer and keep `X402_BUYER_PRIVATE_KEY` outside prompts,
tool arguments, repositories, and logs. Use the public Viridis buyer client:

```bash
git clone https://github.com/jdhart81/viridis-agent-fleet.git
cd viridis-agent-fleet
python3 -m pip install "x402[requests,evm]==2.16.0"

# Set X402_BUYER_PRIVATE_KEY outside the conversation and command logs.
python3 scripts/x402_demo_client.py \
  --route regulatory-radar --max-payment-usdc 0.01
```

Use a $0.01 ceiling for a new wallet. For a returning wallet, use the same
unpaid preflight with its public payer address and never exceed $0.25 unless a
future live contract and a new mandate explicitly change that ceiling.

Make exactly one paid attempt. If the outcome is ambiguous, inspect the receipt
and on-chain state before any retry. Accept success only when the response is
HTTP 200 and includes `PAYMENT-RESPONSE`; preserve the result digest and
settlement receipt.

## Keep follow-ons disarmed

Treat repeat, next-route, subscription, seat, or monitoring offers as unsigned
proposals. Never follow or schedule one automatically. Obtain new buyer facts,
a new live 402, and a new explicit mandate for every later purchase.

The production HTTP inventory does not currently include
`regulatory-radar/monitor_changes`. Do not advertise, invoke, or substitute
that non-serving candidate.
