import pytest

from singular.models import Opportunity
from singular.portfolio import PortfolioEngine


def opportunity(identifier: str, *, impact: float, probability: float, leverage: float, cost: float, risk: float, reversibility: float = 8, optionality: float = 8) -> Opportunity:
    return Opportunity(
        id=identifier,
        name=identifier,
        impact=impact,
        probability=probability,
        leverage=leverage,
        cost=cost,
        risk=risk,
        reversibility=reversibility,
        optionality=optionality,
    )


def test_portfolio_respects_budget_and_risk_budget() -> None:
    items = [
        opportunity("a", impact=10, probability=0.9, leverage=9, cost=4, risk=2),
        opportunity("b", impact=8, probability=0.8, leverage=8, cost=3, risk=2),
        opportunity("c", impact=9, probability=0.9, leverage=9, cost=4, risk=8),
    ]

    result = PortfolioEngine.optimize(items, budget=5, risk_budget=4)

    assert result.total_cost <= 5
    assert result.total_risk <= 4
    assert {item.opportunity_id for item in result.selections} == {"a"}


def test_portfolio_excludes_ignored_and_high_risk_escalations() -> None:
    items = [
        opportunity("test", impact=10, probability=0.8, leverage=9, cost=1, risk=1),
        opportunity("ignored", impact=2, probability=0.1, leverage=1, cost=9, risk=9),
        opportunity("escalate", impact=10, probability=0.9, leverage=10, cost=1, risk=8, reversibility=2),
    ]

    result = PortfolioEngine.optimize(items, budget=10, risk_budget=10)

    assert [item.opportunity_id for item in result.selections] == ["test"]
    assert set(result.rejected_ids) == {"escalate", "ignored"}


def test_portfolio_is_deterministic_on_ties() -> None:
    items = [
        opportunity("b", impact=5, probability=0.5, leverage=5, cost=1, risk=1),
        opportunity("a", impact=5, probability=0.5, leverage=5, cost=1, risk=1),
    ]

    first = PortfolioEngine.optimize(items, budget=1, risk_budget=2)
    second = PortfolioEngine.optimize(items, budget=1, risk_budget=2)

    assert first == second
    assert [item.opportunity_id for item in first.selections] == ["a"]


def test_invalid_portfolio_constraints_fail_closed() -> None:
    with pytest.raises(ValueError):
        PortfolioEngine.optimize([], budget=-1, risk_budget=1)
    with pytest.raises(ValueError):
        PortfolioEngine.optimize([], budget=1, risk_budget=-1)
    with pytest.raises(ValueError):
        PortfolioEngine.optimize([], budget=1, risk_budget=1, max_positions=-1)
