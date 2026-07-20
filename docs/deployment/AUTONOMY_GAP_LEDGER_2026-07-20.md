# Autonomy gap ledger — 2026-07-20

**Wave:** 10, Full Autonomy Closure
**Audit status:** reviewed before production-code changes
**Production baseline verified:** 1156 passed / 0 failed / 0 errors, 29/29 suites on the droplet
**Legal status:** engineering audit, not legal advice. The Connect conclusion remains subject to the separate FA-A4 research record and counsel.

## Classification rules

- **FA-I1:** Viridis-only allocation; autonomous, no external counterparty.
- **FA-I2:** external counterparty is Stripe Connect-onboarded and `payouts_enabled` pull-verifies true; autonomous through the Transfer API.
- **FA-I3:** genuine non-Connect third-party funds transmission; keep the certified human/counsel gate.
- **FA-I4:** account-holder-only setup such as KYC, platform enablement, or credential provisioning; document separately, never count as a recurring autonomy gap.
- **Unclassified:** does not fit FA-I2/FA-I3/FA-I4 cleanly and therefore requires an explicit scope decision rather than an inferred code change.

## Audit scope and method

The audit searched `mark_executed`, `manual fallback`, `certified manual`, `action_for_justin`, `human-gated`, payout, refund, claimant, cash-out, and transfer markers across `weave.py`, `escrow_custody.py`, `bond_bridge.py`, `connect_rail.py`, `participant_bridge.py`, gateway tool wiring, and the arbitration/surety cores. Each apparent gate was then traced to the actual execution primitive rather than classified from comments alone.

## Current-state ledger

