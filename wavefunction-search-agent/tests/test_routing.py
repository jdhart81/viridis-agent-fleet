"""
Tests for Wavefunction Search routing engine.

Covers intention capture, constitutional matching, semantic alignment,
and routing probability amplitude normalization.
"""

import pytest
import asyncio
from src.core import (
    WavefunctionSearchCore, UserWavefunction, CollectiveProfile, ConstitutionalAxis
)


@pytest.fixture
def wavefunction_engine():
    """Create a Wavefunction Search instance."""
    return WavefunctionSearchCore()


class TestIntakeCapsule:
    """Tests for INTAKE stage (intention discovery)."""

    @pytest.mark.asyncio
    async def test_intake_extracts_explicit_intentions(self, wavefunction_engine):
        """Test that intake dialogue extracts clear intentions."""
        dialogue = [
            {"role": "user", "content": "I want to help restore climate and carbon systems"},
            {"role": "assistant", "content": "Tell me more about your vision"},
            {"role": "user", "content": "I'm passionate about climate action and soil carbon"}
        ]

        wavefunction = await wavefunction_engine.intake_dialogue("user123", dialogue)

        assert "climate_action" in wavefunction.explicit_intentions
        assert wavefunction.user_id == "user123"
        assert wavefunction.confidence > 0.0

    @pytest.mark.asyncio
    async def test_intake_builds_confidence_with_clarity(self, wavefunction_engine):
        """Test that confidence increases with more explicit intentions."""
        dialogue_clear = [
            {"role": "user", "content": "I want climate action and community building"}
        ]

        wavefunction_clear = await wavefunction_engine.intake_dialogue("user_clear", dialogue_clear)

        dialogue_vague = [
            {"role": "user", "content": "Um, I want to help somehow"}
        ]

        wavefunction_vague = await wavefunction_engine.intake_dialogue("user_vague", dialogue_vague)

        assert wavefunction_clear.confidence >= wavefunction_vague.confidence

    @pytest.mark.asyncio
    async def test_intake_detects_community_intent(self, wavefunction_engine):
        """Test detection of community-focused intentions."""
        dialogue = [
            {"role": "user", "content": "I love working with community members"}
        ]

        wavefunction = await wavefunction_engine.intake_dialogue("community_user", dialogue)

        assert "community_building" in wavefunction.explicit_intentions


class TestCollapseCapsule:
    """Tests for COLLAPSE stage (commitment)."""

    @pytest.mark.asyncio
    async def test_collapse_requires_intake_first(self, wavefunction_engine):
        """Test that collapse fails if user never went through intake."""
        result = await wavefunction_engine.collapse_intention("unknown_user", 100.0)

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_collapse_records_stake(self, wavefunction_engine):
        """Test that stake commitment is recorded."""
        await wavefunction_engine.intake_dialogue("staker", [
            {"role": "user", "content": "climate action"}
        ])

        result = await wavefunction_engine.collapse_intention("staker", 500.0)

        assert result["status"] == "ok"
        record = result["intention_record"]
        assert record["user_id"] == "staker"
        assert record["stake_amount"] == 500.0
        assert "collapsed_intentions" in record

    @pytest.mark.asyncio
    async def test_collapse_creates_immutable_record(self, wavefunction_engine):
        """Test that collapsed state is immutable."""
        await wavefunction_engine.intake_dialogue("immutable_user", [
            {"role": "user", "content": "climate and community"}
        ])

        result = await wavefunction_engine.collapse_intention("immutable_user", 200.0)

        record = result["intention_record"]
        assert "collapsed_at" in record
        assert isinstance(record["collapsed_at"], str)


