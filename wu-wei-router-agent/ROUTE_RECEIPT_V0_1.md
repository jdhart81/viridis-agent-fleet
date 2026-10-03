# Wu Wei counterfactual route receipt v0.1

The hosted gateway can bundle an Outcome Receipt with an admitted `route_task` analysis when `WU_WEI_RECEIPTS_ENABLED=1`, with the fleet mount and Wilson v2 engine already enabled. The receipts flag defaults off. This document specifies the profile; deployment and payment activation require Justin's separate checkpoints.

The profile is `viridis.wu-wei/route`, using ORC v0.1. The issuer is Viridis. `subject.decision_sha256` binds the deterministic normalized route decision from the native Wilson engine. The seal's output contains `decision`, `chosen_profile`, `baseline_profile`, `task_count`, `selection_objective`, `thermo`, `eligibility: "wilson-lower-bound"`, and `execution_authorized: false`.

Energy is modeled energy per routed decision. The declared `power_w` is normalized to integer microwatts; modeled duration is `p95_latency_ms × task_count` milliseconds. Integer microjoules equal `power_uw × modeled_duration_ms // 1000`. These are the same declared power and modeled duration inputs used for compute-ledger work entries; ledger calculations may use internal floats, while sealed values contain no floats.

`thermo.method` is `modeled-wallclock-v1`, and `energy_savings_measured` remains false. Modeled savings equal `max(0, baseline_energy_uj − chosen_energy_uj)`. A higher-energy recommendation retains the analysis, reports zero modeled savings, and sets `chosen_energy_exceeds_baseline: true`. A baseline-optimal recommendation seals with zero modeled savings when power data are available. Missing declared power omits energy deltas and reports `insufficient data for savings`. No power is inferred.

The recommendation is independent of the fee and recommends only; execution is never authorized. Eligibility uses the Wilson lower bound. Audit-event identifiers and timestamps are separate from the deterministic decision digest and sealed output. Repeating the same decision at different times preserves that digest and body; receipt issuance timestamps and commitment salts remain separate issuance metadata.

Verification remains free. INTACT establishes that the digest and commitment recompute. **ISSUED means issuer binding only; it is not evidence of payment, correctness, validation, or buyer-confirmed usefulness.** The gateway's `/verify` view displays the modeled-energy fields with this boundary when receipts are enabled.

All Viridis-issued receipts, including self-seal smoke tests and fleet-internal routing, are class `viridis`. These counts do not establish external adoption or revenue. Opt-out and read-only calls remain unsealed. Receipt persistence failures return an explicit unsealed status; receipt state is never deleted for rollback. Existing generic auto-sealing does not add a second seal to a specialized route receipt.


## Selection objective (PR 2b)

With the Wilson v2 flag enabled, the router selects the lowest modeled energy among quality-eligible routes that cost no more than your baseline. Ties use declared cost, p95 latency, then profile ID. All eligible routes within that cost cap must declare power; otherwise selection falls back to the cheapest capped eligible route and labels `selection_objective: cost_fallback_missing_power`. The baseline must remain eligible; the input gate rejects ineligible baselines, and the cost-capped set must contain the baseline. The energy objective is labeled `least_energy_within_baseline_cost`.

`selection_objective` is part of the deterministic decision record, digest and sealed body. Eligibility and fee neutrality are unchanged. Historical records without this field remain importable under their original cost-selection rule, preserving their digests. Missing power for the chosen or baseline profile still omits the savings delta.
