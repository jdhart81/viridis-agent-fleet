from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from .graph import CognitiveEdge, CognitiveGraph, utc_now
from .routing import Router


@dataclass(frozen=True)
class ComputeProfile:
    """Estimated cost and capability profile for a model, tool, or execution backend.

    A profile can represent a local GPU model, a cloud transformer API, an embedding model,
    a rules engine, a cached workflow, or any other callable cognitive resource.
    """

    id: str
    kind: str = "model"
    quality_score: float = 0.5
    cost_per_1k_input_tokens: float = 0.0
    cost_per_1k_output_tokens: float = 0.0
    latency_ms: float = 1000.0
    gpu_memory_gb: float = 0.0
    max_context_tokens: int = 4096
    local: bool = False
    reliability_score: float = 1.0
    execution_mode: str = ""
    capabilities: Tuple[str, ...] = ()
    energy_wh_per_1k_input_tokens: Optional[float] = None
    energy_wh_per_1k_output_tokens: Optional[float] = None
    fixed_energy_wh: Optional[float] = None
    average_power_watts: Optional[float] = None
    carbon_intensity_g_per_kwh: Optional[float] = None
    cache_confidence: Optional[float] = None
    cache_age_seconds: Optional[float] = None
    metadata: Dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        profile_id = str(self.id).strip()
        if not profile_id:
            raise ValueError("ComputeProfile.id must be non-empty.")
        object.__setattr__(self, "id", profile_id)
        for name in ("quality_score", "reliability_score"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"ComputeProfile.{name} must be in [0,1].")
        for name in (
            "cost_per_1k_input_tokens", "cost_per_1k_output_tokens",
            "latency_ms", "gpu_memory_gb",
        ):
            self._validate_nonnegative(name, getattr(self, name), required=True)
        for name in (
            "energy_wh_per_1k_input_tokens",
            "energy_wh_per_1k_output_tokens", "fixed_energy_wh",
            "average_power_watts", "carbon_intensity_g_per_kwh",
            "cache_age_seconds",
        ):
            self._validate_nonnegative(name, getattr(self, name))
        if (not isinstance(self.max_context_tokens, int)
                or isinstance(self.max_context_tokens, bool)
                or self.max_context_tokens < 0):
            raise ValueError(
                "ComputeProfile.max_context_tokens must be a non-negative int.")
        if self.cache_confidence is not None:
            confidence = float(self.cache_confidence)
            if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                raise ValueError(
                    "ComputeProfile.cache_confidence must be in [0,1].")
        capabilities = tuple(sorted({
            str(item).strip() for item in self.capabilities
            if str(item).strip()
        }))
        object.__setattr__(self, "capabilities", capabilities)
        if self.execution_mode:
            mode = self.execution_mode.strip().lower().replace("-", "_")
            if mode not in {"reuse", "rule", "local", "cloud", "tool"}:
                raise ValueError(
                    "ComputeProfile.execution_mode must be reuse, rule, "
                    "local, cloud, or tool.")
            object.__setattr__(self, "execution_mode", mode)

    @staticmethod
    def _validate_nonnegative(
        name: str, value: Optional[float], *, required: bool = False,
    ) -> None:
        if value is None and not required:
            return
        numeric = float(value)  # type: ignore[arg-type]
        if not math.isfinite(numeric) or numeric < 0:
            raise ValueError(f"ComputeProfile.{name} must be non-negative.")

    @property
    def mode(self) -> str:
        if self.execution_mode:
            return self.execution_mode
        kind = self.kind.strip().lower().replace("-", "_")
        if kind in {"cache", "cached", "reuse", "memoized"}:
            return "reuse"
        if kind in {"rule", "rules", "rules_engine", "deterministic"}:
            return "rule"
        if kind in {"tool", "workflow", "function"}:
            return "tool"
        return "local" if self.local else "cloud"

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            (input_tokens / 1000.0) * self.cost_per_1k_input_tokens
            + (output_tokens / 1000.0) * self.cost_per_1k_output_tokens
        )

    def estimate_energy(self, input_tokens: int,
                        output_tokens: int) -> Tuple[Optional[float], str]:
        """Return estimated Wh plus an explicit evidence classification."""
        token_rates_present = any(value is not None for value in (
            self.energy_wh_per_1k_input_tokens,
            self.energy_wh_per_1k_output_tokens,
        ))
        fixed = self.fixed_energy_wh or 0.0
        if token_rates_present:
            energy = fixed + (
                (input_tokens / 1000.0)
                * (self.energy_wh_per_1k_input_tokens or 0.0)
                + (output_tokens / 1000.0)
                * (self.energy_wh_per_1k_output_tokens or 0.0)
            )
            return energy, "profile_token_energy_estimate"
        if self.average_power_watts is not None:
            energy = fixed + (
                self.average_power_watts * self.latency_ms / 3_600_000.0)
            return energy, "profile_power_latency_estimate"
        if self.fixed_energy_wh is not None:
            return fixed, "profile_fixed_energy_estimate"
        return None, "unknown"

    def estimate_carbon(self, energy_wh: Optional[float]) -> Optional[float]:
        if energy_wh is None or self.carbon_intensity_g_per_kwh is None:
            return None
        return (energy_wh / 1000.0) * self.carbon_intensity_g_per_kwh


