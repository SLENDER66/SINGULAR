"""Compatibility facade for the canonical human optimization engine.

New code should import from ``singular.human_optimization``. This module keeps
SINGULAR's historical HumanDomainState/Plan API stable while delegating all
optimization math to the canonical engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from .domain_learning import LearningDomain
from .human_optimization import (
    DomainInteraction,
    DomainState,
    HumanOptimizationEngine as CanonicalHumanOptimizationEngine,
    OptimizationDisposition,
)


class OptimizationAction(str, Enum):
    ACCELERATE = "ACCELERATE"
    IMPROVE = "IMPROVE"
    MAINTAIN = "MAINTAIN"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class HumanDomainState:
    domain: LearningDomain
    level: float
    target: float = 1.0
    confidence: float = 0.5
    leverage: float = 0.5
    dependencies: tuple[LearningDomain, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (("level", self.level), ("target", self.target), ("confidence", self.confidence), ("leverage", self.leverage)):
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and between 0 and 1")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("dependencies must be unique")
        if self.domain in self.dependencies:
            raise ValueError("a domain cannot depend on itself")

    @property
    def gap(self) -> float:
        return max(0.0, self.target - self.level)


@dataclass(frozen=True)
class HumanOptimizationPriority:
    domain: LearningDomain
    action: OptimizationAction
    score: float
    bottleneck_score: float
    reasons: tuple[str, ...]
    human_review: bool = False


@dataclass(frozen=True)
class HumanOptimizationPlan:
    priorities: tuple[HumanOptimizationPriority, ...]
    bottlenecks: tuple[LearningDomain, ...]
    warnings: tuple[str, ...]
    global_readiness: float

    @property
    def primary(self) -> HumanOptimizationPriority | None:
        return self.priorities[0] if self.priorities else None


class HumanOptimizationEngine:
    """Legacy API adapter; the canonical engine lives in human_optimization."""

    @staticmethod
    def optimize(states: tuple[HumanDomainState, ...], *, max_priorities: int = 5) -> HumanOptimizationPlan:
        if max_priorities <= 0:
            raise ValueError("max_priorities must be positive")
        if not states:
            return HumanOptimizationPlan((), (), ("NO_HUMAN_STATE_DATA",), 0.0)

        canonical_states = tuple(
            DomainState(
                domain=state.domain,
                level=state.level,
                target=state.target,
                confidence=state.confidence,
                leverage=state.leverage,
            )
            for state in states
        )
        known_domains = {item.domain for item in canonical_states}
        interactions = tuple(
            DomainInteraction(source=state.domain, target=dependency, multiplier=state.leverage, confidence=1.0)
            for state in states
            for dependency in state.dependencies
            if dependency in known_domains
        )
        report = CanonicalHumanOptimizationEngine.optimize(
            canonical_states,
            (),
            interactions,
            max_candidates=max_priorities,
        )

        by_domain = {state.domain: state for state in canonical_states}
        pressures = {domain: 0.0 for domain in by_domain}
        warnings = list(report.warnings)
        for state in states:
            for dependency in state.dependencies:
                dependency_state = by_domain.get(dependency)
                if dependency_state is None:
                    warnings.append(f"MISSING_DEPENDENCY:{state.domain.value}:{dependency.value}")
                else:
                    pressures[dependency] += state.leverage * dependency_state.gap

        priorities: list[HumanOptimizationPriority] = []
        for domain in report.bottlenecks:
            state = by_domain[domain]
            bottleneck = state.gap * (0.5 + state.leverage) + pressures[domain]
            score = bottleneck * (0.35 + 0.65 * state.confidence)
            reasons: list[str] = []
            if state.gap >= 0.5:
                reasons.append("LARGE_TARGET_GAP")
            if state.leverage >= 0.7:
                reasons.append("HIGH_CROSS_DOMAIN_LEVERAGE")
            if pressures[domain] > 0:
                reasons.append("CONSTRAINS_DEPENDENT_DOMAINS")
            if state.confidence < 0.5:
                reasons.append("LOW_STATE_CONFIDENCE")
                action = OptimizationAction.REVIEW
            elif state.gap <= 0.1:
                action = OptimizationAction.MAINTAIN
            elif score >= 0.65:
                action = OptimizationAction.ACCELERATE
            else:
                action = OptimizationAction.IMPROVE
            if domain in CanonicalHumanOptimizationEngine.SENSITIVE:
                reasons.append("SENSITIVE_DOMAIN_EVIDENCE_REQUIRED")
            priorities.append(HumanOptimizationPriority(
                domain,
                action,
                round(score, 6),
                round(bottleneck, 6),
                tuple(dict.fromkeys(reasons)),
                domain in CanonicalHumanOptimizationEngine.SENSITIVE or state.confidence < 0.5,
            ))

        total_weight = sum(0.25 + state.leverage for state in canonical_states)
        readiness = sum((0.25 + state.leverage) * state.level * state.confidence for state in canonical_states) / total_weight
        if any(state.confidence < 0.5 for state in canonical_states):
            warnings.append("LOW_CONFIDENCE_STATE_REQUIRES_MEASUREMENT")
        if report.bottlenecks:
            warnings.append("BOTTLENECKS_DETECTED")

        return HumanOptimizationPlan(
            tuple(sorted(priorities, key=lambda item: (-item.score, item.domain.value))[:max_priorities]),
            report.bottlenecks,
            tuple(dict.fromkeys(warnings)),
            round(readiness, 6),
        )


__all__ = [
    "HumanDomainState",
    "HumanOptimizationEngine",
    "HumanOptimizationPlan",
    "HumanOptimizationPriority",
    "OptimizationAction",
    "OptimizationDisposition",
]
