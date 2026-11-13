"""
Input validation for RegulatoryRadarAgent — transforms unchecked inputs into observable,
loggable validation events. Required for compliance advisory audit trail.

Cross-pollinated from dscore-agent validation pattern (Night 6 → Night 7).

Usage:
    from src.validation import validate_scan_input, ValidationError

    try:
        clean = validate_scan_input(raw_data)
    except ValidationError as e:
        return {"status": "error", "error_type": "ValidationError", ...}
"""

import logging
from typing import Any, Dict, List, Optional

# Bound at import time on purpose: the MCP gateway evicts every `src*`
# module between agent loads, so a call-time relative import here would
# resolve against another agent's `src` package (RG5, gateway G1).
from .applicability import ENTITY_FORMS, ENTITY_PROFILE_FIELDS, EXEMPTIONS

logger = logging.getLogger(__name__)

# Valid jurisdictions (must match Jurisdiction enum in core.py)
VALID_JURISDICTIONS = {
    "eu", "uk", "us", "california", "ca", "au", "jp", "sg", "global",
}
JURISDICTION_ALIASES = {
    "us-ca": "california",
    "ca-us": "california",
    # J1: other spellings of a covered jurisdiction. "ca" stays Canada.
    "usa": "us", "u.s.": "us", "u.s.a.": "us", "united states": "us",
    "united states of america": "us", "america": "us", "federal": "us",
    "european union": "eu", "europe": "eu",
    "united kingdom": "uk", "great britain": "uk", "britain": "uk", "gb": "uk",
    "england": "uk", "scotland": "uk", "wales": "uk", "northern ireland": "uk",
    "canada": "ca", "australia": "au", "japan": "jp", "singapore": "sg",
    "worldwide": "global", "international": "global", "world": "global",
}
# J2: places inside a covered jurisdiction. The scan answers for the covering
# jurisdiction and says so; rules made by the place itself are not in the
# dataset, and the response states that rather than implying coverage.
_EU_MEMBERS = (
    "austria", "belgium", "bulgaria", "croatia", "cyprus", "czechia",
    "czech republic", "denmark", "estonia", "finland", "france", "germany",
    "greece", "hungary", "ireland", "italy", "latvia", "lithuania",
    "luxembourg", "malta", "netherlands", "poland", "portugal", "romania",
    "slovakia", "slovenia", "spain", "sweden",
)
# Georgia is omitted: it is also a country outside every covered jurisdiction.
_US_STATES = (
    "alabama", "alaska", "arizona", "arkansas", "colorado", "connecticut",
    "delaware", "florida", "hawaii", "idaho", "illinois", "indiana", "iowa",
    "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts",
    "michigan", "minnesota", "mississippi", "missouri", "montana", "nebraska",
    "nevada", "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
)
JURISDICTION_WITHIN = {
    **{name: "eu" for name in _EU_MEMBERS},
    **{name: "us" for name in _US_STATES},
}
_WITHIN_NOTE = {
    "eu": ("read as the EU: EU-level rules apply in this member state; its "
           "national transposition and national-only rules are not in the dataset"),
    "us": ("read as the US: federal rules apply in this state; the state's own "
           "rules are not in the dataset (California is the one state covered)"),
}
SECTOR_ALIASES = {
    "tech": "technology", "software": "technology", "saas": "technology",
    "it": "technology", "information technology": "technology",
    "data centers": "technology", "data center": "technology",
    "finance": "financial_services", "financial": "financial_services",
    "financial services": "financial_services", "banking": "financial_services",
    "insurance": "financial_services", "asset management": "financial_services",
    "power": "energy", "utilities": "energy", "utility": "energy",
    "oil and gas": "energy", "oil & gas": "energy", "renewables": "energy",
    "industrial": "manufacturing", "industry": "manufacturing",
    "retail": "consumer_goods", "consumer goods": "consumer_goods",
    "farming": "agriculture", "timber": "forestry", "fishing": "fisheries",
}

# Valid sectors (must match Sector enum in core.py)
VALID_SECTORS = {
    "agriculture", "energy", "forestry", "fisheries",
    "manufacturing", "financial_services", "consumer_goods", "technology",
}

