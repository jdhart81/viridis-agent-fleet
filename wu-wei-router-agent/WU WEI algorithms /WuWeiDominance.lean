/-
===============================================================================
  The Wu Wei Dominance Theorem  —  Lean 4 / Mathlib formalization
  Viridis LLC.  For submission to Aristotle.
===============================================================================

WHAT IS PROVEN (completely, no `sorry`, no axioms beyond Mathlib):

  Model an ecosystem (or a belief / value distribution) as an abundance vector.
  Management is a *multiplicative drift* (replicator / Bayesian / selection
  update) followed by an *extinction cull* that removes any type below the
  one-individual threshold `thr = 1/N`.

  1. ABSORBING BOUNDARY.  Drift cannot resurrect an extinct type, and the cull
     only removes types: `support (Step c) ⊆ support c`.  (Extinction = Bayes
     assigning probability 0 = irreversible.)
  2. PERMANENCE.  Support — hence species richness — is antitone along any
     trajectory.  Loss is forever.
  3. SUB-CRITICAL SAFETY.  If every step keeps each extant type's drifted
     abundance at or above `thr`, the support is preserved.
  4. SUPER-CRITICAL COLLAPSE.  If at some step the drift pushes an extant type
     below `thr`, that type goes extinct and richness strictly, permanently drops.
  5. DOMINANCE.  A sub-critical (slow / wu wei) policy attains strictly greater
     long-run species richness than a super-critical (aggressive) policy.
     Richness is the Hill-0 diversity index and the ceiling on Shannon diversity
     (max entropy on a k-type support is log k), so this is genuine diversity
     dominance.

THE HONEST BOUNDARY (the input, NOT formalized here):

  WHICH rate regime a policy falls in — i.e. whether hypotheses `hsub`
  (sub-critical) or `hsuper` (super-critical) hold for a given intervention rate
  `r_int` relative to the ecosystem's intrinsic rate `r_eco` — is governed by a
  Kramers / Freidlin–Wentzell escape law:  the mean first-passage time of the
  selection-balanced Wright–Fisher process to the absorbing boundary obeys
  `MFPT ≍ exp(ΔU(r_eco − r_int) / σ²)`, with a critical rate `r* = Θ(r_eco)`
  (empirically ≈ 0.85·r_eco; see `analysis_kramers.py`).  Mathlib lacks
  Freidlin–Wentzell, so that law is supplied as the hypotheses `hsub`/`hsuper`
  below.  This file proves everything downstream of it.

  Tested against a recent Mathlib.  A few lemma names in Mathlib drift between
  releases; the three most likely to need a local rename are flagged inline.
===============================================================================
-/
import Mathlib

open Classical
open Finset

namespace WuWei

variable {n : ℕ}

/-- An abundance vector over `n` types. -/
abbrev Abund (n : ℕ) := Fin n → ℝ

/-- The types currently present (strictly positive abundance). -/
noncomputable def support (c : Abund n) : Finset (Fin n) :=
  univ.filter (fun i => 0 < c i)

@[simp] lemma mem_support {c : Abund n} {i : Fin n} :
    i ∈ support c ↔ 0 < c i := by
  simp [support]

/-- Species richness = Hill number of order 0 = number of extant types.
    This is the diversity *ceiling*: the maximum Shannon entropy on a support of
    size `k` is `log k`, so richness dominance implies attainable-diversity
    dominance. -/
noncomputable def richness (c : Abund n) : ℕ := (support c).card

/-! ### Multiplicative drift and the absorbing boundary -/

/-- A multiplicative drift: each coordinate is scaled by a nonnegative,
    state-dependent factor.  Replicator dynamics, Bayesian conditioning, and
    selection are all of this form. -/
structure Drift (n : ℕ) where
  factor        : Abund n → Fin n → ℝ
  factor_nonneg : ∀ c i, 0 ≤ factor c i

/-- Apply the drift. -/
def Drift.apply (D : Drift n) (c : Abund n) : Abund n :=
  fun i => D.factor c i * c i

/-- **Absorbing boundary.** Multiplicative drift cannot resurrect an extinct
    type: a positive output forces a positive input. -/
lemma Drift.support_subset (D : Drift n) (c : Abund n) :
    support (D.apply c) ⊆ support c := by
  intro i hi
  rw [mem_support] at hi ⊢
  rcases le_or_lt (c i) 0 with hc | hc
  · exact absurd hi (not_lt.mpr (mul_nonpos_of_nonneg_of_nonpos (D.factor_nonneg c i) hc))
  · exact hc

/-- The extinction cull at granularity `thr`: any abundance below `thr`
    (less than one individual, `1/N`) is set to 0. -/
