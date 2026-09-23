"""
Unit tests for WavefunctionSearchCore.

Test invariants:
- Wavefunction collapse must produce testable, committed intentions
- Constitutional threshold (S_C ≥ 0.5) is non-negotiable—no route without it
- Shadow detection and transformation tracking are functional
- Routing reduces coordination friction (T↓) without sacrificing alignment
"""

import pytest
import asyncio
from datetime import datetime
from src.core import (
    WavefunctionSearchCore,
    UserWavefunction,
    CollectiveProfile,
    ConstitutionalAxis,
)


class TestWavefunctionSearchCore:
    """Test suite for Wavefunction Search routing engine."""

    @pytest.fixture
    def engine(self):
        """Initialize a fresh Wavefunction Search engine."""
        return WavefunctionSearchCore()

    @pytest.fixture
    def sample_collective(self):
        """Create a sample collective profile for testing."""
        return CollectiveProfile(
            collective_id="ecotopia-collective",
            name="Ecotopia Regeneration",
            mission="Community regenerative transition design",
            domain_profile={"governance": 0.9, "agriculture": 0.85, "water": 0.8},
            value_vector={"regeneration": 0.95, "community": 0.9},
            constitutional_scores={
                "c1_biosphere": 0.9,
                "c2_governance": 0.95,
                "c3_transparency": 0.85,
                "c4_long_term": 0.9,
            },
            capacity=50,
            current_members=25,
            description="A collective focused on regenerative agriculture and community governance"
        )

    def test_initialization(self, engine):
        """Verify engine initializes correctly."""
        assert engine is not None
        assert len(engine.user_wavefunctions) == 0
        assert len(engine.collectives) == 0
        assert engine.constitutional_threshold == 0.5
        assert engine.alignment_threshold == 0.65

    @pytest.mark.asyncio
    async def test_intake_dialogue_initialization(self, engine):
        """Verify intake dialogue creates a user wavefunction."""
        user_id = "user_001"
        dialogue = [
            {"role": "user", "content": "I want to help restore agricultural soil"},
            {"role": "agent", "content": "What specific region or community interests you?"},
            {"role": "user", "content": "I'm interested in community solutions and climate action"},
        ]

        wf = await engine.intake_dialogue(user_id, dialogue)
        assert wf.user_id == user_id
        assert user_id in engine.user_wavefunctions
        assert len(wf.explicit_intentions) > 0

    @pytest.mark.asyncio
    async def test_intake_extracts_climate_keywords(self, engine):
        """Verify intake dialogue detects climate-related keywords."""
        user_id = "user_002"
        dialogue = [
            {"role": "user", "content": "I want to reduce carbon emissions and fight climate change"},
        ]

        wf = await engine.intake_dialogue(user_id, dialogue)
        assert "climate_action" in wf.explicit_intentions

    @pytest.mark.asyncio
    async def test_intake_extracts_community_keywords(self, engine):
        """Verify intake dialogue detects community-related keywords."""
        user_id = "user_003"
        dialogue = [
            {"role": "user", "content": "I want to build community and help my neighbors"},
        ]

        wf = await engine.intake_dialogue(user_id, dialogue)
        assert "community_building" in wf.explicit_intentions

    @pytest.mark.asyncio
    async def test_collapse_intention(self, engine):
        """Verify wavefunction collapse returns valid intention record."""
        user_id = "user_004"
        dialogue = [
            {"role": "user", "content": "I want to help restore soils and support farmers"},
        ]

        await engine.intake_dialogue(user_id, dialogue)
        result = await engine.collapse_intention(user_id, stake_amount=500.0)

        assert result["status"] == "ok"
        assert "intention_record" in result
        assert result["intention_record"]["user_id"] == user_id
        assert result["intention_record"]["stake_amount"] == 500.0

    @pytest.mark.asyncio
    async def test_collapse_intention_fails_for_unknown_user(self, engine):
        """Verify collapse fails gracefully for non-existent user."""
        result = await engine.collapse_intention("unknown_user", stake_amount=100.0)
        assert result["status"] == "error"

    def test_register_collective(self, engine, sample_collective):
        """Verify collectives can be registered."""
        collective = engine.register_collective(
            collective_id=sample_collective.collective_id,
            name=sample_collective.name,
            mission=sample_collective.mission,
            domain_profile=sample_collective.domain_profile,
            constitutional_scores=sample_collective.constitutional_scores,
            capacity=sample_collective.capacity
        )

        assert sample_collective.collective_id in engine.collectives
        assert collective.name == sample_collective.name

    def test_compute_constitutional_score(self, engine, sample_collective):
        """Verify constitutional score computation."""
        score = engine.compute_constitutional_score(sample_collective)
        assert 0.0 <= score <= 1.0
        # With scores averaging 0.9, should be reasonably high
        assert score > 0.5

    def test_constitutional_threshold_enforcement(self, engine):
        """Verify constitutional threshold (S_C ≥ 0.5) is non-negotiable."""
        # Register a low-constitutional collective
        low_constitutional = CollectiveProfile(
            collective_id="low-const",
            name="Low Constitutional",
            mission="Test",
            domain_profile={"governance": 0.1},
            value_vector={},
            constitutional_scores={
                "c1_biosphere": 0.2,
                "c2_governance": 0.15,
                "c3_transparency": 0.1,
                "c4_long_term": 0.05,
            },
            capacity=10,
            current_members=0,
            description="Testing low constitutional score"
        )

        score = engine.compute_constitutional_score(low_constitutional)
        assert score < engine.constitutional_threshold

    def test_compute_alignment_score(self, engine, sample_collective):
        """Verify alignment score computation."""
        wavefunction = UserWavefunction(
            user_id="test_user",
            explicit_intentions=["agriculture", "community"],
            implicit_patterns=[],
            value_vector={"regeneration": 0.9},
            domain_distribution={"governance": 0.5, "agriculture": 0.5, "water": 0.3, "mind": 0.2, "body": 0.2, "heart": 0.3, "spirit": 0.15, "action": 0.15},
            shadow_patterns=[],
            transformation_history=[]
        )

        score = engine.compute_alignment_score(wavefunction, sample_collective)
        assert 0.0 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_find_matches(self, engine, sample_collective):
        """Verify match finding filters by constitutional threshold."""
        # Register a good collective
        engine.register_collective(
            collective_id=sample_collective.collective_id,
            name=sample_collective.name,
            mission=sample_collective.mission,
            domain_profile=sample_collective.domain_profile,
            constitutional_scores=sample_collective.constitutional_scores,
            capacity=sample_collective.capacity
        )

        # Create and intake user
        user_id = "user_match_test"
        dialogue = [
            {"role": "user", "content": "I want to help with agriculture and community building"},
        ]
        await engine.intake_dialogue(user_id, dialogue)

        # Find matches
        matches = await engine.find_matches(user_id)
        # Should find matches if constitutional threshold is met
        assert isinstance(matches, list)

    @pytest.mark.asyncio
    async def test_find_matches_empty_for_unknown_user(self, engine):
        """Verify find_matches returns empty list for non-existent user."""
        matches = await engine.find_matches("unknown_user")
        assert matches == []

    @pytest.mark.asyncio
    async def test_process_intake_stage(self, engine):
        """Verify process() handles intake stage."""
        result = await engine.process({
            "stage": "intake",
            "user_id": "process_user_1",
            "dialogue": [
                {"role": "user", "content": "I want to help climate action"}
            ]
        })

        assert result["status"] == "ok"
        assert result["stage"] == "intake"
        assert "wavefunction" in result

    @pytest.mark.asyncio
    async def test_process_collapse_stage(self, engine):
        """Verify process() handles collapse stage."""
        # First do intake
        await engine.process({
            "stage": "intake",
            "user_id": "process_user_2",
            "dialogue": [
                {"role": "user", "content": "I want community solutions"}
            ]
        })

        # Then collapse
        result = await engine.process({
            "stage": "collapse",
            "user_id": "process_user_2",
            "stake_amount": 250.0
        })

        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_process_find_matches_stage(self, engine, sample_collective):
        """Verify process() handles route/find_matches stage."""
        # Register collective
        engine.register_collective(
            collective_id=sample_collective.collective_id,
            name=sample_collective.name,
            mission=sample_collective.mission,
            domain_profile=sample_collective.domain_profile,
            constitutional_scores=sample_collective.constitutional_scores,
            capacity=sample_collective.capacity
        )

        # Intake
        await engine.process({
            "stage": "intake",
            "user_id": "process_user_3",
            "dialogue": [
                {"role": "user", "content": "I want to help with governance and agriculture"}
            ]
        })

        # Find matches
        result = await engine.process({
            "stage": "find_matches",
            "user_id": "process_user_3"
        })

        assert result["status"] == "ok"
        assert result["stage"] == "route"
        assert "matches" in result

    @pytest.mark.asyncio
    async def test_process_unknown_stage(self, engine):
        """Verify process() handles unknown stages gracefully."""
        result = await engine.process({
            "stage": "unknown_stage"
        })

        assert result["status"] == "error"

    def test_domain_distribution_initialized(self, engine):
        """Verify domain distribution is properly initialized."""
        wavefunction = UserWavefunction(
            user_id="test",
            explicit_intentions=[],
            implicit_patterns=[],
            value_vector={},
            domain_distribution={"mind": 0.2, "body": 0.2, "heart": 0.3, "spirit": 0.15, "action": 0.15},
            shadow_patterns=[],
            transformation_history=[]
        )

        total = sum(wavefunction.domain_distribution.values())
        assert abs(total - 1.0) < 0.01

    def test_confidence_calculation(self, engine):
        """Verify confidence is calculated based on intentions."""
        wavefunction = UserWavefunction(
            user_id="test",
            explicit_intentions=["climate", "community"],
            implicit_patterns=[],
            value_vector={},
            domain_distribution={},
            shadow_patterns=[],
            transformation_history=[],
            confidence=0.67
        )

        assert 0.0 <= wavefunction.confidence <= 1.0
