from singular.cashflow_engine import CashflowOpportunity, RapidCashObjective
from singular.rapid_wealth import RapidWealthEngine


def test_rapid_wealth_sprint_targets_cash_without_execution() -> None:
    objective = RapidCashObjective(target_cash=1_000, horizon_days=14)
    opportunities = [
        CashflowOpportunity("fast", "Fast service", 600, 0.9, 12, 0, 0.8, 0.9, 1.0, 0.2),
        CashflowOpportunity("slow", "Slow project", 2_000, 0.8, 240, 50, 0.9, 0.8, 1.0, 0.5),
    ]
    sprint = RapidWealthEngine.build_sprint(opportunities, objective)
    assert sprint.target_cash == 1_000
    assert sprint.selected_opportunities
    assert sprint.selected_opportunities[0].opportunity_id == "fast"
    assert sprint.expected_cash > 0
    assert "GENERATE_CASH" in RapidWealthEngine.next_stage()


def test_rapid_wealth_sprint_is_bounded() -> None:
    objective = RapidCashObjective(target_cash=1_000)
    opportunities = [
        CashflowOpportunity(str(i), f"Opportunity {i}", 500, 0.9, 12, 0)
        for i in range(5)
    ]
    sprint = RapidWealthEngine.build_sprint(opportunities, objective, max_parallel_tests=2)
    assert len(sprint.selected_opportunities) == 2