noncomputable def cull (thr : ℝ) (c : Abund n) : Abund n :=
  fun i => if c i < thr then 0 else c i

/-- The cull only removes types. -/
lemma cull_support_subset (thr : ℝ) (c : Abund n) :
    support (cull thr c) ⊆ support c := by
  intro i hi
  rw [mem_support] at hi ⊢
  unfold cull at hi
  by_cases h : c i < thr
  · simp [h] at hi
  · simpa [h] using hi

/-- One management step: drift, then extinction cull. -/
noncomputable def Step (D : Drift n) (thr : ℝ) (c : Abund n) : Abund n :=
  cull thr (D.apply c)

/-- A management step only ever removes types. -/
lemma Step_support_subset (D : Drift n) (thr : ℝ) (c : Abund n) :
    support (Step D thr c) ⊆ support c :=
  (cull_support_subset thr (D.apply c)).trans (D.support_subset c)

/-- Iterated dynamics. -/
noncomputable def evolve (D : Drift n) (thr : ℝ) : ℕ → Abund n → Abund n
  | 0,     c => c
  | (k+1), c => Step D thr (evolve D thr k c)

lemma support_evolve_succ (D : Drift n) (thr : ℝ) (c : Abund n) (k : ℕ) :
    support (evolve D thr (k+1) c) ⊆ support (evolve D thr k c) :=
  Step_support_subset D thr (evolve D thr k c)

/-- **Permanence.** Support is antitone along the trajectory: extinction is
    irreversible. -/
lemma support_antitone (D : Drift n) (thr : ℝ) (c : Abund n) :
    ∀ {a b : ℕ}, a ≤ b → support (evolve D thr b c) ⊆ support (evolve D thr a c) := by
  intro a b hab
  induction b, hab using Nat.le_induction with
  | base => exact subset_rfl
  | succ m _ ih => exact (support_evolve_succ D thr c m).trans ih

/-- Richness is non-increasing: species are never gained. -/
lemma richness_antitone (D : Drift n) (thr : ℝ) (c : Abund n) {a b : ℕ}
    (hab : a ≤ b) : richness (evolve D thr b c) ≤ richness (evolve D thr a c) :=
  -- `Finset.card_le_card` (older Mathlib: `Finset.card_le_of_subset`)
  Finset.card_le_card (support_antitone D thr c hab)

/-! ### Super-critical collapse -/

/-- If the drift pushes an extant type below the extinction threshold in one
    step, richness strictly drops. -/
lemma richness_drop_of_push (D : Drift n) (thr : ℝ) (c : Abund n) (i : Fin n)
    (halive : i ∈ support c) (hpush : D.apply c i < thr) :
    richness (Step D thr c) < richness c := by
  have hstep : Step D thr c i = 0 := by
    simp only [Step, cull]
    rw [if_pos hpush]
  have hout : i ∉ support (Step D thr c) := by
    rw [mem_support, hstep]; exact lt_irrefl 0
  have hssub : support (Step D thr c) ⊂ support c :=
    -- `Finset.ssubset_iff_of_subset` : (s ⊆ t) → (s ⊂ t ↔ ∃ x ∈ t, x ∉ s)
    (Finset.ssubset_iff_of_subset (Step_support_subset D thr c)).mpr ⟨i, halive, hout⟩
  unfold richness
  exact Finset.card_lt_card hssub

/-- A single super-critical event at any time `t < T` yields a strictly smaller
    support at the horizon `T` (and, by permanence, forever after). -/
lemma fast_collapse (D : Drift n) (thr : ℝ) (c₀ : Abund n) (T t : ℕ) (i : Fin n)
    (ht : t < T)
    (halive : i ∈ support (evolve D thr t c₀))
    (hpush : D.apply (evolve D thr t c₀) i < thr) :
    support (evolve D thr T c₀) ⊂ support c₀ := by
  have hdead : i ∉ support (evolve D thr (t+1) c₀) := by
    have hstep : Step D thr (evolve D thr t c₀) i = 0 := by
      simp only [Step, cull]; rw [if_pos hpush]
    have : evolve D thr (t+1) c₀ i = 0 := hstep
    rw [mem_support, this]; exact lt_irrefl 0
  have hdeadT : i ∉ support (evolve D thr T c₀) := fun hmem =>
    hdead (support_antitone D thr c₀ ht hmem)
  have halive0 : i ∈ support c₀ := support_antitone D thr c₀ (Nat.zero_le t) halive
  have hsub : support (evolve D thr T c₀) ⊆ support c₀ :=
    support_antitone D thr c₀ (Nat.zero_le T)
  exact (Finset.ssubset_iff_of_subset hsub).mpr ⟨i, halive0, hdeadT⟩

/-! ### Sub-critical safety -/

