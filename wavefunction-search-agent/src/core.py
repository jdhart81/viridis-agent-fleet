"""
Wavefunction Search Core — Quantum Cognition Routing Infrastructure

Routes users through intention discovery to semantically and constitutionally aligned collectives.

Core Pipeline: INTAKE → COLLAPSE → MATCH → ROUTE
"""

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
import asyncio

from src.validation import validate_process_input

logger = logging.getLogger(__name__)

VERSION = "0.2.0"

_DOMAIN_ALIASES = {
    "agriculture": "agriculture",
    "agricultural": "agriculture",
    "farm": "agriculture",
    "farmer": "agriculture",
    "farmers": "agriculture",
    "soil": "soil",
    "soils": "soil",
    "carbon": "climate",
    "climate": "climate",
    "emission": "climate",
    "emissions": "climate",
    "community": "community",
    "communities": "community",
    "cooperative": "community",
    "governance": "governance",
    "democratic": "governance",
    "watershed": "water",
    "watersheds": "water",
    "water": "water",
    "forest": "forest",
    "forests": "forest",
    "forestry": "forest",
    "energy": "energy",
    "compliance": "compliance",
    "regulation": "compliance",
    "regulations": "compliance",
    "regulatory": "compliance",
    "finance": "finance",
    "financial": "finance",
    "investment": "finance",
    "investing": "finance",
    "mining": "mining",
    "industrial": "industry",
    "industry": "industry",
    "action": "action",
}

_FALLBACK_DOMAIN_DISTRIBUTION = {
    "mind": 0.2,
    "body": 0.2,
    "heart": 0.3,
    "spirit": 0.15,
    "action": 0.15,
}


class ConstitutionalAxis(str, Enum):
    """Constitutional alignment criteria."""
    BIOSPHERE_RESTORATION = "c1_biosphere"
    DEMOCRATIC_GOVERNANCE = "c2_governance"
    TRANSPARENCY = "c3_transparency"
    LONG_TERM_FLOURISHING = "c4_long_term"


@dataclass
class UserWavefunction:
    """User cognitive state in superposition."""
    user_id: str
    explicit_intentions: List[str]
    implicit_patterns: List[str]
    value_vector: Dict[str, float]
    domain_distribution: Dict[str, float]
    shadow_patterns: List[str]
    transformation_history: List[str]
    confidence: float = 0.5
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CollectiveProfile:
    """Registered collective mission and values."""
    collective_id: str
    name: str
    mission: str
    domain_profile: Dict[str, float]
    value_vector: Dict[str, float]
    constitutional_scores: Dict[str, float]
    capacity: int
    current_members: int
    description: str
    created_at: datetime = field(default_factory=datetime.utcnow)


