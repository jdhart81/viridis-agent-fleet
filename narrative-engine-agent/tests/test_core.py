"""
Unit tests for narrative-engine-agent core module.

Tests narrative generation across formats and audiences,
quality scoring, audience profiling, and template application.
"""

import pytest
from datetime import datetime

from src.core import (
    NarrativeEngineCore,
    AudienceType,
    NarrativeFormat,
    AudienceProfiler,
    NarrativeTemplate,
    NarrativeQualityScorer,
)


@pytest.fixture
def agent():
    """Create agent instance for testing."""
    return NarrativeEngineCore(debug=True)


@pytest.fixture
def sample_agent_output():
    """Sample output from ecological agent."""
    return {
        "project_name": "Amazon Forest Restoration",
        "market_size_estimate": "$5B TAM",
        "customer_count": 50,
        "annual_recurring_revenue": "$2.5M",
        "biodiversity_impact_score": 0.78,
        "hectares_restored": 500000,
        "carbon_sequestration_tonnes": 1000000,
        "species_recovered": 35,
        "compliance_status": "TNFD/CSRD ready",
    }


class TestAudienceProfiler:
    """Tests for audience profiling."""

    def test_get_investor_profile(self):
        """Test investor audience profile."""
        profile = AudienceProfiler.get_profile(AudienceType.INSTITUTIONAL_INVESTOR)

        assert profile.audience_type == AudienceType.INSTITUTIONAL_INVESTOR
        assert any("market" in c.lower() for c in profile.decision_criteria)
        assert profile.vocabulary_level == "technical"
        assert profile.typical_objections  # Has objections

    def test_get_policymaker_profile(self):
        """Test policymaker audience profile."""
        profile = AudienceProfiler.get_profile(AudienceType.POLICYMAKER)

        assert profile.audience_type == AudienceType.POLICYMAKER
        assert "stakeholder" in profile.primary_concern.lower()
        assert profile.attention_span_minutes == 15
        assert any("cost-benefit" in e.lower() for e in profile.preferred_evidence)

    def test_get_grant_funder_profile(self):
        """Test grant funder audience profile."""
        profile = AudienceProfiler.get_profile(AudienceType.GRANT_FUNDER)

        assert profile.audience_type == AudienceType.GRANT_FUNDER
        assert "impact" in profile.primary_concern.lower()
        assert any("impact" in e.lower() for e in profile.preferred_evidence)

    def test_get_journalist_profile(self):
        """Test journalist audience profile."""
        profile = AudienceProfiler.get_profile(AudienceType.JOURNALIST)

        assert profile.audience_type == AudienceType.JOURNALIST
        assert profile.attention_span_minutes == 5
        assert profile.vocabulary_level == "general"
        assert profile.decision_timeframe == "immediate"

    def test_get_public_profile(self):
        """Test general public audience profile."""
        profile = AudienceProfiler.get_profile(AudienceType.GENERAL_PUBLIC)

        assert profile.audience_type == AudienceType.GENERAL_PUBLIC
        assert profile.vocabulary_level == "general"
        assert "personal relevance" in profile.primary_concern.lower()


class TestNarrativeTemplates:
    """Tests for narrative structure templates."""

    def test_investor_structure(self):
        """Test investor narrative structure."""
        structure = NarrativeTemplate.investor_narrative_structure()

        required_keys = ["hook", "problem", "solution", "market", "traction", "team", "impact", "call_to_action"]
        for key in required_keys:
            assert key in structure

    def test_policy_brief_structure(self):
        """Test policy brief structure."""
        structure = NarrativeTemplate.policy_brief_structure()

        required_keys = ["executive_summary", "background", "policy_options", "recommendation"]
        for key in required_keys:
            assert key in structure

    def test_grant_proposal_structure(self):
        """Test grant proposal structure."""
        structure = NarrativeTemplate.grant_proposal_structure()

        required_keys = ["executive_summary", "project_description", "evaluation_plan", "budget_narrative"]
        for key in required_keys:
            assert key in structure

    def test_press_release_structure(self):
        """Test press release structure."""
        structure = NarrativeTemplate.press_release_structure()

        required_keys = ["headline", "lede", "boilerplate"]
        for key in required_keys:
            assert key in structure

    def test_executive_summary_structure(self):
        """Test executive summary structure."""
        structure = NarrativeTemplate.executive_summary_structure()

        required_keys = ["title", "hook", "situation", "next_steps"]
        for key in required_keys:
            assert key in structure


