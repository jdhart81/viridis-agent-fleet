# the402 Regulatory Radar onboarding — 2026-07-24

## Outcome

Viridis submitted one admin-assisted provider-onboarding inquiry to the402.
The contact page displayed:

> Message sent — we'll get back to you soon.

The inquiry was submitted as:

- name: Justin Hart — Viridis North LLC
- email: `justin@viridisconservation.com`
- topic: Provider inquiry
- product: Viridis Regulatory Radar
- proposed provider price: $0.25
- public quickstart:
  `https://mcp.viridisconservation.com/quickstart`
- planned webhook:
  `https://mcp.viridisconservation.com/integrations/the402/webhook`

The inquiry asked the402 to provide credentials only through a secure
onboarding path. It explicitly stated that Viridis is not creating a wallet or
making a paid registration at this stage.

## Technical readiness

The isolated adapter is located at:

`integrations/the402-regulatory-radar-adapter/`

Verified on 2026-07-24:

- adapter tests: 11 passed
- existing Regulatory Radar tests: 102 passed
- Python compile check: passed
- service manifest JSON validation: passed
- HMAC timestamp and signature verification: covered
- replay/idempotency behavior: covered
- callback host and path allowlist: covered
- automatic bidding: disabled
- wallet custody and payment signing: absent

## Brand

Use the existing Viridis Connected V asset for any marketplace avatar or
provider-brand field offered during onboarding:

`deploy/gateway/viridis-mark.svg`

Do not substitute a generic marketplace icon when the platform supports a
provider or service image.

## Current money truth

- account created: no
- service listed: no
- wallet created or connected: no
- payment made: no
- paid job received: no
- settlement verified: no
- revenue from this channel: $0

## Next gate

Wait for a reply at `justin@viridisconservation.com`. Before production
activation:

1. Review the secure credential-delivery path and current provider terms.
2. Decide which payout wallet Viridis will use; do not let the adapter hold a
   private key.
3. Deploy the isolated adapter and verify its health route.
4. Register the webhook and run the platform's no-money health test.
5. Create exactly one Regulatory Radar listing from `service.json`, using the
   Viridis logo when supported.
6. Keep request-notification bidding disabled.
7. Count revenue only after an independently initiated job settles.

Do not self-purchase the listing to manufacture activity or revenue.
