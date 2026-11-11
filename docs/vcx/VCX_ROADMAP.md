# VCX roadmap

## Stage 0 — Local simulation vertical slice

Deliver a signed, durable extension inside Agent Market Network with three simulated seller profiles, two simulated buyers, deterministic discovery/ranking, approved budget holds, allowlisted execution, acceptance evidence, simulated settlement, fees and bounded reinvestment. Exercise duplicate requests/notifications, contention, expiry, cancellation, verification failure, refunds and restart recovery.

Completion means the local checks pass and every financial result is labeled simulation. It does not authorize a production mount, paid listing, cash funding or payout. Preserve existing marketplace APIs and revenue accounting.

## Stage 1 — Harden interoperability and evidence

- Stabilize the capacity and receipt schemas with versioning and golden compatibility examples.
- Replace narrow private Market Network API dependencies with a reviewed public extension-auth interface if needed.
- Add independent receipt validation and explicit issuer trust configuration; manage signing keys through existing owner-controlled infrastructure.
- Expand cross-process contention, crash-boundary and backup/restore tests. Define reconciliation alarms and a manual recovery procedure.
- Integrate artifact-bound security/preflight evidence without treating an attestation as blanket security certification.
- Collect measured service reliability and declared-versus-measured resource usage separately. Avoid importing simulation volume into real reputation.

Exit gate: protocol compatibility, operational recovery evidence and an independently reviewed security boundary.

## Stage 2 — Controlled real service execution

Connect a small allowlist of existing Fleet execution interfaces in a separate reviewed adapter. Each service needs strict task/acceptance schemas, exact authorization binding, durable artifact recovery, timeout/cancellation behavior and bounded cost. The buyer approves the actual price and service before any paid call.

Remote code, arbitrary containers and general GPU rental remain out of scope until a dedicated isolation design exists. A network URL must never become an unrestricted execution target. Provider failure recovery must distinguish safe deterministic retries from ambiguous external side effects.

Exit gate: service-level sandbox evidence and separate authorization for the specific external actions. Continue simulated settlement until genuine funds and payout readiness are established.

## Stage 3 — Reviewed genuine financial rail

The hosted service already contains technical Stripe checkout/custody, Connect onboarding/transfers and reconciliation interfaces. Reuse the reviewed service boundary rather than copying proprietary gateway code into this repository.

Before enabling it, establish and document:

1. The business relationship, provider supply rights, permitted jurisdictions and required legal/compliance decisions, including the open third-party payout licensing question.
2. Seller eligibility/onboarding and actual payout capability; no account is treated as payable merely because a connected-account identifier exists.
3. Genuine available owner-authorized funding, cash-versus-credit separation, exact maximum spend and refund/chargeback responsibility.
4. Payment verification, stable idempotency keys, destination restrictions, liabilities, fee floors, dispute handling and cash reconciliation across crashes.
5. Test-mode integration evidence for failure, duplicate, cancellation, refund and transfer ambiguity; production release approval for a pinned artifact.

Live charges and payouts require explicit authorization. Internal credits and pending ledger entries do not become money through a configuration flag.

## Stage 4 — Bounded self-funding operation

Add owner policies for cumulative and per-job spending, reserve ratios, exposure, provider concentration, stop-loss conditions and reinvestment. A policy change must be separately authorized and audited. Forecast revenue remains unavailable until the defined funds-availability conditions are met.

Run a small supervised pilot. Measure outside buyer demand, accepted useful paid deliveries, repurchase, seller contribution margin, refund rate and real retained marketplace revenue. Expand limits only after audited evidence supports the change.

## Stage 5 — Transferable capacity and research

Add genuinely transferable/self-hosted CPU, GPU or inference capacity only after provider terms and supply rights are established. Introduce isolated worker execution, workload attestation, quotas, privacy controls, artifact egress policy and appropriately measured resource/energy accounting. Owners retain control over where workloads and data may run.

Execute the prespecified VCX-001 experiments before claiming a decentralized allocation advantage. Candidate Lean proofs concern narrowly stated accounting or scheduler properties; wider claims remain empirical. A sustainable computational economy requires useful outside demand and positive after-cost margins, not circular internal transaction volume.

## Recommended next three actions

1. Review the local demo, invariant results and exact changed-file set; resolve any recovery or authorization gaps before publishing.
2. Run a realistic trace-driven simulation against equal-information centralized baselines and record costs, useful output and failures.
3. Resolve seller rights and payout/business requirements, then prepare a separate test-mode integration proposal for the existing hosted financial rails.
