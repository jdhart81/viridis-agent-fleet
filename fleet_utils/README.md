# fleet_utils — Viridis Agent Fleet Shared Primitives

Shared, fleet-wide utilities extracted from individual agents once the same
pattern appeared in three or more places. Every primitive here started as
inline code in a single agent, was recognized during a Nightkeeper cross-
pollination pass, and promoted here only when the pattern was stable.

This README documents:

1. What lives in `fleet_utils` and when to reach for each piece.
2. The **ImportError-shim pattern** — the canonical way agents depend on
   `fleet_utils` while staying runnable in isolated/editable installs.
3. Adoption status across the fleet.

---

## Modules

| Module            | Exports                                                              | Origin                          |
| ----------------- | -------------------------------------------------------------------- | ------------------------------- |
| `scoring`         | `WeightedBooleanScorer`, `MultiFactorScorer`                         | Energy AI, Bounty Hunter        |
| `validation`      | `ValidationError`, `require_number`, `bind_to_error`                 | Carbon-Bridge (Night 18)        |
| `normalization`   | `RangeNormalizer`, `NormalizeResult`, `clamp_to_range`               | D-Score + Bounty Hunter (N19)   |
| `mcp_output`      | `FleetToolResult`, `structured_result`                               | Agent Market Network (FS8)      |

All symbols are re-exported at package level:

```python
from fleet_utils import (
    WeightedBooleanScorer,
    MultiFactorScorer,
    ValidationError,
    require_number,
    bind_to_error,
    RangeNormalizer,
    NormalizeResult,
    clamp_to_range,
    FleetToolResult,
    structured_result,
)
```

### `mcp_output`

- Annotate each MCP tool with `-> FleetToolResult`.
- Register it with `@mcp.tool(structured_output=True)`.
- Return `structured_result(core_result)`, never `json.dumps(core_result)`.
- The helper rejects missing status fields and NaN/Infinity before FastMCP
  serialization. This is the one fleet pattern for removing double-encoded
  MCP responses; adapters migrate individually and then regenerate
  `tools.json`.

### `scoring`

- `WeightedBooleanScorer(factors, weights)` — score an entity by weighted
  boolean predicates (present/absent). Origin: Energy AI portfolio scoring.
- `MultiFactorScorer(subscores, weights)` — score by weighted numeric
  sub-scores in [0, 1]. Origin: Bounty Hunter fit scoring.

### `validation`

- `ValidationError` — base class for structured validation failures.
  Carries `field`, `value`, `constraint`, and (optionally) `message`.
- `require_number(value, field, **bounds)` — NaN/Inf/bool-safe float
  coercion with optional `min_value`, `max_value`, `min_exclusive`,
  `max_exclusive`. Raises the caller's `ValidationError` subclass on
  failure. **The fleet's single source of truth for numeric validation.**
- `bind_to_error(err_cls)` — factory that returns a `require_number`
  bound to the caller's `ValidationError` subclass. Each agent has its
  own `ValidationError` (with its own module path) so agents bind once
  at module load time and call the bound version.

### `normalization`

- `RangeNormalizer(lo, hi)` — configurable clamp primitive with three
  construction paths: `RangeNormalizer(lo, hi)`, `RangeNormalizer.unit()`
  (→ [0, 1]), and `RangeNormalizer.winsorize(sample, q_low, q_high)`.
  `.apply(x)` returns a `NormalizeResult(value, clipped, reason)`.
- `NormalizeResult` — namedtuple `(value: float, clipped: bool,
  reason: Optional[str])`. `reason` is `"below min" | "above max" | None`.