# Valid compliance levels
VALID_COMPLIANCE_LEVELS = {"compliant", "partial", "non_compliant", "not_applicable"}

# Valid regulatory standards
VALID_STANDARDS = {"TNFD", "CSRD", "EU Taxonomy", "SEC Climate", "ISSB", "GRI"}


class ValidationError(Exception):
    """Harness-compliant validation error with structured metadata."""

    def __init__(self, field: str, value: Any, constraint: str):
        self.field = field
        self.value = value
        self.constraint = constraint
        super().__init__(f"Field '{field}={value}' violates: {constraint}")


class ValidationWarning:
    """Represents a non-fatal validation issue (e.g. unrecognized value)."""

    def __init__(self, field: str, original: Any, adjusted: Any, reason: str):
        self.field = field
        self.original = original
        self.adjusted = adjusted
        self.reason = reason

    def __repr__(self) -> str:
        return f"ValidationWarning({self.field}: {self.original} → {self.adjusted}, {self.reason})"


def normalize_jurisdiction(value: Any) -> str:
    """Return the canonical jurisdiction value; ``ca`` remains Canada."""
    normalized = " ".join(str(value).strip().lower().split())
    normalized = JURISDICTION_ALIASES.get(normalized, normalized)
    return JURISDICTION_WITHIN.get(normalized, normalized)


def jurisdiction_reading(value: Any) -> Optional[Dict[str, str]]:
    """J2: how a place name was read, when it is not itself a covered jurisdiction."""
    given = " ".join(str(value).strip().lower().split())
    given = JURISDICTION_ALIASES.get(given, given)
    parent = JURISDICTION_WITHIN.get(given)
    if parent is None:
        return None
    return {"given": str(value).strip(), "read_as": parent,
            "note": _WITHIN_NOTE[parent]}


def normalize_sector(value: Any) -> str:
    """Return the canonical sector for a common synonym; unknown values pass through."""
    normalized = " ".join(str(value).strip().lower().replace("-", " ").split())
    normalized = SECTOR_ALIASES.get(normalized, normalized)
    return normalized.replace(" ", "_")


def validate_scan_input(data: dict) -> Dict[str, Any]:
    """
    Validate input for scan_regulations().

    Raises ValidationError for hard failures (invalid jurisdiction).
    Returns dict with '_validation_warnings' for soft issues.

    Invariants enforced:
      - jurisdiction must be a recognized value
      - sector, if provided, must be recognized
    """
    warnings: List[ValidationWarning] = []

    # Jurisdiction — required
    jurisdiction = data.get("jurisdiction", "")
    if not jurisdiction:
        raise ValidationError("jurisdiction", jurisdiction, "is required for regulatory scan")
    jurisdiction = normalize_jurisdiction(jurisdiction)
    if jurisdiction not in VALID_JURISDICTIONS:
        raise ValidationError(
            "jurisdiction", jurisdiction,
            f"must be one of: {sorted(VALID_JURISDICTIONS)}"
        )

    # Sector — optional but must be valid
    sector = data.get("sector")
    if sector:
        sector = normalize_sector(sector)
        if sector not in VALID_SECTORS:
            warnings.append(ValidationWarning(
                field="sector", original=sector, adjusted=sector,
                reason=f"Unrecognized sector; valid: {sorted(VALID_SECTORS)}"
            ))

    validated = {
        "jurisdiction": jurisdiction,
        "sector": sector,
        "query": data.get("query"),
        "_validation_warnings": warnings,
    }

    if warnings:
        for w in warnings:
            logger.warning(f"RegulatoryRadar validation: {w}")

    return validated


def _optional_revenue(data: Dict[str, Any], name: str):
    """A finite, non-negative revenue figure, or None when absent."""
    value = data.get(name)
    if value is None:
        return None
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or value != value or value in (float("inf"), float("-inf"))):
        raise ValidationError(name, value, "must be a finite number")
    if value < 0:
        raise ValidationError(name, value, "must be non-negative")
    return value


