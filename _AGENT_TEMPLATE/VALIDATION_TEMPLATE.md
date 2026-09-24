# Fleet-Standard Validation Pattern

> Copy `src/validation.py` from this template into any new agent and adapt the per-action validators. This pattern is deployed across 26+ Viridis agents as of April 2026.

---

## Why Validation Matters

The Intelligence Bound theorem states: `dI/dt ≤ P·D/k_B·T·ln 2`. Garbage-in-garbage-out is a form of wasted power (P) — it generates entropy instead of intelligence. Validation is the trust barrier at every agent's entry point: it ensures only well-formed inputs reach the business logic, protecting the fleet's signal quality.

---

## The Contract

Every agent's `process()` function is protected by a single dispatcher:

```python
from src.validation import validate_process_input

def process(self, input_data: dict) -> dict:
    errors, warnings = validate_process_input(input_data)
    if errors:
        return {
            "status": "error",
            "message": "Validation failed",
            "errors": [e.to_dict() for e in errors],
            "warnings": [w.to_dict() for w in warnings],
            "timestamp": datetime.utcnow().isoformat(),
        }
    if warnings:
        logger.warning("Validation warnings: %s", [w.to_dict() for w in warnings])
    # ... business logic continues
```

---

## `src/validation.py` Structure

```python
"""
[Agent Name] — Input Validation
Fleet-standard ValidationError/ValidationWarning contract.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class ValidationError:
    field: str       # Dot-notation path: "data.species_list", "action", etc.
    message: str     # Human-readable explanation of what went wrong
    error_type: str = "validation_error"
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, str]:
        return {"field": self.field, "message": self.message,
                "error_type": self.error_type, "timestamp": self.timestamp}


@dataclass
class ValidationWarning:
    field: str
    message: str
    warning_type: str = "validation_warning"
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, str]:
        return {"field": self.field, "message": self.message,
                "warning_type": self.warning_type, "timestamp": self.timestamp}


# Known valid values for enum-like fields
VALID_ACTIONS = frozenset(["action_a", "action_b", "action_c"])


def _validate_action_a(data: dict):
    errors, warnings = [], []
    # Check required fields, types, bounds
    required_field = data.get("required_field")
    if not required_field or not isinstance(required_field, str):
        errors.append(ValidationError("data.required_field",
            "required_field is required and must be a non-empty string"))
    # Warnings for suspicious but not invalid inputs
    if isinstance(required_field, str) and len(required_field) > 1000:
        warnings.append(ValidationWarning("data.required_field",
            "required_field is very long; verify this is intentional"))
    return errors, warnings


def validate_process_input(input_data: Any):
    errors, warnings = [], []

    # 1. Type check
    if not isinstance(input_data, dict):
        errors.append(ValidationError("input", "input_data must be a dict"))
        return errors, warnings

    # 2. Action check
    action = input_data.get("action", "")
    if not isinstance(action, str) or not action.strip():
        errors.append(ValidationError("action", "action is required and must be a non-empty string"))
        return errors, warnings
    if action not in VALID_ACTIONS:
        errors.append(ValidationError("action",
            f"Unknown action '{action}'; valid: {sorted(VALID_ACTIONS)}"))
        return errors, warnings

    # 3. Data check
    data = input_data.get("data", {})
    if not isinstance(data, dict):
        errors.append(ValidationError("data", "data must be a dict"))
        return errors, warnings

    # 4. Per-action dispatch
    if action == "action_a":
        a_errors, a_warnings = _validate_action_a(data)
        errors.extend(a_errors)
        warnings.extend(a_warnings)

    return errors, warnings
```

---

## Rules

| Rule | Detail |
|------|--------|
| **Errors block execution** | Any `ValidationError` means `process()` returns immediately with `status: error` |
| **Warnings are advisory** | `ValidationWarning` is logged but does not block execution |
| **Field names use dot-notation** | `"data.species_list"`, `"data.abundances[0]"` — locates the problem precisely |
| **Messages are human-readable** | Include the invalid value and the constraint: `"time_horizon_years must be an integer between 1 and 100"` |
| **Enum fields use frozensets** | Define `VALID_ACTIONS`, `VALID_TYPES`, etc. as module-level `frozenset` constants |
| **Bounds on numbers** | Always validate: type (int vs float), min, max, special cases (zero, negative) |
| **List fields** | Check: is list, non-empty (if required), element types, max length |
| **Optional fields** | Only validate if present (`if field is not None: ...`) |
| **Never modify MISSION.md** | Validation is implementation; MISSION.md is constitutional identity |

---

## Testing Pattern

Every `validation.py` ships with inline tests runnable as `python validation.py`:

```python
if __name__ == "__main__":
    import sys
    results = []

    def check(name, condition):
        print(f"  [{'PASS' if condition else 'FAIL'}] {name}")
        results.append(condition)

    # Test 1: non-dict input
    e, _ = validate_process_input("not a dict")
    check("non-dict input rejected", len(e) == 1 and e[0].field == "input")

    # Test 2: unknown action
    e, _ = validate_process_input({"action": "unknown"})
    check("unknown action rejected", any(err.field == "action" for err in e))

    # Test 3: valid input passes
    e, _ = validate_process_input({"action": "action_a", "data": {"required_field": "hello"}})
    check("valid input passes", len(e) == 0)

    passed = sum(results)
    print(f"\nResults: {passed}/{len(results)} passed")
    if passed < len(results):
        sys.exit(1)
```

Syntax-check all files with:
```bash
python3 -c "import ast; ast.parse(open('src/validation.py').read()); print('OK')"
```

---

## Error Response Shape

```json
{
  "status": "error",
  "message": "Validation failed",
  "errors": [
    {
      "field": "data.abundances",
      "message": "species_list and abundances must have equal length (got 3 vs 2)",
      "error_type": "validation_error",
      "timestamp": "2026-04-14T03:00:00.000000"
    }
  ],
  "warnings": [],
  "timestamp": "2026-04-14T03:00:00.000000"
}
```

---

*Added by Nightkeeper 2026-04-14 — standardizes fleet-wide validation onboarding.*
