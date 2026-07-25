# Pre-payment input validation release

**Released:** 2026-07-25

**Outcome:** Deployed, public-smoked, and restart-verified

**Money moved:** None

## Incident

The third external Regulatory Radar settlement succeeded on Base mainnet at
`2026-07-25T21:17:03Z`. A narrow production log window at that timestamp then
showed the deterministic core rejecting:

```text
jurisdiction=california
must be one of: ['au', 'ca', 'eu', 'global', 'jp', 'sg', 'uk', 'us']
```

The timing strongly correlates the validation error with the new paid request.
It does not identify the payer as a human or autonomous agent, and the log
alone cannot prove what response the buyer retained.

The contract defect was independently clear:

- the public x402 schema advertised `jurisdiction` as an unrestricted string;
- the HTTP x402 v2 route emitted a payment challenge and settled before
  parsing or validating the request body; and
- the Regulatory Radar core supports only eight country/region codes, not
  state-specific California coverage.

Silently converting California to US would overstate the service's
state-specific coverage. The safe correction is fail-before-pay validation
against the exact advertised capability.

## Fix

The Regulatory Radar x402 and A2A schema now advertises:

`AU, CA, EU, GLOBAL, JP, SG, UK, US`

Uppercase and lowercase values are accepted. HTTP x402 v2 now parses and
validates the request against the route's advertised JSON schema before it
builds a payment requirement.

An invalid request returns:

```json
{
  "error": "input does not match advertised schema",
  "error_type": "input_validation_error",
  "payment_required": false,
  "hint": "jurisdiction must be one of AU, CA, EU, GLOBAL, JP, SG, UK, or US; values are case-insensitive"
}
```

The response is HTTP 400 and contains no `PAYMENT-REQUIRED` header. The
facilitator, durable settlement ledger, A2A task store, and underlying tool are
not touched. This preflight is generic across all five HTTP x402 v2 routes.
A2A already validated before task creation; its now-exact schema closes the
same semantic gap there.

The default-off x402 v1 rail was not modified. Its SHA-256 remains:

`ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`

## Verification

| Gate | Result |
|---|---:|
| Focused x402 + A2A | 50 passed |
| Gateway suite | 422 passed |
| Full isolated fleet | 1,440 passed, 0 failed, 33/33 suites |
| Candidate invalid HTTP input | 400, no payment header |
| Candidate valid HTTP input | 402, payment header present |
| Candidate invalid A2A input | 400, no task created |
| Candidate database | integrity `ok`, 32 rows |
| Public invalid HTTP input | 400, `payment_required:false` |
| Public valid HTTP input | 402, payment header present |
| Public invalid A2A input | 400, no task created |
| Public Agent Card | exact jurisdiction enum present |
| Controlled restart | healthy; behavior and counters preserved |

No signed payment request or paid smoke was used.

## Production and rollback

Production:

- image:
  `sha256:eacdbc2b9d5a02bf90acde361a1ccb216bdff25b260ad131b15182a2d116cc40`
- `x402_http.py`:
  `5116ef2b81d7fdbc60cb25f47fe478faafc3e6f90c0ce16866cfc662dcbaf7db`
- `a2a_commerce.py`:
  `11353cf97ed8aaec43ebb374d8f8bdecfc3927a5644e233df871a127c86db3a6`

Rollback:

- tag: `viridis-stable:prev-2026-07-25-prepay-validation`
- image:
  `sha256:f716b452733b68c54c85a3523079559ae2407f017bdb9425564289a7eb62103e`

Only the gateway was recreated. Growth Agent, Agent Market, and Caddy retained
their existing containers. Disk remained 25% used with 18 GB free.

## State and commercial truth

The verified pre- and post-deployment SQLite backups are byte-identical:

- SHA-256:
  `3e559a2cf42b374e6608629f41cadb9b778b677c62d1d98bb8007244e2594e61`
- integrity: `ok`
- agent-state rows: 32
- durable off-droplet copies retained outside the public repository.

The live ledger remained:

- 7 strict settlements;
- 4 self settlements;
- 3 external settlements;
- 3 distinct external payer wallets;
- 0 repeat external purchases;
- 270,000 atomic USDC ($0.27) external revenue;
- 1 unpaid A2A input-required task and 0 completed; and
- 0 active subscriptions / $0 MRR.

This release prevents a buyer from paying for the known invalid request. It
does not refund or attribute the earlier payer, manufacture another purchase,
or convert unsigned interest into revenue.

## Communication decision

The relevant ecosystem email said the x402 endpoint-validator team will tag
Viridis when archive replay or a future scan surfaces another interoperability
edge. That is a wait-for-evidence invitation, not a request for a status bump.
No email, Discord message, duplicate listing, or community post was sent for
this correction.

The next business gate remains the first genuine repeat external purchase or a
fourth independent payer.
