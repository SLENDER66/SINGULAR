import pytest

from singular.cashflow_engine import CashflowAction, CashflowOpportunity, RapidCashEngine, RapidCashObjective


def test_fast_positive_cash_path_is_prioritized() -> None:
    objective = RapidCashObjective(target_cash=1_000, horizon_days=14)
    opportunity = CashflowOpportunity("a", "Short service", 500, 0.9, 8, 20, 0.8, 0.9, 1.0, 0.3)
    result = RapidCashEngine.assess(opportunity, objective)
    assert result.action is CashflowAction.PRIORITIZE
    assert "FAST_FIRST_CASH" in result.reasons


def test_high_irreversible_exposure_requires_human_review() -> None:
    objective = RapidCashObjective(target_cash=1_000)
    opportunity = CashflowOpportunity("a", "Risky deal", 2_000, 0.9, 24, 400, 0.5, 0.8, 0.1, 0.2)
    result = RapidCashEngine.assess(opportunity, objective)
    assert result.action is CashflowAction.HUMAN_REVIEW
    assert result.human_review_required


def test_negative_expected_cash_is_ignored() -> None:
    objective = RapidCashObjective(target_cash=1_000)
    opportunity = CashflowOpportunity("a", "Loss", 100, 0.2, 10, 100, 0.1, 0.5, 1.0, 0.0)
    result = RapidCashEngine.assess(opportunity, objective)
    assert result.action is CashflowAction.IGNORE
    assert result.expected_value == -80


def test_sprint_is_deterministic_and_bounded() -> None:
    objective = RapidCashObjective(target_cash=1_000)
    opportunities = [
        CashflowOpportunity("b", "B", 600, 0.9, 12, 0, 0.8, 0.8, 1.0, 0.2),
        CashflowOpportunity("a", "A", 500, 0.9, 10, 0, 0.8, 0.8, 1.0, 0.2),
        CashflowOpportunity("c", "C", 50, 0.9, 8, 0, 0.1, 0.5, 1.0, 0.0),
    ]
    result = RapidCashEngine.build_sprint(opportunities, objective, max_parallel_tests=2)
    assert len(result) == 2
    assert result[0].opportunity_id == "a"


def test_invalid_sprint_size_is_rejected() -> None:
    with pytest.raises(ValueError):
        RapidCashEngine.build_sprint([], RapidCashObjective(target_cash=100), max_parallel_tests=0)
