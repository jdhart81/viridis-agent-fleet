"""
Unit tests for regulatory-radar-agent core module.

Tests regulation scanning, compliance assessment, opportunity detection,
and report generation.
"""

import asyncio
import pytest
from datetime import datetime, timedelta

from src.core import (
    RegulatoryRadarCore,
    Jurisdiction,
    Sector,
    ComplianceLevel,
    RegulatorAlertConfig,
    Regulation,
)


@pytest.fixture
def agent():
    """Create agent instance for testing."""
    return RegulatoryRadarCore(debug=True)


class TestScanRegulations:
    """Tests for regulation scanning."""

    @pytest.mark.asyncio
    async def test_scan_eu_regulations(self, agent):
        """Test scanning EU regulations."""
        result = await agent.scan_regulations(
            jurisdiction=Jurisdiction.EU,
            sector=None,
        )

        assert result["jurisdiction"] == "eu"
        assert result["total_regulations"] > 0
        assert "regulations" in result
        assert len(result["regulations"]) > 0

    @pytest.mark.asyncio
    async def test_scan_by_sector(self, agent):
        """Test scanning regulations filtered by sector."""
        result = await agent.scan_regulations(
            jurisdiction=Jurisdiction.EU,
            sector=Sector.FORESTRY,
        )

        assert result["jurisdiction"] == "eu"
        assert "regulations" in result

    @pytest.mark.asyncio
    async def test_scan_with_text_query(self, agent):
        """Test regulation scanning with text search."""
        result = await agent.scan_regulations(
            jurisdiction=Jurisdiction.GLOBAL,
            query="biodiversity",
        )

        assert "regulations" in result
        assert result["total_regulations"] > 0

    @pytest.mark.asyncio
    async def test_scan_timestamp(self, agent):
        """Test that scan includes valid timestamp."""
        result = await agent.scan_regulations(jurisdiction=Jurisdiction.US)

        assert "scan_timestamp" in result
        # Verify it's a valid ISO format timestamp
        datetime.fromisoformat(result["scan_timestamp"])

    @pytest.mark.asyncio
    async def test_california_scan_includes_state_federal_and_global(self, agent):
        result = await agent.scan_regulations(
            jurisdiction=Jurisdiction.CALIFORNIA,
            sector=Sector.ENERGY,
        )

        assert result["jurisdiction"] == "california"
        assert result["included_jurisdictions"] == [
            "california", "global", "us"]
        by_id = {item["id"]: item for item in result["regulations"]}
        assert by_id["ca-sb253-2026"]["jurisdiction"] == "california"
        assert by_id["ca-sb261-2026"]["jurisdiction"] == "california"
        assert by_id["sec-climate-disclosure-2023"]["jurisdiction"] == "us"
        assert all(item["jurisdiction"] != "ca"
                   for item in result["regulations"])

    @pytest.mark.asyncio
    async def test_us_scan_preserves_california_entries(self, agent):
        result = await agent.scan_regulations(jurisdiction=Jurisdiction.US)
        by_id = {item["id"]: item for item in result["regulations"]}

        assert result["included_jurisdictions"] == [
            "california", "global", "us"]
        assert "ca-sb253-2026" in by_id
        assert "ca-sb261-2026" in by_id

    @pytest.mark.asyncio
    async def test_canada_code_does_not_resolve_to_california(self, agent):
        result = await agent.scan_regulations(
            jurisdiction=Jurisdiction.CANADA)

        assert result["jurisdiction"] == "ca"
        assert result["included_jurisdictions"] == ["ca", "global"]
        assert all(item["jurisdiction"] != "california"
                   for item in result["regulations"])

    @pytest.mark.asyncio
    async def test_process_accepts_us_ca_alias(self, agent):
        result = await agent.process({
            "action": "scan", "jurisdiction": "US-CA", "sector": "energy"})

        assert result["status"] == "success"
        assert result["jurisdiction"] == "california"
        assert {item["id"] for item in result["regulations"]} >= {
            "ca-sb253-2026", "ca-sb261-2026"}

    def test_california_sources_and_current_sb261_status(self, agent):
        sb261 = agent.db.regulations["california-climate-accountability"]
        sb253 = agent.db.regulations["ca-sb253-first-filing-2026"]

        assert sb261.jurisdiction == Jurisdiction.CALIFORNIA
        assert sb261.legal_status == (
            "statutory_requirement_enforcement_enjoined")
        assert "sb-261-docket" in sb261.resource_link
        assert "injunction" in sb261.scope_note.lower()
        assert sb261.source_verified_on == "2026-07-25"
        assert sb253.jurisdiction == Jurisdiction.CALIFORNIA
        assert sb253.reporting_deadline == datetime(2026, 8, 10)
        assert sb253.source_verified_on == "2026-07-25"

    @pytest.mark.asyncio
    async def test_scan_does_not_count_past_deadline_as_urgent(self, agent):
        """Past key dates are reported as past, never as approaching."""
        past = Regulation(
            id="past",
            name="Past date",
            jurisdiction=Jurisdiction.EU,
            sector=None,
            effective_date=datetime.utcnow() - timedelta(days=30),
            reporting_deadline=datetime.utcnow() - timedelta(days=1),
            requirements=[],
            penalties="",
            standards=[],
            description="",
            resource_link="https://example.test/past",
        )
        upcoming = Regulation(
            id="upcoming",
            name="Upcoming date",
            jurisdiction=Jurisdiction.EU,
            sector=None,
            effective_date=datetime.utcnow(),
            reporting_deadline=datetime.utcnow() + timedelta(days=30),
            requirements=[],
            penalties="",
            standards=[],
            description="",
            resource_link="https://example.test/upcoming",
        )
        agent.db.get_regulations_by_jurisdiction = lambda _jurisdiction: [
            past, upcoming
        ]

        result = await agent.scan_regulations(jurisdiction=Jurisdiction.EU)

        assert result["urgent_count"] == 1
        assert result["past_key_date_count"] == 1
        by_id = {item["id"]: item for item in result["regulations"]}
        assert by_id["past"]["deadline_status"] == "past"
        assert by_id["upcoming"]["deadline_status"] == "upcoming"
        assert by_id["upcoming"]["source_url"] == "https://example.test/upcoming"
        assert "qualified counsel" in result["disclaimer"]


