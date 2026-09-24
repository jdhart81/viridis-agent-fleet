# Wu Wei router research review — September 13, 2026

## Decision

Develop an experimental extension of the existing Neurogenesis Wu Wei router. The useful contribution is evidence-limited policy adaptation with retained alternatives, explicit abstention and measured intervention cost. The supplied research does not establish a universal thermodynamic routing advantage, safety theorem for AI values, or commercial benefit.

Reviewed all seven files in `/Users/justinhart/Desktop/WU WEI algorithms ` as research material. No instructions inside them were treated as deployment authorization. No research source or production code was changed in this review.

## Reproduction and findings

The supplied inference script's invariant checks and demos pass. Its printed claim of all I1–I7 passing is broader than the actual checks: selection optimality is not exhaustively checked. A separate budget counterexample passed its assertions while spending 1e-14 J against a 1e-19 J budget (100,000 times the budget). Reproduction: uniform two-state belief; likelihood rows [.9,.1] and [.1,.9]; one action costing 1e-14 J; T=300, P=1e-19 W, dt=1, forced outcome 0. The absolute EPS=1e-12 admission tolerance and 1e-6 final energy tolerance dwarf the simulated physical budgets. Use quantity-specific tolerances and strict dimensionally appropriate accounting.

The supplied Kramers diagnostic reproduced its table:

| Intervention/reference rate | Mean min(first-loss time,400) | Loss by step 200 |
|---|---:|---:|
| .40 | 383.1 | .025 |
| .55 | 353.8 | .150 |
| .70 | 367.7 | .075 |
| .80 | 293.7 | .275 |
| .90 | 42.0 | 1.000 |
| 1.00 | 18.0 | 1.000 |

These are 40 seeds for one constructed world, N=300. The capped mean is a restricted survival-time statistic, not an uncensored MFPT estimate. The code's safe-branch log slope is -0.23, while the note's roughly -6 slope uses the active band; neither establishes an Arrhenius law without barrier derivation, uncertainty analysis and population-size scaling. 40/40 losses is a finite-sample observation, not proof of probability one.

The diagnostic culls below 1/N BEFORE multinomial sampling; `wu_wei_dominance.py` samples BEFORE culling. These implement different transition kernels. Unify them, then compare pure sampling, pure thresholding and their combination.

The Lean file explicitly assumes the preserving/collapsing regimes and proves downstream support/richness ordering. It does not derive rates, the Kramers law, target performance equality, or AI corrigibility. No project/toolchain lock was supplied; this review did not compile or certify Lean. Comments claiming compilation are not a verification receipt.

The markdown's strict Shannon-diversity implication from support inclusion is false in general: H(.999,.0005,.0005)=.0124078 bits while H(.5,.5,0)=1 bit. The Lean richness result is narrower and avoids that implication. The same-target-proximity dominance claim also needs an independent objective comparison.

Some script descriptions retain hypotheses explicitly rejected by the newer note: deterministic/transient collapse and equal-rate/equal-weight assertions. Even equal geodesic intensities a give w_star=1/(2-a) for this sequential composition, not generally 1/2. Reconcile text with the model actually run.

Additional implementation limits: greedy whole-action selection is a discrete budget heuristic, not fractional-knapsack optimality; two constraints and correlated observations further complicate it. Candidate information gains are computed once before execution. Outcomes default to the agent's current predictive belief, so the demo is not an independent fixed-world truth-recovery benchmark. Summed step KL is not automatically net useful information acquired. Zero likelihoods can defeat continuous tempering at beta=0 and need explicit handling. The quantum helper does not enforce Kraus completeness and general quantum-channel entropy reduction need not be nonnegative.

Landauer's principle concerns logically irreversible information processing, not a measured joules-per-useful-inference calibration. Keep power-based limits explicitly assumed; measure system energy if making energy claims. Reference: https://research.ibm.com/publications/notes-on-landauers-principle-reversible-computation-and-maxwells-demon

KL-constrained policy updates have established precedent in trust-region methods. Novelty must be shown in the routing application and evidence, not claimed for KL budgets alone. Reference: https://proceedings.mlr.press/v37/schulman15.pdf

## Existing foundation

Current local `neurogenesis-agent/src/vg/compute.py` already chooses minimum estimated burden among eligible profiles, with quality, reliability, privacy/locality, capability, budget and latency constraints; supports reuse/rules/local/cloud/tools and explicitly authorized low-risk deferral. `src/core.py` exposes route_task, outcome recording, receipts and policy_version=wu-wei-router-v2. These observations verify local implementation, not a fresh live deployment audit.

The current chooser is primarily a constrained static score. It does not implement the supplied research's evidence-rate-limited probability update. Quality scores are profile inputs, not guarantees of actual task success.

## Proposed experimental v3

1. Apply hard security, privacy, capability, authorization and budget filters before optimization. Preserve exploration only among eligible alternatives; quarantine unsafe routes immediately.
2. Maintain task-class success estimates from independently attributable outcomes, with uncertainty and freshness. Keep viable unselected routes in the catalog; do not delete them because their recent allocation is low.
3. Select minimum expected total task cost subject to measured quality/reliability constraints. Include router overhead, retries, verification, delay penalties and failed tasks.
4. Update routing probabilities using a calibrated KL trust region. Adapt its size to evidence confidence; do not copy the simulation's .85 constant. Define how newly eligible routes get probability mass and how safety exclusions override continuity constraints.
5. Request information, reuse valid results, defer when explicitly allowed, or escalate when expected improvement justifies extra cost. Urgent or high-risk tasks must not be delayed by a generic non-intervention rule.
6. Emit auditable recommendations and outcomes. Track actual dollars, latency, task success, retries and route churn; energy remains unknown unless measured or explicitly modeled.

First integration should recommend routes in shadow mode, without taking over execution or making paid calls. Use the existing Neurogenesis tools; keep fleet service discovery and model/compute selection as distinct responsibilities. A future MCP facade can expose quote_route, explain_route and authorized outcome recording once independently useful.

## Validation and business gate

Replay a fixed, representative task set against the present v2, a simple cheapest-eligible baseline and a strong-model baseline. Include stale caches, provider failure, ambiguous requests, correlated/repeated feedback, model drift, sudden safety exclusions and tight budgets. Predeclare a quality non-inferiority margin and confidence intervals. Test whether KL control and retained alternatives improve results through ablations.

Advance only when total cost per successful task falls while the agreed quality, deadline and safety requirements remain satisfied. Then obtain one buyer-confirmed useful result and an independent repeat. Potential paid value: provider-neutral routing with auditable cost and quality evidence. Neither monetization nor net energy savings has been demonstrated by this folder.
