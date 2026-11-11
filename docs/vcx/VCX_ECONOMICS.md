# VCX v0.1 economics

Every amount in the local VCX demonstration is simulated. A successful job produces simulated seller earnings and simulated marketplace fees. It does not establish customer demand, real revenue, redeemable funds or a functioning payout business.

## Price and fee contract

The seller discloses a fixed job price and currency/minor units. The buyer supplies a maximum authorized price. Matching may prioritize reliability, latency and energy preferences as well as price; a quote above the maximum remains ineligible regardless of its score.

The default marketplace simulation fee is 500 basis points (5%). Fees round upward in minor units: `fee = (price_minor × fee_bps + 9,999) // 10,000`, and the rate is frozen with the accepted job. For a price of 1,000 minor units, the fee is 50 and the seller receives 950 pending simulated units. At very small prices this rounding can consume the whole price: a one-unit job has a one-unit fee and zero net seller earnings. A full cancellation before accepted delivery returns the buyer's entire hold and creates no fee or seller earning.

| Example, simulated minor units | Buyer available | Held for job | Seller pending | Fees |
|---|---:|---:|---:|---:|
| Buyer funded | 2,000 | 0 | 0 | 0 |
| Price 1,000 authorized | 1,000 | 1,000 | 0 | 0 |
| Accepted and settled | 1,000 | 0 | 950 | 50 |
| Seller reinvests 400 under policy | 1,000 | 0 | 550 | 50 |

The last row additionally creates 400 available simulated units for the seller. It is an internal transfer, not new capital. The simulated external funding contra account balances the initial 2,000-unit seed.

## Capital controls

The capital manager reports available spending budget, protected reserve, held exposure, pending earnings, cumulative spending, gross service revenue, fees, realized margin and allowed reinvestment. Pending earnings are not automatically available to spend.

An owner sets the spend limit, minimum reserve, maximum in-flight exposure and reinvestment ratio. Reinvestment eligibility is bounded by both unreinvested pending earnings and the cumulative reinvestment allowance. Spending remains subject to the same budget rules after reinvestment. A buyer cannot raise these limits through a signed marketplace request.

An accepted quote estimates job cost. Expected seller revenue is conditional on successful accepted delivery and should never be counted as already available funding. Pending work can fail, be cancelled or time out. A production design also needs a reserve against refund, dispute and payout liabilities.

## Unit economics to measure

For a seller on a defined accounting horizon, use:

\[
\text{contribution margin} = \text{accepted gross service revenue}
- \text{market fees} - \text{compute cost} - \text{energy cost}
- \text{verification cost} - \text{retry/support cost}.
\]

For the marketplace, use fees actually collected less payment processing, payouts, refunds, fraud losses, infrastructure and support. A 5% nominal fee is not a prediction of net margin. Existing hosted cash-custody fee floors may differ and must not be silently overwritten by the simulation rate.

The deterministic demo does not meter electricity or price real model tokens. Resource counters and configured costs must identify whether they are measured, modeled or declared. Do not infer energy savings from a broker's energy preference alone.

## Main commercial risks

- **Thin demand:** more listings do not imply paid demand or useful repeat use. Measure accepted useful deliveries and buyer repurchase.
- **Verification cost:** cheap work can become uneconomic if independent acceptance costs more than the service.
- **Adverse selection:** self-reported speed and reliability may attract selection without reflecting actual outcomes. Keep declared and observed metrics separate.
- **Payment minimums:** card, transfer, currency and refund costs can overwhelm small job fees. Batch settlement would require a reviewed custody design.
- **Correlated failures:** providers sharing one model, host or credential arrangement may fail together. Three simulated sellers are not independent infrastructure.
- **Capital illusion:** circular internal trading can inflate gross volume without producing useful outside revenue. Exclude internal simulations from cash MRR.
- **Provider rights:** authorized task fulfillment and resale of provider entitlements are different activities. Capacity onboarding must document the right to supply the service.

## Production gate

Before real economics can be evaluated, verify owner-authorized genuine funding, eligible seller onboarding, provider rights, settlement/refund/dispute responsibilities, operational reconciliation and the required business/legal review. Technical Stripe Connect support in the existing service does not resolve these questions. Live charges and payouts require separate explicit authorization and remain disabled in this MVP.
