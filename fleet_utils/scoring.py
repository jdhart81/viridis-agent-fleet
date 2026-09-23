"""
Fleet-wide scoring utilities.

Extracted from Energy AI (LeadQualityFactors) and Bounty Hunter (fit_score)
to provide reusable scoring patterns for any agent that evaluates entities.

Usage:
    # Boolean factor scoring (like Energy AI lead quality)
    scorer = WeightedBooleanScorer({
        "has_email": 20,
        "has_phone": 20,
        "is_homeowner": 20,
        "has_bill_data": 15,
    })
    score = scorer.score({"has_email": True, "has_phone": True, "is_homeowner": False})
    # → 40

    # Multi-factor weighted scoring (like Bounty Hunter qualification)
    scorer = MultiFactorScorer({
        "fit": 0.5,
        "capacity": 0.3,
        "alignment": 0.2,
    })
    score = scorer.score({"fit": 80, "capacity": 70, "alignment": 90})
    # → 77.0
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple


@dataclass
class WeightedBooleanScorer:
    """
    Score an entity by summing weights of boolean factors that are True.

    Pattern origin: Energy AI's LeadQualityFactors.
    Useful for: lead scoring, opportunity screening, eligibility checks.

    Invariant: weights sum defines the max score (capped at max_score).
    """

    weights: Dict[str, int]
    max_score: int = 100

    def score(self, factors: Dict[str, bool]) -> int:
        """
        Compute score from boolean factors.

        Args:
            factors: {factor_name: True/False}

        Returns:
            Integer score, 0 to max_score.
        """
        total = sum(
            self.weights.get(key, 0)
            for key, value in factors.items()
            if value
        )
        return min(self.max_score, total)

    def score_with_breakdown(self, factors: Dict[str, bool]) -> Dict[str, Any]:
        """
        Score with full breakdown of contributing factors.

        Returns:
            {score, max_possible, factors_met, factors_missed, factor_details}
        """
        met = []
        missed = []
        total = 0

        for key, weight in self.weights.items():
            if factors.get(key, False):
                met.append(key)
                total += weight
            else:
                missed.append(key)

        return {
            "score": min(self.max_score, total),
            "max_possible": sum(self.weights.values()),
            "factors_met": met,
            "factors_missed": missed,
            "coverage": len(met) / len(self.weights) if self.weights else 0,
        }

    def validate_weights(self) -> Tuple[bool, str]:
        """Check that weights are well-formed."""
        if not self.weights:
            return False, "No weights defined"
        if any(w < 0 for w in self.weights.values()):
            return False, "Negative weights not allowed"
        return True, "Valid"


@dataclass
class MultiFactorScorer:
    """
    Score an entity by weighted combination of numeric sub-scores.

    Pattern origin: Bounty Hunter's qualification formula.
    Useful for: opportunity qualification, risk assessment, priority ranking.

    Invariant: factor_weights must sum to 1.0 (normalized).
    Each sub-score is 0-100.
    """

    factor_weights: Dict[str, float]

    def __post_init__(self):
        """Normalize weights to sum to 1.0."""
        total = sum(self.factor_weights.values())
        if total > 0 and abs(total - 1.0) > 0.001:
            self.factor_weights = {
                k: v / total for k, v in self.factor_weights.items()
            }

    def score(self, sub_scores: Dict[str, float]) -> float:
        """
        Compute weighted score from sub-scores.

        Args:
            sub_scores: {factor_name: 0-100 score}

        Returns:
            Float score, 0-100.
        """
        total = 0.0
        for factor, weight in self.factor_weights.items():
            value = sub_scores.get(factor, 0.0)
            total += value * weight

        return min(100.0, max(0.0, total))

    def score_with_breakdown(self, sub_scores: Dict[str, float]) -> Dict[str, Any]:
        """
        Score with full breakdown of factor contributions.

        Returns:
            {score, factor_contributions, missing_factors}
        """
        contributions = {}
        missing = []
        total = 0.0

        for factor, weight in self.factor_weights.items():
            if factor in sub_scores:
                contribution = sub_scores[factor] * weight
                contributions[factor] = {
                    "raw_score": sub_scores[factor],
                    "weight": weight,
                    "contribution": contribution,
                }
                total += contribution
            else:
                missing.append(factor)

        return {
            "score": min(100.0, max(0.0, total)),
            "factor_contributions": contributions,
            "missing_factors": missing,
        }

    def validate_weights(self) -> Tuple[bool, str]:
        """Check that weights are well-formed."""
        if not self.factor_weights:
            return False, "No weights defined"
        if any(w < 0 for w in self.factor_weights.values()):
            return False, "Negative weights not allowed"
        total = sum(self.factor_weights.values())
        if abs(total - 1.0) > 0.01:
            return False, f"Weights sum to {total}, expected ~1.0"
        return True, "Valid"