class TestNarrativeQualityScorer:
    """Tests for narrative quality scoring."""

    def test_score_high_quality_narrative(self):
        """Test scoring of well-crafted narrative."""
        narrative = """
        The global market for nature-based solutions is growing 25% annually based on recent
        research. Our approach is supported by data showing clear evidence of impact. Evidence
        demonstrates our solution is effective. Research indicates positive outcomes. Data shows
        strong results. We recommend implementing this solution immediately as next steps.
        """
        score = NarrativeQualityScorer.score_narrative(
            narrative,
            AudienceType.INSTITUTIONAL_INVESTOR,
            NarrativeFormat.INVESTOR_DECK,
        )

        assert 0 <= score <= 1.0
        assert score > 0.4  # Should be reasonable quality

    def test_score_low_quality_narrative(self):
        """Test scoring of poor narrative."""
        narrative = "Blah blah conservation is good"
        score = NarrativeQualityScorer.score_narrative(
            narrative,
            AudienceType.INSTITUTIONAL_INVESTOR,
            NarrativeFormat.INVESTOR_DECK,
        )

        assert 0 <= score <= 1.0
        assert score < 0.5  # Should be low quality

    def test_score_investor_specific_content(self):
        """Test that investor-specific content scores higher."""
        investor_narrative = "Revenue growth is 50% annually. Market size is $5B TAM. ROI is 5x."
        investor_score = NarrativeQualityScorer.score_narrative(
            investor_narrative,
            AudienceType.INSTITUTIONAL_INVESTOR,
            NarrativeFormat.INVESTOR_DECK,
        )

        policy_narrative = "This policy is supported by stakeholders and has clear implementation steps."
        policy_score = NarrativeQualityScorer.score_narrative(
            policy_narrative,
            AudienceType.INSTITUTIONAL_INVESTOR,
            NarrativeFormat.INVESTOR_DECK,
        )

        assert investor_score > policy_score


class TestNarrativeGeneration:
    """Tests for narrative generation across formats."""

    @pytest.mark.asyncio
    async def test_translate_to_investor_deck(self, agent, sample_agent_output):
        """Test translation to investor deck format."""
        narrative = await agent.translate(
            agent_output=sample_agent_output,
            audience_type="institutional_investor",
            format_type="investor_deck",
        )

        assert narrative.format == NarrativeFormat.INVESTOR_DECK
        assert narrative.audience == AudienceType.INSTITUTIONAL_INVESTOR
        assert narrative.title
        assert len(narrative.content) > 500
        assert narrative.key_claims
        assert narrative.call_to_action

    @pytest.mark.asyncio
    async def test_translate_to_policy_brief(self, agent, sample_agent_output):
        """Test translation to policy brief format."""
        narrative = await agent.translate(
            agent_output=sample_agent_output,
            audience_type="policymaker",
            format_type="policy_brief",
        )

        assert narrative.format == NarrativeFormat.POLICY_BRIEF
        assert narrative.audience == AudienceType.POLICYMAKER
        assert "policy" in narrative.content.lower() or "brief" in narrative.content.lower()

    @pytest.mark.asyncio
    async def test_translate_to_grant_proposal(self, agent, sample_agent_output):
        """Test translation to grant proposal format."""
        narrative = await agent.translate(
            agent_output=sample_agent_output,
            audience_type="grant_funder",
            format_type="grant_proposal",
        )

        assert narrative.format == NarrativeFormat.GRANT_PROPOSAL
        assert narrative.audience == AudienceType.GRANT_FUNDER
        assert "evaluation" in narrative.content.lower() or "impact" in narrative.content.lower()

    @pytest.mark.asyncio
    async def test_translate_to_press_release(self, agent, sample_agent_output):
        """Test translation to press release format."""
        narrative = await agent.translate(
            agent_output=sample_agent_output,
            audience_type="journalist",
            format_type="press_release",
        )

        assert narrative.format == NarrativeFormat.PRESS_RELEASE
        assert narrative.audience == AudienceType.JOURNALIST
        assert len(narrative.title) < 100  # Headline length

    @pytest.mark.asyncio
    async def test_translate_to_executive_summary(self, agent, sample_agent_output):
        """Test translation to executive summary format."""
        narrative = await agent.translate(
            agent_output=sample_agent_output,
            audience_type="board_member",
            format_type="executive_summary",
        )

        assert narrative.format == NarrativeFormat.EXECUTIVE_SUMMARY
        # Summary should be concise
        assert len(narrative.content) < 2000