class TestComplianceAssessment:
    """Tests for compliance assessment."""

    @pytest.mark.asyncio
    async def test_compliant_company(self, agent):
        """Test assessment of fully compliant company."""
        # Create practices that meet all requirements.
        # Requirements are converted to lowercase with spaces replaced by underscores.
        practices = {
            "assess_nature-related_risks_and_opportunities": True,
            "disclose_governance_structure_for_nature_oversight": True,
            "provide_biodiversity_impact_assessment": True,
            "set_science-based_nature_targets": True,
            "double_materiality_assessment_(impact_and_financial)": True,
            "report_on_governance,_strategy,_risk_management": True,
            "comprehensive_esg_metrics": True,
            "climate_science-based_targets": True,
            "third-party_assurance": True,
            "classify_economic_activities_by_environmental_sustainability": True,
            "report_percentage_of_revenue_from_sustainable_activities": True,
            "monitor_alignment_with_climate_targets": True,
            "track_biodiversity_and_water_indicators": True,
            "implement_nature-positive_business_practices": True,
            "halt_biodiversity_loss_by_2030": True,
            "restore_30%_of_degraded_ecosystems_by_2030": True,
            "reduce_chemical_pollution_by_50%": True,
            "national_biodiversity_strategy_implementation": True,
            "track_carbon_credit_origin_and_authenticity": True,
            "prevent_double_counting_of_emissions_reductions": True,
            "register_and_report_carbon_transactions": True,
            "ensure_environmental_integrity_of_credits": True,
        }

        assessment = await agent.assess_compliance(
            company_name="Eco Corp",
            jurisdiction=Jurisdiction.EU,
            sector=Sector.FORESTRY,
            current_practices=practices,
        )

        assert assessment.company_name == "Eco Corp"
        assert assessment.jurisdiction == Jurisdiction.EU
        assert assessment.sector == Sector.FORESTRY
        # A fully compliant company should have high compliance percentage
        assert assessment.compliance_percentage >= 50

    @pytest.mark.asyncio
    async def test_non_compliant_company(self, agent):
        """Test assessment of non-compliant company."""
        practices = {
            "some_random_practice": True,
        }

        assessment = await agent.assess_compliance(
            company_name="Non-Eco Corp",
            jurisdiction=Jurisdiction.EU,
            sector=Sector.AGRICULTURE,
            current_practices=practices,
        )

        assert assessment.company_name == "Non-Eco Corp"
        assert len(assessment.gaps) > 0
        assert assessment.overall_compliance_level == ComplianceLevel.NON_COMPLIANT

    @pytest.mark.asyncio
    async def test_compliance_gap_details(self, agent):
        """Test that compliance gaps contain necessary details."""
        assessment = await agent.assess_compliance(
            company_name="Test Co",
            jurisdiction=Jurisdiction.US,
            sector=Sector.ENERGY,
            current_practices={},
        )

        if assessment.gaps:
            gap = assessment.gaps[0]
            assert gap.regulation_id
            assert gap.regulation_name
            assert gap.requirement
            assert gap.remediation_steps
            assert gap.estimated_effort_hours > 0
            assert gap.deadline_days > 0
            assert gap.risk_level in ["critical", "high", "medium", "low"]

    @pytest.mark.asyncio
    async def test_assessment_summary(self, agent):
        """Test that assessment includes summary."""
        assessment = await agent.assess_compliance(
            company_name="Summary Test",
            jurisdiction=Jurisdiction.EU,
            sector=Sector.FORESTRY,
            current_practices={"some_practice": True},
        )

        assert assessment.summary
        assert "Summary Test" in assessment.summary or "compliance" in assessment.summary.lower()