| ID | Path | Current source truth | Classification | Wave-10 disposition |
|---|---|---|---|---|
| FA-01 | Weave, EnergyAI -> Viridis Conservation | New source always creates a same-account `cash_instruction` with `executed: true`, but live `/healthz` still reported one 375-minor pre-WV4 record as pending. Read-only inspection confirmed that record has the old fixed beneficiary text, no payee/rail/scope, and `action_for_justin`. | FA-I1 | Preserve rate/escalator and default behavior; on restore, durably close only an explicit `same_account_allocation` or the exact old fixed EnergyAI-to-Viridis schema. Remove the obsolete human action field. Never touch external/manual records. |
| FA-02 | Weave -> external restoration payee | Mentioned in the module doctrine, but no callable payee parameter or external transfer path exists. The only implementation is the fixed Viridis beneficiary. | FA-I2 when Connect-onboarded; FA-I3 otherwise | Add an optional external payee route: Connect transfer exactly once by purpose key; certified manual fallback only when not onboarded/incomplete; transient rail errors fail closed. |
| FA-03 | Cash escrow refund to original payer | `escrow_custody.settlement_instruction` calls Stripe Refund against the original Checkout evidence and records `refund_id`, exactly once. | Same-originator refund, closed | No change. |
| FA-04 | Cash escrow release to Connect payee | Pull-verifies `payouts_enabled`, executes `ConnectRail.execute_transfer`, records `transfer_id`, and refuses transient errors without falling back. | FA-I2, closed | No change to EC/CR core. |
| FA-05 | Cash escrow release to non-Connect payee | Produces `rail: manual`, `executed: false`, `action_for_justin`, and onboarding guidance; admin mark is the only completion path. | FA-I3 | Keep the gate. This is the only certified fallback and is not an autonomy defect unless counsel later clears a non-Connect structure. |
| FA-06 / FA-15 | Bond provider return | **Closed 2026-07-20.** `bond_bridge.certify_settlement` issues a partial Stripe refund against the original collateral Checkout Session for collateral minus premium minus slashed amount. It records `refund_id` before `executed:true`; deterministic `bond-provider-return:<bond_id>` idempotency makes retry safe. | Same-originator refund, closed | Every executed bond leg now carries `refund_id`, `transfer_id`, or certified `money_primitive_id`; a boolean alone is not payment evidence. |
| FA-07 | Bond slash claimant, Connect-onboarded | Already calls `ConnectRail.execute_transfer` with purpose `bond-slash:<bond>:<claim>`, records `transfer_id`, and is replay-safe. | FA-I2, closed | A3 is already implemented. Add/retain targeted proof tests; do not refactor bond core. |
| FA-08 | Bond slash claimant, non-Connect/incomplete | Produces a manual claimant leg with onboarding guidance and admin close-out. | FA-I3 | Keep the gate. |
| FA-09 | Arbitration ruling -> escrow state -> cash settlement | `ParticipantBridge.execute_ruling` applies `release` or `refund` to the escrow and persists the terminal transition, but does not invoke the custody settlement path. A second recurring call is therefore required before the already-built Refund/Connect rail runs. | FA-I2 for Connect release; same-originator refund for refund rulings; FA-I3 manual fallback otherwise | Close the orchestration gap without changing EC/CR: after durable ruling execution, invoke the existing custody settlement instruction; persist/return the result; make replay retry only an incomplete settlement and never repeat money movement. |
| FA-10 | Participant cash-backed earnings | No separate payout engine exists. Cash-backed earnings are the same escrow records covered by FA-03/04/05; internal earnings spending remains a distinct service-credit path. | Delegated to FA-03/04/05 | Preserve `spend_payee_earnings`; update stale explanatory text only if touched. |
| FA-11 | Participant `claim_payee` review marker | Claim records say `pending-human-review`, but that field is not consulted by custody or Connect and does not gate money movement. Stripe onboarding/KYC is the actual external-money eligibility gate. | Not a money-movement gate | Do not treat as payout authorization. Retain claim-secret controls for internal credits. |
| FA-12 | Connect platform/account enablement and payee KYC | Platform Connect enablement/scopes are complete; every new payee must complete Stripe-hosted onboarding and satisfy Stripe requirements. | FA-I4 | Exempt one-time/account-holder setup; never report it as a recurring CEO execution step. |
| FA-13 | Future non-Connect third-party rails, including direct crypto payouts | No approved licensed intermediary path exists in the audited modules. | FA-I3 | Remain counsel-routed and human-gated. Do not add a new rail. |
| FA-14 | `x402-intro-v1` activation | Built and tested behind default-off `X402_INTRO_ENABLED`; not a recurring execution task after a decision. | FA-I5 design direction | Present one go/no-go decision at handoff. No price/code change in this wave. |

## FA-I4 exemptions (not autonomy defects)

1. Stripe platform KYC, beneficial-owner verification, and any future regulatory or licensing filing that legally requires the account holder.
2. Creating/restricting the Stripe or growth-agent credentials and completing any provider OAuth consent screen that legally binds the account owner.
3. Connected-payee onboarding facts only the payee or its authorized representative can provide.
4. Platform-owner acceptance of materially changed provider terms.

These are one-time identity/authority acts. Scheduling transfers, retrying eligible transfers, posting approved content, checking outcomes, and choosing the next target are recurring operations and remain in-scope for automation.

## Review result before code changes

- **A2 real scope:** new external-payee composition in Weave; default same-account behavior and pricing/rate schedule remain unchanged.
- **A3 real scope:** already closed in current source. Verification only.
- **Additional cleanly classified gap:** FA-09 arbitration-to-custody orchestration.
- **Live-state addition:** production health exposed one legacy same-account Weave record that source grep could not reveal. WV8 closes that FA-I1 bookkeeping remainder automatically and narrowly.
- **FA-15 closure addendum:** after the separately authorized zero-exposure quantification, FA-06 was classified as a same-originator partial refund and closed through the already-proven EC5 Stripe refund primitive. No new money path was introduced.
- **Frozen boundaries confirmed:** the MCP x402 v1 lane, ConnectRail CR1-CR7, EscrowCustody EC-series, participant internal-credit spending, and list prices are outside the edit scope.
