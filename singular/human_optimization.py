from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from .domain_learning import DomainHypothesis, LearningDomain


class OptimizationDisposition(str, Enum):
    PROPOSE = "PROPOSE"
    TEST = "TEST"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class DomainState:
    """Normalized state for one human-development domain.

    This is decision support, not a diagnosis. State confidence is explicitly
    separated from the state itself so uncertainty cannot silently become fact.
    """

    domain: LearningDomain
    level: float
    target: float = 1.0
    confidence: float = 0.5
    leverage: float = 1.0
    capacity_cost: float = 0.0
    sensitive: bool = False

    def __post_init__(self) -> None:
        for name, value in (("level", self.level), ("target", self.target), ("confidence", self.confidence), ("leverage", self.leverage), ("capacity_cost", self.capacity_cost)):
            _finite(name, value)
        if not 0 <= self.level <= 1 or not 0 <= self.target <= 1 or not 0 <= self.confidence <= 1:
            raise ValueError("level, target and confidence must be between 0 and 1")
        if self.leverage < 0 or self.capacity_cost < 0:
            raise ValueError("leverage and capacity_cost cannot be negative")

    @property
    def gap(self) -> float:
        return max(0.0, self.target - self.level)


@dataclass(frozen=True)
class DomainInteraction:
    """A directed, evidence-weighted cross-domain effect."""

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
        for name, value in (("expected_improvement", self.expected_improvement), ("evidence", self.evidence), ("causal_confidence", self.causal_confidence), ("cost", self.cost), ("risk", self.risk), ("capacity", self.capacity), ("reversibility", self.reversibility), ("time_to_result", self.time_to_result), ("recurrence", self.recurrence), ("cross_domain_impact", self.cross_domain_impact)):
            _finite(name, value)
        if self.expected_improvement < 0 or self.cost < 0 or self.risk < 0 or self.capacity < 0 or self.time_to_result < 0:
            raise ValueError("improvement, cost, risk, capacity and time_to_result cannot be negative")
        if not all(0 <= value <= 1 for value in (self.evidence, self.causal_confidence, self.reversibility, self.recurrence, self.cross_domain_impact)):
            raise ValueError("evidence, causal_confidence, reversibility, recurrence and cross_domain_impact must be between 0 and 1")

    @classmethod
    def from_hypothesis(cls, hypothesis: DomainHypothesis, *, id: str | None = None, capacity: float = 0.0, causal_confidence: float | None = None) -> "Intervention":
        """Bridge a learning hypothesis without inventing causal certainty.

        Older hypotheses expose evidence strength but not a separate causal
        estimate. Callers can provide one explicitly; otherwise the conservative
        default of Intervention (0.5) is retained rather than equating evidence
        quality with causal confidence.
        """
        return cls(
            id=id or hypothesis.intervention,
            domain=hypothesis.domain,
            expected_improvement=hypothesis.expected_improvement,
            evidence=hypothesis.evidence_strength,
            causal_confidence=0.5 if causal_confidence is None else causal_confidence,
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
    """Canonical coupled optimizer for whole-person trajectory decisions.

    The engine ranks interventions by expected global value, then solves the
    portfolio constraint deterministically. It does not claim causal certainty,
    does not diagnose, and never authorizes execution.
    """

    SENSITIVE = frozenset({LearningDomain.PSYCHOLOGY, LearningDomain.NUTRITION, LearningDomain.PHYSICAL, LearningDomain.SLEEP})
    _MAX_BRANCH_AND_BOUND_NODES = 250_000

    @staticmethod
    def _validate_unique_domains(states: tuple[DomainState, ...]) -> None:
        domains = [state.domain for state in states]
        if len(domains) != len(set(domains)):
            raise ValueError("domain states must be unique")

    @staticmethod
    def find_bottlenecks(states: tuple[DomainState, ...], interactions: tuple[DomainInteraction, ...] = ()) -> tuple[LearningDomain, ...]:
        HumanOptimizationEngine._validate_unique_domains(states)
        scores: list[tuple[float, LearningDomain]] = []
        for state in states:
            incoming = [edge for edge in interactions if edge.target is state.domain]
            interaction_factor = 1.0 + sum(edge.effective_multiplier for edge in incoming)
            score = state.gap * state.leverage * interaction_factor * (0.5 + 0.5 * state.confidence)
            scores.append((score, state.domain))
        return tuple(domain for _, domain in sorted(scores, key=lambda item: (-item[0], item[1].value)))

    @staticmethod
    def evaluate(intervention: Intervention, states: tuple[DomainState, ...], interactions: tuple[DomainInteraction, ...] = ()) -> OptimizationCandidate:
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

        human_review = bool(state.sensitive or intervention.domain in HumanOptimizationEngine.SENSITIVE or intervention.reversibility <= 0.2 or state.confidence < 0.5)
        if human_review:
            reasons.append("SENSITIVE_OR_HIGH_CONSEQUENCE_REVIEW")

        if score <= 0:
            disposition = OptimizationDisposition.REVIEW
            reasons.append("NON_POSITIVE_EXPECTED_VALUE")
        elif intervention.evidence < 0.7 or intervention.causal_confidence < 0.7 or state.confidence < 0.7:
            disposition = OptimizationDisposition.TEST
        else:
            disposition = OptimizationDisposition.PROPOSE

        return OptimizationCandidate(intervention.id, intervention.domain, round(score, 6), round(global_gain, 6), disposition, tuple(dict.fromkeys(reasons)), human_review)

    @staticmethod
    def _sort_selected(selected: list[OptimizationCandidate]) -> tuple[OptimizationCandidate, ...]:
        return tuple(sorted(selected, key=lambda c: (-c.score, c.domain.value, c.intervention_id)))

    @staticmethod
    def _select_portfolio(candidates: tuple[OptimizationCandidate, ...], interventions: dict[str, Intervention], capacity_budget: float, max_candidates: int) -> tuple[tuple[OptimizationCandidate, ...], bool]:
        """Choose the highest-value feasible portfolio under declared constraints.

        Returns (selection, exact). Small sets are exhaustively solved. Larger
        sets use deterministic branch-and-bound with an explicit node budget;
        if that budget is exhausted, the function falls back to a deterministic
        density heuristic and reports that exact optimality was not established.
        """
        items = [candidate for candidate in candidates if interventions[candidate.intervention_id].capacity <= capacity_budget]
        items.sort(key=lambda c: (-c.score, c.domain.value, c.intervention_id))
        if not items:
            return (), True

        n = len(items)
        if n <= 22:
            best_value = 0.0
            best_key: tuple[str, ...] = ()
            best_selection: tuple[OptimizationCandidate, ...] = ()
            for mask in range(1, 1 << n):
                selected: list[OptimizationCandidate] = []
                used = 0.0
                domains: set[LearningDomain] = set()
                valid = True
                for index, candidate in enumerate(items):
                    if not mask & (1 << index):
                        continue
                    intervention = interventions[candidate.intervention_id]
                    if candidate.domain in domains or len(selected) >= max_candidates or used + intervention.capacity > capacity_budget:
                        valid = False
                        break
                    selected.append(candidate)
                    domains.add(candidate.domain)
                    used += intervention.capacity
                if not valid:
                    continue
                value = sum(c.score for c in selected)
                key = tuple(c.intervention_id for c in selected)
                if value > best_value + 1e-12 or (abs(value - best_value) <= 1e-12 and (not best_key or key < best_key)):
                    best_value = value
                    best_key = key
                    best_selection = HumanOptimizationEngine._sort_selected(selected)
            return best_selection, True

        nodes = 0
        exhausted = False
        best_value = 0.0
        best_key: tuple[str, ...] = ()
        best_selection: tuple[OptimizationCandidate, ...] = ()

        # Suffix sums form an admissible upper bound because they deliberately
        # ignore capacity/domain/count constraints. That makes pruning safe.
        suffix_positive = [0.0] * (n + 1)
        for index in range(n - 1, -1, -1):
            suffix_positive[index] = suffix_positive[index + 1] + max(items[index].score, 0.0)

        def visit(index: int, used: float, selected: list[OptimizationCandidate], domains: set[LearningDomain], value: float) -> None:
            nonlocal nodes, exhausted, best_value, best_key, best_selection
            nodes += 1
            if nodes > HumanOptimizationEngine._MAX_BRANCH_AND_BOUND_NODES:
                exhausted = True
                return
            if index >= n or len(selected) >= max_candidates:
                key = tuple(c.intervention_id for c in selected)
                if value > best_value + 1e-12 or (abs(value - best_value) <= 1e-12 and (not best_key or key < best_key)):
                    best_value = value
                    best_key = key
                    best_selection = HumanOptimizationEngine._sort_selected(selected)
                return
            if value + suffix_positive[index] < best_value - 1e-12:
                return

            candidate = items[index]
            intervention = interventions[candidate.intervention_id]
            if candidate.domain not in domains and used + intervention.capacity <= capacity_budget:
                selected.append(candidate)
                domains.add(candidate.domain)
                visit(index + 1, used + intervention.capacity, selected, domains, value + candidate.score)
                domains.remove(candidate.domain)
                selected.pop()
                if exhausted:
                    return
            visit(index + 1, used, selected, domains, value)

        visit(0, 0.0, [], set(), 0.0)
        if not exhausted:
            return best_selection, True

        # Explicit non-exact fallback. This is deterministic and conservative
        # about its claim: callers receive exact=False and a warning.
        remaining = capacity_budget
        selected = []
        domains: set[LearningDomain] = set()
        for candidate in sorted(items, key=lambda c: (-(c.score / max(interventions[c.intervention_id].capacity, 1e-12)), -c.score, c.domain.value, c.intervention_id)):
            intervention = interventions[candidate.intervention_id]
            if candidate.domain in domains or intervention.capacity > remaining:
                continue
            selected.append(candidate)
            domains.add(candidate.domain)
            remaining -= intervention.capacity
            if len(selected) >= max_candidates:
                break
        return HumanOptimizationEngine._sort_selected(selected), False

    @staticmethod
    def optimize(states: tuple[DomainState, ...], interventions: tuple[Intervention, ...], interactions: tuple[DomainInteraction, ...] = (), capacity_budget: float = float("inf"), max_candidates: int = 5) -> HumanOptimizationReport:
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
        seen_interactions: set[tuple[LearningDomain, LearningDomain]] = set()
        by_id: dict[str, Intervention] = {}
        evaluated: list[OptimizationCandidate] = []
        for edge in interactions:
            edge_key = (edge.source, edge.target)
            if edge_key in seen_interactions:
                raise ValueError("domain interactions must be unique by source and target")
            seen_interactions.add(edge_key)
        for intervention in interventions:
            if intervention.id in seen:
                raise ValueError("intervention ids must be unique")
            seen.add(intervention.id)
            by_id[intervention.id] = intervention
            candidate = HumanOptimizationEngine.evaluate(intervention, states, interactions)
            if candidate.reasons == ("DOMAIN_STATE_MISSING",):
                warnings.append(f"MISSING_DOMAIN_STATE:{intervention.domain.value}")
                continue
            if intervention.capacity > capacity_budget:
                warnings.append(f"INTERVENTION_OVER_CAPACITY:{intervention.id}")
                continue
            if candidate.disposition is not OptimizationDisposition.BLOCK and candidate.score > 0:
                evaluated.append(candidate)

        selected, exact = HumanOptimizationEngine._select_portfolio(tuple(evaluated), by_id, capacity_budget, max_candidates)
        used = sum(by_id[candidate.intervention_id].capacity for candidate in selected)
        remaining = capacity_budget - used if capacity_budget != float("inf") else float("inf")
        if not exact:
            warnings.append("PORTFOLIO_HEURISTIC_FALLBACK_LARGE_SEARCH_SPACE")
        if any(candidate.human_review for candidate in selected):
            warnings.append("SELECTED_CANDIDATE_REQUIRES_HUMAN_REVIEW")

        return HumanOptimizationReport(
            bottlenecks=HumanOptimizationEngine.find_bottlenecks(states, interactions),
            candidates=selected,
            warnings=tuple(dict.fromkeys(warnings)),
            capacity_budget=capacity_budget,
            capacity_used=round(used, 6),
            capacity_remaining=round(remaining, 6) if isfinite(remaining) else remaining,
            uncertainties=tuple(dict.fromkeys(uncertainties)),
        )


def _finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite")