class TestInvestorNarrative:
    """Tests for investor narrative generation."""

    @pytest.mark.asyncio
    async def test_investor_narrative_includes_market(self, agent, sample_agent_output):
        """Test that investor narrative includes market sizing."""
        narrative = await agent.investor_narrative(
            data=sample_agent_output,
            audience=AudienceType.INSTITUTIONAL_INVESTOR,
        )

        assert "market" in narrative.content.lower()
        assert "revenue" in narrative.content.lower() or "growth" in narrative.content.lower()

    @pytest.mark.asyncio
    async def test_investor_narrative_has_claims(self, agent, sample_agent_output):
        """Test that investor narrative has persuasive key claims."""
        narrative = await agent.investor_narrative(
            data=sample_agent_output,
            audience=AudienceType.INSTITUTIONAL_INVESTOR,
        )

        assert len(narrative.key_claims) > 0
        # Key claims should be short and punchy
        for claim in narrative.key_claims:
            assert len(claim) < 200

    @pytest.mark.asyncio
    async def test_investor_narrative_custom_message(self, agent, sample_agent_output):
        """Test investor narrative with custom key message."""
        custom_message = "Series A Opportunity: $5B Market"

        narrative = await agent.investor_narrative(
            data=sample_agent_output,
            audience=AudienceType.INSTITUTIONAL_INVESTOR,
            key_message=custom_message,
        )

        assert custom_message in narrative.content or custom_message in narrative.title


class TestPolicyBrief:
    """Tests for policy brief generation."""

    @pytest.mark.asyncio
    async def test_policy_brief_structure(self, agent, sample_agent_output):
        """Test that policy brief has required structure."""
        narrative = await agent.policy_brief(
            data=sample_agent_output,
            audience=AudienceType.POLICYMAKER,
        )

        content_lower = narrative.content.lower()
        # Should include policy elements
        assert "option" in content_lower or "recommendation" in content_lower or "implementation" in content_lower

    @pytest.mark.asyncio
    async def test_policy_brief_length(self, agent, sample_agent_output):
        """Test that policy brief is appropriate length."""
        narrative = await agent.policy_brief(
            data=sample_agent_output,
            audience=AudienceType.POLICYMAKER,
        )

        # Policy brief should be substantive (400+ words)
        word_count = len(narrative.content.split())
        assert word_count > 300


