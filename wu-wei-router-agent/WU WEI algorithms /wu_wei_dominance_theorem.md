# The Wu Wei Dominance Theorem (stochastic form)

**Rate-matched intervention strictly dominates aggressive intervention — in
ecosystem restoration and in AI value-formation — because over-intervention
shallows a metastable well, and demographic/sampling noise then drives the
system across an *absorbing* boundary at a rate that rises *exponentially*. The
penalty for exceeding the system's own information rate is a sharp, irreversible
cliff, not a soft trade-off.**

Viridis LLC — working note v2. Substrate: `intelligence_bound_inference.py`.
Simulations: `wu_wei_dominance.py`, `analysis_exact_threshold.py`,
`analysis_transient.py`, `analysis_kramers.py`. Every quantitative claim below
is reproduced by those scripts.

---

## 1. The object: ecosystem as inferrer

A community of `n` types is the relative-abundance vector `p ∈ Δⁿ⁻¹`; its
amplitude image `ψᵢ = √pᵢ` lives on the positive orthant of the unit sphere in
ℋ = ℝⁿ — the probability Hilbert space. Exact mapping from the inference engine:

| inference | ecology |
|---|---|
| belief `p` | relative abundance |
| likelihood / fitness | intervention selection vector |
| update rate (bits/step) | intervention rate `r_int` |
| `KL(p′‖p)` | community displacement |
| support `supp(p)` collapses | **extinction** (absorbing boundary `∂Δ`) |
| Shannon entropy `H(p)` | biodiversity = recovery optionality |

`∂Δ` is **absorbing** under multiplicative (replicator/Bayesian) dynamics — a
coordinate at 0 stays at 0. Extinction is irreversible by the geometry of the
update, exactly as Bayes cannot resurrect a probability-0 hypothesis. **Wu wei
and Cromwell's rule are the same theorem.**

## 2. Two forces and the exact fixed point

Each step composes two KL-budgeted e-geodesic (replicator) tilts:

- **Endogenous**: pull toward the true environmental optimum `p_env` (rich, full
  support) at the ecosystem's intrinsic rate
  `r_eco = min(ρB, P_eco/(k_B T ln2))` — *fixed by nature*.
- **Intervention**: pull toward an impoverished target `p_star` (non-target
  types suppressed to a floor `f`) at the *controllable* rate `r_int`.

**Exact fixed point** (solved in log-space, `analysis_exact_threshold.py`):

> `p*ᵢ ∝ p_env,ᵢ^{w_env} · p_star,ᵢ^{w_star}`,  a **normalized weighted
> geometric mean**, with `w_env + w_star = 1` and
> `w_star = aᵢ/(aᵢ + aₑ − aᵢaₑ)`, where `aₑ, aᵢ ∈ [0,1]` are the e-geodesic
> intensities set by `KL = r_eco`, `KL = r_int`.

The lstsq fit confirms the geometric-mean form (weights sum to 1.000). **One
correction to intuition the math forced:** equal *rates* do **not** give equal
*weights*. For a fixed KL, `KL ≈ ½ a² · Var_p[log(target/p)]`, so a more extreme
attractor (the intervention, with huge `log(f/p)` variance) buys a *smaller*
geodesic intensity `a` per unit rate. At `r_int = r_eco` the recovered weights
are ≈ 0.90 (env) / 0.10 (star), not 0.5/0.5. The manager's pull is "cheaper" in
KL precisely because its target is extreme — a subtle and important asymmetry.

## 3. The mechanism is stochastic, not deterministic (three falsified hypotheses)

Digging in falsified the two obvious deterministic stories before the right one
appeared — which is exactly why the final claim is defensible:

1. **Equilibrium impoverishment? No.** The deterministic fixed point keeps the
   rarest non-target type at ≈ 0.024 (≈ 7 individuals at `N=300`), *safe*, until
   `r_int ≈ 1.25·r_eco` (where the intervention tilt saturates at `a=1`).
2. **Transient overshoot? No.** The deterministic trajectory from the rich state
   is monotone — the path minimum equals the equilibrium; it never dips toward
   `∂Δ`.
3. **Noise-activated barrier escape (Kramers)? Yes.** Each non-target type sits
   in a metastable well (endogenous pull up vs intervention pull down). Wright-
   Fisher/multinomial sampling noise drives escape over the absorbing boundary.
   As `r_int → r_eco` the well shallows and the **mean first-passage time (MFPT)
   to extinction falls exponentially.**