@dataclass(frozen=True)
class TaskProfile:
    """Estimated task requirements used for compute-aware routing."""

    id: str
    task_type: str
    difficulty: float = 0.5
    risk: float = 0.5
    expected_input_tokens: int = 1000
    expected_output_tokens: int = 500
    min_quality: float = 0.5
    requires_local: bool = False
    min_reliability: float = 0.0
    allowed_modes: Tuple[str, ...] = ()
    required_capabilities: Tuple[str, ...] = ()
    allow_reuse: bool = True
    min_cache_confidence: float = 0.88
    max_cache_age_seconds: float = 86400.0
    allow_defer: bool = False
    value_score: float = 1.0
    urgency: float = 1.0
    defer_below_value: float = 0.1
    require_energy_estimate: bool = False
    max_cost_usd: Optional[float] = None
    max_energy_wh: Optional[float] = None
    max_latency_ms: Optional[float] = None
    baseline_cost_usd: Optional[float] = None
    baseline_energy_wh: Optional[float] = None
    baseline_latency_ms: Optional[float] = None
    cost_weight: float = 1.0
    latency_weight: float = 1.0
    energy_weight: float = 1.0
    carbon_weight: float = 0.0
    energy_price_per_kwh: float = 0.15
    carbon_price_per_kg: float = 0.05
    unknown_energy_penalty: float = 0.001
    intervention_cost_weight: float = 0.001
    metadata: Dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        task_id = str(self.id).strip()
        task_type = str(self.task_type).strip()
        if not task_id or not task_type:
            raise ValueError("TaskProfile.id and task_type must be non-empty.")
        object.__setattr__(self, "id", task_id)
        object.__setattr__(self, "task_type", task_type)
        for name in (
            "difficulty", "risk", "min_quality", "min_reliability",
            "min_cache_confidence", "value_score", "urgency",
            "defer_below_value",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"TaskProfile.{name} must be in [0,1].")
        if (not isinstance(self.expected_input_tokens, int)
                or isinstance(self.expected_input_tokens, bool)
                or not isinstance(self.expected_output_tokens, int)
                or isinstance(self.expected_output_tokens, bool)
                or self.expected_input_tokens < 0
                or self.expected_output_tokens < 0):
            raise ValueError("TaskProfile token estimates must be non-negative.")
        for name in (
            "max_cache_age_seconds", "max_cost_usd", "max_energy_wh",
            "max_latency_ms", "baseline_cost_usd", "baseline_energy_wh",
            "baseline_latency_ms", "cost_weight", "latency_weight",
            "energy_weight", "carbon_weight", "energy_price_per_kwh",
            "carbon_price_per_kg", "unknown_energy_penalty",
            "intervention_cost_weight",
        ):
            value = getattr(self, name)
            if value is None:
                continue
            numeric = float(value)
            if not math.isfinite(numeric) or numeric < 0:
                raise ValueError(f"TaskProfile.{name} must be non-negative.")
        modes = tuple(sorted({
            str(item).strip().lower().replace("-", "_")
            for item in self.allowed_modes if str(item).strip()
        }))
        invalid_modes = set(modes) - {"reuse", "rule", "local", "cloud", "tool"}
        if invalid_modes:
            raise ValueError("TaskProfile.allowed_modes contains an unknown mode.")
        object.__setattr__(self, "allowed_modes", modes)
        capabilities = tuple(sorted({
            str(item).strip() for item in self.required_capabilities
            if str(item).strip()
        }))
        object.__setattr__(self, "required_capabilities", capabilities)

    def should_defer(self) -> bool:
        """Defer only when the caller explicitly authorizes low-value delay."""
        return (
            self.allow_defer
            and self.value_score < self.defer_below_value
            and self.urgency < 0.5
            and self.risk < 0.75
        )


