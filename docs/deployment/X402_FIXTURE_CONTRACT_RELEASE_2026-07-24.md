# x402 fixture contract release

**Released:** 2026-07-24  
**Outcome:** The live Regulatory Radar x402 v2 quote now publishes one exact,
copyable validator fixture across the buyer quickstart and Bazaar input schema.

## Canonical fixture

```http
POST https://mcp.viridisconservation.com/x402/regulatory-radar/scan_regulations
Content-Type: application/json

{"jurisdiction":"US","sector":"energy","query":"45V clean energy tax credit emissions disclosure"}
```

The buyer-facing contract now states the live v2 sequence explicitly:

1. the server returns `PAYMENT-REQUIRED`;
2. the buyer retries with `PAYMENT-SIGNATURE`; and
3. a settled response returns `PAYMENT-RESPONSE`.

`X-PAYMENT` and `X-PAYMENT-RESPONSE` are identified as legacy v1 names.
`X402-Payer-Address` remains an unsigned introductory-price quote hint only;
the signed payment authorization determines eligibility.

## Contract changes

- The quickstart curl and Python examples use the same canonical payload.
- The Regulatory Radar Bazaar schema includes the optional `query` field.
- The input body is strict with `additionalProperties: false`.
- The public first-call guide pins the same endpoint, body, and v2 sequence.
- Regression gates pin the canonical payload, schema, and legacy-header
  warning.

## Verification

- Operational-source focused gates: **52 passed / 0 failed**
- Public-mirror focused gates: **52 passed / 0 failed**
- Isolated candidate:
  - container health `healthy`;
  - exact quickstart body and all three v2 headers present;
  - unpaid request returned HTTP 402;
  - `x402Version` `2`;
  - network `eip155:8453`;
  - introductory quote `10000` atomic USDC;
  - resource URL matched the public Regulatory Radar route;
  - Bazaar input body matched the canonical fixture;
  - schema properties were `jurisdiction`, `query`, and `sector`;
  - `additionalProperties` was `false`; and
  - no payment was signed or settled.
- Production:
  - gateway health `healthy` and public status `ok`;
  - live image matched the verified candidate;
  - cache-busted quickstart showed the canonical payload and v2 guidance;
  - an unpaid public request reproduced the exact candidate HTTP 402 contract;
  - Caddy, Agent Market, and Growth Agent were not recreated; and
  - the temporary candidate container was removed after cutover.

## Recovery proof

- Pre-cutover online state backup:
  `/data/backups/viridis_state-20260724-x402-fixture.db`
- Backup SHA-256:
  `2a08f5fbe082f913f9b1876d19e01cea4a5b4b76d0b0385024c07f27fdc64843`
- SQLite integrity: `ok`
- Rollback tag:
  `viridis-stable:prev-2026-07-24-x402-fixture`
- Rollback image:
  `sha256:ee4f923e36351692b0ab17cf9c5a39bfe1ff09ac898c1ef0fe0cd4b108169e1b`
- Live image:
  `sha256:a4b3c2ee3eea0e25231ee0d5732885bfcec984885db17cc898e288f9f6086335`
- Gateway container:
  `3498da4feb61698e33e594d84ec78dfc5b1fedc40876a0fa8d129fdd144e4b47`
- Adjacent containers retained:
  - Caddy
    `5d5ecdd94bb2bd2003d8b6e79aced448b957b2f8c4c855ed1c895fdfce01764d`
  - Agent Market
    `0947fce026dc79988a6567f5cc599a6d0d841c0b3dea1e85a792060eb2b4565c`
  - Growth Agent
    `982eb594f36b67be4dca96a97185ff2cdba2273ddb158f8f12c5eacfa5b65ed2`
- Disk after release: 24 GB total, 5.7 GB used, 18 GB free, 25% used.

## Community handoff

The exact payload, deployed header contract, second-external-payer
corroboration, and validator-patch status were sent once to `TomSmart_ai` in
Coinbase Developer Platform `#🌐｜x402` at 16:42 America/Denver. The message
was verified under the `Viridis` account. Content SHA-256:
`f1d8557c5f7076ce62da21515b7d7e2552e027eb42641aa21f19c166df551bf2`.

The send disclosed the remaining GitHub reauthentication gate and did not
claim that a pull request already existed.

## Revenue boundary

The pre- and post-release settlement counters were identical:

| Metric | Verified value |
|---|---:|
| HTTP x402 settlements | 6 |
| External settlements | 2 |
| Distinct external payers | 2 |
| External revenue | 260,000 atomic USDC ($0.26) |
| MRR | $0 |

This release makes the successful second-buyer exchange reproducible for
validators. It did not create a new settlement or recurring revenue.