class WavefunctionSearchCore:
    """Routes users through intention discovery to aligned collectives."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize routing engine."""
        self.config = config or {}
        self.logger = logging.getLogger(__name__)

        self.user_wavefunctions: Dict[str, UserWavefunction] = {}
        self.collectives: Dict[str, CollectiveProfile] = {}
        self.routing_history: List[Dict[str, Any]] = []

        self.constitutional_weights = {
            ConstitutionalAxis.BIOSPHERE_RESTORATION: 0.35,
            ConstitutionalAxis.DEMOCRATIC_GOVERNANCE: 0.25,
            ConstitutionalAxis.TRANSPARENCY: 0.25,
            ConstitutionalAxis.LONG_TERM_FLOURISHING: 0.15
        }
        self.constitutional_threshold = 0.5
        self.alignment_threshold = 0.65

        self.logger.info("Initialized Wavefunction Search v%s", VERSION)

    @staticmethod
    def _dialogue_domain_distribution(
            dialogue_history: List[Dict[str, str]]) -> Dict[str, float]:
        """Extract a deterministic routing vector from user-authored dialogue."""
        weights: Dict[str, float] = {}
        for message in dialogue_history:
            if message.get("role") != "user":
                continue
            for token in re.findall(
                    r"[a-z0-9]+", str(message.get("content", "")).lower()):
                domain = _DOMAIN_ALIASES.get(token)
                if domain:
                    weights[domain] = weights.get(domain, 0.0) + 1.0
        total = sum(weights.values())
        if total <= 0:
            return dict(_FALLBACK_DOMAIN_DISTRIBUTION)
        return {
            domain: weight / total
            for domain, weight in sorted(weights.items())
        }

    async def intake_dialogue(self, user_id: str, dialogue_history: List[Dict[str, str]]) -> UserWavefunction:
        """Stage 1: INTAKE — Transform surface desire into structured intention."""
        wavefunction = UserWavefunction(
            user_id=user_id,
            explicit_intentions=[],
            implicit_patterns=[],
            value_vector={},
            domain_distribution=self._dialogue_domain_distribution(
                dialogue_history),
            shadow_patterns=[],
            transformation_history=[]
        )

        for msg in dialogue_history:
            if msg.get("role") == "user":
                text = msg.get("content", "").lower()
                if "climate" in text or "carbon" in text:
                    wavefunction.explicit_intentions.append("climate_action")
                if "community" in text:
                    wavefunction.explicit_intentions.append("community_building")

        wavefunction.explicit_intentions = list(dict.fromkeys(
            wavefunction.explicit_intentions))
        wavefunction.confidence = min(
            1.0, len(wavefunction.explicit_intentions) / 3.0)
        self.user_wavefunctions[user_id] = wavefunction
        return wavefunction

    async def collapse_intention(self, user_id: str, stake_amount: float) -> Dict[str, Any]:
        """Stage 2: COLLAPSE — Finalize wavefunction collapse (user commitment)."""
        if user_id not in self.user_wavefunctions:
            return {"status": "error", "reason": "User not in intake stage"}

        wavefunction = self.user_wavefunctions[user_id]
        intention_record = {
            "user_id": user_id,
            "collapsed_intentions": wavefunction.explicit_intentions,
            "stake_amount": stake_amount,
            "collapsed_at": datetime.utcnow().isoformat()
        }

        return {"status": "ok", "intention_record": intention_record}

    def compute_constitutional_score(self, collective: CollectiveProfile) -> float:
        """Score collective against constitutional criteria."""
        by_prefix = {
            str(key).split("_", 1)[0]: value
            for key, value in collective.constitutional_scores.items()
        }
        required = {
            "c1": ConstitutionalAxis.BIOSPHERE_RESTORATION,
            "c2": ConstitutionalAxis.DEMOCRATIC_GOVERNANCE,
            "c3": ConstitutionalAxis.TRANSPARENCY,
            "c4": ConstitutionalAxis.LONG_TERM_FLOURISHING,
        }
        if not all(prefix in by_prefix for prefix in required):
            return 0.0
        score = sum(
            self.constitutional_weights[axis]
            * min(1.0, max(0.0, float(by_prefix[prefix])))
            for prefix, axis in required.items()
        )
        return min(1.0, max(0.0, score))

    def compute_alignment_score(self, user_wavefunction: UserWavefunction, collective: CollectiveProfile) -> float:
        """Score dialogue-conditioned domain alignment with cosine similarity."""
        domains = sorted(set(user_wavefunction.domain_distribution)
                         | set(collective.domain_profile))
        user = []
        candidate = []
        for domain in domains:
            try:
                user_value = float(
                    user_wavefunction.domain_distribution.get(domain, 0.0))
                candidate_value = float(
                    collective.domain_profile.get(domain, 0.0))
            except (TypeError, ValueError):
                user_value = candidate_value = 0.0
            user.append(user_value if math.isfinite(user_value)
                        and user_value > 0 else 0.0)
            candidate.append(candidate_value if math.isfinite(candidate_value)
                             and candidate_value > 0 else 0.0)
        user_norm = math.sqrt(sum(value * value for value in user))
        candidate_norm = math.sqrt(
            sum(value * value for value in candidate))
        if user_norm == 0.0 or candidate_norm == 0.0:
            return 0.0
        score = sum(
            left * right for left, right in zip(user, candidate)
        ) / (user_norm * candidate_norm)
        return min(1.0, max(0.0, score))

    async def find_matches(self, user_id: str) -> List[Dict[str, Any]]:
        """Stage 4: ROUTE — Find and rank matches."""
        if user_id not in self.user_wavefunctions:
            return []

        user_wavefunction = self.user_wavefunctions[user_id]
        matches = []

        for collective_id, collective in self.collectives.items():
            constitutional_score = self.compute_constitutional_score(collective)
            if constitutional_score < self.constitutional_threshold:
                continue

            alignment_score = self.compute_alignment_score(user_wavefunction, collective)
            if alignment_score < self.alignment_threshold:
                continue

            if collective.current_members >= collective.capacity:
                continue

            combined_score = (alignment_score * 0.6) + (constitutional_score * 0.4)
            matches.append({
                "collective_id": collective_id,
                "name": collective.name,
                "alignment_score": alignment_score,
                "constitutional_score": constitutional_score,
                "combined_score": combined_score
            })

        matches.sort(key=lambda m: m["combined_score"], reverse=True)
        total_score = sum(match["combined_score"] for match in matches)
        for match in matches:
            match["routing_probability"] = (
                match["combined_score"] / total_score
                if total_score > 0 else 0.0)
        return matches

    def register_collective(self, collective_id: str, name: str, mission: str,
                          domain_profile: Dict[str, float],
                          constitutional_scores: Dict[str, float],
                          capacity: int) -> CollectiveProfile:
        """Register a collective."""
        collective = CollectiveProfile(
            collective_id=collective_id,
            name=name,
            mission=mission,
            domain_profile=domain_profile,
            value_vector={},
            constitutional_scores=constitutional_scores,
            capacity=capacity,
            current_members=0,
            description=""
        )
        self.collectives[collective_id] = collective
        return collective

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Main processing entry point."""
        # --- Validation gate ---
        errors, warnings = validate_process_input(input_data)
        if errors:
            return {
                "status": "error",
                "reason": "Validation failed",
                "errors": [e.to_dict() for e in errors],
                "warnings": [w.to_dict() for w in warnings],
            }
        if warnings:
            self.logger.warning("Validation warnings: %s", [w.to_dict() for w in warnings])

        try:
            stage = input_data.get("stage", "find_matches")

            if stage == "intake":
                wavefunction = await self.intake_dialogue(
                    input_data.get("user_id"),
                    input_data.get("dialogue", [])
                )
                return {
                    "status": "ok",
                    "stage": "intake",
                    "wavefunction": {
                        "user_id": wavefunction.user_id,
                        "intentions": wavefunction.explicit_intentions,
                        "confidence": wavefunction.confidence
                    }
                }

            elif stage == "collapse":
                return await self.collapse_intention(
                    input_data.get("user_id"),
                    input_data.get("stake_amount", 100.0)
                )

            elif stage == "find_matches":
                matches = await self.find_matches(input_data.get("user_id"))
                return {
                    "status": "ok",
                    "stage": "route",
                    "matches": matches
                }

            else:
                return {"status": "error", "reason": f"Unknown stage: {stage}"}

        except Exception as e:
            self.logger.error(f"Error in process: {e}", exc_info=True)
            return {"status": "error", "reason": str(e)}