class TestConstitutionalScoring:
    """Tests for constitutional alignment scoring."""

    def test_constitutional_score_in_valid_range(self, wavefunction_engine):
        """Test that constitutional score is in [0, 1]."""
        collective = CollectiveProfile(
            collective_id="test",
            name="Test Collective",
            mission="Test mission",
            domain_profile={},
            value_vector={},
            constitutional_scores={
                "c1": 0.8,
                "c2": 0.7,
                "c3": 0.9,
                "c4": 0.6
            },
            capacity=50,
            current_members=10,
            description=""
        )

        score = wavefunction_engine.compute_constitutional_score(collective)
        assert 0.0 <= score <= 1.0

    def test_high_constitutional_alignment(self, wavefunction_engine):
        """Test scoring of highly aligned collective."""
        collective = CollectiveProfile(
            collective_id="aligned",
            name="Highly Aligned",
            mission="Restore biosphere",
            domain_profile={},
            value_vector={},
            constitutional_scores={
                "c1": 0.95,  # Biosphere restoration
                "c2": 0.90,  # Democratic governance
                "c3": 0.95,  # Transparency
                "c4": 0.90   # Long-term
            },
            capacity=100,
            current_members=50,
            description=""
        )

        score = wavefunction_engine.compute_constitutional_score(collective)
        assert score > 0.8

    def test_low_constitutional_alignment(self, wavefunction_engine):
        """Test scoring of poorly aligned collective."""
        collective = CollectiveProfile(
            collective_id="misaligned",
            name="Misaligned",
            mission="Extractive",
            domain_profile={},
            value_vector={},
            constitutional_scores={
                "c1": 0.1,   # Poor biosphere focus
                "c2": 0.2,   # Poor governance
                "c3": 0.15,  # Poor transparency
                "c4": 0.1    # Poor long-term
            },
            capacity=50,
            current_members=10,
            description=""
        )

        score = wavefunction_engine.compute_constitutional_score(collective)
        assert score < 0.3


class TestSemanticAlignment:
    """Tests for semantic/domain alignment scoring."""

    def test_alignment_score_in_valid_range(self, wavefunction_engine):
        """Test that alignment score is in [0, 1]."""
        wavefunction = UserWavefunction(
            user_id="user",
            explicit_intentions=["climate_action"],
            implicit_patterns=[],
            value_vector={},
            domain_distribution={"mind": 0.3, "body": 0.1, "heart": 0.4, "spirit": 0.1, "action": 0.1},
            shadow_patterns=[],
            transformation_history=[]
        )

        collective = CollectiveProfile(
            collective_id="collective",
            name="Test",
            mission="Climate restoration",
            domain_profile={"mind": 0.2, "body": 0.1, "heart": 0.4, "spirit": 0.2, "action": 0.1},
            value_vector={},
            constitutional_scores={},
            capacity=50,
            current_members=10,
            description=""
        )

        score = wavefunction_engine.compute_alignment_score(wavefunction, collective)
        assert 0.0 <= score <= 1.0

    def test_high_domain_overlap(self, wavefunction_engine):
        """Test scoring when user and collective have aligned domains."""
        wavefunction = UserWavefunction(
            user_id="aligned_user",
            explicit_intentions=["climate_action"],
            implicit_patterns=[],
            value_vector={},
            domain_distribution={"mind": 0.2, "body": 0.2, "heart": 0.3, "spirit": 0.15, "action": 0.15},
            shadow_patterns=[],
            transformation_history=[]
        )

        collective = CollectiveProfile(
            collective_id="aligned_collective",
            name="Aligned",
            mission="Climate",
            domain_profile={"mind": 0.2, "body": 0.2, "heart": 0.3, "spirit": 0.15, "action": 0.15},
            value_vector={},
            constitutional_scores={},
            capacity=100,
            current_members=50,
            description=""
        )

        score = wavefunction_engine.compute_alignment_score(wavefunction, collective)
        assert score == pytest.approx(1.0)

    def test_low_domain_overlap(self, wavefunction_engine):
        """Test scoring when domains are misaligned."""
        wavefunction = UserWavefunction(
            user_id="misaligned_user",
            explicit_intentions=["climate_action"],
            implicit_patterns=[],
            value_vector={},
            domain_distribution={"mind": 0.8, "body": 0.1, "heart": 0.05, "spirit": 0.03, "action": 0.02},
            shadow_patterns=[],
            transformation_history=[]
        )

        collective = CollectiveProfile(
            collective_id="misaligned_collective",
            name="Different",
            mission="Tech",
            domain_profile={"mind": 0.1, "body": 0.1, "heart": 0.1, "spirit": 0.1, "action": 0.6},
            value_vector={},
            constitutional_scores={},
            capacity=100,
            current_members=50,
            description=""
        )

        score = wavefunction_engine.compute_alignment_score(wavefunction, collective)
        assert score < 0.5