MFPT diagnostic (`analysis_kramers.py`, `N=300`, `r_eco=0.15`, 40 seeds,
window 400, management horizon ≈ 200):

| r_int / r_eco | MFPT (censored@400) | log₁₀ MFPT | P(loss ≤ 200) |
|---:|---:|---:|---:|
| 0.40 | 383 | 2.58 | 0.03 |
| 0.55 | 354 | 2.55 | 0.15 |
| 0.70 | 368 | 2.57 | 0.08 |
| 0.80 | 294 | 2.47 | 0.28 |
| **0.90** | **42** | **1.62** | **1.00** |
| 1.00 | 18 | 1.26 | 1.00 |

Across the active band the slope is `Δlog₁₀ MFPT/Δrate ≈ (1.26−2.47)/0.2 ≈ −6`
per unit `r_eco` — i.e. **~10⁶× drop in survival time per unit rate**: an
Arrhenius cliff. (On the safe branch MFPT is censored by the window, hiding the
true exponential — the visible drop understates it.)

## 4. Theorem

> **Theorem (Wu Wei Dominance, stochastic).**
> Under selection-balanced Wright-Fisher dynamics with endogenous rate `r_eco`
> and intervention rate `r_int` toward an impoverished `p_star`, the non-target
> viable types occupy a metastable well whose barrier `ΔU` shrinks as
> `r_int ↑ r_eco`. The mean first-passage time to the absorbing boundary obeys
> an Arrhenius law `MFPT ≍ exp(ΔU(r_eco − r_int)/σ²)`, `σ² ∝ 1/N`. Hence there is
> a critical rate `r* = Θ(r_eco)` (defined by `MFPT(r*) = horizon`) with:
>
> 1. **Sub-critical safety.** `r_int < r*` ⇒ extinction is exponentially
>    improbable within the horizon; `supp(p) = full`, diversity maximal.
> 2. **Super-critical collapse.** `r_int > r*` ⇒ extinction near-certain within
>    the horizon; `supp(p) ⊊ full` *permanently* (absorbing); transition width
>    `O(σ²)` (sharp).
> 3. **Dominance.** For any `r_int > r*`, the rate-matched policy `min(r_int,r*)`
>    attains the same target proximity with strictly greater long-run diversity.
>    Aggressive intervention is strictly dominated.

Empirically `r* ≈ 0.85·r_eco` for the tested parameters: collapse begins
*below* the ecosystem's own rate.

**Proof sketch.** (1)–(2): metastability of the geometric-mean well (§2) plus
Freidlin–Wentzell / Kramers escape over `∂Δ`; the barrier is the drift integral
from `p*ᵢ` to `1/N`, monotone-decreasing in `r_int`, giving the Arrhenius MFPT
and an `O(σ²)`-width transition. (3): diversity is strictly Schur-concave, so the
strict support inclusion from (2) gives strictly lower `D`. ∎ (modulo the
Freidlin–Wentzell barrier estimate, stated for Lean in §8.)

## 5. Management implication: margin, not matching

Because the cliff is **exponential**, "match the rate" (`r_int = r_eco`) is *not*
safe — at `r_int = r_eco` you are already on the collapsing branch (P(loss)=1 in
the sims). Wu wei is **operate with margin below `r_eco`**: the cost of being
slightly too fast is exponential and irreversible, while the cost of being too
slow is merely linear delay. Asymmetric payoff ⇒ conservative margin is optimal.
This is the quantitative core of "do less."

## 6. Resilience metric (closed form) and its trap

Fisher-Rao distance from `p` to extinction of type `i` (face `{qᵢ=0}`) is exactly
`2·arcsin(√pᵢ)`; the single resilience scalar is `R(p)=2·arcsin(√(min_i pᵢ))`.
**Trap (sim-exposed):** `R` and diversity `D` anti-correlate near collapse — wu
wei is *rich but fragile* (many types near the edge), aggression is *robust but
poor*. A credit instrument pricing `R` alone would **incentivize collapse**.
EcoChain must price `D`/support (the irreversible-to-lose quantity); `R` is only
a secondary stability premium.

## 7. Connections

- **İ(τ).** `r_int ≤ r_eco` is exactly `İ_intervention(τ) ≤ İ_ecosystem(τ)`. The
  unifying thermodynamic bound *is* the non-intervention principle.
- **HDFM** estimates `p_env` and the corridor geometry → less impoverished
  `p_star` → higher `r*`. Better information literally raises the safe rate.
