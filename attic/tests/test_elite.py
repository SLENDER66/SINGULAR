import pytest

from singular.elite import ConflictType, EliteEngine, EliteScore


def test_elite_score_total_and_weakest():
    score = EliteScore(
        expertise=0.9,
        evidence=0.8,
        outcome=0.7,
        calibration=0.6,
        learning=0.95,
    )
    assert score.total == 0.79
    assert score.weakest == "calibration"


def test_elite_score_rejects_out_of_range_values():
    score = EliteScore(1.1, 0.8, 0.7, 0.6, 0.9)
    with pytest.raises(ValueError, match="between 0 and 1"):
        _ = score.total


def test_elite_review_targets_weakest_dimension():
    score = EliteScore(0.9, 0.5, 0.8, 0.7, 0.9)
    review = EliteEngine.review("FINANCE", score)
    assert review.agent == "FINANCE"
    assert review.priority == "evidence"
    assert review.score == score.total
    assert review.wealth_relevance


def test_red_team_challenges_specialist_without_execution_authority():
    review = EliteEngine.review("BUSINESS", EliteScore(0.9, 0.8, 0.4, 0.8, 0.9))
    challenge = EliteEngine.challenge("BUSINESS", review)
    assert challenge["challenger"] == "RED_TEAM"
    assert challenge["target"] == "BUSINESS"
    assert challenge["priority"] == "outcome"
    assert "evidence" in challenge["question"].lower()
    assert challenge["wealth_test"] == review.wealth_relevance


def test_conflicts_have_one_explicit_resolver_and_never_grant_execution():
    expected = {
        ConflictType.FACTUAL: "INTELLIGENCE",
        ConflictType.FORECAST: "STRATEGY",
        ConflictType.STRATEGIC: "COMMANDER",
        ConflictType.RISK: "RED_TEAM",
        ConflictType.AUTHORIZATION: "GOVERNOR",
        ConflictType.OBJECTIVE: "COMMANDER",
        ConflictType.UNSOLVED: "HUMAN",
    }
    for conflict_type, resolver in expected.items():
        resolution = EliteEngine.resolve_conflict(conflict_type)
        assert resolution.resolver == resolver
        assert resolution.action
        assert resolution.execution_allowed is False
