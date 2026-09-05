from singular.v2_1_control import *


def test_portfolio_ranking_and_allocation():
    items = [
        PortfolioItem('A', 'time', 100, .8, 8, 1, 2, optionality=5, strategic_fit=5, resource_need=2),
        PortfolioItem('B', 'time', 20, .5, 2, 4, 6, resource_need=2),
    ]
    budgets = [ResourceBudget('time', 3, minimum_reserve=0.5)]
    eng = PortfolioEngine()
    ranked = eng.rank(items)
    assert ranked[0].name == 'A'
    alloc = eng.allocate(items, budgets)
    assert alloc[0].amount > 0
    assert budgets[0].available < 0.6


def test_compounding_and_risk():
    loops = [CompoundingLoop('Flywheel', ('skill', 'income', 'capital'), 8, 9, 7, 1)]
    assert CompoundingEngine().strongest(loops).name == 'Flywheel'
    risks = [RiskExposure('single dependency', .5, 9, .8, .2), RiskExposure('minor', .2, 2)]
    r = RiskControlEngine()
    assert r.rank(risks)[0].name == 'single dependency'
    assert r.concentration(risks) > .7


def test_snapshot():
    control = EmpireControl()
    items = [PortfolioItem('A', 'time', 10, 1, 1, 1, 1)]
    alloc = [Allocation(items[0].id, 'A', 1, AllocationDecision.TEST, 'x')]
    snap = control.snapshot(items, [], [], alloc)
    assert snap.allocated_resources == 1
    assert snap.top_initiatives == ['A']