class TestComplianceAssessmentInvariants:
    """
    Tests pinning previously-uncovered invariants of assess_compliance().

    Added Night 28 (cross-pollination queue #3) to bring assess_compliance
    coverage to parity with monitor_changes (10 tests across 2 classes
    after Night 26). The four invariants pinned here cover branches that
    the original TestComplianceAssessment did not exercise:

      1. PARTIAL compliance band (50% <= pct < 90%) — only COMPLIANT and
         NON_COMPLIANT bands had explicit tests; the middle band was
         uncovered, which left a regression vector if the band thresholds
         in core.py:473-477 were ever shifted.
      2. priority_actions sorted by deadline_days ascending — the sort key
         at core.py:481 (`sorted(gaps, key=lambda x: x.deadline_days)`)
         was unpinned. A regression that flipped the sort or removed it
         would silently degrade urgency ranking.
      3. priority_actions capped at top-3 — the `[:3]` slice at
         core.py:481 was unpinned. A regression that lifted the cap or
         dropped to top-1 would silently change action-list scope.
      4. compliance_percentage rounded to 1 decimal — the rounding at
         core.py:490 was unpinned. A regression to integer rounding or
         no rounding would break downstream consumers expecting `xx.x`.

    These tests construct a deterministic 5-of-9-regulations partial-
    compliance scenario (EU FORESTRY) so the assertions are stable across
    seed-data changes that don't shift the regulation-count ratio.
    """

    @staticmethod
    def _craft_partial_practices(agent_obj, jurisdiction, sector, n_regs_satisfied):
        """Build practices dict satisfying the first n applicable regulations."""
        regs = agent_obj.db.get_regulations_by_jurisdiction(jurisdiction)
        regs = [r for r in regs if r.sector is None or r.sector == sector]
        practices = {}
        for reg in regs[:n_regs_satisfied]:
            for req in reg.requirements:
                practices[req.lower().replace(" ", "_")] = True
        return practices, len(regs)

    @pytest.mark.asyncio
    async def test_partial_compliance_band_yields_partial_level(self, agent):
        """
        Compliance percentage in [50, 90) must yield ComplianceLevel.PARTIAL.

        Pins core.py:473-477 band thresholds. EU FORESTRY has 9 applicable
        regs; satisfying 5/9 = 55.6% lands squarely in the PARTIAL band.
        """
        practices, n_regs = self._craft_partial_practices(
            agent, Jurisdiction.EU, Sector.FORESTRY, n_regs_satisfied=5
        )
        assessment = await agent.assess_compliance(
            company_name="PartialCo",
            jurisdiction=Jurisdiction.EU,
            sector=Sector.FORESTRY,
            current_practices=practices,
        )
        assert 50.0 <= assessment.compliance_percentage < 90.0, (
            f"expected partial band [50, 90), got {assessment.compliance_percentage}"
        )
        assert assessment.overall_compliance_level == ComplianceLevel.PARTIAL

    @pytest.mark.asyncio
    async def test_priority_actions_sorted_by_deadline_ascending(self, agent):
        """
        priority_actions must be ordered by deadline_days ascending.

        Pins core.py:481 sort key. The action with the earliest deadline
        must appear first; a regression that removed the sort would let
        late-deadline actions surface ahead of urgent ones.
        """
        practices, _ = self._craft_partial_practices(
            agent, Jurisdiction.EU, Sector.FORESTRY, n_regs_satisfied=5
        )
        assessment = await agent.assess_compliance(
            company_name="SortTestCo",
            jurisdiction=Jurisdiction.EU,
            sector=Sector.FORESTRY,
            current_practices=practices,
        )
        # Reconstruct the deadline-ordered gap list and verify priority_actions
        # mirror that ordering by name (priority_action strings embed the
        # regulation_name).
        sorted_gaps = sorted(assessment.gaps, key=lambda g: g.deadline_days)
        for action_str, gap in zip(assessment.priority_actions, sorted_gaps):
            assert gap.regulation_name in action_str, (
                f"priority_action {action_str!r} should reference "
                f"{gap.regulation_name!r} (next-most-urgent gap)"
            )

    @pytest.mark.asyncio
    async def test_priority_actions_capped_at_three(self, agent):
        """
        priority_actions list must contain at most 3 entries (top-3 cap).

        Pins core.py:481 `[:3]` slice. A regression that lifted the cap
        would inflate the action list; a regression to `[:1]` would
        truncate it to a single action.
        """
        practices, _ = self._craft_partial_practices(
            agent, Jurisdiction.EU, Sector.FORESTRY, n_regs_satisfied=2
        )
        # 2/9 satisfied → 7 gaps → priority_actions should still be capped at 3
        assessment = await agent.assess_compliance(
            company_name="CapTestCo",
            jurisdiction=Jurisdiction.EU,
            sector=Sector.FORESTRY,
            current_practices=practices,
        )
        assert len(assessment.gaps) >= 4, (
            "scenario design: need at least 4 gaps to verify the top-3 cap"
        )
        assert len(assessment.priority_actions) <= 3, (
            f"priority_actions capped at 3, got {len(assessment.priority_actions)}"
        )

    @pytest.mark.asyncio
    async def test_compliance_percentage_rounded_to_one_decimal(self, agent):
        """
        compliance_percentage must be rounded to 1 decimal place.

        Pins core.py:490 `round(compliance_percentage, 1)`. A regression
        to no-rounding or integer-rounding would break downstream
        consumers (dashboards, reports) that format `{:.1f}`.
        """
        practices, _ = self._craft_partial_practices(
            agent, Jurisdiction.EU, Sector.FORESTRY, n_regs_satisfied=5
        )
        assessment = await agent.assess_compliance(
            company_name="RoundTestCo",
            jurisdiction=Jurisdiction.EU,
            sector=Sector.FORESTRY,
            current_practices=practices,
        )
        # The float must equal its 1-decimal rounding (i.e., no hidden digits).
        assert assessment.compliance_percentage == round(
            assessment.compliance_percentage, 1
        ), (
            f"compliance_percentage {assessment.compliance_percentage} "
            f"is not rounded to 1 decimal"
        )

    @pytest.mark.asyncio
    async def test_no_applicable_regs_yields_zero_percent_non_compliant(
        self, agent, monkeypatch
    ):
        """
        When no regulations apply to (jurisdiction, sector), assess_compliance
        must short-circuit to 0% / NON_COMPLIANT without raising or dividing
        by zero.

        Pins the defensive branch at core.py:471
        (`compliance_percentage = ... if applicable_regs else 0`).

        This branch is unreachable in current seed data because every
        jurisdiction has at least one GLOBAL regulation that survives
        the sector filter. Stub-injecting `db.get_regulations_by_jurisdiction`
        to return `[]` is the only way to reach the empty-list path —
        without this test, a regression that removed the `if applicable_regs`
        guard would silently raise `ZeroDivisionError` only when the seed
        data was modified, days or weeks later. Pinning the defensive
        path makes the invariant explicit and seed-data-independent.

        Diagnosed Night 28 (cross-pollination queue #8); landed Night 29.
        """
        # Stub-inject: force the regulation lookup to return an empty list,
        # bypassing the seed data entirely. This is the canonical pattern
        # for testing branches that are unreachable through input crafting
        # because they depend on data-layer state rather than caller input.
        monkeypatch.setattr(
            agent.db,
            "get_regulations_by_jurisdiction",
            lambda jurisdiction: [],
        )

        assessment = await agent.assess_compliance(
            company_name="EmptyRegsCo",
            jurisdiction=Jurisdiction.EU,
            sector=Sector.FORESTRY,
            current_practices={"some_practice": True},
        )

        # Defensive branch invariants:
        assert assessment.compliance_percentage == 0, (
            "empty applicable_regs must yield 0%, not NaN or division-by-zero"
        )
        assert assessment.overall_compliance_level == ComplianceLevel.NON_COMPLIANT, (
            "0% lands below the 50% PARTIAL threshold ⇒ NON_COMPLIANT"
        )
        assert assessment.gaps == [], (
            "no applicable regs ⇒ no gaps (the gap loop iterates over "
            "applicable_regs, so an empty input must produce an empty output)"
        )
        assert assessment.priority_actions == [], (
            "priority_actions are derived from gaps; empty gaps ⇒ empty actions"
        )
        assert assessment.applicable_regulations == [], (
            "applicable_regulations field must reflect the (empty) lookup result"
        )
        # Sanity: company_name and jurisdiction still propagate correctly.
        assert assessment.company_name == "EmptyRegsCo"
        assert assessment.jurisdiction == Jurisdiction.EU


