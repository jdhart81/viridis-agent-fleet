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

3 free solves per caller per UTC day, then $5.00 per solve. The public profile
is bounded to 4 subtasks × redundancy 3 (12 hires and 12 reviews). Gateway
workers use the pinned `gpt-5-mini-2025-08-07` cost profile, a 20,000-character
prompt ceiling, 2,048 solve tokens, and 256 review tokens. At $0.25 per solver
contribution, worst-case solver settlements are $3.00 and the conservative
provider ceiling is below $0.18, leaving at least $1.82 contribution margin
before fixed infrastructure. Sub-hires settle through escrow at each solver's
list price; `fee_bps` is frozen at open.

The three free calls are acquisition spend, not evidence of revenue. The
existing anonymous-rotation pool limit still applies.

## Honest limitations (v0.1.0)

- Decomposition is caller-supplied (or whole-problem × redundancy). An
  LLM-planned decomposition stage is a v0.2 candidate — it must remain
  reproducible (plan recorded + content-addressed before execution).
- `shannon_bits` is an information *proxy* (entropy × bytes), used for
  telemetry only — never pricing. The audit says exactly this.
- In-memory job store (fleet FS2 backup posture applies at the gateway).
