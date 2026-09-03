from singular.cashflow_engine import CashflowOpportunity, RapidCashObjective
from singular.capital_allocation import AllocationBucket, AllocationCandidate
from singular.economic_control import EconomicControlPlane, EconomicPlanStatus
from singular.empire_engine import EmpireAsset
from singular.generational import GenerationalCharter
from singular.patrimony_engine import FailureRecord
from singular.wealth_engine import WealthOpportunity, WealthObjective


def test_control_plane_builds_reviewable_economic_plan() -> None:
    cash = CashflowOpportunity("cash-1", "service", 1000, 0.8, 24, 50, 0.8, 0.8, 1.0, 0.2)
    wealth = WealthOpportunity("wealth-1", 5000, 0.7, 1, 2, 1, 0.8, 0.8, 0.8, 0.9)
    candidate = AllocationCandidate(wealth, AllocationBucket.OWNERSHIP, 2, 0.2)
    plan = EconomicControlPlane.build(
        cashflow_opportunities=[cash],
        rapid_cash_objective=RapidCashObjective(500),
        wealth_opportunities=[wealth],
        wealth_objective=WealthObjective(),
        allocation_candidates=[candidate],
        available_capital=100,
        protected_capital=50,
        risk_budget=10,
        capacity_budget=10,
        empire_assets=[EmpireAsset("a", "asset", 100, 1, 10, 0.1, 0.5, 0.8, 0.1)],
        patrimony={"generations": 1, "ownership_continuity": 0.5, "governance": 0.5, "systemization": 0.5, "succession": 0.5, "resilience": 0.5},
        generational_charter=GenerationalCharter(1, "build and transmit"),
        generational_metrics={"capital_protection": 0.8, "founder_independence": 0.5, "institutional_resilience": 0.5},
        failures=[FailureRecord("f1", "cash", 100, 50, 10, True)],
    )
    assert plan.status is EconomicPlanStatus.REVIEW
    assert plan.rapid_cash.selected_opportunities
    assert plan.wealth_assessments
    assert plan.failure_conversions
    assert plan.next_actions


def test_control_plane_blocks_when_no_economic_path_exists() -> None:
    plan = EconomicControlPlane.build(
        cashflow_opportunities=[],
        rapid_cash_objective=RapidCashObjective(1000),
        wealth_opportunities=[],
        wealth_objective=WealthObjective(),
        allocation_candidates=[],
        available_capital=0,
        protected_capital=0,
        risk_budget=0,
        capacity_budget=0,
        empire_assets=[],
        patrimony={"generations": 1, "ownership_continuity": 0.5, "governance": 0.5, "systemization": 0.5, "succession": 0.5, "resilience": 0.5},
        generational_charter=GenerationalCharter(1, "mission"),
        generational_metrics={"capital_protection": 0.5, "founder_independence": 0.5, "institutional_resilience": 0.5},
    )
    assert plan.status is EconomicPlanStatus.BLOCKED
    assert "NO_ECONOMIC_OPPORTUNITIES" in plan.blockers