- **EcoChain** prices `D` and verifies interventions stayed sub-critical: a
  thermodynamically-grounded MRV layer.

## 8. AI-safety transfer (same theorem)

Relabel: types → value-hypotheses; `p_env` → the true (rich, under-determined)
value manifold; `p_star` → a nameable proxy reward; `r_int` → optimizer update
rate; extinction → **value lock-in** (probability 0 on a value that should stay
open); `r_eco` → the rate at which genuine value-information actually arrives.
The theorem says: an optimizer updating faster than `r*≈Θ(r_eco)` undergoes
*Kramers escape into lock-in* — exponentially sharp in the update rate, and
irreversible. **Corollary:** corrigibility ⊇ sub-critical updating, with a
*margin*. The constraint is power-meterable and proxy-independent: cap update
rate (≈ power and informative-data intake) safely below the value-information
rate, and lock-in becomes exponentially improbable within the horizon. The
conservation theorem and the safety theorem are one object; the open question is
the granularity `1/N` for value-hypotheses (what is "one individual" of a value?).

## 9. Lean 4 / Aristotle scaffold

```lean
import Mathlib.Analysis.SpecialFunctions.Log.Basic
import Mathlib.Probability.ProbabilityMassFunction.Basic

namespace WuWei

structure Community (n : ℕ) where
  p : Fin n → ℝ
  nonneg : ∀ i, 0 ≤ p i
  norm   : (∑ i, p i) = 1

def support {n} (c : Community n) : Finset (Fin n) :=
  Finset.univ.filter (fun i => 0 < c.p i)

noncomputable def diversity {n} (c : Community n) : ℝ :=
  -∑ i, (if 0 < c.p i then c.p i * Real.log (c.p i) else 0)

/-- Exact deterministic fixed point: normalized weighted geometric mean. -/
noncomputable def fixedPoint {n} (p_env p_star : Fin n → ℝ) (wEnv wStar : ℝ)
  (_ : wEnv + wStar = 1) : Community n := sorry

/-- LEMMA A (absorbing): a type at zero stays at zero under one step.
    Pure algebra on the multiplicative update — dischargeable now. -/
theorem extinction_absorbing {n} (step : Community n → Community n)
    (hmul : ∀ c i, c.p i = 0 → (step c).p i = 0)
    (c) (i) (h : c.p i = 0) : (step c).p i = 0 := hmul c i h

/-- LEMMA B (metastable barrier): the escape barrier ΔU for a non-target type
    is monotone decreasing in r_int and vanishes as r_int → r_eco. -/
theorem barrier_monotone {n} (p_env p_star) (r_eco : ℝ) :
    ∀ r₁ r₂, r₁ ≤ r₂ → barrier p_env p_star r_eco r₂ ≤ barrier p_env p_star r_eco r₁
  := by sorry

/-- LEMMA C (Arrhenius MFPT / Freidlin–Wentzell): mean first-passage time to the
    absorbing boundary ≍ exp(ΔU / σ²). -/
theorem mfpt_arrhenius {n} (p_env p_star) (r_eco σ² r_int : ℝ) :
    ∃ C > 0, MFPT p_env p_star r_eco σ² r_int
           = C * Real.exp (barrier p_env p_star r_eco r_int / σ²) := by sorry

/-- THEOREM (dominance): above the critical rate, rate-matched intervention
    yields strictly greater long-run diversity. -/
theorem wu_wei_dominance {n} (p_env p_star) (r_eco σ² horizon : ℝ) (c₀)
    (hfull : support c₀ = Finset.univ) :
    ∀ r_int, criticalRate p_env p_star r_eco σ² horizon < r_int →
      ∃ r', r' ≤ r_eco ∧
        diversity (evolveExpected p_env p_star r_eco r'    horizon c₀)
      > diversity (evolveExpected p_env p_star r_eco r_int horizon c₀) := by
  sorry

end WuWei
```

Obligations in order: **A** discharges now (algebra). **B** is a calculus
monotonicity on the drift integral. **C** is the real prize — a Freidlin–
Wentzell large-deviations estimate for the Wright-Fisher generator near `∂Δ`.
**Dominance** follows from C + Schur-concavity of `diversity`.

### Open items
- Closed form for `r*` from the barrier `ΔU(r_eco − r_int)=σ²·log(horizon/C)`.
- Replace threshold-extinction with the genuine Wright-Fisher generator so C is a
  theorem, not a fit.
- AI-safety `1/N` granularity (§8) deserves its own note.
