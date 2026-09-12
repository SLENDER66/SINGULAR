from singular.v2_empire import *

def test_capital_snapshot():
    c=CapitalEngine(CapitalPosition(cash=6000, monthly_income=2500, monthly_expenses=1500, debt=2000))
    assert c.snapshot()['surplus']==1000
    assert c.snapshot()['runway_months']==4.0

def test_opportunity_classification():
    o=Opportunity('high leverage', impact=10, probability=0.9, leverage=10, timing=1, cost=1, risk=1)
    assert o.classify()==OpportunityDecision.ACT

def test_risky_irreversible_does_not_auto_act():
    o=Opportunity('danger', impact=10, probability=0.9, leverage=10, timing=1, cost=1, risk=9, reversibility=0.1)
    assert o.classify()!=OpportunityDecision.ACT

def test_revenue_expected_value():
    e=RevenueExperiment('test', setup_cost=100, expected_monthly_revenue=500, probability=.5, duration_days=30)
    assert e.expected_value==150
    assert e.go_no_go(200)=='GO'

def test_asset_compounding():
    a=StrategicAsset('skill', capability_value=10, network_value=5, optionality=7)
    assert a.strategic_value==22
