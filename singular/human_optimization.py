from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from .domain_learning import LearningDomain


class OptimizationDisposition(str, Enum):
    PROPOSE = "PROPOSE"
    TEST = "TEST"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class DomainState:
    domain: LearningDomain
    level: float
    confidence: float = 0.5
    leverage: float = 1.0
    capacity_cost: float = 0.0
    sensitive: bool = False

    def __post_init__(self) -> None:
        for name, value in (("level", self.level), ("confidence", self.confidence), ("leverage", self.leverage), ("capacity_cost", self.capacity_cost)):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if not 0 <= self.level <= 1 or not 0 <= self.confidence <= 1:
            raise ValueError("level and confidence must be between 0 and 1")
        if self.leverage < 0 or self.capacity_cost < 0:
            raise ValueError("leverage and capacity_cost cannot be negative")


@dataclass(frozen=True)
class DomainInteraction:
    source: LearningDomain
    target: LearningDomain
    multiplier: float = 1.0
    confidence: float = 0.5

    def __post_init__(self) -> None:
        for name, value in (("multiplier", self.multiplier), ("confidence", self.confidence)):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.multiplier < 0 or not 0 <= self.confidence <= 1:
            raise ValueError("multiplier must be non-negative and confidence between 0 and 1")


@dataclass(frozen=True)
class Intervention:
    id: str
    domain: LearningDomain
    expected_improvement: float
    evidence: float = 0.5
    cost: float = 0.0
    risk: float = 0.0
    reversibility: float = 1.0
    capacity: float = 0.0
    causal_confidence: float = 0.5

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("id cannot be empty")
        for name, value in (("expected_improvement", self.expected_improvement), ("evidence", self.evidence), ("cost", self.cost), ("risk", self.risk), ("reversibility", self.reversibility), ("capacity", self.capacity), ("causal_confidence", self.causal_confidence)):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.expected_improvement < 0 or self.cost < 0 or self.risk < 0 or self.capacity < 0:
            raise ValueError("improvement, cost, risk and capacity cannot be negative")
        if not all(0 <= value <= 1 for value in (self.evidence, self.reversibility, self.causal_confidence)):
            raise ValueError("evidence, reversibility and causal_confidence must be between 0 and 1")


@dataclass(frozen=True)
class OptimizationCandidate:
    intervention_id: str
    domain: LearningDomain
    score: float
    disposition: OptimizationDisposition
    reasons: tuple[str, ...]
    human_review: bool


@dataclass(frozen=True)
class HumanOptimizationReport:
    bottlenecks: tuple[LearningDomain, ...]
    candidates: tuple[OptimizationCandidate, ...]
    warnings: tuple[str, ...]