def _optional_entity_profile(profile):
    """entity_profile for applicability gates (A6); every field optional."""
    if profile is None:
        return None
    if not isinstance(profile, dict):
        raise ValidationError("entity_profile", type(profile).__name__,
                              "must be an object when provided")
    unknown = sorted(set(profile) - set(ENTITY_PROFILE_FIELDS))
    if unknown:
        raise ValidationError("entity_profile", unknown,
                              f"unsupported fields; allowed: {list(ENTITY_PROFILE_FIELDS)}")
    cleaned: Dict[str, Any] = {}
    for key, value in profile.items():
        if value is None:
            continue
        if key in ("formed_under_us_law", "does_business_in_california"):
            if not isinstance(value, bool):
                raise ValidationError(f"entity_profile.{key}", value,
                                      "must be true or false")
            cleaned[key] = value
        elif key == "entity_form":
            norm = str(value).strip().lower() if isinstance(value, str) else value
            if norm not in ENTITY_FORMS:
                raise ValidationError(f"entity_profile.{key}", value,
                                      f"must be one of: {list(ENTITY_FORMS)}")
            cleaned[key] = norm
        elif key == "exemption":
            norm = str(value).strip().lower() if isinstance(value, str) else value
            if norm not in EXEMPTIONS:
                raise ValidationError(f"entity_profile.{key}", value,
                                      f"must be one of: {list(EXEMPTIONS)}")
            cleaned[key] = norm
    return cleaned


def validate_compliance_assessment_input(data: dict) -> Dict[str, Any]:
    """
    Validate input for assess_compliance().

    Invariants:
      - company_name must be non-empty
      - jurisdiction must be valid
      - sector must be valid
    """
    warnings: List[ValidationWarning] = []

    # Company name — required
    company_name = data.get("company_name", "")
    if not company_name or not str(company_name).strip():
        raise ValidationError("company_name", company_name, "must be non-empty")

    # Jurisdiction — required
    jurisdiction = data.get("jurisdiction", "")
    if not jurisdiction:
        raise ValidationError("jurisdiction", jurisdiction, "is required")
    jurisdiction = normalize_jurisdiction(jurisdiction)
    if jurisdiction not in VALID_JURISDICTIONS:
        raise ValidationError(
            "jurisdiction", jurisdiction,
            f"must be one of: {sorted(VALID_JURISDICTIONS)}"
        )

    # Sector — required for assessment
    sector = data.get("sector", "")
    if not sector:
        raise ValidationError("sector", sector, "is required for compliance assessment")
    sector = normalize_sector(sector)
    if sector not in VALID_SECTORS:
        raise ValidationError(
            "sector", sector,
            f"must be one of: {sorted(VALID_SECTORS)}"
        )

    # Existing compliance data — optional, validate structure
    existing_compliance = data.get("existing_compliance", {})
    if existing_compliance and not isinstance(existing_compliance, dict):
        warnings.append(ValidationWarning(
            field="existing_compliance", original=type(existing_compliance).__name__,
            adjusted="{}",
            reason="Expected dict of regulation_id → compliance status; ignoring"
        ))
        existing_compliance = {}

    # Revenue and entity profile — optional; gate size- and entity-limited
    # obligations (A6). annual_revenue_usd is the most recent completed
    # fiscal year; prior_year_revenue_usd is the year before it.
    annual_revenue_usd = _optional_revenue(data, "annual_revenue_usd")
    prior_year_revenue_usd = _optional_revenue(data, "prior_year_revenue_usd")
    entity_profile = _optional_entity_profile(data.get("entity_profile"))

    validated = {
        "company_name": str(company_name).strip(),
        "jurisdiction": jurisdiction,
        "sector": sector,
        "existing_compliance": existing_compliance,
        "annual_revenue_usd": annual_revenue_usd,
        "prior_year_revenue_usd": prior_year_revenue_usd,
        "entity_profile": entity_profile,
        "_validation_warnings": warnings,
    }

    if warnings:
        for w in warnings:
            logger.warning(f"RegulatoryRadar compliance validation: {w}")

    return validated


