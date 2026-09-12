import pytest

from singular.jarvis.trajectory import TrajectoryCandidate, prioritize


def test_reversible_learning_opportunity_is_prioritized():
    priority = prioritize(TrajectoryCandidate(
        name="experiment",
        impact=7,
        risk=2,
        reversibility=9,
        leverage=8,
        dependency=8,
        uncertainty=8,
        cost=2,
        learning=9,
        ownership=8,
        recurrence=7,
    ))

    assert priority.score > 50
    assert priority.test_first is True
    assert "LOW_COST_TEST_FIRST" in priority.reasons
    assert "OWNERSHIP" in priority.reasons


def test_local_impact_does_not_ignore_risk_and_cost():
    risky = prioritize(TrajectoryCandidate(
        name="big-bet", impact=10, risk=10, reversibility=1,
        leverage=3, dependency=1, uncertainty=9, cost=10,
    ))
    safe = prioritize(TrajectoryCandidate(
        name="small-test", impact=6, risk=2, reversibility=9,
        leverage=7, dependency=7, uncertainty=6, cost=2, learning=8,
    ))

    assert safe.score > risky.score


def test_candidate_values_are_bounded_and_finite():
    with pytest.raises(ValueError):
        TrajectoryCandidate(name="x", impact=float("nan"), risk=1, reversibility=1)
    with pytest.raises(ValueError):
        TrajectoryCandidate(name="x", impact=1, risk=11, reversibility=1)