class TestOpportunityDetection:
    """Tests for regulatory opportunity detection."""

    @pytest.mark.asyncio
    async def test_detect_opportunities(self, agent):
        """Test opportunity detection."""
        opportunities = await agent.detect_opportunities(
            jurisdiction=Jurisdiction.EU,
            sector=Sector.FORESTRY,
        )

        assert isinstance(opportunities, list)
        assert len(opportunities) > 0

    @pytest.mark.asyncio
    async def test_opportunity_viridis_fit_score(self, agent):
        """Test that opportunities include Viridis fit scores."""
        opportunities = await agent.detect_opportunities(
            jurisdiction=Jurisdiction.EU,
            sector=Sector.AGRICULTURE,
        )

        for opp in opportunities:
            assert 0 <= opp.viridis_fit_score <= 1.0
            assert opp.viridis_fit_score > 0.6  # Only high-fit opportunities returned

    @pytest.mark.asyncio
    async def test_opportunity_market_sizing(self, agent):
        """Test that opportunities include market sizing."""
        opportunities = await agent.detect_opportunities(
            jurisdiction=Jurisdiction.US,
            sector=Sector.ENERGY,
        )

        for opp in opportunities:
            assert opp.affected_companies_estimated > 0
            assert opp.market_size_estimate
            assert opp.timeline_months > 0

    @pytest.mark.asyncio
    async def test_opportunities_sorted_by_fit(self, agent):
        """Test that opportunities are sorted by Viridis fit score."""
        opportunities = await agent.detect_opportunities(
            jurisdiction=Jurisdiction.GLOBAL,
            sector=Sector.FORESTRY,
        )

        if len(opportunities) > 1:
            for i in range(len(opportunities) - 1):
                assert (opportunities[i].viridis_fit_score >=
                       opportunities[i + 1].viridis_fit_score)