# ---------------------------------------------------------------------------
# monitor_changes validation — Nightkeeper 2026-04-18
#
# MISSION.md §3 lists monitor_changes as a core value function (continuous T↓
# channel — the data-richness enabler). Core.py already has regulatory_forecast()
# and generate_alerts() as private methods; wiring them via a validated action
# surface closes the fleet-standard interface gap.
#
# Input schema (MISSION.md §5):
#   jurisdiction: str (required)
#   topics:       list[str] (optional — future enrichment signal)
#   active_projects: list[dict] (optional — project IDs to watch)
#   lookback_days: int (default 30, bounded [1, 365])
# ---------------------------------------------------------------------------

# Reasonable lookback bounds for monitor_changes (avoid 0/∞/negative)
_MIN_LOOKBACK_DAYS = 1
_MAX_LOOKBACK_DAYS = 365


def validate_monitor_changes_input(data: dict) -> Dict[str, Any]:
    """
    Validate input for monitor_changes().

    Invariants enforced:
      - jurisdiction must be a recognized value (required)
      - topics, if provided, must be a list of non-empty strings (warn on unknown)
      - active_projects, if provided, must be a list (items coerced to strings)
      - lookback_days ∈ [1, 365], defaults to 30
    """
    warnings: List[ValidationWarning] = []

    # Jurisdiction — required
    jurisdiction = data.get("jurisdiction", "")
    if not jurisdiction:
        raise ValidationError(
            "jurisdiction", jurisdiction,
            "is required for change monitoring"
        )
    jurisdiction = normalize_jurisdiction(jurisdiction)
    if jurisdiction not in VALID_JURISDICTIONS:
        raise ValidationError(
            "jurisdiction", jurisdiction,
            f"must be one of: {sorted(VALID_JURISDICTIONS)}"
        )

    # topics — optional list of strings
    topics_raw = data.get("topics")
    topics_clean: List[str] = []
    if topics_raw is not None:
        if not isinstance(topics_raw, list):
            raise ValidationError(
                "topics", topics_raw,
                "must be a list of topic strings (or None)"
            )
        for i, t in enumerate(topics_raw):
            if not isinstance(t, str):
                raise ValidationError(
                    f"topics[{i}]", t, "must be a string"
                )
            t_clean = t.strip()
            if not t_clean:
                raise ValidationError(
                    f"topics[{i}]", t, "must be non-empty"
                )
            topics_clean.append(t_clean)

    # active_projects — optional list
    projects_raw = data.get("active_projects")
    projects_clean: List[Any] = []
    if projects_raw is not None:
        if not isinstance(projects_raw, list):
            raise ValidationError(
                "active_projects", projects_raw,
                "must be a list of project identifiers or dicts (or None)"
            )
        for i, p in enumerate(projects_raw):
            if isinstance(p, dict):
                pid = p.get("project_id") or p.get("id")
                if not pid or not str(pid).strip():
                    warnings.append(ValidationWarning(
                        field=f"active_projects[{i}]",
                        original=p, adjusted=p,
                        reason="dict has no project_id/id field; passed through as-is",
                    ))
                projects_clean.append(p)
            elif isinstance(p, str):
                if not p.strip():
                    raise ValidationError(
                        f"active_projects[{i}]", p, "must be a non-empty string"
                    )
                projects_clean.append(p.strip())
            else:
                raise ValidationError(
                    f"active_projects[{i}]", p,
                    "must be a string project_id or dict"
                )

    # lookback_days — optional int, bounded
    lookback_raw = data.get("lookback_days", 30)
    if isinstance(lookback_raw, bool):
        raise ValidationError(
            "lookback_days", lookback_raw, "must be an integer, not bool"
        )
    try:
        lookback = int(lookback_raw)
        if float(lookback_raw) != lookback:
            raise ValidationError(
                "lookback_days", lookback_raw,
                "must be an integer (no fractional days)"
            )
    except (TypeError, ValueError):
        raise ValidationError(
            "lookback_days", lookback_raw, "must be an integer"
        )
    if lookback < _MIN_LOOKBACK_DAYS or lookback > _MAX_LOOKBACK_DAYS:
        raise ValidationError(
            "lookback_days", lookback,
            f"must be in [{_MIN_LOOKBACK_DAYS}, {_MAX_LOOKBACK_DAYS}]"
        )

    validated = {
        "jurisdiction": jurisdiction,
        "topics": topics_clean,
        "active_projects": projects_clean,
        "lookback_days": lookback,
        "_validation_warnings": warnings,
    }

    if warnings:
        for w in warnings:
            logger.warning(f"RegulatoryRadar monitor_changes validation: {w}")

    return validated