/-- If every extant type's drifted abundance stays at or above the positive
    threshold, one step preserves the support exactly. -/
lemma Step_support_eq_of_safe (D : Drift n) (thr : ℝ) (hthr : 0 < thr)
    (c : Abund n) (hsafe : ∀ i ∈ support c, thr ≤ D.apply c i) :
    support (Step D thr c) = support c := by
  apply Finset.Subset.antisymm (Step_support_subset D thr c)
  intro i hi
  rw [mem_support]
  have hge : ¬ (D.apply c i < thr) := not_lt.mpr (hsafe i hi)
  have hval : Step D thr c i = D.apply c i := by
    simp only [Step, cull]; rw [if_neg hge]
  rw [hval]; linarith [hsafe i hi]

/-- A sub-critical trajectory (every step keeps extant types above threshold)
    preserves the support over the whole horizon. -/
lemma support_evolve_eq_of_safe (D : Drift n) (thr : ℝ) (hthr : 0 < thr)
    (c : Abund n) :
    ∀ T, (∀ t < T, ∀ i ∈ support (evolve D thr t c),
            thr ≤ D.apply (evolve D thr t c) i) →
      support (evolve D thr T c) = support c := by
  intro T
  induction T with
  | zero => intro _; rfl
  | succ k ih =>
      intro hsafe
      have hk : support (evolve D thr k c) = support c :=
        ih (fun t ht => hsafe t (Nat.lt_succ_of_lt ht))
      have hstep : support (evolve D thr (k+1) c) = support (evolve D thr k c) :=
        Step_support_eq_of_safe D thr hthr (evolve D thr k c)
          (hsafe k (Nat.lt_succ_self k))
      rw [hstep, hk]

/-! ### The Wu Wei Dominance Theorem -/

/-- **Wu Wei Dominance (bare form).** A policy whose support strictly collapses
    is strictly diversity-dominated by one that preserves the support. -/
theorem wu_wei_dominance
    (Dslow Dfast : Drift n) (thr : ℝ) (c₀ : Abund n) (T : ℕ)
    (hslow : support (evolve Dslow thr T c₀) = support c₀)
    (hfast : support (evolve Dfast thr T c₀) ⊂ support c₀) :
    richness (evolve Dfast thr T c₀) < richness (evolve Dslow thr T c₀) := by
  unfold richness
  rw [hslow]
  exact Finset.card_lt_card hfast

/-- **Wu Wei Dominance (assembled from rate regimes).**
    A sub-critical slow policy and a super-critical fast policy together yield
    strict, permanent species-richness dominance for the slow policy.

    The hypotheses `hsub` (sub-critical) and `hsuper` (super-critical) are the
    interface to the Kramers / Freidlin–Wentzell escape law: `hsub` holds when
    `r_int < r* = Θ(r_eco)`, and `hsuper` holds when `r_int > r*`.  That law is
    the one analytic input not formalized here. -/
theorem wu_wei_dominance_of_rates
    (Dslow Dfast : Drift n) (thr : ℝ) (hthr : 0 < thr) (c₀ : Abund n) (T : ℕ)
    (hsub : ∀ t < T, ∀ i ∈ support (evolve Dslow thr t c₀),
              thr ≤ Dslow.apply (evolve Dslow thr t c₀) i)
    (hsuper : ∃ t < T, ∃ i ∈ support (evolve Dfast thr t c₀),
              Dfast.apply (evolve Dfast thr t c₀) i < thr) :
    richness (evolve Dfast thr T c₀) < richness (evolve Dslow thr T c₀) := by
  obtain ⟨t, ht, i, halive, hpush⟩ := hsuper
  have hfast : support (evolve Dfast thr T c₀) ⊂ support c₀ :=
    fast_collapse Dfast thr c₀ T t i ht halive hpush
  have hslow : support (evolve Dslow thr T c₀) = support c₀ :=
    support_evolve_eq_of_safe Dslow thr hthr c₀ T hsub
  exact wu_wei_dominance Dslow Dfast thr c₀ T hslow hfast

/-
===============================================================================
  REMAINING OBLIGATION (the input, deliberately not formalized):

    Discharge `hsub` / `hsuper` from `r_int` vs `r_eco` via the escape law
        MFPT(r_int) ≍ exp( ΔU(r_eco − r_int) / σ² ),   σ² ∝ 1/N,
    with critical rate `r*` solving  ΔU(r_eco − r*) = σ² · log(horizon).
    This is a Freidlin–Wentzell large-deviations estimate for the Wright–Fisher
    generator near the absorbing boundary; Mathlib does not yet contain the
    machinery.  Everything in this file is downstream of that law and is proven.
===============================================================================
-/

end WuWei