- `clamp_to_range(value, lo, hi, field="value")` — **one-shot** warn+clamp
  helper. Functionally equivalent to `RangeNormalizer(lo, hi).apply(value)`
  but without requiring callers to instantiate a normalizer. Reach for
  this when you just need to clip one number and know whether a clip
  happened. (Added Night 25, queue #3.)

---

## The ImportError-Shim Pattern (Canonical)

Agents depend on `fleet_utils` for shared primitives but must remain
runnable in two degraded environments:

1. **Editable installs** — an agent dropped into another repo without
   the fleet root on `PYTHONPATH`.
2. **Containerized deploys** — a single-agent Cloudflare Worker / FastAPI
   adapter that ships only its own code.

To handle both, every agent that adopts `fleet_utils` uses this pattern
at the top of the module that needs it (typically `src/validation.py`):

```python
# fleet_utils.require_number — shared numeric validation primitive.
#
# We bind it to our local ValidationError so error types remain
# unchanged to callers. If fleet_utils is unavailable (editable install,
# isolated container, PYTHONPATH not set), fall back to a local shim
# that mirrors the fleet_utils.require_number semantics exactly.
try:
    from fleet_utils.validation import bind_to_error as _fleet_bind_to_error
    _FLEET_UTILS_AVAILABLE = True
except ImportError:  # pragma: no cover — safety net for isolated runs
    _fleet_bind_to_error = None
    _FLEET_UTILS_AVAILABLE = False


if _FLEET_UTILS_AVAILABLE:
    require_number = _fleet_bind_to_error(ValidationError)
else:
    def require_number(value, field, *, min_value=None, max_value=None,
                       min_exclusive=None, max_exclusive=None):
        """Fallback shim — mirrors fleet_utils.require_number semantics."""
        # ... local implementation ...
```

### Why this shape

- **`try` at module top** — binding happens once at import time, not
  per-call. The `require_number` name is then identical at the call
  site whether fleet_utils is present or the fallback was used.
- **`bind_to_error(ValidationError)`** — each agent has its own
  `ValidationError` subclass. Binding at import keeps the exception
  type local even though the validation logic lives in fleet_utils.
- **`_FLEET_UTILS_AVAILABLE` flag** — allows the module to introspect
  the environment (useful in tests or `describe()` health metadata).
- **`# pragma: no cover`** — the fallback branch is defensive and
  should never execute in the primary fleet test run; pragma keeps
  coverage honest.
- **Fallback shim mirrors semantics, not implementation** — the shim
  doesn't need to be bytewise-identical, only behaviorally equivalent
  for the error envelope and constraint strings. Tests in the fleet
  root verify fleet_utils; agent-local tests verify the shim via their
  own ValidationError path.

### Conftest path setup

For tests to find `fleet_utils` without an editable install, each
agent's `conftest.py` adds the fleet root to `sys.path`:

```python
# Agent root — for `from src.validation import ...`
sys.path.insert(0, str(Path(__file__).parent))
# Fleet root — for `from fleet_utils import ...`
sys.path.insert(0, str(Path(__file__).parent.parent))
```

This pattern is also canonical — every agent with fleet_utils adoption
uses it.

---

## The shim-container idiom — sub-namespace fields with dotted error paths

`require_number(container, field, ...)` raises `ValidationError(field, ...)`
on failure. The literal `field` argument flows through unchanged onto the
raised exception, so when a caller wants the error message and `e.field`
attribute to carry a **dotted path** (e.g., `"soil_data.carbon_percent"`
instead of bare `"carbon_percent"`), it must build a one-key container
keyed by that exact dotted string and pass the same string as `field`.

### Canonical worked example

From `evoterra-agent/src/validation.py` (carbon_percent, Night 28):

```python
# Validate soil_data.carbon_percent ∈ [0, 100] with a dotted error path
# so existing tests that pin `e.field == "soil_data.carbon_percent"`
# continue to pass after the migration from inline try/float.
if "carbon_percent" in soil_data:
    dotted = "soil_data.carbon_percent"
    clean_soil["carbon_percent"] = require_number(
        {dotted: soil_data["carbon_percent"]},  # one-key shim container
        dotted,                                  # same string as field arg
        min_value=0.0,
        max_value=100.0,
    )
```

The two `dotted` references are intentionally identical — the shim's
sole job is to make `container[field]` resolve to the value being
validated while preserving the parent-prefixed path on the raised
`ValidationError`. Agents that already have a flat top-level container
(`data["area_hectares"]`, `data["year_count"]`) call `require_number`
directly with no shim — the shim is only for nested fields where the
error-path naming convention is `parent.child`.

### When to reach for it

Use the shim-container idiom when:

1. The field being validated lives inside a nested dict (e.g., `soil_data`,
   `climate_inputs`, `pricing_metadata`).
2. Existing tests, dashboards, or downstream consumers expect the dotted
   path on `ValidationError.field` (changing it is a breaking API shift).
3. You're migrating an inline `try/float/range-check` block to
   `require_number` and want to preserve the prior error envelope exactly.

Use a **flat** call (no shim) when the validated field is a top-level key
on the input dict — the shim adds noise without value in that case.

### Why this idiom rather than a `field_prefix=` parameter

We considered adding a `field_prefix=` kwarg to `require_number` itself
(`require_number(soil_data, "carbon_percent", field_prefix="soil_data")`).
The shim approach was preferred because:

- **Zero primitive surface-area growth** — the canonical shape of
  `require_number(container, field, **bounds)` stays small. Every adopter
  reads the same five-arg signature instead of an optional sixth.
- **Prefix logic stays in the caller** — the dotted path is naming-convention,
  not validation logic. Keeping it caller-side means the primitive is
  agnostic to how agents structure their error namespaces.
- **The shim is two lines** — the cost of the idiom (one dict literal,
  one variable) is below the cost of a primitive parameter that must be
  documented, tested, and maintained.

### Adoption (as of 2026-04-28, Night 29)

| Agent | Field | Night |
| ----- | ----- | ----- |
| evoterra-agent | `soil_data.silt_fraction` | 27 |
| evoterra-agent | `soil_data.clay_fraction` | 27 |
| evoterra-agent | `soil_data.carbon_percent` | 28 |

Three adoption sites in two consecutive nights crossed the canonicalization
threshold per the promotion protocol. Future agents validating nested-dict
numeric fields should reach for this idiom rather than re-deriving it.

---

## Adoption Status (as of 2026-04-28, Night 29)

| Agent                         | Primitive                        | Status       | Night landed |
| ----------------------------- | -------------------------------- | ------------ | ------------ |
| carbon-bridge-agent           | `require_number` (origin)        | ADOPTED      | 18           |
| evoterra-agent                | `require_number` (area_hectares) | ADOPTED      | 20           |
| dscore-agent                  | `require_number`                 | ADOPTED      | 21           |
| sentinel-watch-agent          | `require_number` (wave 4)        | ADOPTED      | 22–23        |
| smartscale-agent              | `require_number`                 | ADOPTED      | 22           |
| evoterra-agent                | `require_number` (year_count)    | ADOPTED      | 22           |
| bioacoustic-agent             | fleet-interface tests            | PINNED       | 24           |
| carbon-bridge-agent           | fleet-interface tests            | PINNED       | 24           |
| sentinel-watch-agent          | fleet-interface tests            | PINNED       | 25           |
| evoterra-agent                | `require_number` (silt + clay via shim-container) | ADOPTED | 27 |
| evoterra-agent                | `require_number` (carbon_percent via shim-container) | ADOPTED | 28 |
| dscore-agent                  | `RangeNormalizer` (T/P/F/S)      | QUEUED       | —            |
| evoterra-agent                | `clamp_to_range` (soil fractions)| DEQUEUED ✗   | N26 (rejected — RAISE-not-CLAMP semantics; superseded by `require_number` migration N27/N28) |
| bounty-hunter-agent           | `RangeNormalizer` (fit-score)    | QUEUED       | —            |

`_AGENT_TEMPLATE/` carries a commented scaffold for the fleet-interface
test pattern (added Night 24) so new agents scaffold with the regression
fence documented.

---

## Adding a New Primitive

Promotion criteria (Nightkeeper protocol):

1. The same pattern appears **inline in ≥3 agents** with at most cosmetic
   variation.
2. The pattern is **stateless** or has simple, well-defined state.
3. The pattern has **no heavy dependency** (numpy is acceptable but
   optional; scipy / torch / pandas are not).
4. A Nightkeeper cross-pollination pass has flagged it at least twice
   before the promotion run.

Promotion steps:

1. Extract the pattern into a new file under `fleet_utils/` with
   docstrings documenting origin, invariants, and usage.
2. Add comprehensive tests under `fleet_utils/test_<module>.py`.
3. Re-export from `fleet_utils/__init__.py` and add to `__all__`.
4. Update this README's module table and adoption status.
5. Queue migrations agent-by-agent in the Nightkeeper log; do **not**
   migrate all callers in the same run — one agent per night keeps
   each change reviewable.

---

## Running tests

From fleet root:

```bash
python3 -m pytest fleet_utils/
```

Tests are isolated from agent test runs and do not require any agent's
`src/` on path.
