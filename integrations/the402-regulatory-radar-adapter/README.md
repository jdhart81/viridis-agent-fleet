# the402 Regulatory Radar adapter

This isolated provider adapter connects one Viridis product to the402:
Regulatory Radar.

It:

- verifies both `X-Platform-Secret` and the documented HMAC-SHA256 webhook
  signature;
- rejects signatures older than five minutes;
- stores only event hashes and bounded status metadata in a durable SQLite
  idempotency ledger;
- replies once to a genuine inbound service inquiry;
- fulfills a paid fixed-price job with the existing deterministic Regulatory
  Radar core;
- posts completion or failure only to allowlisted
  `https://api.the402.ai/v1/...` callback paths;
- never creates or stores a wallet key, signs payments, auto-bids, or treats
  platform activity as Viridis x402 revenue.

## Public routes

- `GET /integrations/the402/healthz`
- `POST /integrations/the402/webhook`

The intended production webhook URL is:

`https://mcp.viridisconservation.com/integrations/the402/webhook`

## Local test

From the fleet root:

```bash
python3 -m pytest \
  integrations/the402-regulatory-radar-adapter/tests/test_app.py -q
```

## Container build

Build from the fleet root so the image can copy the existing Regulatory Radar
package:

```bash
docker build \
  -f integrations/the402-regulatory-radar-adapter/Dockerfile \
  -t viridis-the402-regulatory-radar:latest .
```

The public GitHub mirror does not carry every private fleet agent package.
Building this image therefore requires the full fleet workspace containing
`regulatory-radar-agent/`, matching the existing gateway build contract.

## Production gates

1. Obtain admin-assisted provider credentials from the402.
2. Store `THE402_API_KEY` and `THE402_WEBHOOK_SECRET` only in the isolated
   production `.env.the402` file with owner-only permissions.
3. Build the image and add the compose and Caddy snippets.
4. Confirm the health route reports `configured=true` and `radar=ok`.
5. Register the webhook and run the platform health check.
6. Create exactly one service from `service.json`; set its returned ID as
   `THE402_SERVICE_ID`, then restart only this adapter.
7. Run one signed synthetic webhook test without payment.
8. Do not run a paid self-purchase. The first paid job must be independently
   initiated and is revenue only after platform settlement is verified.

## Inbound agent reply

The adapter sends one bounded reply only after a valid signed
`thread_inquiry`. It asks for the three accepted fields and includes the public
quickstart. Duplicate delivery of the same inquiry does not send twice.

Automatic bidding on `request.created` events is deliberately disabled.
