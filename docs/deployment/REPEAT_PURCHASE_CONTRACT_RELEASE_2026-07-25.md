# Executable repeat-purchase contract release

**Released:** 2026-07-26T06:03Z
**Outcome:** Live and publicly verified
**Money moved:** None

## Business outcome

Every successful paid x402 result that already exposes
`viridis_commerce.next_paid_routes` now also exposes
`viridis_commerce.repeat_purchase`.

The new object gives an autonomous buyer the complete contract for purchasing
the same service again with a new request:

- agent, tool, HTTP endpoint, and MCP endpoint;
- method and non-authoritative list price;
- input schema and concrete input example;
- required caller-supplied fields;
- an explicit new-input policy; and
- a fresh unpaid-402 quote contract.

This closes a concrete conversion gap. Paid results previously made
cross-service continuation executable but forced a satisfied buyer to
rediscover the contract for buying the same service again.

## Authorization and truth boundary

The repeat object is an unsigned offer, never an instruction to spend.

It explicitly requires:

- a new caller-owned request;
- no implicit reuse of the prior request or result;
- a new route-and-amount mandate;
- a fresh unpaid HTTP 402 challenge; and
- a separate signed settlement.

`auto_execute` remains `false`, `payment_required` remains `true`, and
`buyer_authorization_required` remains `true`. No repeat or follow-on payment
is signed, initiated, retried, or executed by the fleet.

The advertised price is not authoritative. The next unpaid challenge remains
the only authoritative source for route, network, asset, receiver, and amount.

## Buyer-path update

The installable `viridis-paid-tools` buyer skill now teaches agents to:

1. treat `repeat_purchase` as an unsigned same-service offer;
2. construct a new request only from caller-owned facts;
3. obtain a fresh spending mandate; and
4. fetch and validate a new unpaid challenge before any purchase.

The separate `next_paid_routes` behavior remains unchanged and still requires
independent authorization for every cross-service purchase.

## Verification

| Gate | Result |
|---|---:|
| Focused x402/buyer-skill checks | 77 passed |
| Gateway suite | 438 passed |
| Full fleet | 1,520 passed, 0 failed, 34/34 suites |
| Local + Registry + live coherence | Pass, 27 agents |
| Production-copy candidate | Healthy, no mount errors |
| Production-copy state | 33 rows, sequence sum 1,689 |
| Public buyer skill | `repeat_purchase` contract present |
| Public unpaid x402 preflight | HTTP 402 |
| Production database integrity | `ok` |

The copied-state and live checks verify exact repeat contracts for both:

- Regulatory Radar at $0.25 / 250,000 atomic USDC; and
- the fixed-price Hive at $5.00 / 5,000,000 atomic USDC.

No production paid smoke was used. Successful-payment response behavior is
covered by the mocked facilitator tests and by direct inspection of the exact
live image code path.

## Production and rollback

- live image:
  `sha256:d054258a076746beeb4c74757945f0f8411222413bd36bc2d98c294243ccf917`;
- rollback tag:
  `viridis-stable:prev-2026-07-25-repeat-purchase-contract`;
- rollback image:
  `sha256:5f89c39145a48191d170f5ea49d94220a37862c574edc7ff2e8b4266bedebe87`;
- image archive SHA-256:
  `918a389a8677ae719204704afd627d791b8ac505dae3bcf78e7c48539f5d11a8`;
- `x402_http.py` SHA-256:
  `360b1f4242d66d0e92aa8c3a2d518b169dd637771e8b0c506c2d2b59ef74494c`;
- buyer skill SHA-256:
  `1836ae733b701d1ef80b2e325cc800d7e657b2c5bc16ce8645104105a2ccee88`;
- transactional pre-release backup:
  `/root/viridis-repeat-purchase-contract-20260725/viridis_state.pre_repeat_purchase.sqlite3`;
- backup SHA-256:
  `fe7bc0b26d5945af2f7a8ca5d5597bba69e12c4e4c1bd4fdee37d3fad726acf6`.

The image was built off-host for `linux/amd64`, transferred with a matching
checksum, and run under resource limits against a copied production database
before cutover. Only the gateway container was recreated. Agent Market,
Caddy, and all persistent volumes were retained.

## Honest commercial baseline

Before and after:

- 7 classified settlements;
- 4 self settlements;
- 3 external settlements;
- 3 distinct external payers;
- 270,000 atomic USDC / $0.27 external revenue;
- 0 repeat external purchases;
- 0 Hive jobs; and
- $0 MRR.

This release makes a real repeat easier; it does not claim one occurred.

The current inbox and participating GitHub notifications contain no new buyer
request. Tom Smart's latest interoperability note says he will tag Viridis
when the next archive replay or scan cycle surfaces a real edge, so no
redundant message was sent. Two earlier Registry failure notifications were
also checked; later workflow runs already succeeded.