class TestRoutingMatching:
    """Tests for the full routing pipeline."""

    @pytest.mark.asyncio
    async def test_find_matches_enforces_constitutional_threshold(self, wavefunction_engine):
        """Test that matching requires constitutional score ≥ 0.5."""
        await wavefunction_engine.intake_dialogue("router", [
            {"role": "user", "content": "climate action"}
        ])

        # Register bad collective (fails constitutional threshold)
        wavefunction_engine.register_collective(
            "bad",
            "Bad Collective",
            "Bad mission",
            {"mind": 0.2, "body": 0.2, "heart": 0.2, "spirit": 0.2, "action": 0.2},
            {"c1": 0.1, "c2": 0.1, "c3": 0.1, "c4": 0.1},
            100
        )

        matches = await wavefunction_engine.find_matches("router")

        # Should not include bad collective
        assert not any(m["collective_id"] == "bad" for m in matches)

    @pytest.mark.asyncio
    async def test_find_matches_returns_ranked_results(self, wavefunction_engine):
        """Test that matches are ranked by combined score."""
        await wavefunction_engine.intake_dialogue("ranker", [
            {"role": "user", "content": "climate action"}
        ])

        # Register two good collectives with different scores
        wavefunction_engine.register_collective(
            "good1",
            "Good One",
            "Climate mission",
            {"mind": 0.2, "body": 0.2, "heart": 0.3, "spirit": 0.15, "action": 0.15},
            {"c1": 0.9, "c2": 0.8, "c3": 0.9, "c4": 0.8},
            100
        )

        wavefunction_engine.register_collective(
            "good2",
            "Good Two",
            "Climate mission",
            {"mind": 0.1, "body": 0.1, "heart": 0.2, "spirit": 0.1, "action": 0.5},
            {"c1": 0.85, "c2": 0.75, "c3": 0.85, "c4": 0.75},
            100
        )

        matches = await wavefunction_engine.find_matches("ranker")

        if len(matches) > 1:
            # Verify ranking: first should score higher
            assert matches[0]["combined_score"] >= matches[1]["combined_score"]

    @pytest.mark.asyncio
    async def test_find_matches_respects_capacity(self, wavefunction_engine):
        """Test that full collectives are excluded from matches."""
        await wavefunction_engine.intake_dialogue("capacity_user", [
            {"role": "user", "content": "climate"}
        ])

        # Register at-capacity collective
        full_collective = wavefunction_engine.register_collective(
            "full",
            "Full Collective",
            "Full",
            {"mind": 0.2, "body": 0.2, "heart": 0.3, "spirit": 0.15, "action": 0.15},
            {"c1": 0.9, "c2": 0.8, "c3": 0.9, "c4": 0.8},
            10
        )
        full_collective.current_members = 10

        matches = await wavefunction_engine.find_matches("capacity_user")

        # Should not include full collective
        assert not any(m["collective_id"] == "full" for m in matches)


class TestProbabilityNormalization:
    """Tests for quantum probability normalization."""

    @pytest.mark.asyncio
    async def test_routing_scores_sum_meaningfully(self, wavefunction_engine):
        """Test that routing score distributions are normalized."""
        await wavefunction_engine.intake_dialogue("normer", [
            {"role": "user", "content": "climate"}
        ])

        # Register multiple collectives
        for i in range(3):
            wavefunction_engine.register_collective(
                f"coll{i}",
                f"Collective {i}",
                f"Mission {i}",
                {"mind": 0.2, "body": 0.2, "heart": 0.3, "spirit": 0.15, "action": 0.15},
                {"c1": 0.8 + i*0.05, "c2": 0.7 + i*0.05, "c3": 0.8 + i*0.05, "c4": 0.7 + i*0.05},
                100
            )

        matches = await wavefunction_engine.find_matches("normer")

        # All scores should be in [0, 1]
        for match in matches:
            assert 0.0 <= match["alignment_score"] <= 1.0
            assert 0.0 <= match["constitutional_score"] <= 1.0
            assert 0.0 <= match["combined_score"] <= 1.0
            assert 0.0 <= match["routing_probability"] <= 1.0
        if matches:
            assert sum(match["routing_probability"] for match in matches) == (
                pytest.approx(1.0))
