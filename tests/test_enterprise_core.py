from singular.enterprise_core import EnterpriseOperatingCore, Initiative, InitiativeStatus, OperatingDecision, KPI


def test_operating_core_selects_best_feasible_initiatives() -> None:
    initiatives = (
        Initiative("A", "Fast cash", "cash", "BUSINESS", 100, 0.9, 10, 2, urgency=9, strategic_fit=9, recurring_gain=0.5),
        Initiative("B", "Long bet", "ownership", "STRATEGY", 300, 0.8, 80, 8, strategic_fit=10, ownership_gain=1.0),
        Initiative("C", "Bad bet", "cash", "BUSINESS", 20, 0.2, 20, 1),
    )
    plan = EnterpriseOperatingCore.prioritize("rebuild and grow", initiatives, capacity_budget=3, financial_budget=20)
    assert plan.selected_ids == ("A",)
    assert plan.has_positive_engine is True
    assert plan.capacity_used == 2
    assert plan.budget_used == 10
    assert plan.allocations[0].decision is OperatingDecision.INVEST


def test_operating_core_is_constraint_aware() -> None:
    initiative = Initiative("A", "Expensive", "growth", "FINANCE", 100, 0.9, 50, 2)
    plan = EnterpriseOperatingCore.prioritize("growth", (initiative,), capacity_budget=10, financial_budget=10)
    assert plan.selected_ids == ()
    assert "NO_POSITIVE_FEASIBLE_INITIATIVE" in plan.warnings


def test_operating_core_surfaces_kpi_underperformance() -> None:
    """KPIs are only weighed once there is a portfolio to weigh them against.

    This passed no initiatives, and prioritize() short-circuits on an empty
    portfolio before it ever looks at KPIs -- so the assertion could not hold and
    the KPI path was never exercised.
    """
    kpi = KPI("recurring revenue", 40, 100)
    initiative = Initiative("A", "Fast cash", "cash", "BUSINESS", 100, 0.9, 10, 2, urgency=9, strategic_fit=9)
    plan = EnterpriseOperatingCore.prioritize("growth", (initiative,), capacity_budget=3, financial_budget=20, kpis=(kpi,))
    assert "KPI_PORTFOLIO_BELOW_TARGET" in plan.warnings


def test_operating_core_reports_an_empty_portfolio_before_anything_else() -> None:
    kpi = KPI("recurring revenue", 40, 100)
    plan = EnterpriseOperatingCore.prioritize("growth", (), capacity_budget=1, financial_budget=1, kpis=(kpi,))
    assert plan.warnings == ("NO_INITIATIVES",)
    assert plan.selected_ids == ()


def test_blocked_completed_and_dropped_work_is_not_selected() -> None:
    initiatives = (
        Initiative("B", "Blocked", "x", "A", 100, 1, 0, 1, status=InitiativeStatus.BLOCKED),
        Initiative("C", "Completed", "x", "A", 100, 1, 0, 1, status=InitiativeStatus.COMPLETED),
        Initiative("D", "Dropped", "x", "A", 100, 1, 0, 1, status=InitiativeStatus.DROPPED),
    )
    plan = EnterpriseOperatingCore.prioritize("x", initiatives, capacity_budget=10, financial_budget=10)
    assert plan.selected_ids == ()
    assert plan.blocked_ids == ("B",)
