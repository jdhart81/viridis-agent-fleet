# VCX-001 — Adaptive Computational Resource Allocation

**Status:** Research conjecture and benchmark specification. No theorem, measured advantage, market equilibrium or Intelligence Bound consequence is claimed by the local marketplace demonstration.

## Falsifiable hypothesis

For prespecified workloads, costs, capacity, market conditions and trust constraints, a decentralized service-allocation policy can increase **verified useful output** per unit of economic input and per unit of energy input relative to a defined centralized scheduling baseline.

**H1, the only mechanism claimed.** When some eligible capacity is idle and outside the pool a centralized scheduler can assign, a posted-price exchange that can reach that capacity raises verified useful output per unit of economic input, net of coordination and verification cost. With identical feasible sets and information, no advantage is claimed (prediction 4).

**Operational definitions for the first experiment.** `u_j = 1` for each job whose deterministic acceptance predicate passes before its deadline, so `U` is the accepted-job count. The centralized baseline is earliest-deadline-first assignment to the cheapest eligible provider inside its own pool, under the same admission and security rules. The offline oracle is the integer-program optimum over the full job stream.

**Refutation rule, fixed before any run.** Use at least 30 seeded job streams per cell of the experiment matrix, paired across policies. H1 is refuted in a cell when the 95% confidence interval for the paired mean difference in `U/C` (VCX minus baseline) lies entirely below +5% of the baseline mean. Every cell is reported.

**v0.1 cannot produce this evidence.** All of its providers are the same function running in the exchange process, so there is no heterogeneous or idle capacity to reach.

The claim is conditional. Compare both economic and energy efficiency separately; improving one can worsen the other. A marketplace should not be credited for refusing difficult jobs unless the same admission rules apply to its baseline.

## Model and assumptions

Let jobs be `j ∈ J`, providers `i ∈ I`, and allocation `x_ij ∈ {0,1}`. Job j has deadline `d_j`, buyer budget `b_j`, resource requirement vector `r_j`, trust requirement `t_j`, and acceptance predicate `V_j`. Provider i offers capacity vector `K_i`, price `p_ij`, execution duration `τ_ij`, failure probability `q_ij`, verification cost `v_ij`, and energy `e_ij`. Inputs and acceptance predicates must be versioned before experiments.

Define `u_j ≥ 0` as an externally specified useful-output weight, not the number of tokens produced. Let `a_ij` indicate accepted delivery before deadline. Then:

\[
U = \sum_{i,j} x_{ij} a_{ij} u_j,
\qquad
C = \sum_{i,j} x_{ij}(c_{ij}+v_{ij}+h_{ij}),
\qquad
E = \sum_{i,j} x_{ij}(e_{ij}+e^{verify}_{ij}+e^{coord}_{ij}).
\]

Here `c` is resource cost and `h` coordination/retry cost. Prices and fees are transfers within a closed system; for system-efficiency analysis, avoid double-counting them as resource consumption. Analyze buyer expenditure and provider margin separately.

Report `U/C` and `U/E` when denominators are positive, total U, completion/deadline rates and cost/energy distributions. A combined objective such as `U − λC − μE − νRisk` requires declared weights and a sensitivity analysis; it must not hide a tradeoff.

Constraints include one accepted assignment per job, concurrent capacity, buyer authorized budget/reserve/exposure, service compatibility, security eligibility, provider supply rights and execution before deadline. Real jobs may need multidimensional resources and correlated failure models; the local v0.1 implementation is narrower.

## Market assumptions

A simulation must state whether providers are price takers, whether prices are fixed or strategic, how offers arrive, what information is visible, and how identities resist Sybil behavior. Start with a finite posted-price allocation process; do not assume a competitive equilibrium exists or that broker matching computes one.

A later equilibrium model would need utility/quasilinearity assumptions, outside options, capacity scarcity, entry costs and information conditions. Discrete tasks, fixed costs and nonconvex constraints can prevent the existence or uniqueness of convenient equilibrium forms. Any equilibrium theorem must prove existence under explicit assumptions before discussing convergence.

## Baselines and experiment matrix

| Baseline/policy | Purpose |
|---|---|
| Centralized scheduler with identical information and constraints | Tests allocation structure without granting VCX an information advantage. |
| Fixed provider with deterministic fallback | Measures a practical simple deployment. |
| Cheapest eligible provider | Separates multicriteria ranking from price-only selection. |
| Centralized offline oracle with full future workload knowledge | Upper benchmark; not a fair online competitor. |
| VCX posted-price deterministic broker | Candidate policy under study. |

Use common random numbers, identical job streams and provider models, equal admission/security rules, fixed experiment seeds and an untouched evaluation set. Publish configuration, raw outcomes, accounting reconciliation, modeled/measured energy provenance and uncertainty intervals. Report all prespecified workloads, including negative results.

Vary provider heterogeneity, demand/capacity ratio, price spread, failure correlation, verification expense, network/coordination overhead, deadline tightness and identity/trust restrictions. Separate warm-up from evaluation. Run ablations removing reliability, latency and energy score components. Measure whether gains survive realistic estimation error.

## Testable predictions and counterexamples

1. With heterogeneous capacity and accurate quality/latency information, multicriteria matching may improve accepted useful output at equal budget relative to cheapest-only matching. Test across increasing information error.
2. With correlated provider failures, apparent diversification gains should shrink. Test the same marginal failure rates under independent and correlated failures.
3. When coordination and verification dominate execution cost, a centralized fixed-provider policy may outperform VCX. This is an expected counterexample, not a failed accounting invariant.
4. If the centralized baseline has the same feasible choices and uses an optimal policy with the same objective and information, VCX cannot claim an advantage merely from decentralization. Gains require an identified mechanism, such as better access to otherwise idle eligible capacity, and its associated costs.
5. Malicious low-price listings or inflated reliability can reduce output and margins without robust evidence requirements. Evaluate Sybils, collusion, false delivery and strategic timeout behavior.

## Formal verification candidates

| Claim | Appropriate validation |
|---|---|
| Integer ledger conservation for each transition and their composition | Lean 4 model plus implementation tests/refinement argument. |
| No negative spendable balance under atomic budget rules | Formal state-machine invariant with stated initial conditions. |
| Idempotent settlement keys cannot produce two financial outcomes | Formal transition model; concurrency/storage semantics also need implementation validation. |
| Ranking respects hard constraints and deterministic tie rules | Formal finite-list properties and executable tests. |
| Scheduler improves utility/cost or energy in realistic markets | Empirical benchmark; any theorem requires a separately specified model. |
| Output is useful, secure, scientifically correct or environmentally beneficial | Domain evidence and independent assessment; not implied by a hash, signature or generic Lean proof. |

A formal model is not proof that the Python/SQLite implementation satisfies it unless the refinement or extraction relationship is established. v0.1 supplies no Lean proof artifact by default.

## Intelligence Bound connection

The Viridis research program proposes relationships among information production, power, temperature and other modeled quantities. VCX currently measures neither general intelligence production nor all quantities needed to instantiate such a relationship. Job utility, accepted output count and token count must not be substituted for an unestablished information/intelligence variable.

A defensible connection requires a precise definition and units for useful information output, a derivation under declared physical/computational assumptions, calibrated energy measurements and falsifiable predictions beyond ordinary cost optimization. Until that work exists, VCX is a resource-allocation experiment that may generate relevant data; it is not evidence for, or a realization of, an upper Intelligence Bound.
