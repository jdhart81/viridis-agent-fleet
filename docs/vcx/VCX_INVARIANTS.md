# VCX v0.1 invariants

These are acceptance requirements. Passing tests establish behavior for the tested implementation and modeled conditions; they do not establish operational or legal readiness for a live marketplace.

## Authorization and isolation

| ID | Required invariant | Verification obligation |
|---|---|---|
| A1 | Only seller-authorized service capacity may be listed. No subscription credits, API keys, accounts or provider entitlements are sold or transferred. | Reject unsupported supply types and credential-bearing inputs. |
| A2 | Every public mutation is authenticated against an active signed Market Network identity. Its actor must own the affected buyer or seller role. | Wrong actor, forged signature, expired profile, stale auth, replayed nonce and changed-body replay tests. |
| A3 | Owner policy and simulated account seeding are trusted setup controls, unavailable to buyer-facing MCP mutations. | API surface and attempted policy/funding mutation tests. |
| A4 | Existing Fleet identities, service APIs, payment semantics and revenue counters remain compatible. | Market Network/ORC regressions; no VCX simulation entry in real settlements. |
| S1 | Buyer payloads select only fixed reviewed provider identifiers and strict service-specific schemas. They cannot provide executable code, import paths, URLs or host access. | Unknown service, unexpected fields, excessive work and credential leakage tests. |
| S2 | A service executes without receiving either party's private credentials. | No secret-bearing metadata passthrough; receipts/logs contain only validated task data and public references. |
| S3 | v0.1 performs no live charge, refund, transfer, payout, deployment or remote model call. | Local execution tests and adapter dependency review; simulation mode is explicit in all financial outputs. |

## Money and capital

All amounts are nonnegative integers in an explicitly named simulation currency/minor-unit system. Booleans, floats, nonfinite numbers and implicit currency conversion are invalid. A negative simulated funding contra balance is an accounting source, not a spendable account.

Let `A_i` be agent i's simulated available budget, `H_j` a job hold, `P_i` seller pending earnings, `F` marketplace fees and `X` the external simulated funding contra balance. The conservation requirement is:

\[
\sum_i A_i + \sum_j H_j + \sum_i P_i + F + X = 0.
\]

Each journal operation must balance independently. No reconciliation operation may mint value to hide a discrepancy.

| ID | Required invariant | Verification obligation |
|---|---|---|
| M1 | A buyer cannot reserve beyond its available balance, owner spend cap, maximum exposure or protected operating reserve. | Boundary and concurrent-process reservation tests. |
| M2 | The accepted quote freezes service/version, price, fee rate, seller and acceptance terms. Authorization never increases the buyer's maximum price. | Changed listing and conflicting authorization replay tests. |
| M3 | At settlement, buyer cost equals seller pending earnings plus marketplace fee. At hold release, the complete unspent hold returns exactly once. | Per-operation and aggregate conservation checks. |
| M4 | A completed job has one authoritative settlement; failures/cancellations have one authoritative hold release or refund outcome. | Duplicate events, concurrent settlement, changed-terms replay and terminal-state tests. |
| M5 | Simulation balances, service credits, pending earnings and actual settled funds have distinct meanings. VCX v0.1 reports no actual settled funds or actual revenue. | Response/receipt labels and existing accounting isolation checks. |
| M6 | Reinvestment moves authorized simulated pending earnings into available budget; it creates no value and remains subject to owner policy. | Reinvestment ratio, reserve, cap, duplicate-request and overspend tests. |
| M7 | A failed durable write cannot authorize spending, acknowledge settlement or fall back to volatile state. | Write-failure/rollback and restart tests. |

Default simulated fee: `fee_bps = 500`. For gross price `p`, fee is rounded upward, `ceil(p × 500 / 10,000)`; seller pending earnings are exactly `p − fee`. Any change in rate or rounding must be explicit and covered by receipts/tests.

## Jobs and proof

| ID | Required invariant | Verification obligation |
|---|---|---|
| J1 | An idempotency key is bound to canonical immutable terms. The same request can replay; changed terms cannot reuse its key. | Duplicate job/payment calls and conflict tests. |
| J2 | Capacity limits and expiry are checked at selection and reservation. Capacity cannot be oversubscribed by concurrent buyers. | Expired listing, deadline, capacity and simultaneous reservation tests. |
| J3 | Execution requires an authorized durable hold and an unexpired execution claim. | Direct execution without authorization; timeout and lease tests. |
| J4 | Recovery, cancellation and late workers cannot spend twice, revive a terminal job or lose a liability. | Restart, interrupted execution, fencing and delayed-result tests. |
| J5 | Verification is tied to the accepted provider, input and artifact hash. A seller's assertion alone cannot release a hold. | Tampered result, mismatched service/input, verification failure and duplicate verification tests. |
| J6 | Receipt state reflects the authoritative job and ledger outcome, with public identity references and service version. | Recompute output hash, receipt integrity, optional issuer-signature and restart retrieval tests. |
| J7 | A dispute cannot trigger automatic cash payout or irreversible financial correction. | Disputed/frozen-state behavior and documented manual-resolution boundary. |

A deterministic acceptance function establishes its defined software property only. It does not verify arbitrary research conclusions, subjective usefulness or real-world construction correctness. Lean proof claims are limited to named formal statements and trusted assumptions; no Lean artifact is claimed by v0.1 unless separately supplied and checked.

## Review invariants (2026-11-11)

Added after independent review. Each has a regression test in `tests/test_vcx_review_fixes.py` that fails on the pre-review build.

| ID | Required invariant |
|---|---|
| R1 | Accepted work is paid. The buyer may cancel only until a result exists. The result is withheld until settlement. Verification and settlement can be driven by either party or by recovery and never expire. A dispute freezes the hold and is closed only by the seller's concession or a trusted third-party decision. |
| R2 | An expired lease holds neither seller capacity nor buyer budget, with or without a scheduler. Delivered and disputed jobs do not occupy a slot. |
| R3 | A signed action names one exchange. It is rejected by any other exchange that shares the same identities. |
| R4 | Every signed call consumes its nonce, reads included. The signed envelope is stored with the outcome of each mutation. |
| R5 | The owner can change policy and freeze an account through trusted, audited controls that no signed agent request can reach. A cap cannot be set below committed spending. Existing holds are honoured after a freeze. |
| R6 | Only a seller fault (provider failure, contract rejection, conceded or arbitrated refund) excludes the listing or counts against its observed record. Host timeouts, interrupted execution and buyer lapses do not. |
| R7 | A receipt carries the input hash, output hash, listing, quote, exchange, service version, fee and seller net. Only a settled job has a settlement time. |
| R8 | An internal fault is reported as `ExchangeInternalError` and logged with the action and exception class, never as a caller rejection and never with caller input. |
| R9 | VCX reaches Market identities only through the three public extension methods. Verification through them moves no Market state. |
