# Viridis Regulatory Radar for OpenClaw

This OpenClaw skill starts with an unpaid x402 v2 contract check for the live
Viridis Regulatory Radar scan. It cannot sign or submit a payment.

## Install from the public repository

```bash
git clone --depth 1 https://github.com/jdhart81/viridis-agent-fleet.git
openclaw skills install \
  ./viridis-agent-fleet/integrations/openclaw/viridis-regulatory-radar \
  --as viridis-regulatory-radar
openclaw skills check
```

Open a new OpenClaw session after installation, then ask:

```text
Use $viridis-regulatory-radar to inspect an unpaid quote for a US energy
regulatory scan about 45V emissions disclosure. Do not pay.
```

The live HTTP 402 is authoritative. An unpaid quote, install, view, or test is
not customer revenue.

## Run the preflight directly

```bash
python3 scripts/radar_preflight.py \
  --jurisdiction US \
  --sector energy \
  --query "45V clean energy tax credit emissions disclosure"
```

The script requires x402 v2, the exact Viridis scan resource, Base mainnet,
official Base USDC, a positive quote within the selected ceiling, and a
receiver. It sends no `PAYMENT-SIGNATURE`, legacy `X-PAYMENT`, authorization
token, or private key.

The production HTTP inventory does not currently serve
`regulatory-radar/monitor_changes`. This package does not advertise or invoke
that candidate.

## Test

```bash
python3 -m unittest scripts/test_radar_preflight.py
```