@dataclass(frozen=True)
class ComputeDecision:
    """A compute routing decision with auditable reasoning."""

    profile_id: Optional[str]
    execution_mode: str
    score: float
    total_burden: float
    estimated_cost: float
    estimated_latency_ms: float
    estimated_gpu_memory_gb: float
    estimated_energy_wh: Optional[float]
    energy_estimate_status: str
    estimated_carbon_g: Optional[float]
    estimated_cost_saved: Optional[float]
    estimated_energy_saved_wh: Optional[float]
    estimated_latency_saved_ms: Optional[float]
    reason: str


@dataclass
class EfficiencyReport:
    """Aggregated efficiency metrics for a run or experiment."""

    task_success: float
    total_estimated_cost: float
    total_latency_ms: float
    total_gpu_memory_gb: float
    model_calls: int
    cache_hits: int = 0
    tool_calls: int = 0

    @property
    def cognitive_efficiency(self) -> float:
        denominator = max(1e-9, self.total_estimated_cost + (self.total_latency_ms / 1000.0) * 0.001)
        return self.task_success / denominator


class ComputeOptimizer:
    """Compute-aware routing layer for Verdigraph.

    This class does not optimize transformer kernels directly. Instead, it optimizes
    agent-level compute by choosing the cheapest reliable execution path: cache,
    rule, local model, small cloud model, large cloud model, or high-assurance evaluator.
    """

    def __init__(self, profiles: Iterable[ComputeProfile]) -> None:
        self.profiles: Dict[str, ComputeProfile] = {profile.id: profile for profile in profiles}
        self.decisions: List[Dict[str, object]] = []

    def choose_profile(self, task: TaskProfile) -> ComputeDecision:
        if task.should_defer():
            return ComputeDecision(
                profile_id=None,
                execution_mode="defer",
                score=100.0,
                total_burden=0.0,
                estimated_cost=0.0,
                estimated_latency_ms=0.0,
                estimated_gpu_memory_gb=0.0,
                estimated_energy_wh=0.0,
                energy_estimate_status="avoided_by_explicit_defer_policy",
                estimated_carbon_g=0.0,
                estimated_cost_saved=task.baseline_cost_usd,
                estimated_energy_saved_wh=task.baseline_energy_wh,
                estimated_latency_saved_ms=task.baseline_latency_ms,
                reason=("explicit Wu Wei defer: caller allowed delay, value "
                        "is below threshold, and urgency/risk are low"),
            )
        if not self.profiles:
            raise ValueError("At least one ComputeProfile is required.")

        candidates: List[ComputeDecision] = []
        for profile in self.profiles.values():
            mode = profile.mode
            if task.allowed_modes and mode not in task.allowed_modes:
                continue
            if task.requires_local and not profile.local:
                continue
            if profile.reliability_score < task.min_reliability:
                continue
            if not set(task.required_capabilities).issubset(
                    profile.capabilities):
                continue
            if profile.max_context_tokens < task.expected_input_tokens + task.expected_output_tokens:
                continue
            # Hard contract: a profile that does not meet the task's minimum quality
            # bar is ineligible, regardless of cost. This preserves the invariant that
            # compute savings never silently regress task quality below the requested floor.
            if profile.quality_score < task.min_quality:
                continue

            if mode == "reuse":
                if not task.allow_reuse or task.risk >= 0.75:
                    continue
                if (profile.cache_confidence is None
                        or profile.cache_confidence
                        < max(task.min_quality, task.min_cache_confidence)):
                    continue
                if (profile.cache_age_seconds is None
                        or profile.cache_age_seconds
                        > task.max_cache_age_seconds):
                    continue

            estimated_cost = profile.estimate_cost(task.expected_input_tokens, task.expected_output_tokens)
            energy_wh, energy_status = profile.estimate_energy(
                task.expected_input_tokens, task.expected_output_tokens)
            carbon_g = profile.estimate_carbon(energy_wh)
            if task.max_cost_usd is not None and estimated_cost > task.max_cost_usd:
                continue
            if task.max_latency_ms is not None and profile.latency_ms > task.max_latency_ms:
                continue
            if (task.require_energy_estimate or task.max_energy_wh is not None) \
                    and energy_wh is None:
                continue
            if (task.max_energy_wh is not None and energy_wh is not None
                    and energy_wh > task.max_energy_wh):
                continue

            mode_intervention = {
                "reuse": 0.0,
                "rule": 0.1,
                "local": 0.3,
                "tool": 0.5,
                "cloud": 1.0,
            }[mode]
            energy_component = (
                task.unknown_energy_penalty
                if energy_wh is None
                else (energy_wh / 1000.0) * task.energy_price_per_kwh
            )
            carbon_component = (
                0.0 if carbon_g is None
                else (carbon_g / 1000.0) * task.carbon_price_per_kg
            )
            total_burden = (
                task.cost_weight * estimated_cost
                + task.latency_weight * (profile.latency_ms / 1000.0) * 0.001
                + task.energy_weight * energy_component
                + task.carbon_weight * carbon_component
                + task.intervention_cost_weight * mode_intervention
            )
            score = 1.0 / max(1e-9, total_burden + 0.01)

            cost_saved = (
                None if task.baseline_cost_usd is None
                else task.baseline_cost_usd - estimated_cost
            )
            energy_saved = (
                None if task.baseline_energy_wh is None or energy_wh is None
                else task.baseline_energy_wh - energy_wh
            )
            latency_saved = (
                None if task.baseline_latency_ms is None
                else task.baseline_latency_ms - profile.latency_ms
            )

            reason = (
                f"eligible mode={mode}, kind={profile.kind}, "
                f"quality={profile.quality_score:.2f}, "
                f"reliability={profile.reliability_score:.2f}, "
                f"cost={estimated_cost:.6f}, latency_ms={profile.latency_ms:.0f}, "
                f"energy_wh={energy_wh if energy_wh is not None else 'unknown'}, "
                f"burden={total_burden:.9f}"
            )
            candidates.append(
                ComputeDecision(
                    profile_id=profile.id,
                    execution_mode=mode,
                    score=score,
                    total_burden=total_burden,
                    estimated_cost=estimated_cost,
                    estimated_latency_ms=profile.latency_ms,
                    estimated_gpu_memory_gb=profile.gpu_memory_gb,
                    estimated_energy_wh=energy_wh,
                    energy_estimate_status=energy_status,
                    estimated_carbon_g=carbon_g,
                    estimated_cost_saved=cost_saved,
                    estimated_energy_saved_wh=energy_saved,
                    estimated_latency_saved_ms=latency_saved,
                    reason=reason,
                )
            )

        if not candidates:
            raise ValueError(
                f"No compute profile satisfies the task constraints for task '{task.id}' "
                f"(task_type={task.task_type}, requires_local={task.requires_local}, "
                f"min_quality={task.min_quality}, "
                f"context_required={task.expected_input_tokens + task.expected_output_tokens})."
            )

        # Wu Wei policy: after every hard contract is satisfied, choose the
        # least total intervention burden. Stable id ordering makes ties exact.
        decision = min(
            candidates,
            key=lambda item: (
                item.total_burden,
                -self.profiles[item.profile_id].quality_score,  # type: ignore[index]
                item.profile_id or "",
            ),
        )
        self.decisions.append({
            "timestamp": utc_now(),
            "task_id": task.id,
            "task_type": task.task_type,
            "profile_id": decision.profile_id,
            "execution_mode": decision.execution_mode,
            "score": decision.score,
            "total_burden": decision.total_burden,
            "estimated_cost": decision.estimated_cost,
            "estimated_latency_ms": decision.estimated_latency_ms,
            "estimated_energy_wh": decision.estimated_energy_wh,
        })
        return decision

    @staticmethod
    def route_compute_efficiency(edge: CognitiveEdge, task_relevance: float = 1.0) -> float:
        """Score a cognitive edge by expected task success per compute cost."""
        success = edge.weight * edge.trust_score * max(0.01, edge.success_rate or 0.5) * task_relevance
        compute_cost = max(1e-9, edge.token_cost + (edge.latency_ms / 1000.0) + edge.risk_score)
        return success / compute_cost

    def best_compute_edges(self, graph: CognitiveGraph, from_node: str, limit: int = 3) -> List[CognitiveEdge]:
        edges = graph.outgoing(from_node)
        return sorted(edges, key=self.route_compute_efficiency, reverse=True)[:limit]

    @staticmethod
    def should_use_cache(cache_confidence: float, task_risk: float, threshold: float = 0.88) -> bool:
        """Return True when cached reasoning is likely safe and efficient."""
        if task_risk >= 0.75:
            return False
        return cache_confidence >= threshold

    @staticmethod
    def should_escalate(current_confidence: float, task_risk: float, min_confidence: float = 0.78) -> bool:
        """Return True when the route should escalate to a stronger model/evaluator."""
        required = min_confidence + max(0.0, task_risk - 0.5) * 0.25
        return current_confidence < required