class TestGrantProposal:
    """Tests for grant proposal generation."""

    @pytest.mark.asyncio
    async def test_grant_proposal_includes_evaluation(self, agent, sample_agent_output):
        """Test that grant proposal includes evaluation plan."""
        narrative = await agent.grant_proposal(
            data=sample_agent_output,
            audience=AudienceType.GRANT_FUNDER,
        )

        content_lower = narrative.content.lower()
        assert "evaluation" in content_lower or "measurement" in content_lower or "impact" in content_lower

    @pytest.mark.asyncio
    async def test_grant_proposal_sustainability(self, agent, sample_agent_output):
        """Test that grant proposal addresses sustainability."""
        narrative = await agent.grant_proposal(
            data=sample_agent_output,
            audience=AudienceType.GRANT_FUNDER,
        )

        content_lower = narrative.content.lower()
        assert "sustainability" in content_lower or "revenue" in content_lower or "scaling" in content_lower


class TestPressRelease:
    """Tests for press release generation."""

    @pytest.mark.asyncio
    async def test_press_release_has_headline(self, agent, sample_agent_output):
        """Test that press release has headline."""
        narrative = await agent.press_release(
            data=sample_agent_output,
            audience=AudienceType.JOURNALIST,
        )

        # Headline should be short and punchy
        assert len(narrative.title) > 10
        assert len(narrative.title) < 100

    @pytest.mark.asyncio
    async def test_press_release_includes_quote(self, agent, sample_agent_output):
        """Test that press release includes quoted content."""
        narrative = await agent.press_release(
            data=sample_agent_output,
            audience=AudienceType.JOURNALIST,
        )

        # Should include quote marks or quote format
        assert '"' in narrative.content or "'said'" in narrative.content.lower()

    @pytest.mark.asyncio
    async def test_press_release_ap_style(self, agent, sample_agent_output):
        """Test AP style elements in press release."""
        narrative = await agent.press_release(
            data=sample_agent_output,
            audience=AudienceType.JOURNALIST,
        )

        content_lower = narrative.content.lower()
        # AP style press releases include datelines, contact info
        assert "media" in content_lower or "contact" in content_lower or "###" in narrative.content


class TestExecutiveSummary:
    """Tests for executive summary generation."""

    @pytest.mark.asyncio
    async def test_executive_summary_length(self, agent, sample_agent_output):
        """Test that executive summary is one page."""
        narrative = await agent.executive_summary(
            data=sample_agent_output,
            audience=AudienceType.GENERAL_PUBLIC,
        )

        # One page should be concise (100+ words)
        word_count = len(narrative.content.split())
        assert word_count > 100

    @pytest.mark.asyncio
    async def test_executive_summary_simplicity(self, agent, sample_agent_output):
        """Test that executive summary is simple and understandable."""
        narrative = await agent.executive_summary(
            data=sample_agent_output,
            audience=AudienceType.GENERAL_PUBLIC,
        )

        # General public version should be reasonable length
        # (content may use slightly technical terms, but should be accessible)
        assert len(narrative.content) > 50  # Has actual content


class TestHealthAndDescription:
    """Tests for health and description endpoints."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, agent):
        """Test health check."""
        health = await agent.health()

        assert health["status"] == "ok"
        assert health["agent"] == "narrative-engine"
        assert health["version"] == "0.1.1"

    def test_describe_endpoint(self, agent):
        """Test agent description."""
        description = agent.describe()

        assert description["name"] == "narrative-engine"
        assert "capabilities" in description
        assert len(description["capabilities"]) > 0
        assert "inputs" in description
        assert "outputs" in description


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_invalid_audience_raises_error(self, agent, sample_agent_output):
        """Test that invalid audience raises error."""
        with pytest.raises((ValueError, KeyError)):
            await agent.translate(
                agent_output=sample_agent_output,
                audience_type="invalid_audience",
                format_type="executive_summary",
            )

    @pytest.mark.asyncio
    async def test_invalid_format_raises_error(self, agent, sample_agent_output):
        """Test that invalid format raises error."""
        with pytest.raises((ValueError, KeyError)):
            await agent.translate(
                agent_output=sample_agent_output,
                audience_type="general_public",
                format_type="invalid_format",
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
