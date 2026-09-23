"""
Tests for RegulatoryRadar input validation module.

Covers both happy-path (valid input) and error-path (ValidationError) for:
  - validate_scan_input
  - validate_compliance_assessment_input

Nightkeeper Night 9: validation test coverage cross-pollination.
"""

import pytest
import sys
import os

# Add agent root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.validation import (
    validate_scan_input,
    validate_compliance_assessment_input,
    validate_monitor_changes_input,
    ValidationError,
    ValidationWarning,
    VALID_JURISDICTIONS,
    VALID_SECTORS,
)


# ─── validate_scan_input ─────────────────────────────────────────────────────

class TestScanValidation:
    """Tests for regulatory scan input validation."""

    def test_valid_input(self):
        """Happy path: valid jurisdiction, no warnings."""
        result = validate_scan_input({"jurisdiction": "eu"})
        assert result["jurisdiction"] == "eu"
        assert result["_validation_warnings"] == []

    def test_jurisdiction_normalized_lowercase(self):
        """Jurisdiction is normalized to lowercase."""
        result = validate_scan_input({"jurisdiction": "EU"})
        assert result["jurisdiction"] == "eu"

    def test_jurisdiction_stripped(self):
        """Whitespace is stripped from jurisdiction."""
        result = validate_scan_input({"jurisdiction": "  us  "})
        assert result["jurisdiction"] == "us"

    @pytest.mark.parametrize("supplied", [
        "california", "California", "CALIFORNIA", "us-ca", "US-CA", "ca-us",
    ])
    def test_california_aliases_normalize_to_canonical(self, supplied):
        result = validate_scan_input({"jurisdiction": supplied})
        assert result["jurisdiction"] == "california"

    def test_ca_remains_canada(self):
        result = validate_scan_input({"jurisdiction": "CA"})
        assert result["jurisdiction"] == "ca"

    def test_missing_jurisdiction_raises(self):
        """Missing jurisdiction raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_scan_input({})
        assert exc_info.value.field == "jurisdiction"

    def test_empty_jurisdiction_raises(self):
        """Empty jurisdiction raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_scan_input({"jurisdiction": ""})
        assert exc_info.value.field == "jurisdiction"

    def test_invalid_jurisdiction_raises(self):
        """Unrecognized jurisdiction raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_scan_input({"jurisdiction": "mars"})
        assert exc_info.value.field == "jurisdiction"

    def test_all_valid_jurisdictions(self):
        """All known jurisdictions are accepted."""
        for jur in VALID_JURISDICTIONS:
            result = validate_scan_input({"jurisdiction": jur})
            assert result["jurisdiction"] == jur

    def test_valid_sector_no_warning(self):
        """Valid sector produces no warning."""
        result = validate_scan_input({
            "jurisdiction": "eu", "sector": "forestry"
        })
        assert result["sector"] == "forestry"
        sector_warnings = [w for w in result["_validation_warnings"]
                           if w.field == "sector"]
        assert len(sector_warnings) == 0

    def test_unrecognized_sector_warns(self):
        """Unrecognized sector produces warning, not error."""
        result = validate_scan_input({
            "jurisdiction": "eu", "sector": "space_mining"
        })
        warnings = result["_validation_warnings"]
        assert len(warnings) >= 1
        assert any(w.field == "sector" for w in warnings)

    def test_query_passed_through(self):
        """Query field is passed through to validated output."""
        result = validate_scan_input({
            "jurisdiction": "us", "query": "deforestation reporting"
        })
        assert result["query"] == "deforestation reporting"

    def test_sector_normalized_lowercase(self):
        """Sector is normalized to lowercase."""
        result = validate_scan_input({
            "jurisdiction": "eu", "sector": "Forestry"
        })
        assert result["sector"] == "forestry"


# ─── validate_compliance_assessment_input ─────────────────────────────────────

class TestComplianceAssessmentValidation:
    """Tests for compliance assessment input validation."""

    def test_valid_input(self):
        """Happy path: all required fields valid."""
        result = validate_compliance_assessment_input({
            "company_name": "Viridis LLC",
            "jurisdiction": "eu",
            "sector": "forestry",
        })
        assert result["company_name"] == "Viridis LLC"
        assert result["jurisdiction"] == "eu"
        assert result["sector"] == "forestry"
        assert result["_validation_warnings"] == []

    def test_missing_company_name_raises(self):
        """Missing company_name raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_compliance_assessment_input({
                "jurisdiction": "eu", "sector": "forestry"
            })
        assert exc_info.value.field == "company_name"

    def test_empty_company_name_raises(self):
        """Empty company_name raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_compliance_assessment_input({
                "company_name": "", "jurisdiction": "eu", "sector": "forestry"
            })
        assert exc_info.value.field == "company_name"

    def test_missing_jurisdiction_raises(self):
        """Missing jurisdiction raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_compliance_assessment_input({
                "company_name": "Viridis LLC", "sector": "forestry"
            })
        assert exc_info.value.field == "jurisdiction"

    def test_invalid_jurisdiction_raises(self):
        """Invalid jurisdiction raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_compliance_assessment_input({
                "company_name": "Viridis LLC",
                "jurisdiction": "mars",
                "sector": "forestry",
            })
        assert exc_info.value.field == "jurisdiction"

    def test_missing_sector_raises(self):
        """Missing sector raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_compliance_assessment_input({
                "company_name": "Viridis LLC", "jurisdiction": "eu"
            })
        assert exc_info.value.field == "sector"

    def test_invalid_sector_raises(self):
        """Invalid sector raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_compliance_assessment_input({
                "company_name": "Viridis LLC",
                "jurisdiction": "eu",
                "sector": "space_mining",
            })
        assert exc_info.value.field == "sector"

    def test_all_valid_sectors(self):
        """All known sectors are accepted."""
        for sec in VALID_SECTORS:
            result = validate_compliance_assessment_input({
                "company_name": "Test Co",
                "jurisdiction": "eu",
                "sector": sec,
            })
            assert result["sector"] == sec

    def test_existing_compliance_dict_accepted(self):
        """Valid existing_compliance dict is accepted."""
        result = validate_compliance_assessment_input({
            "company_name": "Viridis LLC",
            "jurisdiction": "eu",
            "sector": "forestry",
            "existing_compliance": {"TNFD": "compliant"},
        })
        assert result["existing_compliance"] == {"TNFD": "compliant"}

    def test_existing_compliance_non_dict_warns(self):
        """Non-dict existing_compliance produces warning and defaults to {}."""
        result = validate_compliance_assessment_input({
            "company_name": "Viridis LLC",
            "jurisdiction": "eu",
            "sector": "forestry",
            "existing_compliance": "not_a_dict",
        })
        assert result["existing_compliance"] == {}
        warnings = result["_validation_warnings"]
        assert any(w.field == "existing_compliance" for w in warnings)

    def test_company_name_stripped(self):
        """company_name whitespace is stripped."""
        result = validate_compliance_assessment_input({
            "company_name": "  Viridis LLC  ",
            "jurisdiction": "eu",
            "sector": "forestry",
        })
        assert result["company_name"] == "Viridis LLC"

    def test_jurisdiction_normalized(self):
        """Jurisdiction is normalized to lowercase."""
        result = validate_compliance_assessment_input({
            "company_name": "Test Co",
            "jurisdiction": "  EU  ",
            "sector": "forestry",
        })
        assert result["jurisdiction"] == "eu"

    def test_california_alias_normalized(self):
        result = validate_compliance_assessment_input({
            "company_name": "Test Co",
            "jurisdiction": "US-CA",
            "sector": "energy",
        })
        assert result["jurisdiction"] == "california"


# ─── validate_monitor_changes_input ───────────────────────────────────────────

class TestMonitorChangesValidation:
    """Tests for monitor_changes input validation (MISSION.md §3 value function)."""

    def test_valid_minimal_input(self):
        """Happy path: jurisdiction only, defaults applied."""
        result = validate_monitor_changes_input({"jurisdiction": "eu"})
        assert result["jurisdiction"] == "eu"
        assert result["lookback_days"] == 30  # default
        assert result["topics"] == []
        assert result["active_projects"] == []
        assert result["_validation_warnings"] == []

    def test_valid_full_input(self):
        result = validate_monitor_changes_input({
            "jurisdiction": "us",
            "topics": ["biodiversity", "carbon"],
            "active_projects": ["PROJ-001", "PROJ-002"],
            "lookback_days": 60,
        })
        assert result["jurisdiction"] == "us"
        assert result["topics"] == ["biodiversity", "carbon"]
        assert result["active_projects"] == ["PROJ-001", "PROJ-002"]
        assert result["lookback_days"] == 60

    def test_missing_jurisdiction_raises(self):
        with pytest.raises(ValidationError) as exc:
            validate_monitor_changes_input({})
        assert exc.value.field == "jurisdiction"

    def test_empty_jurisdiction_raises(self):
        with pytest.raises(ValidationError):
            validate_monitor_changes_input({"jurisdiction": ""})

    def test_invalid_jurisdiction_raises(self):
        with pytest.raises(ValidationError):
            validate_monitor_changes_input({"jurisdiction": "mars"})

    def test_jurisdiction_normalized(self):
        result = validate_monitor_changes_input({"jurisdiction": "  UK  "})
        assert result["jurisdiction"] == "uk"

    def test_topics_non_list_raises(self):
        with pytest.raises(ValidationError) as exc:
            validate_monitor_changes_input({
                "jurisdiction": "eu",
                "topics": "biodiversity",  # string not list
            })
        assert exc.value.field == "topics"

    def test_topics_non_string_element_raises(self):
        with pytest.raises(ValidationError) as exc:
            validate_monitor_changes_input({
                "jurisdiction": "eu",
                "topics": ["biodiversity", 42],
            })
        assert "topics[1]" in exc.value.field

    def test_topics_empty_string_raises(self):
        with pytest.raises(ValidationError):
            validate_monitor_changes_input({
                "jurisdiction": "eu",
                "topics": ["biodiversity", ""],
            })

    def test_topics_stripped(self):
        result = validate_monitor_changes_input({
            "jurisdiction": "eu",
            "topics": ["  biodiversity  ", " carbon "],
        })
        assert result["topics"] == ["biodiversity", "carbon"]

    def test_topics_none_becomes_empty_list(self):
        result = validate_monitor_changes_input({
            "jurisdiction": "eu",
            "topics": None,
        })
        assert result["topics"] == []

    def test_active_projects_non_list_raises(self):
        with pytest.raises(ValidationError) as exc:
            validate_monitor_changes_input({
                "jurisdiction": "eu",
                "active_projects": "PROJ-001",
            })
        assert exc.value.field == "active_projects"

    def test_active_projects_mixed_types_allowed(self):
        """String IDs and dicts are both valid — MISSION schema lists both."""
        result = validate_monitor_changes_input({
            "jurisdiction": "eu",
            "active_projects": ["PROJ-001", {"project_id": "PROJ-002"}],
        })
        assert result["active_projects"][0] == "PROJ-001"
        assert result["active_projects"][1] == {"project_id": "PROJ-002"}

    def test_active_projects_dict_without_id_warns(self):
        result = validate_monitor_changes_input({
            "jurisdiction": "eu",
            "active_projects": [{"name": "no id here"}],
        })
        # Passed through but warned
        assert len(result["active_projects"]) == 1
        assert any(
            "active_projects[0]" in w.field
            for w in result["_validation_warnings"]
        )

    def test_active_projects_empty_string_raises(self):
        with pytest.raises(ValidationError):
            validate_monitor_changes_input({
                "jurisdiction": "eu",
                "active_projects": [""],
            })

    def test_active_projects_unsupported_type_raises(self):
        with pytest.raises(ValidationError):
            validate_monitor_changes_input({
                "jurisdiction": "eu",
                "active_projects": [42],  # int
            })

    def test_lookback_days_default(self):
        result = validate_monitor_changes_input({"jurisdiction": "eu"})
        assert result["lookback_days"] == 30

    def test_lookback_days_explicit(self):
        result = validate_monitor_changes_input({
            "jurisdiction": "eu",
            "lookback_days": 90,
        })
        assert result["lookback_days"] == 90

    def test_lookback_days_bounds_lower(self):
        """lookback_days = 0 is invalid (must be >= 1)."""
        with pytest.raises(ValidationError):
            validate_monitor_changes_input({
                "jurisdiction": "eu",
                "lookback_days": 0,
            })

    def test_lookback_days_bounds_upper(self):
        """lookback_days > 365 is invalid."""
        with pytest.raises(ValidationError):
            validate_monitor_changes_input({
                "jurisdiction": "eu",
                "lookback_days": 400,
            })

    def test_lookback_days_negative_raises(self):
        with pytest.raises(ValidationError):
            validate_monitor_changes_input({
                "jurisdiction": "eu",
                "lookback_days": -1,
            })

    def test_lookback_days_bool_raises(self):
        """bool is a subclass of int — must be rejected explicitly."""
        with pytest.raises(ValidationError):
            validate_monitor_changes_input({
                "jurisdiction": "eu",
                "lookback_days": True,
            })

    def test_lookback_days_float_raises(self):
        with pytest.raises(ValidationError):
            validate_monitor_changes_input({
                "jurisdiction": "eu",
                "lookback_days": 30.5,
            })

    def test_lookback_days_string_raises(self):
        with pytest.raises(ValidationError):
            validate_monitor_changes_input({
                "jurisdiction": "eu",
                "lookback_days": "thirty",
            })

    def test_lookback_days_boundary_values(self):
        """Boundary values (1 and 365) are valid."""
        r1 = validate_monitor_changes_input({
            "jurisdiction": "eu",
            "lookback_days": 1,
        })
        assert r1["lookback_days"] == 1
        r365 = validate_monitor_changes_input({
            "jurisdiction": "eu",
            "lookback_days": 365,
        })
        assert r365["lookback_days"] == 365
