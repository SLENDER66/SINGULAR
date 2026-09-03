from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import isfinite

from .human_optimization import Intervention, OptimizationCandidate
from .domain_learning import LearningDomain


@dataclass(frozen=True)
class TrajectoryInteraction:
    """Pairwise portfolio effect between two interventions.

    A positive value models synergy; a negative value models conflict or
    diminishing returns. Confidence scales the declared effect so uncertain
    interactions cannot silently dominate the portfolio.
    """

    first: str
    second: str
    effect: float = 0.0
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.first.strip() or not self.second.strip():
            raise ValueError("interaction intervention ids cannot be empty")
        if self.first == self.second:
            raise ValueError("an interaction cannot target itself")
        if not isfinite(self.effect) or not isfinite(self.confidence):
            raise ValueError("interaction values must be finite")
        if not 0 <= self.confidence <= 1:
            raise ValueError("interaction confidence must be between 0 and 1")

    @property
    def effective_effect(self) -> float:
        return self.effect * self.confidence


@dataclass(frozen=True)
class TrajectoryPortfolio:
    candidates: tuple[OptimizationCandidate, ...]
    objective: float
    capacity_used: float
    capacity_remaining: float
    interaction_effect: float


class TrajectoryOptimizationEngine:
    """Select a portfolio using candidate value plus pairwise trajectory effects.

    This is deliberately separate from HumanOptimizationEngine: the latter
    evaluates individual interventions, while this layer evaluates combinations.
    It remains recommendation-only and never authorizes execution.
    """

    @staticmethod
    def _validate_unique_domains(candidates: tuple[OptimizationCandidate, ...]) -> None:
        domains = [candidate.domain for candidate in candidates]
        if len(domains) != len(set(domains)):
            raise ValueError("trajectory portfolio permits at most one intervention per domain")

    @staticmethod
    def _interaction_map(interactions: tuple[TrajectoryInteraction, ...]) -> dict[frozenset[str], float]:
        result: dict[frozenset[str], float] = {}
        for interaction in interactions:
            key = frozenset((interaction.first, interaction.second))
            if len(key) != 2 or key in result:
                raise ValueError("trajectory interaction pairs must be unique")
            result[key] = interaction.effective_effect
        return result

    @staticmethod
    def _objective(selected: tuple[OptimizationCandidate, ...], interaction_map: dict[frozenset[str], float]) -> tuple[float, float]:
        base = sum(candidate.score for candidate in selected)
        interaction_effect = sum(
            interaction_map.get(frozenset((first.intervention_id, second.intervention_id)), 0.0)
            for first, second in combinations(selected, 2)
        )
        return base + interaction_effect, interaction_effect

    @staticmethod
    def optimize(
        candidates: tuple[OptimizationCandidate, ...],
        interventions: dict[str, Intervention],
        interactions: tuple[TrajectoryInteraction, ...] = (),
        *,
        capacity_budget: float = float("inf"),
        max_candidates: int = 5,
    ) -> TrajectoryPortfolio:
        if capacity_budget < 0 or (not isfinite(capacity_budget) and capacity_budget != float("inf")):
            raise ValueError("capacity_budget must be non-negative or infinity")
        if max_candidates < 1:
            raise ValueError("max_candidates must be positive")
        if len({candidate.intervention_id for candidate in candidates}) != len(candidates):
            raise ValueError("candidate intervention ids must be unique")
        if any(candidate.intervention_id not in interventions for candidate in candidates):
            raise ValueError("every candidate must have an intervention definition")

        interaction_map = TrajectoryOptimizationEngine._interaction_map(interactions)
        items = tuple(sorted(candidates, key=lambda c: (c.intervention_id, c.domain.value)))
        best_objective = 0.0
        best_key: tuple[str, ...] = ()
        best: tuple[OptimizationCandidate, ...] = ()
        best_used = 0.0
        best_interaction = 0.0

        # Exact enumeration keeps the semantics transparent and makes pairwise
        # effects genuinely part of the global objective rather than a ranking
        # afterthought. Large search spaces are rejected instead of silently
        # returning an unverified approximation.
        if len(items) > 22:
            raise ValueError("trajectory search space exceeds exact safety limit of 22 candidates")

        for mask in range(1, 1 << len(items)):
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

            portfolio = tuple(selected)
            objective, interaction_effect = TrajectoryOptimizationEngine._objective(portfolio, interaction_map)
            key = tuple(candidate.intervention_id for candidate in portfolio)
            if objective > best_objective + 1e-12 or (abs(objective - best_objective) <= 1e-12 and key < best_key):
                best_objective = objective
                best_key = key
                best = tuple(sorted(portfolio, key=lambda c: (-c.score, c.domain.value, c.intervention_id)))
                best_used = used
                best_interaction = interaction_effect

        remaining = capacity_budget - best_used if capacity_budget != float("inf") else float("inf")
        return TrajectoryPortfolio(
            candidates=best,
            objective=round(best_objective, 6),
            capacity_used=round(best_used, 6),
            capacity_remaining=round(remaining, 6) if isfinite(remaining) else remaining,
            interaction_effect=round(best_interaction, 6),
        )
