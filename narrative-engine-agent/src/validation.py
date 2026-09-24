"""
Input validation for NarrativeEngineAgent — guards the translate() entry point
against malformed audience types, unrecognized formats, and empty agent outputs.

Cross-pollinated from fleet validation pattern (Nightkeeper Night 11).

Usage:
    from src.validation import validate_translate_input, ValidationError

    try:
        clean = validate_translate_input(raw_data)
    except ValidationError as e:
        return {"status": "error", "error_type": "ValidationError", ...}
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Valid audience types — must match AudienceType enum values in core.py
VALID_AUDIENCE_TYPES = {
    "institutional_investor", "retail_investor", "policymaker", "regulator",
    "scientist", "journalist", "grant_funder", "board_member", "general_public",
}

# Valid narrative formats — must match NarrativeFormat enum values in core.py
VALID_FORMAT_TYPES = {
    "investor_deck", "policy_brief", "grant_proposal", "press_release",
    "executive_summary", "academic_paper", "newsletter",
}

# Recommended (but not required) top-level keys in agent_output for quality signal
KNOWN_OUTPUT_KEYS = {
    "biodiversity_score", "d_score", "carbon_credits", "revenue", "risk_score",
    "temperature_delta", "ecosystem_type", "site_name", "project_id",
    "claim_value", "claim_unit", "valuation", "findings", "summary",
    "metrics", "data", "results", "verification_status",
}

# Valid actions for process()-routed calls (fleet standard pattern)
VALID_ACTIONS = {"translate", "describe", "health"}


class ValidationError(ValueError):
    """Harness-compliant validation error with structured metadata."""

    def __init__(self, field: str, value: Any, constraint: str):
        self.field = field
        self.value = value
        self.constraint = constraint
        super().__init__(f"Field '{field}={value}' violates: {constraint}")


class ValidationWarning:
    """Non-fatal validation issue (unrecognized value with fallback)."""

    def __init__(self, field: str, original: Any, adjusted: Any, reason: str):
        self.field = field
        self.original = original
        self.adjusted = adjusted
        self.reason = reason

    def __repr__(self) -> str:
        return f"ValidationWarning({self.field}: {self.original!r} → {self.adjusted!r}, {self.reason})"


def validate_translate_input(data: dict) -> Dict[str, Any]:
    """
    Validate input for the translate() / "translate" action.

    Invariants:
      - agent_output must be a non-empty dict
      - audience_type must be one of VALID_AUDIENCE_TYPES (case-insensitive)
      - format_type must be one of VALID_FORMAT_TYPES (case-insensitive)
      - key_message, if present, must be a non-empty string
      - agent_output with zero recognized keys emits a ValidationWarning

    Returns:
        Cleaned dict ready for NarrativeEngineCore.translate()
    """
    warnings: List[ValidationWarning] = []
    out: Dict[str, Any] = {}

    # --- agent_output ---
    agent_output = data.get("agent_output")
    if agent_output is None:
        raise ValidationError("agent_output", None, "required field; must be a dict of agent data")
    if not isinstance(agent_output, dict):
        raise ValidationError(
            "agent_output", type(agent_output).__name__,
            "must be a dict (e.g. output from viridis-science-agent, carbon-bridge-agent, etc.)"
        )
    if len(agent_output) == 0:
        raise ValidationError("agent_output", {}, "must be non-empty; pass at least one data field")
    recognized = set(str(k).lower() for k in agent_output) & KNOWN_OUTPUT_KEYS
    if not recognized:
        w = ValidationWarning(
            "agent_output", list(agent_output.keys())[:5], "no recognized keys",
            f"None of the top-level keys are in the known set {sorted(KNOWN_OUTPUT_KEYS)[:8]}...; "
            "narrative quality may be degraded"
        )
        warnings.append(w)
        logger.warning(f"NarrativeEngine translate validation: {w}")
    out["agent_output"] = agent_output

    # --- audience_type ---
    audience_type = data.get("audience_type")
    if audience_type is None:
        raise ValidationError("audience_type", None, f"required; must be one of {sorted(VALID_AUDIENCE_TYPES)}")
    audience_type = str(audience_type).strip().lower()
    if audience_type not in VALID_AUDIENCE_TYPES:
        raise ValidationError(
            "audience_type", audience_type,
            f"unrecognized audience; valid values: {sorted(VALID_AUDIENCE_TYPES)}"
        )
    out["audience_type"] = audience_type

    # --- format_type ---
    format_type = data.get("format_type")
    if format_type is None:
        raise ValidationError("format_type", None, f"required; must be one of {sorted(VALID_FORMAT_TYPES)}")
    format_type = str(format_type).strip().lower()
    if format_type not in VALID_FORMAT_TYPES:
        raise ValidationError(
            "format_type", format_type,
            f"unrecognized format; valid values: {sorted(VALID_FORMAT_TYPES)}"
        )
    out["format_type"] = format_type

    # --- key_message (optional) ---
    key_message = data.get("key_message")
    if key_message is not None:
        key_message = str(key_message).strip()
        if not key_message:
            raise ValidationError(
                "key_message", "", "if provided, must be a non-empty string"
            )
        if len(key_message) > 2000:
            w = ValidationWarning(
                "key_message", f"{len(key_message)} chars", "2000 chars",
                "key_message exceeds 2000 characters; narrative engines perform best with concise signals"
            )
            warnings.append(w)
            logger.warning(f"NarrativeEngine translate validation: {w}")
    out["key_message"] = key_message

    # Pass through any extra keys (e.g. "action") for router compatibility
    for k, v in data.items():
        if k not in out:
            out[k] = v

    return out


def validate_process_input(data: dict) -> Dict[str, Any]:
    """
    Validate top-level input for the fleet-standard process() router.

    Invariants:
      - action must be one of VALID_ACTIONS
      - For action="translate": delegates to validate_translate_input()
    """
    action = str(data.get("action", "")).strip().lower()
    if not action:
        raise ValidationError("action", "", f"required; must be one of {sorted(VALID_ACTIONS)}")
    if action not in VALID_ACTIONS:
        raise ValidationError(
            "action", action,
            f"unrecognized action; valid values: {sorted(VALID_ACTIONS)}"
        )
    if action == "translate":
        return validate_translate_input(data)
    return dict(data)


# ---------------------------------------------------------------------------
# Inline self-tests (run with: python3 -m src.validation)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    passed = 0
    failed = 0

    def check(label: str, fn, expect_error: bool = False):
        global passed, failed
        try:
            result = fn()
            if expect_error:
                print(f"  FAIL [{label}] expected ValidationError but got: {result}")
                failed += 1
            else:
                print(f"  PASS [{label}]")
                passed += 1
        except ValidationError as e:
            if expect_error:
                print(f"  PASS [{label}] → ValidationError({e.field}): {e.constraint[:60]}")
                passed += 1
            else:
                print(f"  FAIL [{label}] unexpected ValidationError: {e}")
                failed += 1
        except Exception as e:
            print(f"  FAIL [{label}] unexpected exception: {e}")
            failed += 1

    sample_output = {"d_score": 0.72, "site_name": "Amazon Basin Site 7", "carbon_credits": 1200}

    print("=== validate_translate_input ===")
    check("valid grant_funder + grant_proposal",
          lambda: validate_translate_input({
              "agent_output": sample_output,
              "audience_type": "grant_funder",
              "format_type": "grant_proposal",
          }))
    check("case-insensitive audience/format",
          lambda: validate_translate_input({
              "agent_output": sample_output,
              "audience_type": "POLICYMAKER",
              "format_type": "POLICY_BRIEF",
          }))
    check("with key_message",
          lambda: validate_translate_input({
              "agent_output": sample_output,
              "audience_type": "institutional_investor",
              "format_type": "investor_deck",
              "key_message": "Forest restoration yields 3.2x IRR over 10 years.",
          }))
    check("missing agent_output → error",
          lambda: validate_translate_input({
              "audience_type": "scientist",
              "format_type": "academic_paper",
          }), expect_error=True)
    check("empty agent_output → error",
          lambda: validate_translate_input({
              "agent_output": {},
              "audience_type": "journalist",
              "format_type": "press_release",
          }), expect_error=True)
    check("bad audience_type → error",
          lambda: validate_translate_input({
              "agent_output": sample_output,
              "audience_type": "alien_species",
              "format_type": "press_release",
          }), expect_error=True)
    check("bad format_type → error",
          lambda: validate_translate_input({
              "agent_output": sample_output,
              "audience_type": "general_public",
              "format_type": "comic_book",
          }), expect_error=True)
    check("empty key_message → error",
          lambda: validate_translate_input({
              "agent_output": sample_output,
              "audience_type": "journalist",
              "format_type": "press_release",
              "key_message": "   ",
          }), expect_error=True)
    check("unknown agent_output keys → warning (not error)",
          lambda: validate_translate_input({
              "agent_output": {"foo": 1, "bar": 2},
              "audience_type": "board_member",
              "format_type": "executive_summary",
          }))

    print("\n=== validate_process_input ===")
    check("translate action routes correctly",
          lambda: validate_process_input({
              "action": "translate",
              "agent_output": sample_output,
              "audience_type": "grant_funder",
              "format_type": "grant_proposal",
          }))
    check("missing action → error",
          lambda: validate_process_input({}), expect_error=True)
    check("invalid action → error",
          lambda: validate_process_input({"action": "manipulate"}), expect_error=True)

    print(f"\nResult: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
