from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Iterable

from .domain_learning import DomainHypothesis, LearningDomain


class OptimizationDisposition(str, Enum):
    PROPOSE = "PROPOSE"
    TEST = "TEST"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class DomainState:
    """Normalized state for one human-development domain.

    This is a decision-support model, not a diagnosis. ``level`` and
    ``confidence`` are normalized to [0, 1]. ``leverage`` is non-negative.
    """

    domain: LearningDomain
    level: float
    confidence: float = 0.5
    leverage: float = 1.0
    capacity_cost: float = 0.0
    sensitive: bool = False

    def __post_init__(self) -> None:
        _finite("level", self.level)
        _finite("confidence", self.confidence)
        _finite("leverage", self.leverage)
        _finite("capacity_cost", self.capacity_cost)
        if not 0 <= self.level <= 1 or not 0 <= self.confidence <= 1:
            raise ValueError("level and confidence must be between 0 and 1")
        if self.leverage < 0 or self.capacity_cost < 0:
            raise ValueError("leverage and capacity_cost cannot be negative")

    @property
    def gap(self) -> float:
        return 1.0 - self.level


@dataclass(frozen=True)
class DomainInteraction:
    source: LearningDomain
    target: LearningDomain
    multiplier: float = 1.0
    confidence: float = 0.5
    causal_strength: float = 0.5

    def __post_init__(self) -> None:
        for name, value in (("multiplier", self.multiplier), ("confidence", self.confidence), ("causal_strength", self.causal_strength)):
            _finite(name, value)
        if self.source is self.target:
            raise ValueError("an interaction cannot target its own source")
        if self.multiplier < 0 or not 0 <= self.confidence <= 1 or not 0 <= self.causal_strength <= 1:
            raise ValueError("multiplier must be non-negative; confidence and causal_strength must be between 0 and 1")

    @property
    def effective_multiplier(self) -> float:
        return self.multiplier * self.confidence * self.causal_strength


@dataclass(frozen=True)
class Intervention:
    id: str
    domain: LearningDomain
    expected_improvement: float
    evidence: float = 0.5
    causal_confidence: float = 0.5
    cost: float = 0.0
    risk: float = 0.0
    capacity: float = 0.0
    reversibility: float = 1.0
    time_to_result: float = 1.0
    recurrence: float = 0.0
    cross_domain_impact: float = 0.0

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("id cannot be empty")
        for name, value in (
            ("expected_improvement", self.expected_improvement),
            ("evidence", self.evidence),
            ("causal_confidence", self.causal_confidence),
            ("cost", self.cost),
            ("risk", self.risk),
            ("capacity", self.capacity),
            ("reversibility", self.reversibility),
            ("time_to_result", self.time_to_result),
            ("recurrence", self.recurrence),
            ("cross_domain_impact", self.cross_domain_impact),
        ):
            _finite(name, value)
        if self.expected_improvement < 0 or self.cost < 0 or self.risk < 0 or self.capacity < 0 or self.time_to_result < 0:
            raise ValueError("improvement, cost, risk, capacity and time_to_result cannot be negative")
        if not all(0 <= value <= 1 for value in (self.evidence, self.causal_confidence, self.reversibility, self.recurrence, self.cross_domain_impact)):
            raise ValueError("evidence, causal_confidence, reversibility, recurrence and cross_domain_impact must be between 0 and 1")

    @classmethod
    def from_hypothesis(cls, hypothesis: DomainHypothesis, *, id: str | None = None, capacity: float = 0.0) -> "Intervention":
        """Bridge domain-learning hypotheses into the canonical optimizer."""
        return cls(
            id=id or hypothesis.intervention,
            domain=hypothesis.domain,
            expected_improvement=hypothesis.expected_improvement,
            evidence=hypothesis.evidence_strength,
            causal_confidence=hypothesis.evidence_strength,
            cost=hypothesis.cost,
            risk=hypothesis.risk,
            capacity=capacity,
            reversibility=hypothesis.reversibility,
        )


