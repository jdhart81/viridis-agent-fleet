"""
Wavefunction Search Agent — Input Validation
Fleet-standard ValidationError/ValidationWarning contract.

Validates process() inputs for the INTAKE → COLLAPSE → MATCH → ROUTE pipeline.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Fleet-standard error / warning types
# ---------------------------------------------------------------------------

@dataclass
class ValidationError:
    field: str
    message: str
    error_type: str = "validation_error"
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, str]:
        return {
            "field": self.field,
            "message": self.message,
            "error_type": self.error_type,
            "timestamp": self.timestamp,
        }


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
        return {
            "field": self.field,
            "message": self.message,
            "warning_type": self.warning_type,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Known constants
# ---------------------------------------------------------------------------

VALID_STAGES = frozenset(["intake", "collapse", "find_matches"])

VALID_DIALOGUE_ROLES = frozenset(["user", "assistant", "system"])

# Reasonable stake bounds for wavefunction collapse
MIN_STAKE = 0.0
MAX_STAKE = 1_000_000.0


# ---------------------------------------------------------------------------
# Per-stage validators
# ---------------------------------------------------------------------------

def _validate_intake(input_data: dict) -> tuple:
    errors: List[ValidationError] = []
    warnings: List[ValidationWarning] = []

    user_id = input_data.get("user_id")
    if not user_id or not isinstance(user_id, str):
        errors.append(ValidationError("user_id", "user_id is required and must be a non-empty string"))
    elif len(user_id) > 256:
        errors.append(ValidationError("user_id", f"user_id too long ({len(user_id)} chars); max 256"))

    dialogue = input_data.get("dialogue", [])
    if not isinstance(dialogue, list):
        errors.append(ValidationError("dialogue", "dialogue must be a list of message dicts"))
    else:
        for i, msg in enumerate(dialogue):
            if not isinstance(msg, dict):
                errors.append(ValidationError(f"dialogue[{i}]",
                    "Each dialogue entry must be a dict with 'role' and 'content'"))
                continue
            if "role" not in msg:
                errors.append(ValidationError(f"dialogue[{i}].role", "role is required"))
            elif msg["role"] not in VALID_DIALOGUE_ROLES:
                warnings.append(ValidationWarning(f"dialogue[{i}].role",
                    f"Unknown role '{msg['role']}'; expected one of {sorted(VALID_DIALOGUE_ROLES)}"))
            if "content" not in msg:
                errors.append(ValidationError(f"dialogue[{i}].content", "content is required"))
            elif not isinstance(msg["content"], str):
                errors.append(ValidationError(f"dialogue[{i}].content", "content must be a string"))

    if isinstance(dialogue, list) and len(dialogue) == 0:
        warnings.append(ValidationWarning("dialogue",
            "Empty dialogue provided; intention detection will produce minimal signal"))

    if isinstance(dialogue, list) and len(dialogue) > 100:
        warnings.append(ValidationWarning("dialogue",
            f"Very long dialogue ({len(dialogue)} turns); may slow intention extraction"))

    return errors, warnings


def _validate_collapse(input_data: dict) -> tuple:
    errors: List[ValidationError] = []
    warnings: List[ValidationWarning] = []

    user_id = input_data.get("user_id")
    if not user_id or not isinstance(user_id, str):
        errors.append(ValidationError("user_id", "user_id is required and must be a non-empty string"))
    elif len(user_id) > 256:
        errors.append(ValidationError("user_id", f"user_id too long ({len(user_id)} chars); max 256"))

    stake_amount = input_data.get("stake_amount", 100.0)
    if not isinstance(stake_amount, (int, float)):
        errors.append(ValidationError("stake_amount", "stake_amount must be a number"))
    elif stake_amount < MIN_STAKE:
        errors.append(ValidationError("stake_amount",
            f"stake_amount must be non-negative (got {stake_amount})"))
    elif stake_amount > MAX_STAKE:
        errors.append(ValidationError("stake_amount",
            f"stake_amount {stake_amount} exceeds maximum {MAX_STAKE}"))

    if isinstance(stake_amount, (int, float)) and stake_amount == 0.0:
        warnings.append(ValidationWarning("stake_amount",
            "stake_amount is 0.0; zero-stake collapse provides minimal commitment signal"))

    return errors, warnings


def _validate_find_matches(input_data: dict) -> tuple:
    errors: List[ValidationError] = []
    warnings: List[ValidationWarning] = []

    user_id = input_data.get("user_id")
    if not user_id or not isinstance(user_id, str):
        errors.append(ValidationError("user_id", "user_id is required and must be a non-empty string"))
    elif len(user_id) > 256:
        errors.append(ValidationError("user_id", f"user_id too long ({len(user_id)} chars); max 256"))

    return errors, warnings


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

def validate_process_input(input_data: Any) -> tuple:
    """
    Validate process() input for wavefunction-search-agent.

    Returns (errors, warnings). If errors is non-empty, reject the request.
    Warnings are advisory and do not block execution.

    Invariants:
    - input_data must be a dict
    - 'stage' must be one of VALID_STAGES (defaults to 'find_matches' if omitted)
    - 'user_id' is required for all stages
    - Stage-specific field constraints apply per-stage
    """
    errors: List[ValidationError] = []
    warnings: List[ValidationWarning] = []

    if not isinstance(input_data, dict):
        errors.append(ValidationError("input", "input_data must be a dict"))
        return errors, warnings

    stage = input_data.get("stage", "find_matches")
    if not isinstance(stage, str):
        errors.append(ValidationError("stage", "stage must be a string"))
        return errors, warnings

    if stage not in VALID_STAGES:
        errors.append(ValidationError("stage",
            f"Unknown stage '{stage}'; valid: {sorted(VALID_STAGES)}"))
        return errors, warnings

    if stage == "intake":
        a_errors, a_warnings = _validate_intake(input_data)
    elif stage == "collapse":
        a_errors, a_warnings = _validate_collapse(input_data)
    elif stage == "find_matches":
        a_errors, a_warnings = _validate_find_matches(input_data)
    else:
        a_errors, a_warnings = [], []

    errors.extend(a_errors)
    warnings.extend(a_warnings)
    return errors, warnings


# ---------------------------------------------------------------------------
# Inline tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    PASS = "\033[92mPASS\033[0m"
    FAIL = "\033[91mFAIL\033[0m"
    results = []

    def check(name: str, condition: bool):
        tag = PASS if condition else FAIL
        print(f"  [{tag}] {name}")
        results.append(condition)

    print("\n=== wavefunction-search-agent validation tests ===\n")

    # --- Global ---
    print("Global:")
    e, _ = validate_process_input("not a dict")
    check("non-dict input rejected", len(e) == 1 and e[0].field == "input")

    e, _ = validate_process_input({"stage": 123})
    check("non-string stage rejected", len(e) > 0)

    e, _ = validate_process_input({"stage": "unknown_stage"})
    check("unknown stage rejected", any(err.field == "stage" for err in e))

    # --- intake ---
    print("\nintake:")
    e, _ = validate_process_input({
        "stage": "intake",
        "user_id": "user_42",
        "dialogue": [
            {"role": "user", "content": "I want to help fight climate change"},
            {"role": "assistant", "content": "Tell me more about your motivation"}
        ]
    })
    check("valid intake passes", len(e) == 0)

    e, _ = validate_process_input({"stage": "intake"})
    check("missing user_id in intake rejected", any("user_id" in err.field for err in e))

    e, _ = validate_process_input({"stage": "intake", "user_id": "u1", "dialogue": "not_a_list"})
    check("non-list dialogue rejected", any("dialogue" in err.field for err in e))

    e, _ = validate_process_input({"stage": "intake", "user_id": "u1",
        "dialogue": [{"role": "user"}]})  # missing content
    check("dialogue entry missing content rejected", any("content" in err.field for err in e))

    _, w = validate_process_input({"stage": "intake", "user_id": "u1", "dialogue": []})
    check("empty dialogue generates warning", len(w) > 0)

    _, w = validate_process_input({"stage": "intake", "user_id": "u1",
        "dialogue": [{"role": "unknown_role", "content": "hello"}]})
    check("unknown dialogue role generates warning", len(w) > 0)

    e, _ = validate_process_input({"stage": "intake", "user_id": "x" * 257, "dialogue": []})
    check("user_id too long rejected", any("user_id" in err.field for err in e))

    # --- collapse ---
    print("\ncollapse:")
    e, _ = validate_process_input({
        "stage": "collapse",
        "user_id": "user_42",
        "stake_amount": 500.0
    })
    check("valid collapse passes", len(e) == 0)

    e, _ = validate_process_input({"stage": "collapse"})
    check("missing user_id in collapse rejected", any("user_id" in err.field for err in e))

    e, _ = validate_process_input({"stage": "collapse", "user_id": "u1", "stake_amount": -10})
    check("negative stake_amount rejected", any("stake_amount" in err.field for err in e))

    e, _ = validate_process_input({"stage": "collapse", "user_id": "u1", "stake_amount": 2_000_000})
    check("stake_amount exceeding max rejected", any("stake_amount" in err.field for err in e))

    _, w = validate_process_input({"stage": "collapse", "user_id": "u1", "stake_amount": 0.0})
    check("zero stake generates warning", len(w) > 0)

    e, _ = validate_process_input({"stage": "collapse", "user_id": "u1", "stake_amount": "lots"})
    check("non-numeric stake rejected", any("stake_amount" in err.field for err in e))

    # --- find_matches ---
    print("\nfind_matches:")
    e, _ = validate_process_input({"stage": "find_matches", "user_id": "user_42"})
    check("valid find_matches passes", len(e) == 0)

    e, _ = validate_process_input({"stage": "find_matches"})
    check("missing user_id in find_matches rejected", any("user_id" in err.field for err in e))

    # defaults to find_matches if stage omitted
    e, _ = validate_process_input({"user_id": "user_42"})
    check("no stage defaults to find_matches (valid)", len(e) == 0)

    # --- Summary ---
    passed = sum(results)
    total = len(results)
    print(f"\n{'='*40}")
    print(f"Results: {passed}/{total} passed")
    if passed < total:
        sys.exit(1)
