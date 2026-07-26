# Executable repeat-commerce continuation release

**Released:** 2026-07-26 UTC  
**Outcome:** Deployed and publicly verified  
**Money moved:** None

## Business outcome

The existing `viridis_commerce.next_paid_routes` continuation contract is now
directly executable by an autonomous buyer. Every compatible follow-on offer
includes:

- exact HTTP and MCP endpoints;
- description;
- JSON input schema and a concrete input example;
- the required buyer-supplied fields; and
- a quote contract that requires a fresh unpaid HTTP 402 preflight.

The advertised list price is deliberately non-authoritative. The next unpaid
HTTP 402 response is the authoritative quote, so introductory eligibility and
any later pricing policy are evaluated at purchase time.

Nothing auto-executes. The buyer must supply caller-owned facts, hold a fresh
spend mandate, obtain the live challenge, and sign its own payment.

## Verification

| Gate | Result |
|---|---:|
| Focused continuation/buyer tests | 76 passed |
| Full fleet | 1,517 passed, 0 failed, 34/34 suites |
| Isolated production-copy health | `ok`, no mount errors |
| Isolated production-copy persistence | 33 rows, sequence sum 1,688 |
| Follow-on offers | 9/9 contain the executable contract |
| Public catalog | 9/9 offers verified |
| Public buyer skill | Updated instructions verified |
| Production health | `ok`, no mount errors |

The production-copy candidate used a transactional copy of the live database.
No paid route, facilitator, model, escrow, customer job, signature, or outbound
message was invoked.

## Production and rollback

Production image:

`sha256:ea5b2093edde340cc2fb43eea621a6389907a0ac403dd7c8328e6b4e000895be`

Rollback:

- tag: `viridis-stable:prev-2026-07-25-executable-continuation`
- image:
  `sha256:7830f28236d8e081681ca425dcc27f5423c8a0f894f1d8e355ffe1bd3f3cf416`

Transactional backup:

- path:
  `/root/viridis-repeat-commerce-20260725/viridis_state.pre_exec_continuation.sqlite3`
- SHA-256:
  `da3560f12eb91629fa7683255d596977bf37c81af542d06f3cb75fe3ed8e96ca`

Runtime source hashes:

- `deploy/gateway/x402_http.py`:
  `121a7847a9cf8184e2892de08345cbe893e21529ee61f97513d225172d37667e`
- `integrations/viridis-paid-tools/SKILL.md`:
  `97a25387504e0087b7321f044d211aa01dce6c328aa4383e417d107f1af71c41`

Only the gateway was recreated. Agent Market and Caddy retained their running
containers.

## Honest commercial baseline

The pre- and post-deployment strict external-settlement counters match:

- 3 external settlements;
- 3 distinct external payers;
- 270,000 atomic USDC / $0.27 external revenue;
- 0 repeat external purchases; and
- $0 MRR.

This release removes contract rediscovery after a purchase. It is conversion
infrastructure, not evidence that conversion occurred.

## Nightkeeper contract

Read-only monitoring must pin all nine follow-on offers and require
`input_schema`, `input_example`, `required_buyer_inputs`, and `quote`.
`quote.preflight_required` must remain true and
`quote.authoritative_source` must remain
`next_route_unpaid_http_402`. Monitoring must report repeat purchases from
versioned external settlements only and must never manufacture a payment.