@dataclass(frozen=True)
class OptimizationCandidate:
    intervention_id: str
    domain: LearningDomain
    score: float
    expected_global_gain: float
    disposition: OptimizationDisposition
    reasons: tuple[str, ...]
    human_review: bool


@dataclass(frozen=True)
class HumanOptimizationReport:
    bottlenecks: tuple[LearningDomain, ...]
    candidates: tuple[OptimizationCandidate, ...]
    warnings: tuple[str, ...]
    capacity_budget: float
    capacity_used: float
    capacity_remaining: float
    uncertainties: tuple[str, ...]


class HumanOptimizationEngine:
    """Canonical coupled human-trajectory optimizer.

    The engine combines state gaps, leverage, dependencies, evidence, causal
    confidence, cost, risk, reversibility, capacity and cross-domain effects.
    It recommends or blocks candidates; it never authorizes execution.
    """

    SENSITIVE = frozenset({
        LearningDomain.PSYCHOLOGY,
        LearningDomain.NUTRITION,
        LearningDomain.PHYSICAL,
        LearningDomain.SLEEP,
    })

    @staticmethod
    def _validate_unique_domains(states: tuple[DomainState, ...]) -> None:
        domains = [state.domain for state in states]
        if len(domains) != len(set(domains)):
            raise ValueError("domain states must be unique")

    @staticmethod
    def find_bottlenecks(
        states: tuple[DomainState, ...],
        interactions: tuple[DomainInteraction, ...] = (),
    ) -> tuple[LearningDomain, ...]:
        HumanOptimizationEngine._validate_unique_domains(states)
        scores: list[tuple[float, LearningDomain]] = []
        for state in states:
            incoming = [edge for edge in interactions if edge.target is state.domain]
            interaction_factor = 1.0 + sum(edge.effective_multiplier for edge in incoming)
            score = state.gap * state.leverage * interaction_factor * (0.5 + 0.5 * state.confidence)
            scores.append((score, state.domain))
        return tuple(domain for _, domain in sorted(scores, key=lambda item: (-item[0], item[1].value)))

    @staticmethod
    def evaluate(
        intervention: Intervention,
        states: tuple[DomainState, ...],
        interactions: tuple[DomainInteraction, ...] = (),
    ) -> OptimizationCandidate:
        HumanOptimizationEngine._validate_unique_domains(states)
        state = next((item for item in states if item.domain is intervention.domain), None)
        if state is None:
            return OptimizationCandidate(intervention.id, intervention.domain, -1.0, 0.0, OptimizationDisposition.REVIEW, ("DOMAIN_STATE_MISSING",), True)
        if intervention.risk >= 8:
            return OptimizationCandidate(intervention.id, intervention.domain, -1.0, 0.0, OptimizationDisposition.BLOCK, ("RISK_TOO_HIGH",), True)

        incoming = [edge for edge in interactions if edge.target is intervention.domain]
        multiplier = 1.0 + sum(edge.effective_multiplier for edge in incoming)
        expected_gain = intervention.expected_improvement * state.gap * state.leverage * multiplier
        evidence_factor = 0.5 + 0.5 * min(intervention.evidence, intervention.causal_confidence, state.confidence)
        recurrence_factor = 1.0 + 0.25 * intervention.recurrence
        cross_domain_factor = 1.0 + 0.25 * intervention.cross_domain_impact
        time_factor = 1.0 / (1.0 + intervention.time_to_result)
        global_gain = expected_gain * evidence_factor * recurrence_factor * cross_domain_factor * time_factor
        score = global_gain - intervention.cost - 0.5 * intervention.risk
        if not isfinite(score):
            raise ValueError("optimization score must be finite")

        reasons: list[str] = []
        if intervention.evidence < 0.5:
            reasons.append("LOW_EVIDENCE")
        if intervention.causal_confidence < 0.5:
            reasons.append("CAUSALITY_UNCERTAIN")
        if state.confidence < 0.5:
            reasons.append("STATE_UNCERTAIN")
        if intervention.reversibility <= 0.2:
            reasons.append("LOW_REVERSIBILITY")
        if intervention.time_to_result > 3:
            reasons.append("SLOW_TIME_TO_RESULT")
        if intervention.recurrence > 0:
            reasons.append("RECURRING_VALUE")
        if intervention.cross_domain_impact > 0:
            reasons.append("CROSS_DOMAIN_EFFECT")
        if incoming:
            reasons.append("DEPENDENCY_EFFECT")

        human_review = bool(
            state.sensitive
            or intervention.domain in HumanOptimizationEngine.SENSITIVE
            or intervention.reversibility <= 0.2
            or state.confidence < 0.5
        )
        if human_review:
            reasons.append("SENSITIVE_OR_HIGH_CONSEQUENCE_REVIEW")

        if score <= 0:
            disposition = OptimizationDisposition.REVIEW
            reasons.append("NON_POSITIVE_EXPECTED_VALUE")
        elif intervention.evidence < 0.7 or intervention.causal_confidence < 0.7 or state.confidence < 0.7:
            disposition = OptimizationDisposition.TEST
        else:
            disposition = OptimizationDisposition.PROPOSE

        return OptimizationCandidate(
            intervention.id,
            intervention.domain,
            round(score, 6),
            round(global_gain, 6),
            disposition,
            tuple(dict.fromkeys(reasons)),
            human_review,
        )

    @staticmethod
    def optimize(
        states: tuple[DomainState, ...],
        interventions: tuple[Intervention, ...],
        interactions: tuple[DomainInteraction, ...] = (),
        capacity_budget: float = float("inf"),
        max_candidates: int = 5,
    ) -> HumanOptimizationReport:
        if capacity_budget < 0 or (not isfinite(capacity_budget) and capacity_budget != float("inf")):
            raise ValueError("capacity_budget must be non-negative or infinity")
        if max_candidates < 1:
            raise ValueError("max_candidates must be positive")
        HumanOptimizationEngine._validate_unique_domains(states)

        warnings: list[str] = []
        uncertainties: list[str] = []
        if not states:
            warnings.append("NO_DOMAIN_STATE")
        if not interventions:
            warnings.append("NO_INTERVENTIONS")
        if not interactions:
            warnings.append("NO_CROSS_DOMAIN_MODEL")
        if any(state.confidence < 0.5 for state in states):
            uncertainties.append("LOW_STATE_CONFIDENCE")
        if any(intervention.evidence < 0.5 or intervention.causal_confidence < 0.5 for intervention in interventions):
            uncertainties.append("LOW_EVIDENCE_OR_CAUSAL_CONFIDENCE")

        seen: set[str] = set()
        evaluated: list[OptimizationCandidate] = []
        by_id: dict[str, Intervention] = {}
        for intervention in interventions:
            if intervention.id in seen:
                raise ValueError("intervention ids must be unique")
            seen.add(intervention.id)
            by_id[intervention.id] = intervention
            if intervention.capacity > capacity_budget:
                continue
            candidate = HumanOptimizationEngine.evaluate(intervention, states, interactions)
            if candidate.disposition is not OptimizationDisposition.BLOCK and candidate.score > 0:
                evaluated.append(candidate)

        evaluated.sort(key=lambda item: (-item.score, item.domain.value, item.intervention_id))
        selected: list[OptimizationCandidate] = []
        remaining = capacity_budget
        used = 0.0
        selected_domains: set[LearningDomain] = set()
        for candidate in evaluated:
            intervention = by_id[candidate.intervention_id]
            if intervention.capacity > remaining or candidate.domain in selected_domains:
                continue
            selected.append(candidate)
            selected_domains.add(candidate.domain)
            used += intervention.capacity
            remaining -= intervention.capacity
            if len(selected) >= max_candidates:
                break

        return HumanOptimizationReport(
            bottlenecks=HumanOptimizationEngine.find_bottlenecks(states, interactions),
            candidates=tuple(selected),
            warnings=tuple(dict.fromkeys(warnings)),
            capacity_budget=capacity_budget,
            capacity_used=round(used, 6),
            capacity_remaining=round(remaining, 6),
            uncertainties=tuple(dict.fromkeys(uncertainties)),
        )


def _finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite")
