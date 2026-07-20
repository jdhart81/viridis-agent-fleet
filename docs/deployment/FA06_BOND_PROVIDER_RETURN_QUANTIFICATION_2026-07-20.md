# FA-06 bond provider-return quantification — 2026-07-20

**Scope:** read-only production audit required by the Wave 10 cutover authorization
**Code changes at audit time:** none
**Production source queried:** `/data/viridis_state.db`, `agent_state` namespace `bonds`, in the live Wave 9 gateway before the Wave 10 cutover

## Result

| Measure | Production result |
|---|---:|
| Collateralized bond records | 0 |
| Bond settlement instructions | 0 |
| `same_party_refund` legs with `executed:true` | 0 |
| Money primitive found | 0 |
| No money primitive found / bookkeeping-only | 0 |
| Total amount at stake | **$0.00** |
| Affected date range | Not applicable |
| Affected providers | 0 |
| Affected-provider disputes or inquiries | Not applicable; there are no affected providers or settlement records |

The `bonds` persistence namespace has no row in production. A direct read-only
snapshot query therefore returned `bond_count: 0`, `instruction_count: 0`, and
`snapshot_updated_at: null`. There were no records for which a Stripe
`refund_id`, `transfer_id`, or equivalent primitive could or needed to be
cross-checked.

## Evidence-based classification

This is **not evidence of a historical non-payment** and not evidence of a
logging-only payment. It is a **latent implementation/semantic gap with zero
production exposure so far**: current source can label a future
`provider_return` leg `same_party_refund` and `executed:true` without recording
an API money primitive, but production has never created a collateralized bond
or provider-return settlement.

Urgency is therefore prospective rather than incident-response urgency. Before
the first collateralized bond is sold or settled, the provider-return execution
contract should receive its separately authorized custody design. This audit
does not propose or implement that fix, and `bond_bridge.py` remains unchanged.

## FA-15 closure addendum

After this zero-exposure result, Justin separately authorized the prospective
fix. `BondBridge.certify_settlement` now refunds the provider's remaining
collateral through the original Stripe Checkout Session before recording the
provider-return leg as executed. The deterministic refund idempotency key is
`bond-provider-return:<bond_id>`, and the executed leg carries `refund_id` and
`payment_intent`. Refund errors record no settlement instruction and remain
retryable. Manual claimant close-out now also requires an external
`money_primitive_id`, so no executed bond leg can rely on a bare boolean.

The historical quantification above remains unchanged: there were zero records
to migrate, zero affected providers, and $0.00 at stake.

## Audit method

1. Opened the mounted production SQLite database read-only from the running
   gateway container.
2. Queried `agent_state` for the `bonds` namespace used by `BondBridge`.
3. Counted persisted `bonds` and `instructions`, then selected settlement legs
   whose `scope` is `same_party_refund` and whose `executed` flag is true.
4. The namespace was absent, so the audit terminated with zero affected rows;
   no Stripe write or money movement was attempted.
