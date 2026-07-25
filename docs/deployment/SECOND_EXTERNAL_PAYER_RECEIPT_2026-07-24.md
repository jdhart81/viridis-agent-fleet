# Second external payer receipt

**Observed:** 2026-07-25T02:09:07Z (2026-07-24 America/Denver)

**Commercial outcome:** Two distinct external payers verified

**External revenue:** 260,000 atomic USDC ($0.26)

**Next gate:** A repeat purchase from an existing external payer

## Production evidence

A cache-busted production health read returned `status: ok`, no mount errors,
and the following durable HTTP x402 settlement counters:

| Counter | Fleet total | Regulatory Radar |
|---|---:|---:|
| Settlements | 6 | 3 |
| Self-settlements | 4 | 1 |
| External settlements | 2 | 2 |
| Distinct external payers | 2 | 2 |
| External revenue | 260,000 atomic USDC ($0.26) | 260,000 atomic USDC ($0.26) |

The authoritative fields are under
`payment_gate.x402.http_settlement_telemetry.total` and
`payment_gate.x402.http_settlement_telemetry.per_route`.

The prior verified baseline was one external settlement from one payer for
250,000 atomic USDC ($0.25). The new evidence therefore adds exactly:

- one external settlement;
- one distinct external payer; and
- 10,000 atomic USDC ($0.01) of external revenue.

All external x402 revenue remains on
`regulatory-radar/scan_regulations`. Self-settlements are excluded from
external revenue.

## Independent corroboration

External validator pull request
[`smartflowproai-lang/x402-endpoint-validator#12`](https://github.com/smartflowproai-lang/x402-endpoint-validator/pull/12)
records an independently completed fresh-wallet Regulatory Radar call for
10,000 atomic USDC, the exact request body, Base block provenance, and a
51-test validation result.

That pull request corroborates the second-buyer transaction context. It does
not prove a repeat purchase, recurring revenue, or a specific acquisition
channel. Viridis assigns no causal attribution without stronger evidence.

## Revenue boundary

The same production read confirmed:

| Signal | Verified value |
|---|---:|
| Repeat external purchases | 0 confirmed |
| Active subscriptions | 0 |
| MRR | $0 |
| Compliance Snapshot page views | 2 |
| Compliance Snapshot checkout starts | 0 |
| Verified paid Compliance Snapshots | 0 |
| Agent Market active profiles | 10 |
| Agent Market open work | 3 |
| Agent Market messages | 0 |
| Independently verified Agent Market jobs | 0 |
| A2A completed tasks | 0 |

Profiles, open work, page views, self-payments, tests, and unsigned pipeline are
not customer revenue.

## Next commercial move

The next proof is one independently initiated repeat Regulatory Radar purchase
from either existing external payer. Viridis should support a real buyer
question quickly and point that buyer to the bounded one-route quickstart.

Do not self-purchase, expand the fleet, or send a broad Discord blast to
manufacture activity. No additional owned-channel Discord post is due while
the current channel cooldowns remain active and there is no inbound question.

## Public proof chain

- [Regulatory Radar quickstart](https://mcp.viridisconservation.com/quickstart)
- [Live x402 catalog](https://mcp.viridisconservation.com/x402/catalog)
- [x402 fixture contract release](X402_FIXTURE_CONTRACT_RELEASE_2026-07-24.md)
- [Current fleet status](../../STATUS.md)