def validate_watch_changes_input(data: dict) -> Dict[str, Any]:
    """Validate a watch_changes poll.

    since is the cursor returned by the previous poll (0 = from the start of
    the log); max_age_hours bounds how stale the last sweep may be before
    this call refreshes it.
    """
    validated = validate_monitor_changes_input(data)
    since = data.get("since", 0)
    if isinstance(since, bool) or not isinstance(since, int) or since < 0:
        raise ValidationError(
            "since", since,
            "must be a non-negative integer: the cursor from your last poll, or 0")
    max_age = data.get("max_age_hours", 24)
    if isinstance(max_age, bool) or not isinstance(max_age, int) \
            or not 1 <= max_age <= 168:
        raise ValidationError(
            "max_age_hours", max_age, "must be an integer from 1 to 168")
    validated["since"] = since
    validated["max_age_hours"] = max_age
    return validated


def validate_evidence_pack_input(data: dict) -> Dict[str, Any]:
    """Validate an authoritative-source evidence-pack request."""
    validated = validate_monitor_changes_input(data)
    warnings = list(validated.get("_validation_warnings", []))

    source_ids_raw = data.get("source_ids")
    source_ids: List[str] = []
    if source_ids_raw is not None:
        if not isinstance(source_ids_raw, list):
            raise ValidationError(
                "source_ids", source_ids_raw,
                "must be a list of registry-owned source identifiers",
            )
        if len(source_ids_raw) > 12:
            raise ValidationError(
                "source_ids", len(source_ids_raw), "must contain at most 12 items"
            )
        for index, source_id in enumerate(source_ids_raw):
            if not isinstance(source_id, str) or not source_id.strip():
                raise ValidationError(
                    f"source_ids[{index}]", source_id,
                    "must be a non-empty string",
                )
            source_ids.append(source_id.strip())

    company_profile = data.get("company_profile") or {}
    if not isinstance(company_profile, dict):
        raise ValidationError(
            "company_profile", company_profile,
            "must be an object when provided",
        )
    allowed_profile_fields = {
        "company_name", "sector", "operating_jurisdictions",
        "annual_revenue_usd", "employee_count", "notes",
    }
    unknown_profile_fields = sorted(
        set(company_profile) - allowed_profile_fields
    )
    if unknown_profile_fields:
        raise ValidationError(
            "company_profile", unknown_profile_fields,
            f"unsupported fields; allowed: {sorted(allowed_profile_fields)}",
        )
    cleaned_profile: Dict[str, Any] = {}
    for field, value in company_profile.items():
        if field in {"annual_revenue_usd", "employee_count"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValidationError(field, value, "must be numeric")
            if value < 0:
                raise ValidationError(field, value, "must be non-negative")
            cleaned_profile[field] = value
        elif field == "operating_jurisdictions":
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                raise ValidationError(
                    field, value, "must be a list of non-empty strings"
                )
            cleaned_profile[field] = [item.strip() for item in value]
        else:
            if not isinstance(value, str):
                raise ValidationError(field, value, "must be a string")
            cleaned_profile[field] = value.strip()

    persist_snapshot = data.get("persist_snapshot", True)
    if not isinstance(persist_snapshot, bool):
        raise ValidationError(
            "persist_snapshot", persist_snapshot, "must be a boolean"
        )

    validated.update({
        "source_ids": source_ids,
        "company_profile": cleaned_profile,
        "persist_snapshot": persist_snapshot,
        "_validation_warnings": warnings,
    })
    return validated
