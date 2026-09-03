import pytest

from singular.domain_learning import LearningDomain
from singular.human_optimization import Intervention, OptimizationCandidate, OptimizationDisposition
from singular.trajectory_optimization import TrajectoryInteraction, TrajectoryOptimizationEngine


def candidate(identifier: str, domain: LearningDomain, score: float) -> OptimizationCandidate:
    return OptimizationCandidate(identifier, domain, score, score, OptimizationDisposition.PROPOSE, (), False)


def test_synergy_can_make_combination_better_than_individual_ranking() -> None:
    candidates = (
        candidate("career", LearningDomain.CAREER, 6),
        candidate("learning", LearningDomain.LEARNING, 5),
        candidate("finance", LearningDomain.FINANCE, 5),
    )
    interventions = {item.intervention_id: Intervention(item.intervention_id, item.domain, 1, capacity=1) for item in candidates}
    portfolio = TrajectoryOptimizationEngine.optimize(
        candidates,
        interventions,
        (TrajectoryInteraction("learning", "finance", effect=4),),
        capacity_budget=2,
    )
    assert tuple(item.intervention_id for item in portfolio.candidates) == ("finance", "learning")
    assert portfolio.interaction_effect == 4
    assert portfolio.objective == 14


def test_conflict_can_make_individually_good_interventions_bad_together() -> None:
    candidates = (
        candidate("career", LearningDomain.CAREER, 7),
        candidate("business", LearningDomain.BUSINESS, 6),
    )
    interventions = {item.intervention_id: Intervention(item.intervention_id, item.domain, 1, capacity=1) for item in candidates}
    portfolio = TrajectoryOptimizationEngine.optimize(
        candidates,
        interventions,
        (TrajectoryInteraction("career", "business", effect=-20),),
        capacity_budget=2,
    )
    assert tuple(item.intervention_id for item in portfolio.candidates) == ("career",)
    assert portfolio.objective == 7


def test_uncertain_interaction_is_discounted() -> None:
    interaction = TrajectoryInteraction("a", "b", effect=10, confidence=0.2)
    assert interaction.effective_effect == 2


def test_duplicate_interaction_pair_fails_closed() -> None:
    candidates = (candidate("a", LearningDomain.CAREER, 2), candidate("b", LearningDomain.BUSINESS, 2))
    interventions = {item.intervention_id: Intervention(item.intervention_id, item.domain, 1) for item in candidates}
    with pytest.raises(ValueError):
        TrajectoryOptimizationEngine.optimize(
            candidates,
            interventions,
            (TrajectoryInteraction("a", "b"), TrajectoryInteraction("b", "a")),
        )


def test_large_search_space_is_not_presented_as_exact() -> None:
    domains = list(LearningDomain)
    candidates = tuple(candidate(f"i{index}", domains[index], 1) for index in range(23))
    interventions = {item.intervention_id: Intervention(item.intervention_id, item.domain, 1) for item in candidates}
    with pytest.raises(ValueError, match="exact safety limit"):
        TrajectoryOptimizationEngine.optimize(candidates, interventions)