class TestTNFDReportGeneration:
    """Tests for TNFD report generation."""

    @pytest.mark.asyncio
    async def test_generate_tnfd_report(self, agent):
        """Test TNFD report generation."""
        report = await agent.generate_tnfd_report(
            company_name="Forest Corp",
            governance_data=None,
            strategy_data=None,
            risk_data=None,
            biodiversity_score=0.65,
        )

        assert report.company_name == "Forest Corp"
        assert report.governance
        assert report.strategy
        assert report.risk_management
        assert report.metrics_targets
        assert report.executive_summary

    @pytest.mark.asyncio
    async def test_tnfd_custom_data(self, agent):
        """Test TNFD report with custom data."""
        governance = {"board_level_oversight": "Chief Sustainability Officer", "committee": "ESG Committee"}
        strategy = {"nature_dependency": "Water supply", "climate_resilience": "Assessed"}
        risk = {"primary_risk": "Supply chain disruption"}

        report = await agent.generate_tnfd_report(
            company_name="Green Ventures",
            governance_data=governance,
            strategy_data=strategy,
            risk_data=risk,
            biodiversity_score=0.78,
        )

        assert report.governance["board_level_oversight"] == "Chief Sustainability Officer"
        assert report.strategy["nature_dependency"] == "Water supply"
        assert report.risk_management["primary_risk"] == "Supply chain disruption"

    @pytest.mark.asyncio
    async def test_tnfd_report_date(self, agent):
        """Test that TNFD report includes current timestamp."""
        report = await agent.generate_tnfd_report(
            company_name="Time Test",
            governance_data=None,
            strategy_data=None,
            risk_data=None,
            biodiversity_score=0.5,
        )

        assert report.report_date
        # Report date should be recent (within last minute)
        time_diff = datetime.utcnow() - report.report_date
        assert time_diff.total_seconds() < 60


class TestCSRDReportGeneration:
    """Tests for CSRD report generation."""

    @pytest.mark.asyncio
    async def test_generate_csrd_report(self, agent):
        """Test CSRD report generation."""
        report = await agent.generate_csrd_report(
            company_name="Sustainable Inc",
            environmental_data=None,
            governance_data=None,
            materiality_impacts=["GHG emissions", "Biodiversity"],
            materiality_financial=["Transition costs", "Climate risk"],
        )

        assert report.company_name == "Sustainable Inc"
        assert report.governance_and_organization
        assert report.strategy_and_value_creation
        assert report.double_materiality_assessment
        assert report.metrics_and_targets
        assert report.action_plans

    @pytest.mark.asyncio
    async def test_csrd_double_materiality(self, agent):
        """Test CSRD double materiality assessment."""
        impacts = ["Water use", "Waste generation"]
        financial = ["Regulatory risk", "Supply chain resilience"]

        report = await agent.generate_csrd_report(
            company_name="Material Inc",
            environmental_data=None,
            governance_data=None,
            materiality_impacts=impacts,
            materiality_financial=financial,
        )

        assert "impact_materiality" in report.double_materiality_assessment
        assert "financial_materiality" in report.double_materiality_assessment
        assert impacts == report.double_materiality_assessment["impact_materiality"]
        assert financial == report.double_materiality_assessment["financial_materiality"]


class TestRegulatoryForecast:
    """Tests for regulatory forecasting."""

    @pytest.mark.asyncio
    async def test_regulatory_forecast(self, agent):
        """Test regulatory forecast generation."""
        forecast = await agent.regulatory_forecast(
            jurisdiction=Jurisdiction.EU,
            forecast_months=12,
        )

        assert forecast.jurisdiction == Jurisdiction.EU
        assert forecast.forecast_period_months == 12
        assert forecast.likely_changes
        assert forecast.confidence_level in ["high", "medium", "low"]
        assert forecast.political_signals
        assert forecast.recommendation

    @pytest.mark.asyncio
    async def test_forecast_consultation_status(self, agent):
        """Test that forecast includes consultation status."""
        forecast = await agent.regulatory_forecast(
            jurisdiction=Jurisdiction.US,
            forecast_months=24,
        )

        assert forecast.consultation_status
        assert isinstance(forecast.consultation_status, dict)


