from singular.models import Opportunity
from singular.opportunity_engine import OpportunityDecision, OpportunityEngine


def test_outlier_like_opportunity_becomes_low_cost_test():
    opportunity = Opportunity(
        id="O1", name="high leverage experiment", impact=9, probability=0.7,
        leverage=9, cost=1, risk=3, reversibility=9, optionality=9,
    )
    assessment = OpportunityEngine.assess(opportunity)
    assert assessment.decision is OpportunityDecision.TEST
    assert assessment.red_team_required is True
    assert assessment.human_review_required is False
    assert "FORT_LEVERAGE" in assessment.reasons
    assert "FAIBLE_COUT_INITIAL" in assessment.reasons


def test_high_risk_opportunity_escalates_instead_of_auto_testing():
    opportunity = Opportunity(
        id="O2", name="dangerous outlier", impact=10, probability=0.8,
        leverage=10, cost=1, risk=9, reversibility=8, optionality=10,
    )
    assessment = OpportunityEngine.assess(opportunity)
    assert assessment.decision is OpportunityDecision.ESCALATE
    assert assessment.human_review_required is True


def test_ordinary_low_value_opportunity_is_ignored():
    opportunity = Opportunity(
        id="O3", name="weak opportunity", impact=2, probability=0.2,
        leverage=1, cost=8, risk=7, reversibility=3, optionality=1,
    )
    assessment = OpportunityEngine.assess(opportunity)
    assert assessment.decision is OpportunityDecision.IGNORE


def test_rank_and_shortlist_are_deterministic():
    opportunities = [
        Opportunity("O1", "test", 9, .7, 9, 1, 3, 9, 9),
        Opportunity("O2", "watch", 7, .6, 5, 2, 3, 7, 7),
    ]
    ranked = OpportunityEngine.rank(opportunities)
    assert [item.opportunity_id for item in ranked] == ["O1", "O2"]
    assert [item.opportunity_id for item in OpportunityEngine.shortlist_tests(opportunities)] == ["O1"]
