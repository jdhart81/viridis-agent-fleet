# Infrastructure Agent Architecture Patterns

**Date:** April 3, 2026
**Context:** Patterns and lessons learned from optimizing Evolution, Mycelium IQ, and Wavefunction Search agents

---

## 0. Conventions: Reading the Two-Witness Rule

Pattern sections in this document use a **two-witness rule** to mark a
sub-pattern as canonical: a sub-pattern is promoted to canonical status
once it has been independently observed and uniformly implemented in
≥ 2 places. Section 9.1's stewardship arc (N46-A → N47-A/B → N48-A →
N49-A/B) demonstrated that the *quality* of those two witnesses matters
as much as the count — two copies of the same observation are weaker
evidence for generality than two observations from genuinely independent
contexts.

### Sub-rule: Independent-Context Witnesses Are Stronger

**Two copy-paste witnesses** — two adopters that share a single lineage
(same originating agent, same constant name, same dispatch field, same
pattern context, copy-edited into the second adopter) — establish that
the implementation is mechanically reproducible, but they do not yet
establish that the pattern is *general*. The second witness could be a
copy of the first with the names changed; the generality claim is
unverified.

**Two independent-context witnesses** — two adopters that share only the
abstract pattern, but differ in the concrete context where the pattern
manifests (different agent, different field, different constant name,
different pattern context, different sub-discipline being applied) —
establish that the pattern generalizes across the dimension along which
the contexts differ. The generality claim ("applies to ANY constant
rename" / "applies to ANY pattern's originator") is supported by
genuinely independent observation rather than copy-paste lineage.

### Two Observed Forms of Independent-Context Evidence

| Form | Introduced | Sub-pattern canonicalized | What independence the second witness adds |
|------|------------|---------------------------|--------------------------------------------|
| **Independent-rename-context** | N48-A | Section 9.1 backward-compatibility alias (`OLD_NAME = NEW_NAME` + `is`-identity guard) | Different agent + different dispatch field + different legacy constant name; generalises "applies to ANY constant rename, not just `SUPPORTED_*`" |
| **Independent-pattern-context** | N49-A/B | Section 9.1 back-propagation discipline (downstream-discovered strengthening propagated to originator) | Different pattern + different sub-discipline being back-propagated (Section 9.1 drift-guard vs Section 10 linearity-formulation); generalises "applies to ANY pattern's originator, not just Section 9.1" |

### How to Apply the Sub-rule

When promoting a sub-pattern to canonical status, examine the second
witness: does it differ from the first only in mechanical details
(variable names, identifier strings), or does it differ along the
dimension the generality claim asserts? If the latter, mark the
canonicalization explicitly as supported by independent-context
evidence, and name the dimension of independence (rename context,
pattern context, agent context, …). If the former, treat the
canonicalization as provisional and seek a genuinely independent third
witness before treating the generality claim as load-bearing for
downstream stewardship work.

**The meta-discipline itself has reached two witnesses** (N48-A
introduction as independent-rename-context; N49-A/B application as
independent-pattern-context), so this convention is itself canonical
under the two-witness rule it describes — a property worth flagging
because it means the convention is self-consistent: the rule for
promoting sub-patterns has been promoted using exactly the discipline
it prescribes.

---


## 1. Graph-Based Fleet Topology (Evolution Agent)

### Pattern: Centrality Metrics for Network Health

The Evolution Agent models the fleet as a directed graph and computes three centrality measures to identify critical agents and vulnerabilities:

**Betweenness Centrality:** Measure of how many shortest paths pass through a node
- High value → agent is critical for connectivity between fleet components
- Used to detect bottlenecks

**Closeness Centrality:** Average distance to all other nodes
- Computed as: `1.0 / (1.0 + avg_distance)` — always ∈ [0, 1]
- High value → agent can reach others quickly
- Used to identify communication hubs

**Clustering Coefficient:** Local density of triangles in the graph
- Measure of how well a node's neighbors are connected
- High value → agent operates within tight cluster
- Used to identify isolated subgraphs (pillars)

**Key Invariant:** All measures guaranteed ∈ [0.0, 1.0] via explicit normalization and bounds checking.

### Pattern: Recommendation as Graph Extensions

Rather than prescribing specific actions, Evolution recommends new edges (connections):
1. Cross-pillar connections: Bridge disconnected network components
2. Bottleneck redundancy: Add parallel paths around critical nodes
3. Orphan integration: Connect isolated agents to main network

Each recommendation has (source, target, reason), making it immediately actionable.

---

## 2. Multi-Criteria Fitness Evaluation with Pillar Weighting (Evolution Agent)

### Pattern: Component Scores + Pillar-Specific Weights

Fitness evaluation decouples component scoring from aggregation:

**Component Scores** (always ∈ [0, 1]):
- `revenue_score`: Normalized revenue generated
- `uptime_score`: Availability (NINES-based scaling)
- `reliability_score`: Error rate inverse
- `utilization_score`: Requests processed / capacity
- `connectivity_score`: Number of network connections
- `thesis_alignment_score`: Contribution to thesis

**Pillar-Specific Weights** (sum to 1.0):
- Revenue pillar: weights revenue_score heavily (≥0.40)
- Infrastructure pillar: weights uptime + reliability heavily (≥0.50)
- Climate-intelligence pillar: balanced weighting

**Composite Score Guarantee:**
```
composite = Σ(component_score × pillar_weight)
∈ [0, 1] because all components ∈ [0,1] and weights sum to 1.0
```

**Key Invariant:** Weights are validated at initialization to always sum to 1.0 ± 0.0001.

### Pattern: Threshold-Based Recommendations

Clear boundaries define agent lifecycle decisions:

| Composite Score | Recommendation | Action |
|---|---|---|
| > 0.75 | **promote** | Move to higher status (prototype → mvp → production) |
| 0.50–0.75 | **maintain** | Continue current operations, monitor |
| 0.40–0.50 | **evolve** | Refine design, improve weak components |
| < 0.40 | **compost** | Retire or redesign from scratch |

Thresholds are explicit and documented, avoiding ambiguous grading.

---

## 3. Agent Scaffolding as Template Instantiation (Evolution Agent)

### Pattern: Agent as YAML Manifest + Generated Code

The scaffolder generates agents from a proposal containing:
- Agent metadata (name, pillar, status, revenue model)
- Capabilities (inputs/outputs as a formal interface)
- Dependencies (other agents, external services)
- Environment variables (configuration)

**Generated Structure:**
```
agent-name/
├── agent.yaml              # YAML manifest (source of truth)
├── src/core.py             # Implementation (generated stub)
├── src/core.py             # Implementation (generated stub)
├── tests/test_core.py      # Pytest template
├── adapters/
│   ├── mcp_server.py       # MCP (Model Context Protocol)
│   └── fastapi_server.py   # REST API (optional)
├── requirements.txt
├── .env.example
└── .gitignore
```

**Key Invariants:**
- agent.yaml is valid YAML (checked with `yaml.safe_load()`)
- All generated Python files compile without syntax errors
- All required files are present (validation step)
- Dependencies form a valid DAG (no circular dependencies in declarations)

### Pattern: Code Generation + Compilation Verification

Rather than hand-coding each agent, scaffolding generates correct boilerplate:
1. Parse proposal dictionary
2. Generate files with Jinja2-like templates
3. Validate YAML syntax
4. Compile generated Python (catch syntax errors early)
5. Check file presence
6. Report actionable next steps

This ensures consistency across the fleet and catches errors at agent creation time, not deployment time.

---

## 4. State Machine Health Monitoring (Mycelium IQ Agent)

### Pattern: Health State Machine

Fleet health is modeled as discrete states with transitions:

```
HEALTHY
  ↓ (if degradation detected)
DEGRADED
  ↓ (if failures accumulate)
FAILING
  ↓ (if recovery not attempted)
OFFLINE
```

**Transition Triggers:**
- HEALTHY → DEGRADED: Load > threshold OR recent error spike
- DEGRADED → FAILING: Consecutive failures OR extended downtime
- FAILING → HEALTHY: Recovery successful AND clear log

**Key Invariant:** Health status is discrete; no intermediate states. All agents in fleet have explicit status.

### Pattern: Load Normalization to [0, 1]

Agent load is normalized to a unit interval:
```
normalized_load = min(1.0, max(0.0, current_load / capacity))
```

This allows:
- Fair comparison of agents with different capacities
- Resource conflict resolution (allocate proportionally by urgency)
- Fleet-level aggregation (average load across all agents)

---

## 5. Failure Composting and Pattern Detection (Mycelium IQ Agent)

### Pattern: Treat Failures as Compostable Knowledge

Rather than just logging errors, failures are analyzed for patterns:

1. **Capture:** Store error type, message, context, timestamp
2. **Pattern Detect:** Group failures by type and identify recurrence
3. **Learn:** Extract actionable insights (e.g., "memory leak in module X")
4. **Resolve:** Link failure to resolution action taken
5. **Compost:** Generate aggregated insights for future design

**Key Insight:** Failures are data points, not just problems. Each failure contributes to fleet knowledge.

---

## 6. Symbiotic Pairing via Complementarity Scoring (Mycelium IQ Agent)

### Pattern: Algorithmic Agent Matchmaking

Pairs of agents are scored for synergistic potential:

```
complementarity_score = Σ w_i · overlap_i(A, B)
```

Where `overlap_i` measures how agent A's outputs align with agent B's inputs across domains:
- High score (> 0.8) → strong synergy, recommend pairing
- Medium score (0.5–0.8) → potential synergy, monitor
- Low score (< 0.5) → independent agents, no pairing

**Application:** Mycelium IQ uses this to suggest:
- Resource trading partnerships
- Cross-pillar collaboration opportunities
- Symbiotic pairings that increase fleet revenue

---

## 7. Quantum Cognition Routing (Wavefunction Search Agent)

### Pattern: 4-Stage Intention-to-Matching Pipeline

User interaction flows through four distinct stages:

**INTAKE Stage:** Dialogue-driven intention discovery
- Extract explicit goals from user messages
- Detect whether intent is individual or community-focused
- Build confidence as intent clarifies (0.0 → 1.0)
- Require explicit articulation before proceeding

**COLLAPSE Stage:** Commitment via stake
- User commits stake amount (financial or reputational)
- Creates immutable intention record (timestamp + proof)
- Acts as signal of genuine commitment
- Prevents proposal spam

**MATCH Stage:** Constitutional + semantic alignment
- Constitutional scoring: S_C = Σ w_i · C_i(C)
  - Hard constraint: S_C ≥ 0.5 (no routes if violated)
  - Axes: BIOSPHERE_RESTORATION (0.35), DEMOCRATIC_GOVERNANCE (0.25), TRANSPARENCY (0.25), LONG_TERM_FLOURISHING (0.15)
- Semantic alignment: Domain overlap × value alignment
  - Soft constraint: A ≥ 0.65
- Only collectives meeting both constraints are considered

**ROUTE Stage:** Ranked matches with explanation
- Combined score: 0.6×alignment + 0.4×constitutional
- Results ordered by score (deterministic)
- Each match includes "why" bullets explaining reasoning
- Respects collective capacity limits

**Key Invariant:** All scores ∈ [0, 1]. Probability amplitudes are normalized.

### Pattern: Superposition → Collapse → Measurement

This maps quantum mechanics concepts to user interaction:
- **Superposition:** User's intention exists in multiple possible states
- **Collapse:** Stake acts as measurement, collapsing superposition
- **Amplitude:** Constitutional and semantic alignment scores
- **Measurement:** Routing produces deterministic, ranked results

---

## 8. Production-Grade Invariant Validation

### Pattern: Test-Driven Invariant Discovery

Each agent includes exhaustive test coverage for critical invariants:

**How to Validate:**
1. List all mathematical invariants (e.g., "all scores ∈ [0, 1]")
2. Create tests that verify invariants at boundaries and extremes
3. Test edge cases (empty inputs, single elements, max values)
4. Test integration workflows
5. Document invariants explicitly in test docstrings

**Example (Evolution Agent):**
```python
def test_centrality_values_in_valid_range(self):
    """Verify all centrality measures stay within [0, 1]."""
    topo = FleetTopology()
    # Build graph
    topo.compute_centrality_measures()

    # Assert invariant
    for node in topo.nodes.values():
        assert 0.0 <= node.betweenness_centrality <= 1.0
        assert 0.0 <= node.closeness_centrality <= 1.0
        assert 0.0 <= node.clustering_coefficient <= 1.0
```

---

## 9. Validator Integration Patterns

*Date added: May 10, 2026 (Night 41) — surfaced by N39-C audit, canonicalized after the dscore-agent N40 wiring landed as the second cross-agent adopter of the dispatcher pattern.*

Three observed patterns for integrating per-action input validators with `process()`-style multi-action agent dispatch. All three are equivalently safe at the "no input reaches a compute method without invariant checks" level; they trade differently along axes of test isolation, code locality, and the cost of adding a new action.

### Pattern A: Per-branch repetition (carbon-bridge / sentinel-watch)

```python
async def process(self, input_data: dict) -> dict:
    action = input_data.get("action", "").lower()
    if action == "score_patch":
        validated = validate_score_patch_input(input_data)
        return self._score_patch(validated)
    elif action == "score_landscape":
        validated = validate_score_landscape_input(input_data)
        return self._score_landscape(validated)
    # ...
```

**When to use:** small action surfaces (≤3 actions), or when each validator returns a strongly-typed dataclass that the downstream branch consumes directly.

**Tradeoffs:** Simple to read, easy to test each validator in isolation. Scales poorly: adding a new action requires touching the dispatch in two places (validator import + per-branch call), and orphan risk grows linearly with action count (the N38-B finding that surfaced this pattern).

### Pattern B: Top-level dispatcher (evoterra / dscore)

```python
def validate_process_input(input_data: dict) -> dict:
    """Single entry point — validates and returns a normalized payload."""
    if not isinstance(input_data, dict):
        raise ValidationError("input", input_data, "must be dict")
    action = input_data.get("action", "").lower()
    if action not in SUPPORTED_ACTIONS:
        raise ValidationError("action", action, f"must be one of {SUPPORTED_ACTIONS}")
    if action == "score_patch":
        return validate_score_patch_input(input_data)
    elif action == "score_landscape":
        return validate_score_landscape_input(input_data)
    # ...

async def process(self, input_data: dict) -> dict:
    try:
        validated = validate_process_input(input_data)
    except ValidationError as e:
        return {"error_type": "ValidationError", "field": e.field, ...}
    return self._dispatch(validated)
```

**When to use:** medium-to-large action surfaces (≥3 actions), or whenever the agent needs uniform error-response shaping at the entry point.

**Tradeoffs:** Single point of contract translation (one `try/except ValidationError → structured response` block instead of N). The `SUPPORTED_ACTIONS` frozenset surfaces dispatch-vs-validator drift as a test failure rather than a runtime surprise. Slightly higher upfront cost (one extra function); the dispatcher itself is a small wrapper. **This is the recommended default for new agents.**

**Cycle hazard:** if the validator soft-imports from `core.py` (e.g., taxonomy keys) AND `core.py` eagerly imports the dispatcher, the import cycle silently degrades validation. Use a lazy-loader (`_ensure_validator_loaded()` called inside `process()`) to defer the binding until both modules are fully initialized. Pattern surfaced and resolved during dscore-agent N40-A landing — see the lazy-loader idiom in `dscore-agent/src/core.py`.

### Pattern C: Inline-per-parameter (thermo-econ)

```python
def compute_displacement_dividend(self, data: dict) -> dict:
    gdp_usd = _require_number(data, "gdp_usd", positive=True)
    productivity = _require_number(data, "productivity", min_value=0, max_value=1)
    # ... compute ...
```

**When to use:** agents whose actions are small numeric pure-functions over a flat parameter dict, where each compute method's input contract is fully captured by ~3–5 numeric fields. No separate validator module exists.

**Tradeoffs:** Lowest coupling — no orphan risk because there are no separate validator functions to orphan. Validation is co-located with the computation that depends on it, which makes the "why is this field bounded?" question answerable in one place. Harder to test validation in isolation (validators are not callable without running the compute). Doesn't scale to nested inputs or list-of-dict payloads.

### Decision matrix

| Action surface | Input shape | Pattern |
|---|---|---|
| 1–2 actions, flat numeric inputs | flat | C (inline) |
| 1–2 actions, structured inputs | nested/list | A (per-branch) |
| ≥3 actions, mixed shapes | any | B (dispatcher) — the default |

### Two-witness rule

A pattern earns its place in this document only after two independent agents adopt it without modification:

- **Pattern A** has 2 adopters (carbon-bridge, sentinel-watch — both pre-Night 32).
- **Pattern B** has 2 adopters (evoterra is the prototype; dscore is the second adopter, landed in N40-A on 2026-05-09).
- **Pattern C** has 1 adopter (thermo-econ); promotion to canonical status pending a second observation.

When the third pattern earns its second witness, expand this section accordingly.

### Back-propagation discipline (fleet-wide, promoted from Section 9.1)

*Promoted N50-B (2026-05-18) from Section 9.1's per-section witness
table to a Section 9 fleet-wide discipline. Originally surfaced and
canonicalized at N49-A/B (Section 9.1 back-propagation Two-Witness
Status).*

When a pattern is canonicalized in this document (Section 9.1's
SUPPORTED_ACTIONS drift detector, Section 10's linearity-check
formulation, or any future section's canonical form), the
canonicalization implicitly creates an asymmetry: the second and
later witnesses adopt the canonical form, but the **originator** —
the first witness, which was canonicalized after the fact — is often
the weakest implementation of its own pattern. Left unaddressed, the
originator becomes a permanent counterexample to its own canonical
status, eroding the generality claim and confusing future
contributors who grep for the pattern.

**The discipline:** every canonicalization carries an obligation to
back-propagate the canonical form to its originator if the originator
pre-dates the canonicalization. The originator must be brought to
parity with the downstream witnesses — not left as the historically
weakest implementation of the pattern it founded.

**Why it's a Section 9 (not 9.1) discipline:** the back-propagation
obligation applies to *any* canonicalized pattern, not just Section
9.1's drift-detection family. The two existing witnesses are
deliberately drawn from **independent pattern contexts**:

1. **dscore N45-B** — Section 9.1 symmetric-form upgrade
   (test-completeness strengthening back-propagated from the
   canonicalized drift-detection pattern to dscore as Section 9.1's
   originator).
2. **sentinel-watch N49-A** — Section 10 linearity-formulation
   refactor (assertion-form canonicalization back-propagated from
   carbon-bridge's multiplication form to sentinel-watch as Section
   10's originator).

These two witnesses share only the abstract discipline; they differ
in agent, pattern, sub-discipline, and section. Per the Section 0
independent-pattern-context convention, this is sufficient to treat
the back-propagation discipline as fleet-universal rather than a
Section 9.1 quirk.

**How to apply during stewardship:** when canonicalizing a pattern in
a future section, identify the originator in that section's "Observed
Adoptions" table. If the originator's implementation pre-dates the
canonical form, file a back-propagation candidate as a Nightkeeper
queue item with the same priority as the canonicalization itself
(typically HIGH for the night following the canonicalization, per the
Section 9.1 stewardship arc rhythm).

**Section 9.1's per-section witness-status block for the
back-propagation discipline is retained** for historical traceability
(it records the two witnesses that earned the canonicalization), but
the discipline itself is now governed at Section 9 scope.


---

---

## 9.1 SUPPORTED_ACTIONS Dispatcher Constant + Drift-Detection Test Class

**Origin:** dscore-agent N38-B (constant introduced) → N40-A (wired into
`validate_process_input`) — the originating witness. Cross-agent propagation:
carbon-bridge-agent N44-A (second witness, novel source-inspection symmetric
drift detector). Third-witness uniformity: sentinel-watch-agent N45-A
(quote-style-agnostic regex variant + backward-compatibility alias
sub-pattern). Originator parity restored: dscore-agent N45-B (back-propagation
of the symmetric drift detector). Canonicalized N46-A.

This sub-section is the canonical reference for the `SUPPORTED_*` dispatcher
constant + companion test-class technique introduced as part of Pattern B
(top-level dispatcher) above. It exists as 9.1 rather than as a Pattern B
footnote because the technique applies to **any** multi-action `process()`
agent regardless of which validator-integration pattern (A, B, or C) the
agent adopts — the drift-detection guard is orthogonal to where the
per-action validators live.

### The Problem

A multi-action `process()` agent has at least two parallel surfaces that
encode the action vocabulary: the dispatch chain (`if action == "score_patch":
... elif action == "score_landscape": ...`) and the validator routing
(per-branch `validate_*_input(...)` calls or a top-level `validate_process_input`
dispatcher). Without a single source of truth, drift between these surfaces is
**silent**: a contributor adding a new dispatch branch without updating the
validator surface (or vice versa) ships an action that runs unvalidated, or a
documented action that has no implementation. The N38-B finding that surfaced
this pattern in dscore-agent was exactly this class of drift in a 5-action
surface — caught by inspection, but inspection doesn't scale.

### The Pattern

Declare a `SUPPORTED_ACTIONS = frozenset({...})` (or `SUPPORTED_OPERATIONS`,
matching the agent's dispatch field name) constant in `src/validation.py`
listing every canonical action string. Mirror it with a
`TestSupportedActionsContract` test class in `tests/test_core.py` that asserts
the constant and the dispatch chain are the same set, in both directions
simultaneously, with a single symmetric assertion.

#### The constant

```python
# ───────────────────────────────────────────────────────────────────────────
# SUPPORTED_ACTIONS — single source of truth for the <agent> action
# dispatch surface. Mirrors the N dispatch branches in
# <Agent>Core.process() in src/core.py. Any future addition/removal of
# an action MUST update both surfaces — TestSupportedActionsContract in
# tests/test_core.py asserts the two surfaces remain in agreement and
# fails fast on drift.
# ───────────────────────────────────────────────────────────────────────────
SUPPORTED_ACTIONS = frozenset({
    "score_patch",       # validate_score_patch_input      → _score_patch()
    "score_landscape",   # validate_score_landscape_input  → _score_landscape()
    # ...one row per action, with the validator + handler in the comment
})
```

**Naming convention:** the constant name is `SUPPORTED_<DISPATCH_FIELD>S`
in screaming-snake-case, plural. Most agents dispatch on `action`, so
`SUPPORTED_ACTIONS`. Sentinel-watch dispatches on `operation` and uses
`SUPPORTED_OPERATIONS`. The constant must be a **frozenset** — a mutable
`set` could be silently mutated at runtime, defeating the
single-source-of-truth guarantee (see `test_supported_actions_is_frozenset`
below).

#### The companion test class

The canonical 8-test class lives in `tests/test_core.py` and uses
`inspect.getsource()` plus a quote-style-agnostic regex to extract the
dispatch literals from the source at test time:

```python
class TestSupportedActionsContract:
    """SUPPORTED_ACTIONS frozenset must remain in lockstep with
    <Agent>Core.process() dispatch."""

    def test_supported_actions_set_matches_documented_dispatch(self):
        """The N canonical actions are the complete dispatch surface.
        Adding or removing an action requires updating this assertion AND
        the dispatch in core.py — by design, so reviewers see both edits."""
        from src.validation import SUPPORTED_ACTIONS
        assert SUPPORTED_ACTIONS == frozenset({"action_a", "action_b", ...})

    def test_every_supported_action_appears_as_dispatch_branch(self):
        """Forward-direction source inspection: every SUPPORTED_ACTIONS
        member must appear as a dispatch literal in process()."""
        import inspect, re
        from src.core import AgentCore
        from src.validation import SUPPORTED_ACTIONS
        source = inspect.getsource(AgentCore.process)
        dispatch = set(re.findall(r"""action\s*==\s*['"]([^'"]+)['"]""", source))
        for action in SUPPORTED_ACTIONS:
            assert action in dispatch, (
                f"Action {action!r} in SUPPORTED_ACTIONS but missing from "
                f"AgentCore.process() dispatch."
            )

    def test_no_dispatch_branch_missing_from_supported_actions(self):
        """Reverse-direction source inspection: scan dispatch source for
        `action == "..."` literals and verify each is in SUPPORTED_ACTIONS.
        Catches a new dispatch branch without a SUPPORTED_ACTIONS update."""
        import inspect, re
        from src.core import AgentCore
        from src.validation import SUPPORTED_ACTIONS
        source = inspect.getsource(AgentCore.process)
        dispatch = set(re.findall(r"""action\s*==\s*['"]([^'"]+)['"]""", source))
        for action in dispatch:
            assert action in SUPPORTED_ACTIONS, (
                f"Action {action!r} dispatched in process() but missing from "
                f"SUPPORTED_ACTIONS."
            )

    def test_dispatch_and_supported_actions_are_equal_sets(self):
        """Tightest form — symmetric set-equality assertion. The canonical
        drift detector: catches drift in either direction with one check.
        The two prior one-directional tests are kept for diagnostic
        granularity (a forward-only failure prints a different message
        than a reverse-only failure), but this test alone would suffice."""
        import inspect, re
        from src.core import AgentCore
        from src.validation import SUPPORTED_ACTIONS
        source = inspect.getsource(AgentCore.process)
        dispatch = frozenset(re.findall(r"""action\s*==\s*['"]([^'"]+)['"]""", source))
        assert dispatch == SUPPORTED_ACTIONS, (
            f"Dispatch-vs-SUPPORTED_ACTIONS drift detected. "
            f"Only in dispatch: {dispatch - SUPPORTED_ACTIONS}. "
            f"Only in SUPPORTED_ACTIONS: {SUPPORTED_ACTIONS - dispatch}."
        )

    def test_supported_actions_is_frozenset(self):
        """Contract: SUPPORTED_ACTIONS must be a frozenset (immutable).
        A mutable set could be silently mutated at runtime, defeating the
        single-source-of-truth guarantee."""
        from src.validation import SUPPORTED_ACTIONS
        assert isinstance(SUPPORTED_ACTIONS, frozenset)

    def test_supported_actions_has_expected_arity(self):
        """The agent currently dispatches exactly N actions. If this ever
        changes, the change should be deliberate — bumping this assertion
        is the smallest possible review-flag."""
        from src.validation import SUPPORTED_ACTIONS
        assert len(SUPPORTED_ACTIONS) == N

    @pytest.mark.asyncio
    async def test_unknown_action_still_returns_error_dict_envelope(self):
        """Behavior regression: adding SUPPORTED_ACTIONS must not change
        the existing 'unknown action → {error: ...} dict' contract."""
        cfg = AgentConfig(name="<agent>", version="0.1.0", debug=True)
        agent = AgentCore(cfg)
        result = await agent.process({"action": "__synthetic_unknown__"})
        assert isinstance(result, dict)
        assert "error" in result
```

When the agent has a pre-existing constant being canonicalized to this
form (the sentinel-watch N45-A migration case — `VALID_OPERATIONS` predated
the pattern), add a 9th regression-guard test asserting the old name is now
an `is`-identity alias for the new canonical name:

```python
def test_valid_actions_alias_points_to_supported_actions(self):
    """Backward-compatibility alias: VALID_ACTIONS must `is` (not just `==`)
    SUPPORTED_ACTIONS — guards against accidental copy-divergence at any
    future rename or re-binding."""
    from src.validation import SUPPORTED_ACTIONS, VALID_ACTIONS
    assert VALID_ACTIONS is SUPPORTED_ACTIONS
```

### Quote-Style-Agnostic Regex (Canonical Form)

The regex `r"""<field>\s*==\s*['"]([^'"]+)['"]"""` (character class accepting
either quote style) is the **canonical form** going forward. N44-A's original
double-quote-only regex (`r'<field>\s*==\s*"([^"]+)"'`) was the form that
matched carbon-bridge's source convention, but breaks if applied to an agent
whose source uses single quotes (sentinel-watch). N45-A introduced the
character-class generalization and N45-B back-propagated it to dscore for
parity. Always use the character-class form — it is fleet-portable and costs
zero performance.

### Backward-Compatibility Alias Sub-Pattern

When an agent has a pre-existing constant being canonicalized to the
`SUPPORTED_*` naming convention (the migration-not-introduction case), preserve
the old name as an `is`-identity alias rather than deleting it. This prevents
import-site breakage while migrating the codebase:

```python
SUPPORTED_OPERATIONS = frozenset({...})
VALID_OPERATIONS = SUPPORTED_OPERATIONS  # backward-compat alias
```

The companion test (`test_valid_operations_alias_points_to_supported_operations`
or `test_valid_actions_alias_points_to_supported_actions`, above) uses `is`
identity rather than `==` equality so any future rebinding that creates a copy
is caught immediately. **Status:** 2 witnesses, uniformly implemented
(sentinel-watch N45-A `VALID_OPERATIONS = SUPPORTED_OPERATIONS`; evoterra
N47-A `VALID_ACTIONS = SUPPORTED_ACTIONS`). Canonicalized N48-A. The two
witnesses come from **different rename contexts** — different agents,
different dispatch fields (`operation` vs `action`), different legacy constant
names — so the generality claim ("the pattern applies to ANY constant rename,
not just to SUPPORTED_*") is supported by independent observation rather than
a single copy-paste lineage.

### When to Use

Apply 9.1 to **every agent with ≥2 dispatch branches** in `process()`,
regardless of which validator-integration pattern (A, B, or C) the agent
adopts. The constant + test class is additive — it does not change the
dispatch chain itself, it just turns silent drift into a fast test failure.

The pattern is especially valuable for:
- **Pattern B (top-level dispatcher) agents** — `SUPPORTED_ACTIONS` is the
  natural "is this action known?" check inside `validate_process_input`.
- **Pattern A (per-branch repetition) agents** — the orphan-risk that
  Pattern A is known to have (validators per branch, manually kept in sync
  with the dispatch) is exactly what 9.1 catches at test time.
- **Pattern C (inline-per-parameter) agents** — even though Pattern C agents
  rarely have a separate validator surface to drift against, they may still
  have a documented action vocabulary in `describe()` or `agent.yaml`. The
  test class can be adapted to assert dispatch-vs-`describe()` parity.

### Observed Adoptions

| Night | Agent | Field | Constant | Witness role | Notes |
|-------|-------|-------|----------|--------------|-------|
| N38-B → N40-A | dscore-agent | `action` | `SUPPORTED_ACTIONS` (5) | Originator | Original hardcoded-set assertion only; back-propagated to symmetric form at N45-B |
| N44-A | carbon-bridge-agent | `action` | `SUPPORTED_ACTIONS` (6) | Second witness, novel sub-pattern | Source-inspection regex + symmetric set-equality drift detector introduced |
| N45-A | sentinel-watch-agent | `operation` | `SUPPORTED_OPERATIONS` (5) + `VALID_OPERATIONS` alias | Third witness, novel sub-patterns | Quote-style-agnostic regex variant + backward-compatibility alias sub-pattern introduced |
| N45-B | dscore-agent | `action` | `SUPPORTED_ACTIONS` (5) | Originator parity restoration | First back-propagation of a downstream-discovered strengthening to its own pattern's originator |
| N47-A | evoterra-agent | `action` | `SUPPORTED_ACTIONS` (5) + `VALID_ACTIONS` alias | Fourth witness, second witness of alias sub-pattern | First canonical-pattern-apply after Section 9.1 was canonicalized (N46-A); promotes alias sub-pattern to 2-witness/canonical status |
| N47-B | carbon-bridge-agent | `action` | `SUPPORTED_ACTIONS` (6) | Regex parity upgrade | Quote-style-agnostic regex back-propagated to carbon-bridge per Section 9.1 canonical form; closes the last quote-style asymmetry in the fleet |
| N49-A | sentinel-watch-agent | (Section 10 originator) | `test_pixel_area_boundary_acceptance` (linearity) | Back-prop formulation upgrade | Second witness of back-propagation discipline — ratio formulation refactored to canonical multiplication form per Section 10 canonical (cross-section back-prop from Section 10 canonicalization to its Section 10 originator) |

**Witness count:** 4 uniformly-implemented adopters as of N48-A
(dscore-agent N38-B + N45-B, carbon-bridge-agent N44-A + N47-B regex upgrade,
sentinel-watch-agent N45-A, evoterra-agent N47-A). All four agents now use
the symmetric source-inspection drift detector with the quote-style-agnostic
regex — there is no "weaker form" implementation remaining in the fleet.
Pattern is effectively **fleet-universal** for every Pattern B dispatcher
agent.

### Why It Compounds

Each new agent that adopts 9.1 inherits the full 8- (or 9-, with alias) test
contract for free — copy the test class, rename `action` → the agent's
dispatch field, fill in the canonical-set arity, done. Drift between the
documented action surface and the dispatch becomes an immediate test failure
with a clear diagnostic message naming exactly which side is out of sync.

The pattern also creates a **discovery affordance** for new contributors: a
single grep for `SUPPORTED_ACTIONS` (or `SUPPORTED_OPERATIONS`) in a fresh
agent immediately surfaces the canonical action vocabulary — the agent
self-documents its dispatch surface without requiring a contributor to read
the dispatch chain end-to-end. Combined with Section 9's validator-integration
patterns, this makes the question **"what does this agent do?"** answerable
in seconds from `src/validation.py` alone.

### Two-Witness Status

`SUPPORTED_ACTIONS` constant + symmetric drift-detection test class:
**4 witnesses, uniformly implemented** (dscore-agent N38-B + N45-B,
carbon-bridge-agent N44-A + N47-B regex upgrade, sentinel-watch-agent N45-A,
evoterra-agent N47-A). Canonicalized N46-A; fourth witness added N47-A
demonstrating fleet-universality for every Pattern B dispatcher agent.

Quote-style-agnostic regex variant: **4 witnesses, uniformly implemented**
(sentinel-watch N45-A introduction, dscore N45-B back-prop adoption,
carbon-bridge N47-B parity upgrade closing the last quote-style asymmetry,
evoterra N47-A native canonical adoption). The single-quote-only and
double-quote-only variants are fully deprecated; the character-class form is
the only form in use in the fleet as of N47-B.

Backward-compatibility alias sub-pattern (`OLD_NAME = NEW_NAME` after a
constant rename, with `is`-identity test guard): **2 witnesses, uniformly
implemented** (sentinel-watch N45-A `VALID_OPERATIONS = SUPPORTED_OPERATIONS`;
evoterra N47-A `VALID_ACTIONS = SUPPORTED_ACTIONS`). Canonicalized N48-A. The
two witnesses come from independent rename contexts (different agent,
different dispatch field, different legacy name), so the generality claim
("applies to ANY constant rename, not just SUPPORTED_*") is supported by
independent observation rather than a single copy-paste lineage.

Back-propagation discipline (downstream witnesses can improve the originator;
the originator must be brought up to parity rather than left as the weakest
implementation of its own pattern): **2 witnesses, uniformly implemented**
(dscore N45-B `test_dispatch_unknown_action` symmetric-form upgrade — first
back-propagation of a downstream-discovered strengthening to its own
pattern's originator; sentinel-watch N49-A
`test_pixel_area_boundary_acceptance` ratio→multiplication formulation
refactor — first back-propagation of a downstream-discovered Section 10
canonical form to its own Section 10 originator). Canonicalized N49-A.
The two witnesses come from **independent pattern contexts** — the first
is a Section 9.1 dispatcher-vs-validator drift-guard back-propagation
(test-completeness strengthening); the second is a Section 10 linearity-
check formulation back-propagation (assertion-form canonicalization). This
is the stronger form of two-witness evidence (different patterns, different
sub-disciplines being back-propagated) rather than two copies of the same
back-propagation in the same pattern. The discipline now applies fleet-
wide: any future canonicalization (Section 9.1, Section 10, future
sections) automatically inherits the obligation to back-propagate the
canonical form to its originator if the originator pre-dates the
canonicalization. **Promoted to a Section 9 fleet-wide discipline
at N50-B (2026-05-18)** — see "Back-propagation discipline
(fleet-wide, promoted from Section 9.1)" subsection in Section 9.
This per-section witness-status block is retained for historical
traceability of the two witnesses that earned the canonicalization.


---

## 10. Linearity-Check Test Pattern (Carbon-Bridge & Sentinel-Watch)

**Origin:** N41-B (sentinel-watch `test_pixel_area_boundary_acceptance`),
canonicalized N43-C after second-witness adoption in N42-B (carbon-bridge
`TestAreaHectaresValidation` / `TestTfacPremiumMultipleValidation` /
`TestCarbonMarketReferencePriceValidation`) and third-witness adoption in
N43-B (carbon-bridge `TestNpvAreaHectaresValidation` /
`TestNpvDeltaDValidation`).

### The Problem

Input-validation guards protect against silent-corruption vectors (NaN, Inf,
bool, None, out-of-range values) but they do NOT protect against
**coefficient drift** inside the compute function itself. A future refactor
that accidentally re-bases the area scaling from `area * 10000` to `area * 100`
(losing the hectares→m² conversion) would still pass every guard test —
the input is finite, positive, and in-range — but the output magnitude
would be silently corrupted by 100×. Type-correctness is necessary but
not sufficient.

### The Pattern

For any compute parameter that **linearly scales** a return value (verified
by reading the formula), the boundary-acceptance test asserts the linearity
contract across a ≥2-order-of-magnitude range using `pytest.approx`:

```python
def test_boundary_acceptance_with_linearity(self):
    """X is a linear multiplicand of return_value; verify
    scaling X by Nx scales return_value by exactly Nx."""
    engine = SomeEngine()
    small = engine.compute(x=1.0, ...)
    large = engine.compute(x=1000.0, ...)
    assert small["return_value"] > 0
    assert large["return_value"] > 0
    # Linearity: 1000x input → 1000x output
    assert large["return_value"] == pytest.approx(small["return_value"] * 1000.0)
```

For parameters that scale **non-linearly** (e.g., a parameter inside an exp
decay or a polynomial term), the equivalent test asserts **monotonicity**
across the range rather than strict linearity:

```python
def test_boundary_acceptance_monotone(self):
    """X modulates the return non-linearly but monotonically;
    higher X → lower return."""
    low = engine.compute(x=0.05, ...)
    high = engine.compute(x=0.5, ...)
    assert low["return_value"] > high["return_value"]
```

### When to Use

Apply the linearity-check pattern to **every** input-guard boundary test
where the parameter appears as a linear multiplicand in the compute body.
Apply the monotonicity-check variant when the parameter is non-linear but
has a documented directional contract (e.g., `permanence_risk` decreases NPV).

This is the discipline: **passing the guard isn't enough; the math must
still be correct after the guard.**

### Observed Adoptions

| Night | Agent | Parameter | Type | Range |
|-------|-------|-----------|------|-------|
| N41-B | sentinel-watch | `pixel_area_m2` | linear | PlanetScope 9 m² → Sentinel-2 100 m² → Landsat 900 m² (100×) |
| N42-B | carbon-bridge | `area_hectares` | linear | small → large (10×–100×) |
| N42-B | carbon-bridge | `tfac_premium_multiple` | linear | 3.0× → 10.0× |
| N42-B | carbon-bridge | `carbon_market_reference_price` | linear | $10 → $200 (20×) |
| N43-B | carbon-bridge | `area_hectares` (npv direct) | linear | 1 → 1000 (1000×) |
| N43-B | carbon-bridge | `delta_d` (npv direct) | linear + sign-symmetric | -0.1 → 0.0 → 0.2 |
| N43-B | carbon-bridge | `permanence_risk` (npv direct) | monotone (exp-decay, decreasing) | 0.05 → 0.5 |
| N50-C | dscore | `displacement_multiplier` (price_biodiversity) | monotone (log-scaling, increasing) | 1.0 → 1000.0 (3 OOM) |
| N51-A | thermo-econ | `power_joules_per_second` (intelligence_bounded_growth) | monotone + sub-linear (log-scaling, increasing) | 1.8e12 → 1.8e15 (3 OOM) |

### Why It Compounds

Each new agent that adopts an input-guard pattern (Section 9) now has a
**default partner test**: the linearity-check companion that future-proofs
the scaling formula. The two patterns together provide both
type-correctness (Section 9) and arithmetic-correctness (Section 10)
regression coverage on every guarded compute surface.

The pattern also surfaces **hidden non-linearities**: writing a linearity
test forces the engineer to read the formula and confirm linearity is
actually expected. If the linearity assertion fails for what was assumed
to be a linear parameter, that's a finding worth surfacing — the formula
documentation and the implementation are out of sync.

### Two-Witness Status

Linearity-check pattern: **3 witnesses** (sentinel-watch N41-B,
carbon-bridge N42-B, carbon-bridge N43-B). Canonicalized N43-C.

Monotonicity-check variant: **2 witnesses, uniformly implemented**
(carbon-bridge N43-B `TestNpvPermanenceRiskValidation.test_boundary_acceptance_monotone`
exp-decay decreasing form; dscore N50-C
`TestDisplacementMultiplierMonotone.test_boundary_acceptance_monotone`
log-scaling increasing form). Canonicalized N50-C. The two witnesses come
from **independent pattern contexts** (per Section 0): different agent,
different non-linearity family (exponential decay vs logarithmic scaling),
and **opposite directional contracts** (carbon-bridge: higher input →
lower return; dscore: higher input → higher return). The generality claim
("applies to ANY monotone non-linear parameter with a documented
directional contract") is supported by genuinely independent observation
rather than a single copy-paste lineage.

Sub-linearity sub-pattern: **2 witnesses, canonicalized N51-A.**
The companion test `test_boundary_acceptance_monotone_sublinear` asserts
the formal sub-linearity bound (10× input produces strictly <10× output)
for log-scaling monotone parameters. Witnesses:

- **dscore N50-C** `TestDisplacementMultiplierMonotone.test_boundary_acceptance_monotone_sublinear`
  — `displacement_multiplier`, log-scaling, increasing direction.
- **thermo-econ N51-A** `TestPowerSubLinearMonotone.test_boundary_acceptance_monotone_sublinear`
  — `power_joules_per_second`, log-scaling, increasing direction.

The two witnesses are independent along three dimensions per Section 0
(different agent, different parameter context, different domain — ecological
accounting vs thermodynamic bound). They share a fourth dimension
(log-scaling family), so the canonical claim at canonicalization is
specifically **"log-scaling sub-linear monotone parameters"**. Broadening
to polynomial-sub-linear (e.g., square-root, `x^b` for `b<1`) requires a
third witness from a different sub-linear non-linearity family.

The thermo-econ witness additionally adds a stricter **log-scaling signature
check** (per-decade increment within 1% of the prior increment), which is
a candidate sub-discipline of the sub-linearity sub-pattern itself —
distinguishes pure log-scaling from generic sub-linear bounds. Awaiting
its own second witness for sub-discipline canonicalization.


## Cross-Agent Patterns

### Pattern: Composition via Capabilities

Agents expose capabilities (inputs/outputs) in agent.yaml:
```yaml
capabilities:
  inputs: [signal, fitness_metrics, topology_data]
  outputs: [recommendations, scaffold_proposal]
```

Evolution Agent's outputs become Mycelium IQ's inputs:
- Evolution recommends new agents → outputs `scaffold_proposal`
- Mycelium IQ receives proposal → inputs `scaffold_proposal`
- Mycelium IQ deploys and monitors → outputs `health_status`
- Evolution receives status → inputs `health_status` for next cycle

**Key Advantage:** Composition is declarative, enabling fleet self-organization.

### Pattern: Pillar-Based Categorization

All agents belong to one of 4 strategic pillars:
- **Revenue:** Monetization and market engagement
- **Infrastructure:** Reliability, uptime, fleet operations
- **Climate Intelligence:** Domain-specific scientific knowledge
- **High-Ceiling:** Exploratory, speculative, potential breakthrough

Fitness evaluation weights are pillar-specific, allowing:
- Different optimization targets per pillar
- Cross-pillar portfolio balance
- Clear strategic alignment measurement

---

## Summary: Design Principles

1. **Explicit Invariants:** Document mathematical invariants, test them exhaustively
2. **Bounded Ranges:** All scores, metrics, probabilities normalized to [0, 1]
3. **Deterministic Composition:** Agents combine via weighted sums, ensuring reproducibility
4. **State Machines:** Model fleet health as discrete states with clear transitions
5. **Failure as Data:** Treat errors as compostable knowledge for fleet learning
6. **Graph-Based Topology:** Model fleet as directed graph, analyze with centrality metrics
7. **Actionable Recommendations:** Suggest edges/actions, not generic advice
8. **Integration-First Testing:** Include full pipeline tests, not just unit tests
9. **Early Validation:** Catch errors at generation/creation time, not deployment time
10. **Capability Composition:** Enable fleet self-organization through declarative interfaces

---

## Architectural Debt Addressed

1. **Missing Logger Initialization:** Signal processing now logs correctly
2. **Out-of-Bounds Centrality:** Closeness centrality guaranteed ∈ [0, 1]
3. **Incomplete Test Coverage:** 144+ new tests covering edge cases and integration
4. **Stub Implementation:** Wavefunction Search core fully implemented (150+ LOC)
5. **Async Test Isolation:** Mycelium IQ tests ready for async context fix

These patterns enable the fleet to self-evolve, self-repair, and self-organize within thermodynamic bounds.
