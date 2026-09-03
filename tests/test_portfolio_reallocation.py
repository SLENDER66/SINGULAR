from singular.enterprise_core import Initiative, InitiativeStatus
from singular.portfolio_reallocation import (
    DynamicPortfolioEngine,
    InitiativeResult,
    ReallocationAction,
)


def initiative(id: str, value: float, cost: float, effort: float, *, risk: float = 3.0) -> Initiative:
    return Initiative(
        id=id,
        name=id,
        objective="grow",
        owner="agent",
        expected_value=value,
        probability=0.9,
        cost=cost,
        effort=effort,
        strategic_fit=8,
        urgency=8,
        ownership_gain=0.2,
        recurring_gain=0.2,
        risk=risk,
    )


def test_global_reallocation_beats_greedy_first_choice() -> None:
    a = initiative("A", 100, 6, 6)
    b = initiative("B", 70, 4, 4)
    c = initiative("C", 65, 4, 4)
    plan = DynamicPortfolioEngine.rebalance(
        "grow", (a, b, c), capacity_budget=8, financial_budget=8, max_active=2
    )
    assert plan.selected_ids == ("B", "C")
    assert plan.capacity_used == 8
    assert plan.budget_used == 8


def test_outperformance_is_allowed_to_change_allocation() -> None:
    a = initiative("A", 100, 5, 5)
    b = initiative("B", 80, 5, 5)
    plan = DynamicPortfolioEngine.rebalance(
        "grow",
        (a, b),
        results=(InitiativeResult("A", 150, 5, 5), InitiativeResult("B", 40, 5, 5)),
        current_active_ids=("B",),
        capacity_budget=5,
        financial_budget=5,
        max_active=1,
    )
    assert plan.selected_ids == ("A",)
    assert "B" in plan.reduced_ids
    assert next(x for x in plan.reallocations if x.initiative_id == "A").action is ReallocationAction.INVEST


def test_dangerous_result_stops_initiative() -> None:
    a = initiative("A", 100, 5, 5)
    plan = DynamicPortfolioEngine.rebalance(
        "grow", (a,),
        results=(InitiativeResult("A", 0, 5, 5, success=False),),
        current_active_ids=("A",),
        capacity_budget=5,
        financial_budget=5,
    )
    assert plan.stopped_ids == ("A",)
    assert next(x for x in plan.reallocations if x.initiative_id == "A").action is ReallocationAction.STOP


def test_bottlenecks_and_overcapacity_are_visible() -> None:
    a = initiative("A", 100, 5, 5)
    plan = DynamicPortfolioEngine.rebalance(
        "grow", (a,),
        results=(InitiativeResult("A", 90, 7, 7),),
        current_active_ids=("A", "UNKNOWN"),
        capacity_budget=5,
        financial_budget=5,
    )
