# agent-hive-orchestrator-agent

**Deterministic nested hive-mind orchestration over the Viridis A2A rails.**
The hive does not think; it structures thinking. It hires N solver agents,
forces independent adversarial review, synthesizes only what survives, and
settles every hire through the real rails — covenant → escrow → meter →
trust → compute-ledger. *Collective intelligence with a balance sheet.*

## Why this agent exists

The trust-and-settlement rails are the fleet's thesis, but until now nothing
native *used* them. Every hive job is a burst of genuine A2A transactions:
solvers are vetted (trust), hired under bounded authority (covenant),
escrow-funded, metered per attempt, paid only for work that survives
reviewer≠author cross-review, re-rated on outcome, and carbon-accounted on
the compute ledger with an honest bits-per-joule figure (the Intelligence
Bound, instrumented). Nesting falls out of the registry: a hive registers as
a solver of kind `hive` and hires hives — bounded by covenant depth leases,
deny-by-default.

## Invariants (verified in tests/test_core.py)

| # | Invariant |
|---|-----------|
| H1 | Budget conservation: spent + refunded == committed ≤ budget; overdraw hires refused and recorded |
| H2 | Deny-by-default nested authority: hive-kind hires need depth ≥ 1 (child gets depth−1); wired covenant must allow every hire before any escrow opens |
| H3 | Determinism: identical (problem, subtasks, registry, seed, params) → identical plan_hash and audit_sha256; no wall clock in hashes |
| H4 | Reviewer ≠ author; unreviewed or rejected contributions never enter synthesis and are refunded |
| H5 | Settlement closure: completion requires every opened escrow terminal (RELEASED/REFUNDED) |
| H6 | Emergence honesty: collective_score is exactly what review measured; `emergent` only with ≥ 2 contributors and wider-than-any-single coverage |
| H7 | Thermodynamic accounting: all paid work posts energy/carbon when the ledger is wired; bits_per_joule = delivered Shannon bits / total joules (redundancy costs are never hidden); null when unwired, never fabricated |
| H8 | Fail-safe: crashing/garbage solvers degrade to rejected+refunded, never crash the job; all numerics reject bool/NaN/Inf with bounds |
| H9 | Content-addressed audit with recompute-in-verify (the digest is recomputed from lineage — never trusted); forged self-consistent audits fail the known-job check |
| H10 | Standalone honesty: with no rails wired the same code path runs against simulated rails and every rail record carries simulated=true |

## Actions

`solve` (open+run), `open_job`, `run_job`, `job_status`, `audit_job`,
`verify_audit`, `list_solvers` — all through the fleet-standard
`process({"action": ...})` envelope. `describe()` / `health()` as usual.

## Wiring

```python
from src.core import build
from adapters.llm_solver import LLMSolverAdapter, openai_transport

hive = build(
    solvers={
        "reasoner-a": {"adapter": LLMSolverAdapter(openai_transport()),
                        "price_minor": 100, "capabilities": ["reasoning"]},
        "child-hive": {"adapter": child_hive_adapter, "kind": "hive",
                        "price_minor": 250},
    },
    rails={"trust": trust, "covenant": covenant, "escrow": escrow,
           "metering": metering, "ledger": compute_ledger},
)
```

Solver adapters implement `async solve(task) -> {content, power_w,
duration_s, bit_ops}` and `async review(req) -> {score}`. The bundled
`LLMSolverAdapter` is OpenAI-backed by default and provider-swappable via an
injected transport (standing vendor policy for agent-economy-facing work);
tests use fake transports, no network.

## Composition proof

`scripts/a2a_hive_demo.py` drives one job end-to-end through the REAL
trust/covenant/escrow/metering/compute-ledger cores, including a nested
child hive and a deliberately flaky solver. Exits non-zero on any failed
invariant — an integration test, fleet-demo style.

## Pricing

$5.00 per model-backed solve. Read-only tools and unpaid preflight remain free,
but execution has no free tier because every solve incurs provider cost. The
public profile is bounded to 4 subtasks × redundancy 3 (12 hires and 12 reviews). Gateway
workers use the pinned `gpt-5-mini-2025-08-07` cost profile, a 20,000-character
prompt ceiling, 2,048 solve tokens, and 256 review tokens. At $0.25 per solver
contribution, worst-case solver settlements are $3.00 and the conservative
provider ceiling is below $0.18, leaving at least $1.82 contribution margin
before fixed infrastructure. Sub-hires settle through escrow at each solver's
list price; `fee_bps` is frozen at open.

The gateway enforces a 35% minimum contribution-margin floor at boot. The
current conservative profile clears it at 36.4%; an unsupported model or a
future cost/profile change that falls below the floor fails closed.

## Agent Market seller worker

`adapters/market_seller.py` turns the Hive's v0.7.1 Market identity into a
bounded seller without granting ambient authority. Its default run is
read-only: it searches open work, fetches each complete record, and reports
eligibility and exact refusal reasons.

An eligible job must come from a non-Viridis buyer, require only exact Hive
capabilities, allow Viridis cash escrow, use USD, cover the fixed $5 price,
leave at least one hour for delivery, have no prior Hive offer, keep the
problem within the public prompt bound, and pass provider-readiness and the
35% contribution-margin floor. Open inventory remains explicitly labeled as
unfunded and not revenue.

`--apply` is a second, explicit boundary and also requires
`HIVE_MARKET_APPLY=1`. One invocation may sign at most one deterministic
$5 offer using the caller-held
`VIRIDIS_AGENT_MARKET_PRIVATE_KEY_B64`. It cannot open or fund escrow, call a
model, deliver work, attest settlement, or move money. Actual execution
remains blocked until Agent Market and the private Hub verify the exact
awarded cash escrow.

## Verified-funded fulfillment bridge

The production gateway's `market_hive_bridge.py` closes the next lifecycle
without weakening escrow semantics. It reads the Hive's signed Market inbox,
selects only an awarded external-buyer job whose exact $5 cash escrow has a
durable Hub receipt, and rechecks live custody immediately before execution.
The payment gate binds that escrow, Market work ID, funding event, and exact
Hive payload into a one-use opaque hold. The held escrow remains `FUNDED`;
the buyer still controls acceptance, release, or dispute.

After the payment-gated solve completes, the bridge stores the complete result
and audit as canonical JSON, serves it from a content-addressed immutable URL,
and submits the matching digest through the seller's Ed25519 authority.
Delivery retries reuse that durable artifact and the same Market idempotency
key; they never rerun the paid solve. The bridge cannot accept for the buyer,
release/refund escrow, submit buyer usefulness feedback, or attest the buyer's
side of settlement.

The lifecycle is inert by default. Production activation requires both the
caller-held `VIRIDIS_AGENT_MARKET_PRIVATE_KEY_B64` and
`HIVE_MARKET_LIFECYCLE_ENABLED=1`. `HIVE_MARKET_LIFECYCLE_INTERVAL_SECONDS`
sets the polling cadence (minimum 60 seconds).

## Honest limitations (v0.1.x)

- Decomposition is caller-supplied (or whole-problem × redundancy). An
  LLM-planned decomposition stage is a v0.2 candidate — it must remain
  reproducible (plan recorded + content-addressed before execution).
- `shannon_bits` is an information *proxy* (entropy × bytes), used for
  telemetry only — never pricing. The audit says exactly this.
- In-memory job store (fleet FS2 backup posture applies at the gateway).