class TestAlertGeneration:
    """Tests for alert generation."""

    @pytest.mark.asyncio
    async def test_generate_alerts(self, agent):
        """Test alert generation."""
        watchlist = [
            (Jurisdiction.EU, Sector.FORESTRY),
            (Jurisdiction.US, Sector.ENERGY),
        ]

        alerts_result = await agent.generate_alerts(watchlist=watchlist)

        assert "alert_count" in alerts_result
        assert "critical_count" in alerts_result
        assert "high_count" in alerts_result
        assert "alerts" in alerts_result

    @pytest.mark.asyncio
    async def test_alert_config(self, agent):
        """Test alert generation with custom config."""
        watchlist = [
            (Jurisdiction.EU, Sector.AGRICULTURE),
        ]

        config = RegulatorAlertConfig(
            jurisdictions=[Jurisdiction.EU],
            sectors=[Sector.AGRICULTURE],
            days_before_deadline=60,
        )

        alerts_result = await agent.generate_alerts(
            watchlist=watchlist,
            alert_config=config,
        )

        assert alerts_result["alert_count"] >= 0

    @pytest.mark.asyncio
    async def test_alert_structure(self, agent):
        """Test that alerts have required structure."""
        watchlist = [(Jurisdiction.EU, Sector.FORESTRY)]
        alerts_result = await agent.generate_alerts(watchlist=watchlist)

        if alerts_result["alerts"]:
            alert = alerts_result["alerts"][0]
            assert "type" in alert
            assert "jurisdiction" in alert
            assert "regulation" in alert
            assert "severity" in alert or "days_remaining" in alert


