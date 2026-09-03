import pytest

from singular.wealth_engine import WealthAction, WealthEngine, WealthObjective, WealthOpportunity


def test_wealth_engine_rewards_ownership_and_compounding() -> None:
    owner = WealthOpportunity("owner", 100, 0.7, 1, 1, 1, 0.9, 0.9, 0.8, 0.9)
    wage = WealthOpportunity("wage", 100, 0.7, 1, 1, 1, 0.1, 0.2, 0.3, 0.9)
    assert WealthEngine.assess(owner).score > WealthEngine.assess(wage).score


def test_ruinous_irreversible_opportunity_requires_human_review() -> None:
    opportunity = WealthOpportunity("ruin", 1000, 0.9, 0.95, 1, 1, 0.8, 0.8, 0.8, 0.1)
    assert WealthEngine.assess(opportunity).action is WealthAction.HUMAN_REVIEW


def test_rank_is_deterministic() -> None:
    opportunities = [
        WealthOpportunity("b", 50, 0.8, 1, 1, 1, 0.5, 0.5, 0.5, 0.8),
        WealthOpportunity("a", 50, 0.8, 1, 1, 1, 0.5, 0.5, 0.5, 0.8),
    ]
    ranked = WealthEngine.rank(opportunities)
    assert [item.opportunity_id for item in ranked] == ["a", "b"]


def test_invalid_probability_is_rejected() -> None:
    with pytest.raises(ValueError):
        WealthOpportunity("bad", 1, 1.1, 0, 0, 0, 0, 0, 0, 0)


def test_objective_changes_downside_and_optionality_preferences() -> None:
    opportunity = WealthOpportunity("o", 100, 0.8, 0.8, 1, 1, 0.8, 0.8, 0.8, 0.9)
    protected = WealthEngine.assess(opportunity, WealthObjective(protect_downside=True))
    permissive = WealthEngine.assess(opportunity, WealthObjective(protect_downside=False, preserve_optionality=False))
    assert protected.score < permissive.score
    assert "DOWNSIDE_PROTECTED" in protected.reasons
    assert "OPTIONALITY_PRESERVED" not in permissive.reasons


def test_objective_horizon_marks_long_term_mismatch() -> None:
    opportunity = WealthOpportunity("long", 100, 1, 0, 1, 100, 0.5, 0.5, 0.5, 0.9)
    assessment = WealthEngine.assess(opportunity, WealthObjective(horizon_years=1))
    assert "BEYOND_OBJECTIVE_HORIZON" in assessment.reasons
