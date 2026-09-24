# Governed Robustness Kernel Pattern

**Status:** Canonical fleet architecture pattern backed by two independent
contexts and a narrow audited Lean nucleus.

**Research package:** `Directed-2026-08-06-RobustnessAlgorithm`

**Formal package:** `Directed-RobustnessKernelV02-attempt-3`, Aristotle project
`be0f0828-7461-4ea5-bd07-0f78fe270ae3`, independently audited
`AUDITED_VERIFIED / ZERO_SORRY`.

## Purpose

Fleet agents often recommend actions, compare fallbacks, or report that a
claim passed a check. Those operations become unsafe when one kind of success
is allowed to impersonate another, when a recalled model remains silently in
use, or when uncertainty is collapsed into a point estimate. This pattern adds
five reusable rules:

1. evaluate fallback diversity over transitive failure domains, not component
   labels;
2. require selection and every explicit authority condition before an action
   can be called authorized; and
3. preserve independent evidence states for proof, authorization, deployment,
   and observed outcome; and
4. content-address model and adapter lineage, then quarantine every descendant
   of an effective recall; and
5. compare interval-valued outcomes only when one candidate's worst case is no
   worse than the other's best case in every dimension and strictly better in
   at least one.

The shared implementation is `fleet_utils.robustness`. The fleet release gate
is `scripts/test_robustness_kernel.py`.

## Rule 1 - expand before scoring independence

Two fallback services can have different names and still share a provider,
owner, identity root, control plane, region, power source, or upstream library.
Agents must declare a parent dependency DAG and expand each path before
calculating one-minus-Jaccard overlap.

```python
from fleet_utils.robustness import two_path_fallback_profile

profile = two_path_fallback_profile(
    {"region_a_runtime"},
    {"region_b_runtime"},
    {
        "region_a_runtime": ("provider_control_plane",),
        "region_b_runtime": ("provider_control_plane",),
        "provider_control_plane": (),
    },
)
```

Required behavior:

- cycles, missing parents, and missing direct nodes fail closed;
- both direct and expanded values remain visible;
- shared ancestors are named in the receipt;
- two empty paths receive zero useful independence credit;
- the score is a diagnostic, not a probability.

The Lean result proves that a shared element makes the declared finite-set
score strictly less than one and that adding a hidden common parent strictly
lowers directly disjoint paths. It does not prove that a real dependency map is
complete.

## Rule 2 - selection is not execution

Use `execution_authorized(selected, lease)` only after the Covenant rail has
resolved the action, active state, scope, and expiry conditions. A selected
candidate is executable only when all of these are true:

- selected;
- not advisory-only;
- action allowed;
- lease active;
- requested scope covered; and
- lease unexpired.

The function produces a Boolean gate. It does not execute the action, verify a
signature, consume a budget, or consult a live revocation service. Those remain
the Covenant and actuator rails' responsibilities.

## Rule 3 - epistemic states have no implication edges

The permitted states are `ASSUMED`, `HYPOTHESIZED`,
`NUMERICALLY_SUPPORTED`, `REPRODUCED`, `FORMALLY_PROVED`,
`EMPIRICALLY_SUPPORTED`, `AUTHORIZED`, `DEPLOYED`, and `OBSERVED`. Each state
requires its matching evidence class.

There are no automatic transitions:

- proof does not imply empirical support or authorization;
- authorization does not imply deployment;
- deployment does not imply an observed successful outcome; and
- an agent recommendation does not create any state transition.

## Rule 4 - recalled lineage fails closed

Use `lineage_artifact_id` to bind an artifact's kind, canonical manifest, and
sorted parent content addresses. Use `evaluate_lineage` at the decision's fixed
timestamp before consuming model or adapter output.

Required behavior:

- a content-address mismatch, duplicate, missing parent, cycle, malformed
  recall, or unknown required artifact fails closed;
- an effective recall marks the named artifact recalled and every descendant
  quarantined;
- any required recalled or quarantined artifact blocks the decision;
- future-dated recalls remain visible but do not take effect prematurely; and
- an unrelated recalled artifact does not invalidate a decision that did not
  consume it.

This fleet primitive validates the declared record. It does not fetch remote
bytes, authenticate the recall authority, or create a live revocation service.
Those are separate supply-chain and Covenant responsibilities. The v0.3 Lean
package does not formally prove this later v0.4 lineage mechanism.

## Rule 5 - uncertainty stays visible during comparison

Use `numeric_interval` to validate declared closed intervals and
`classify_viability_interval` to classify each invariant as `ROBUST_PASS`,
`ROBUST_FAIL`, or `UNCERTAIN`. A mandatory, non-compensable uncertain invariant
must route the decision to a hold rather than being treated as a pass or fail.

Use `robustly_dominates` for multi-dimensional comparisons. For a dimension to
be no worse, the candidate's worst case must be at least the other candidate's
best case when maximizing, or at most the other candidate's best case when
minimizing. At least one dimension must be strictly separated. Overlapping or
merely touching intervals do not establish dominance.

These interval witnesses express bounded declared uncertainty; they are not
probability distributions or confidence intervals unless the evidence record
separately establishes that interpretation. The audited v0.3 Lean nucleus does
not formally prove this later v0.5 interval mechanism.

## Independent-context witnesses

This pattern clears the fleet two-witness convention through materially
different contexts:

1. the municipal heat fixture exercises public-governance authority,
   non-compensable safety, off-boundary harm, and human selection from a Pareto
   frontier; and
2. the cyber identity fixture exercises shared control planes, transitive
   fallback dependence, adversarial disturbance, and a bounded security action
   lease.

These witnesses show that the same primitives run without domain branches.
They are synthetic software fixtures, not empirical validation.

## Adoption rule

Any agent that compares fallbacks, emits a recommendation that could lead to
action, reports claim completion, or consumes versioned model/adapter output
should import this shared module rather than re-derive the five contracts.
Domain logic may add stricter gates but may not weaken them.

Do not add this candidate to `canon_fingerprint_index.json`. That index is for
published DOI-backed canon records. The research package is currently an
internal directed working-corpus `NEW-BRANCH / Robustness Engineering and
Governance` result; public release remains held on the publication gate.