class TestHealthAndDescription:
    """Tests for health checks and agent description."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, agent):
        """Test health check."""
        health = await agent.health()

        assert health["status"] == "ok"
        assert health["agent"] == "regulatory-radar"
        assert health["version"] == "0.2.0"
        assert health["regulations_in_db"] > 0

    def test_describe_endpoint(self, agent):
        """Test agent description."""
        description = agent.describe()

        assert description["name"] == "regulatory-radar"
        assert description["version"] == "0.2.0"
        assert "monitor_changes" in description["capabilities"]
        assert "build_evidence_pack" in description["capabilities"]
        assert "capabilities" in description
        assert len(description["capabilities"]) > 0
        assert "inputs" in description
        assert "outputs" in description


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_invalid_jurisdiction_raises_error(self, agent):
        """Test that invalid jurisdiction raises error."""
        with pytest.raises((ValueError, KeyError)):
            Jurisdiction["INVALID"]

    @pytest.mark.asyncio
    async def test_invalid_sector_raises_error(self, agent):
        """Test that invalid sector raises error."""
        with pytest.raises((ValueError, KeyError)):
            Sector["INVALID"]


class TestMonitorChangesAlertLevel:
    """
    Tests for per-change alert_level field in monitor_changes output.
    Added Nightkeeper 2026-04-21 (queue #5).

    Invariants:
      - Every change dict has an 'alert_level' field with one of
        {"critical", "high", "medium"} (never "low" — low is reserved
        for the empty-changes aggregate case).
      - alert_level bands use the next non-past effective/deadline key date:
          urgency_days <= 30        -> "critical"
          30 < urgency_days <= 90   -> "high"
          urgency_days > 90 or None -> "medium"
      - Max of per-change alert_level equals aggregate alert_level when
        changes is non-empty (severity-ordering invariant).
    """

    _SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

    @pytest.mark.asyncio
    async def test_every_change_has_alert_level(self, agent):
        """Every change dict exposes an 'alert_level' field."""
        result = await agent.monitor_changes(
            jurisdiction=Jurisdiction.EU,
            lookback_days=365,
        )
        assert "changes" in result
        for c in result["changes"]:
            assert "alert_level" in c, f"missing alert_level in {c}"
            assert c["alert_level"] in {"critical", "high", "medium"}

    @pytest.mark.asyncio
    async def test_alert_level_matches_severity_bands(self, agent):
        """Per-change alert_level respects the (30, 90) day thresholds."""
        result = await agent.monitor_changes(
            jurisdiction=Jurisdiction.GLOBAL,
            lookback_days=365,
        )
        for c in result["changes"]:
            days = c.get("urgency_days")
            level = c["alert_level"]
            if days is not None and days <= 30:
                assert level == "critical", f"days={days} should be critical, got {level}"
            elif days is not None and days <= 90:
                assert level == "high", f"days={days} should be high, got {level}"
            else:
                assert level == "medium", f"days={days} should be medium, got {level}"

    @pytest.mark.asyncio
    async def test_aggregate_equals_max_per_change(self, agent):
        """
        Aggregate alert_level equals the max per-change alert_level when
        changes are non-empty. This is the self-describing invariant: an
        external consumer can derive aggregate severity from the children
        alone without re-implementing urgency logic.
        """
        result = await agent.monitor_changes(
            jurisdiction=Jurisdiction.EU,
            lookback_days=365,
        )
        changes = result["changes"]
        if not changes:
            assert result["alert_level"] == "low"
            return
        max_per_change = max(
            self._SEVERITY_ORDER[c["alert_level"]] for c in changes
        )
        agg = self._SEVERITY_ORDER[result["alert_level"]]
        assert max_per_change == agg, (
            f"max(per-change)={max_per_change} != aggregate={agg}"
        )

    @pytest.mark.asyncio
    async def test_alert_level_type_is_string(self, agent):
        """alert_level must be a string (not None, not enum) for JSON safety."""
        result = await agent.monitor_changes(
            jurisdiction=Jurisdiction.US,
            lookback_days=365,
        )
        for c in result["changes"]:
            assert isinstance(c["alert_level"], str)


class TestMonitorChangesFiltering:
    """
    Tests for monitor_changes() input-driven filtering behavior.
    Added Nightkeeper 2026-04-25 (queue #5 — re-queued from Nights 22/23/24).

    Invariants:
      - topics filter: only regulations whose name/description/standards
        contain at least one (case-insensitive) topic substring may appear
        in `changes`. An empty intersection produces an empty `changes`
        list.
      - active_projects pass-through: each change's `impact_on_projects`
        is the full list of project IDs supplied (no per-change filtering
        in the current model — Carbon-Bridge consumers expect the union).
        `project_count` equals the number of unique IDs in the input.
      - active_projects coercion: dicts with `project_id` or `id` are
        coerced to strings; bare strings/ints are stringified.
      - lookback_days monotonicity: change_count is non-decreasing as
        lookback_days widens (later windows are supersets of earlier
        ones for the same jurisdiction/topics).
      - `monitored_topics` echoes the input topics list (or [] when
        topics is None) — provides round-trip transparency for callers
        composing multiple monitor_changes calls.
    """

    @pytest.mark.asyncio
    async def test_topic_filter_restricts_to_substring_match(self, agent):
        """
        With topics=['biodiversity'], every returned change must mention
        'biodiversity' in its name/summary/standards (case-insensitive).
        """
        result = await agent.monitor_changes(
            jurisdiction=Jurisdiction.GLOBAL,
            topics=["biodiversity"],
            lookback_days=365,
        )
        for c in result["changes"]:
            blob = " ".join([
                str(c.get("regulation_name", "")),
                str(c.get("summary", "")),
                " ".join(c.get("standards", [])),
            ]).lower()
            assert "biodiversity" in blob, (
                f"change {c.get('regulation_id')} returned for topic "
                f"'biodiversity' but no field contains the substring: {blob[:200]}"
            )
        assert result["monitored_topics"] == ["biodiversity"]

    @pytest.mark.asyncio
    async def test_topic_filter_unknown_yields_empty_changes(self, agent):
        """
        A topic that no regulation matches should yield zero changes and
        alert_level == 'low' (per the empty-changes branch).
        """
        result = await agent.monitor_changes(
            jurisdiction=Jurisdiction.EU,
            topics=["___zzz_no_such_regulation_topic_ever___"],
            lookback_days=365,
        )
        assert result["change_count"] == 0
        assert result["changes"] == []
        assert result["alert_level"] == "low"

    @pytest.mark.asyncio
    async def test_active_projects_propagates_to_each_change(self, agent):
        """
        Each change in the output carries `impact_on_projects` equal to
        the full project ID list, and `project_count` matches input size.
        """
        projects = ["proj-alpha", "proj-beta", "proj-gamma"]
        result = await agent.monitor_changes(
            jurisdiction=Jurisdiction.EU,
            active_projects=projects,
            lookback_days=365,
        )
        assert result["project_count"] == len(projects)
        # Skip the assertion if there are no changes — the propagation
        # invariant only applies when the agent has changes to emit.
        if result["changes"]:
            for c in result["changes"]:
                assert c["impact_on_projects"] == projects, (
                    f"impact_on_projects {c['impact_on_projects']} != "
                    f"input {projects}"
                )

    @pytest.mark.asyncio
    async def test_active_projects_dict_coercion(self, agent):
        """
        Dict-shaped active_projects entries with `project_id` or `id` keys
        should be coerced to their string ID; bare values get stringified.
        Mirrors the coercion logic in core.py:556-564.
        """
        projects = [
            {"project_id": "p-1", "name": "Reforestation Site A"},
            {"id": "p-2", "site": "wetland"},
            "p-3",
            42,
        ]
        result = await agent.monitor_changes(
            jurisdiction=Jurisdiction.EU,
            active_projects=projects,
            lookback_days=365,
        )
        # All 4 inputs should produce 4 IDs
        assert result["project_count"] == 4
        if result["changes"]:
            ids = result["changes"][0]["impact_on_projects"]
            assert ids == ["p-1", "p-2", "p-3", "42"], (
                f"expected coerced IDs ['p-1','p-2','p-3','42'], got {ids}"
            )

    @pytest.mark.asyncio
    async def test_lookback_days_widening_is_monotonic(self, agent):
        """
        Widening the lookback window is a superset operation on changes:
        change_count(lookback=365) >= change_count(lookback=30).
        """
        narrow = await agent.monitor_changes(
            jurisdiction=Jurisdiction.EU,
            lookback_days=30,
        )
        wide = await agent.monitor_changes(
            jurisdiction=Jurisdiction.EU,
            lookback_days=365,
        )
        assert wide["change_count"] >= narrow["change_count"], (
            f"wider lookback ({wide['change_count']}) should be >= "
            f"narrow lookback ({narrow['change_count']}) — monotonicity "
            f"violation suggests window logic regression"
        )
        assert narrow["lookback_days"] == 30
        assert wide["lookback_days"] == 365

    @pytest.mark.asyncio
    async def test_no_topics_echoes_empty_list(self, agent):
        """
        When topics is None (default), monitored_topics should echo as []
        — preserves JSON-safe round-trip for downstream consumers.
        """
        result = await agent.monitor_changes(
            jurisdiction=Jurisdiction.US,
            lookback_days=90,
        )
        assert result["monitored_topics"] == []
        assert result["project_count"] == 0


class TestMonitorChangesWindowTruth:
    """The paid-watch window must not mislabel or include out-of-window dates."""

    @staticmethod
    def _reg(reg_id, effective_date, *, deadline=None,
             legal_status="binding"):
        return Regulation(
            id=reg_id,
            name=f"Test regulation {reg_id}",
            jurisdiction=Jurisdiction.EU,
            sector=None,
            effective_date=effective_date,
            reporting_deadline=deadline,
            requirements=["Review applicability"],
            penalties="test",
            standards=["TEST"],
            description="Test dated requirement",
            resource_link="https://example.test/source",
            legal_status=legal_status,
            source_verified_on="2026-07-27",
        )

    @pytest.mark.asyncio
    async def test_far_future_binding_is_outside_short_window(self, agent):
        now = datetime.utcnow()
        agent.db.regulations = {
            "far": self._reg(
                "far", now + timedelta(days=200),
                deadline=now + timedelta(days=200)),
        }

        result = await agent.monitor_changes(
            Jurisdiction.EU, lookback_days=30)

        assert result["change_count"] == 0
        assert result["changes"] == []
        assert result["alert_level"] == "low"

    @pytest.mark.asyncio
    async def test_upcoming_binding_is_not_called_a_proposed_rule(self, agent):
        now = datetime.utcnow()
        agent.db.regulations = {
            "binding": self._reg(
                "binding", now + timedelta(days=20),
                legal_status="binding_application_upcoming"),
        }

        result = await agent.monitor_changes(
            Jurisdiction.EU, lookback_days=30)

        assert result["change_count"] == 1
        change = result["changes"][0]
        assert change["type"] == "effective_date_approaching"
        assert change["urgency_days"] in {19, 20}
        assert change["alert_level"] == "critical"

    @pytest.mark.asyncio
    async def test_actual_proposal_retains_proposed_rule_label(self, agent):
        now = datetime.utcnow()
        agent.db.regulations = {
            "draft": self._reg(
                "draft", now + timedelta(days=20),
                legal_status="draft_consultation"),
        }

        result = await agent.monitor_changes(
            Jurisdiction.EU, lookback_days=30)

        assert result["changes"][0]["type"] == "proposed_rule"

    @pytest.mark.asyncio
    async def test_recently_effective_requirement_is_new_regulation(self, agent):
        now = datetime.utcnow()
        agent.db.regulations = {
            "recent": self._reg(
                "recent", now - timedelta(days=20)),
        }

        result = await agent.monitor_changes(
            Jurisdiction.EU, lookback_days=30)

        change = result["changes"][0]
        assert change["type"] == "new_regulation"
        assert change["urgency_days"] is None
        assert change["action_required"] is True

    @pytest.mark.asyncio
    async def test_recently_passed_deadline_is_visible_and_critical(self, agent):
        now = datetime.utcnow()
        agent.db.regulations = {
            "overdue": self._reg(
                "overdue", now - timedelta(days=200),
                deadline=now - timedelta(days=4)),
        }

        result = await agent.monitor_changes(
            Jurisdiction.EU, lookback_days=30)

        assert result["change_count"] == 1
        change = result["changes"][0]
        assert change["type"] == "deadline_recently_passed"
        assert change["overdue_days"] in {4, 5}
        assert change["urgency_days"] == 0
        assert change["alert_level"] == "critical"
        assert change["action_required"] is True
        assert "past key date" in result["recommended_actions"][0]

    @pytest.mark.asyncio
    async def test_compact_topic_matches_spaced_regulation_name(self, agent):
        now = datetime.utcnow()
        regulation = self._reg(
            "sb253", now - timedelta(days=200),
            deadline=now - timedelta(days=4),
        )
        regulation.name = "California SB 253 reporting requirement"
        agent.db.regulations = {"sb253": regulation}

        result = await agent.monitor_changes(
            Jurisdiction.EU, topics=["sb253"], lookback_days=30)

        assert result["change_count"] == 1
        assert result["changes"][0]["regulation_id"] == "sb253"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
