# Stripe Connect residual licensing research — 2026-07-20

**Question:** When a Viridis payment and third-party disbursement run end-to-end through Stripe Connect, does Stripe's licensed-transmitter status eliminate all residual money-transmission exposure for Viridis?
**Status:** preliminary engineering/compliance research only; **not legal advice and not counsel clearance**.
**Prior question:** `THIRD_PARTY_PAYOUT_LICENSING_QUESTION_2026-07-19.md`.

## Short answer

The primary sources support Stripe Connect as the correct licensed execution rail, but they do **not** support the blanket statement that Stripe's licenses automatically eliminate every federal or state obligation for the platform.

Stripe expressly lists US money-transmitter licensing, KYC/AML, and sanctions screening among Connect's compliance capabilities. Stripe also documents separate charges and transfers as a normal marketplace funds flow and executes transfers to connected accounts. Those facts support continuing autonomous transfers to pull-verified Connect accounts.

At the same time, Stripe states that a platform can remain the merchant of record and legally responsible for the transaction, refunds, disputes, fees, and negative balances. FinCEN states that money-transmitter status is facts-and-circumstances based and that the payment-processor exclusion depends on four conditions, including formal agreement with the seller/creditor and use of qualifying clearance and settlement systems. No reviewed Stripe document promises that using Connect is itself a complete federal or fifty-state safe harbor.

**Engineering disposition:**

1. Keep automated, exactly-once Connect transfers for onboarded payees. Replacing the API call with a human Dashboard click would not change the underlying legal facts and would recreate a recurring operational defect.
2. Keep the existing certified gate for genuinely non-Connect third-party disbursements.
3. Do not describe Connect as eliminating *all* Viridis exposure. Describe it narrowly as Stripe executing the regulated transfer and onboarding/screening the connected account, while Viridis retains its platform/MoR responsibilities.
4. Obtain US payments counsel confirmation of the exact marketplace agreements and state footprint before declaring FA-I3 categorically closed for every Connect use case.

## Primary-source findings

### 1. Stripe supplies regulated-payment and onboarding capabilities

Stripe's Connect risk documentation says its platform compliance capabilities include identity verification, risk-based KYC/AML checks, sanctions screening, and US money-transmitter licenses. It also explains that responsibility allocation depends on the connected-account configuration; assigning some risk to Stripe does not absolve the platform of its own balance and responsibilities.

Source: [Stripe — Risk and liability management with Connect](https://docs.stripe.com/connect/risk-management), especially “Know Your Customer (KYC) and compliance.” Accessed 2026-07-20.

### 2. Connect explicitly supports marketplace transfers to connected accounts

Stripe documents separate charges and transfers as a marketplace flow in which a charge lands on the platform and the platform creates a Stripe Transfer to one or more connected accounts. Stripe also documents automatic payout from the connected account's Stripe balance to the external bank account.

Sources:

- [Stripe — Separate charges and transfers](https://docs.stripe.com/connect/separate-charges-and-transfers)
- [Stripe — Pay out to connected accounts](https://docs.stripe.com/connect/marketplace/tasks/payout)

Accessed 2026-07-20.

### 3. Connect does not erase merchant-of-record responsibilities

Stripe defines the merchant of record as the entity with legal responsibility for a transaction. For indirect charges without `on_behalf_of`, the platform is the merchant of record. Stripe's marketplace guide for separate charges and transfers likewise says the platform is the merchant of record and bears Stripe fees, refunds, and chargebacks.

Sources:

- [Stripe — Understand the merchant of record in a Connect integration](https://docs.stripe.com/connect/merchant-of-record)
- [Stripe — Accept a payment using separate charges and transfers](https://docs.stripe.com/connect/marketplace/tasks/accept-payment/separate-charges-and-transfers)

Accessed 2026-07-20.

### 4. The federal payment-processor exclusion is conditional, not product-branded

FinCEN's FIN-2014-R009 describes four conditions for the payment-processor exclusion:

1. facilitate a purchase of goods/services or payment of bills other than money transmission;
2. operate through clearance and settlement systems that admit only BSA-regulated financial institutions;
3. act under a formal agreement; and
4. have an agreement at least with the seller or creditor that receives the funds.

FinCEN also says money-transmitter status is a facts-and-circumstances inquiry and could not reach a definite conclusion where disbursement details were incomplete.

Source: [FinCEN FIN-2014-R009 — Company Acting as an ISO and Payment Processor](https://www.fincen.gov/resources/statutes-regulations/administrative-rulings/application-money-services-business). Accessed 2026-07-20.

### 5. An underlying transaction-management service can matter

In FIN-2014-R005, FinCEN did not treat a secured buyer/seller transaction service as a money transmitter on the represented facts. The service managed the underlying transaction and dispute process, paid only the named seller, and did not handle unrelated third-party payments. This is directionally relevant to Viridis escrow, but it is a fact-specific administrative ruling, not a portable exemption.

Source: [FinCEN FIN-2014-R005 — Secured Transaction Services](https://www.fincen.gov/resources/statutes-regulations/administrative-rulings/whether-company-offers-secured-transaction). Accessed 2026-07-20.

## Answer to FA-A4

The reviewed sources **do not converge on “fully covered”** in the categorical sense requested by FA-A4. They converge on a narrower conclusion:

- Stripe provides the licensed Connect transfer/payout infrastructure and connected-account screening.
- Viridis can remain the merchant of record and retains transaction/platform obligations.
- Federal exclusions turn on the exact agreements and funds flow, and state licensing is not resolved by the product name alone.

Accordingly, Wave 10 does **not** close FA-I3 as a universal legal rule. It closes recurring human execution on the already-approved Connect rail while preserving the human/counsel gate for non-Connect disbursements and a one-time counsel review of the Connect marketplace structure. That review is an FA-I4-style legal/account setup matter, not a per-transfer approval queue.

## Counsel confirmation packet

Counsel should receive:

1. the platform's current Stripe Services/Connect agreements and connected-account responsibility settings;
2. the Checkout charge type and whether `on_behalf_of`, `transfer_group`, and `source_transaction` are used;
3. the payee agreement and customer-facing merchant-of-record language;
4. the states/countries of Viridis, payers, and connected payees; and
5. the three exact flows: escrow release, bond claimant payment, and external Weave restoration payee.

The requested legal answer should distinguish federal MSB treatment, each relevant state's licensing/agent-of-payee rules, card-network MoR duties, and Stripe contractual responsibility. No engineering document should substitute for that opinion.
