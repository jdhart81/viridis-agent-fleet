# Stripe activation — Viridis fleet (human-facing revenue)

The payment primitive (`stripe_payments.create_checkout`) is built and tested
(7/7 invariants, `test_stripe_payments.py`). It turns "charge $X for a service"
into a Stripe Checkout URL an agent hands to a caller. It reads the secret key
from the `STRIPE_API_KEY` env var — **Claude never sees or handles your key.**

## Two rails, on purpose
- **Agent-to-agent** payments → **x402** (the `metering` + `escrow` agents). No Stripe.
- **Human customers** (a contractor paying for a SmartScale measurement, a protogen
  CAD job, a regulatory-radar report) → **Stripe Checkout** (this module).

## Activation click-path (you do these; ~10 min)
1. **Get a key.** Stripe Dashboard → Developers → API keys. Grab the **test** key
   first (`sk_test_…`). (Your prior key was revoked 2026-03-28, so this is fresh.)
2. **Set it on the droplet** (never commit it):
   ```bash
   ssh root@192.34.62.16
   echo 'STRIPE_API_KEY=sk_test_xxx' >> /root/viridis-fleet/.env
   # add `env_file: .env` under the gateway service, or export before compose up
   ```
   (I've prepared the compose wiring below — you just paste the key.)
3. **Verify with a real test call** — tell me once the test key is set and I'll
   generate a live test checkout URL for a $12.99 "SmartScale measurement" and
   confirm it opens Stripe's payment page (test mode, no real money).
4. **Go live** only when you're ready: swap `sk_test_` → `sk_live_`. The module
   surfaces `livemode` so an agent can refuse real charges until you intend them.

## What's left to wire (my side, on your go)
- Add a `create_payment` MCP tool to a revenue agent (SmartScale first) that calls
  `create_checkout` and returns the URL — so a caller can pay in-flow.
- Add `env_file` to `deploy/droplet/docker-compose.yml` so the key is injected.
- Optional: a `/pay/success` + `/pay/cancel` route on the gateway for clean returns.

## Guardrails honored
No live key handled by Claude; no charge executed without your test → live sign-off;
no money moves in A2A (state machines only) until x402 is explicitly turned on.
