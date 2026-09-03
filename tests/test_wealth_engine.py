import pytest

from singular.wealth_engine import WealthAction, WealthEngine, WealthOpportunity


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
