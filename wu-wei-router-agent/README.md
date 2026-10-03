# Wu Wei Workload Router

The existing `plan_workload` service compares declared costs and representative evaluation counts for up to 20 profiles and 50 workload groups. Its current fleet price is $1 USDC per plan. It returns a complete analysis even when modeled savings do not cover the service fee. `describe_agent` is free.

MCP: https://mcp.viridisconservation.com/wu-wei-router/mcp

Paid HTTP: https://mcp.viridisconservation.com/x402/wu-wei-router/plan_workload

Inspect `service-schema.json` and `example.json`; an unsigned POST returns an unpaid quote. This service recommends only. Eligibility uses a Wilson lower bound on caller-supplied success/trial counts. `execution_authorized` and `energy_savings_measured` remain false.

## Optional native routing/state extension

`WU_WEI_V2_ENABLED` defaults off. With the flag absent or `0`, the original tool schemas, planner output, description, and health remain unchanged. With the existing fleet mount enabled, set the following in the environment of the next host process to expose the extension:

```sh
export WU_WEI_V2_ENABLED=1
```

This command changes the invoking shell environment. A running gateway needs a separately authorized restart. Production activation requires Justin's checkpoint approval. This PR does not activate a route, publish a deployment, issue an ORC, or enable a subscription.

The extension retains `plan_workload` and exposes exactly these seven routing/state tools:

| Tool | Input and purpose |
| --- | --- |
| `register_compute_profile` | `profile`: the existing profile fields, plus optional declared `power_w`; at most 20 profiles |
| `route_task` | `task`: one existing workload-group schema, plus optional inline `profiles`; otherwise uses registered profiles |
| `record_route_outcome` | `decision_id`, integer `successes`/`trials`, optional integer `duration_ms`/`cost_microusd`; caller-reported only |
| `compute_efficiency_report` | Free routing audit with separate event and caller-reported outcome records |
| `describe_agent` | Free scope, policy, price and tool discovery |
| `export_state` | Free portable routing state |
| `import_state` | Validated portable state import; cannot erase or rewrite existing routing audit history |

All v2 mutations, including compatibility `plan_workload`, require host admission. Standalone v2 calls return a `payment_required` envelope. OSS contains no payment transport or billing implementation; self-host integrations may enter the core's `admitted_request()` context only after their own admission checks. That context is not an MCP tool or a payload field. The hosted fleet's billing and persistence wiring lives in its private service repository.

## Decision record and modeled energy

The router retains the original Wilson eligibility predicate and selects by declared cost, then latency, then profile ID. Profile order does not change the recommendation. A baseline-optimal result is full success with `BASELINE_OPTIMAL_NO_CHANGE` and reason `baseline optimal / no change`. The analysis fee is outside the recommendation and its digest.

`decision_sha256` hashes an integer-only canonical record: normalized profiles and task, eligibility outcomes, chosen/baseline profiles, costs, and modeled energy. Wilson bounds are floored to integer basis points for the record. Sorted-key compact JSON uses the ORC canonical encoding; no timestamps or sequence IDs enter that record. `decision_id` and `at` are separate audit fields, so repeated analyses share a decision digest while retaining distinct event identities.

Declared watts are floored to integer microwatts. Modeled duration is `p95_latency_ms × count`; energy in microjoules is `power_uw × p95_latency_ms × count // 1000`. This is modeled energy per routed decision, not energy measurement. Both chosen and baseline power must be present to report a delta. Missing power returns `insufficient data for savings`. Modeled savings are floored at zero, and higher chosen energy is explicitly flagged. A baseline-optimal decision with declared power reports zero modeled savings.

Routing history is capped at 1,000 events and fails closed at capacity. Export/import validates records and their digests. Caller-reported outcomes, local fixture runs and fleet-internal routing do not establish external adoption, revenue, correctness, or usefulness. The policy is `wu-wei-router-v2`; it has no Neurogenesis dependency or agent create/delete/evaluate lifecycle.