class HumanOptimizationEngine:
    """Optimize the person's trajectory as one coupled system, not isolated habits."""

    SENSITIVE = frozenset({LearningDomain.PSYCHOLOGY, LearningDomain.NUTRITION, LearningDomain.PHYSICAL, LearningDomain.SLEEP})

    @staticmethod
    def _validate_unique_domains(states: tuple[DomainState, ...]) -> None:
        domains = [state.domain for state in states]
        if len(domains) != len(set(domains)):
            raise ValueError("domain states must be unique")

    @staticmethod
    def find_bottlenecks(states: tuple[DomainState, ...], interactions: tuple[DomainInteraction, ...] = ()) -> tuple[LearningDomain, ...]:
        HumanOptimizationEngine._validate_unique_domains(states)
        state_map = {item.domain: item for item in states}
        scores: list[tuple[float, LearningDomain]] = []
        for item in states:
            incoming = [edge for edge in interactions if edge.target is item.domain]
            interaction_factor = 1.0 + sum(edge.multiplier * edge.confidence for edge in incoming)
            bottleneck = (1.0 - item.level) * item.leverage * interaction_factor * (0.5 + 0.5 * item.confidence)
            scores.append((bottleneck, item.domain))
        return tuple(domain for _, domain in sorted(scores, key=lambda pair: (-pair[0], pair[1].value)))

    @staticmethod
    def evaluate(intervention: Intervention, states: tuple[DomainState, ...], interactions: tuple[DomainInteraction, ...] = ()) -> OptimizationCandidate:
        HumanOptimizationEngine._validate_unique_domains(states)
        state = next((item for item in states if item.domain is intervention.domain), None)
        if state is None:
            return OptimizationCandidate(intervention.id, intervention.domain, -1.0, OptimizationDisposition.REVIEW, ("DOMAIN_STATE_MISSING",), True)
        if intervention.risk >= 8:
            return OptimizationCandidate(intervention.id, intervention.domain, -1.0, OptimizationDisposition.BLOCK, ("RISK_TOO_HIGH",), True)

        incoming = [edge for edge in interactions if edge.target is intervention.domain]
        multiplier = 1.0 + sum(edge.multiplier * edge.confidence for edge in incoming)
        gap = 1.0 - state.level
        expected_gain = intervention.expected_improvement * gap * state.leverage * multiplier
        evidence_factor = 0.5 + 0.5 * min(intervention.evidence, intervention.causal_confidence)
        score = expected_gain * evidence_factor - intervention.cost - 0.5 * intervention.risk
        if not isfinite(score):
            raise ValueError("optimization score must be finite")
        score = round(score, 6)
        reasons: list[str] = []
        if intervention.evidence < 0.5:
            reasons.append("LOW_EVIDENCE")
        if intervention.causal_confidence < 0.5:
            reasons.append("CAUSALITY_UNCERTAIN")
        if intervention.reversibility <= 0.2:
            reasons.append("LOW_REVERSIBILITY")
        if state.confidence < 0.5:
            reasons.append("STATE_UNCERTAIN")
        if incoming:
            reasons.append("CROSS_DOMAIN_EFFECT")
        human_review = state.sensitive or intervention.domain in HumanOptimizationEngine.SENSITIVE or intervention.reversibility <= 0.2
        if human_review:
            reasons.append("SENSITIVE_OR_HIGH_CONSEQUENCE_REVIEW")
        if score <= 0:
            disposition = OptimizationDisposition.REVIEW
            reasons.append("NON_POSITIVE_EXPECTED_VALUE")
        elif intervention.evidence < 0.7 or intervention.causal_confidence < 0.7:
            disposition = OptimizationDisposition.TEST
        else:
            disposition = OptimizationDisposition.PROPOSE
        return OptimizationCandidate(intervention.id, intervention.domain, score, disposition, tuple(dict.fromkeys(reasons)), human_review)

    @staticmethod
    def optimize(states: tuple[DomainState, ...], interventions: tuple[Intervention, ...], interactions: tuple[DomainInteraction, ...] = (), capacity_budget: float = float("inf"), max_candidates: int = 5) -> HumanOptimizationReport:
        if capacity_budget < 0 or not isfinite(capacity_budget) and capacity_budget != float("inf"):
            raise ValueError("capacity_budget must be non-negative or infinity")
        if max_candidates < 1:
            raise ValueError("max_candidates must be positive")
        seen: set[str] = set()
        warnings: list[str] = []
        candidates: list[OptimizationCandidate] = []
        for intervention in interventions:
            if intervention.id in seen:
                raise ValueError("intervention ids must be unique")
            seen.add(intervention.id)
            if intervention.capacity > capacity_budget:
                continue
            candidate = HumanOptimizationEngine.evaluate(intervention, states, interactions)
            if candidate.disposition is not OptimizationDisposition.BLOCK and candidate.score > 0:
                candidates.append(candidate)
        candidates.sort(key=lambda item: (-item.score, item.domain.value, item.intervention_id))
        selected: list[OptimizationCandidate] = []
        remaining = capacity_budget
        selected_domains: set[LearningDomain] = set()
        by_id = {item.id: item for item in interventions}
        for candidate in candidates:
            intervention = by_id[candidate.intervention_id]
            if intervention.capacity > remaining:
                continue
            if candidate.domain in selected_domains:
                continue
            selected.append(candidate)
            selected_domains.add(candidate.domain)
            remaining -= intervention.capacity
            if len(selected) >= max_candidates:
                break
        if not states:
            warnings.append("NO_DOMAIN_STATE")
        if not interventions:
            warnings.append("NO_INTERVENTIONS")
        if not interactions:
            warnings.append("NO_CROSS_DOMAIN_MODEL")
        return HumanOptimizationReport(HumanOptimizationEngine.find_bottlenecks(states, interactions), tuple(selected), tuple(warnings))
