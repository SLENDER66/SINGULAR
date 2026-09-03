from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from .domain_learning import LearningDomain


class OptimizationAction(str, Enum):
    ACCELERATE = "ACCELERATE"
    IMPROVE = "IMPROVE"
    MAINTAIN = "MAINTAIN"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class HumanDomainState:
    """Normalized state of one human-development domain.

    level, confidence and leverage are in [0, 1]. A dependency is another
    domain whose weakness can constrain this domain. This is a decision model,
    not a medical or psychological diagnosis.
    """

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
    """Optimize the whole trajectory instead of maximizing isolated domains.

    Weak high-leverage domains and dependency bottlenecks receive priority.
    Low-confidence states are surfaced for review rather than converted into
    false certainty. The engine recommends priorities; it never authorizes an
    intervention or mutates the person/system autonomously.
    """

    SENSITIVE = {
        LearningDomain.PSYCHOLOGY,
        LearningDomain.NUTRITION,
        LearningDomain.PHYSICAL,
        LearningDomain.SLEEP,
    }

    @staticmethod
    def optimize(states: tuple[HumanDomainState, ...], *, max_priorities: int = 5) -> HumanOptimizationPlan:
        if max_priorities <= 0:
            raise ValueError("max_priorities must be positive")
        if not states:
            return HumanOptimizationPlan((), (), ("NO_HUMAN_STATE_DATA",), 0.0)

        by_domain = {state.domain: state for state in states}
        if len(by_domain) != len(states):
            raise ValueError("domain states must be unique")

        warnings: list[str] = []
        priorities: list[HumanOptimizationPriority] = []
        dependency_pressure: dict[LearningDomain, float] = {domain: 0.0 for domain in by_domain}

        for state in states:
            for dependency in state.dependencies:
                dependency_state = by_domain.get(dependency)
                if dependency_state is None:
                    warnings.append(f"MISSING_DEPENDENCY:{state.domain.value}:{dependency.value}")
                    continue
                dependency_pressure[dependency] += state.leverage * dependency_state.gap

        for state in states:
            pressure = dependency_pressure[state.domain]
            bottleneck = state.gap * (0.5 + state.leverage) + pressure
            evidence_factor = 0.35 + 0.65 * state.confidence
            score = bottleneck * evidence_factor
            reasons: list[str] = []

            if state.gap >= 0.5:
                reasons.append("LARGE_TARGET_GAP")
            if state.leverage >= 0.7:
                reasons.append("HIGH_CROSS_DOMAIN_LEVERAGE")
            if pressure > 0:
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

            sensitive = state.domain in HumanOptimizationEngine.SENSITIVE
            if sensitive:
                reasons.append("SENSITIVE_DOMAIN_EVIDENCE_REQUIRED")

            priorities.append(HumanOptimizationPriority(
                domain=state.domain,
                action=action,
                score=round(score, 6),
                bottleneck_score=round(bottleneck, 6),
                reasons=tuple(dict.fromkeys(reasons)),
                human_review=sensitive or state.confidence < 0.5,
            ))

        priorities.sort(key=lambda item: (-item.score, item.domain.value))
        bottlenecks = tuple(item.domain for item in priorities if item.bottleneck_score >= 0.5)

        total_weight = sum(0.25 + state.leverage for state in states)
        readiness = sum((0.25 + state.leverage) * state.level * state.confidence for state in states) / total_weight
        if any(state.confidence < 0.5 for state in states):
            warnings.append("LOW_CONFIDENCE_STATE_REQUIRES_MEASUREMENT")
        if bottlenecks:
            warnings.append("BOTTLENECKS_DETECTED")

        return HumanOptimizationPlan(
            priorities=tuple(priorities[:max_priorities]),
            bottlenecks=bottlenecks,
            warnings=tuple(dict.fromkeys(warnings)),
            global_readiness=round(readiness, 6),
        )
