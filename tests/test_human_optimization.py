import pytest

from singular.domain_learning import LearningDomain
from singular.human_optimization import (
    DomainInteraction,
    DomainState,
    HumanOptimizationEngine,
    Intervention,
    OptimizationDisposition,
)


def test_bottleneck_ranks_low_high_leverage_domain_first() -> None:
    states = (
        DomainState(LearningDomain.CAREER, 0.4, leverage=1.0),
        DomainState(LearningDomain.SLEEP, 0.6, leverage=2.0),
    )
    assert HumanOptimizationEngine.find_bottlenecks(states)[0] is LearningDomain.SLEEP


def test_cross_domain_multiplier_changes_priority() -> None:
    states = (
        DomainState(LearningDomain.CAREER, 0.5, leverage=1.0),
        DomainState(LearningDomain.SLEEP, 0.5, leverage=1.0),
    )
    interaction = DomainInteraction(LearningDomain.SLEEP, LearningDomain.CAREER, multiplier=2.0, confidence=1.0)
    report = HumanOptimizationEngine.optimize(
        states,
        (Intervention("career", LearningDomain.CAREER, 0.5, evidence=0.9, causal_confidence=0.9),
         Intervention("sleep", LearningDomain.SLEEP, 0.4, evidence=0.9, causal_confidence=0.9)),
        (interaction,),
    )
    assert report.candidates[0].intervention_id == "career"
    assert "CROSS_DOMAIN_EFFECT" in report.candidates[0].reasons


def test_sensitive_domain_never_becomes_unreviewed_execution() -> None:
    states = (DomainState(LearningDomain.NUTRITION, 0.5),)
    report = HumanOptimizationEngine.optimize(
        states,
        (Intervention("nutrition", LearningDomain.NUTRITION, 0.8, evidence=0.95, causal_confidence=0.95),),
    )
    candidate = report.candidates[0]
    assert candidate.disposition is OptimizationDisposition.PROPOSE
    assert candidate.human_review is True


def test_low_evidence_and_causality_are_test_not_adopt() -> None:
    states = (DomainState(LearningDomain.PRODUCTIVITY, 0.3),)
    candidate = HumanOptimizationEngine.evaluate(
        Intervention("focus", LearningDomain.PRODUCTIVITY, 0.8, evidence=0.4, causal_confidence=0.3),
        states,
    )
    assert candidate.disposition is OptimizationDisposition.TEST
    assert "LOW_EVIDENCE" in candidate.reasons
    assert "CAUSALITY_UNCERTAIN" in candidate.reasons


def test_negative_value_is_reviewed_and_high_risk_is_blocked() -> None:
    states = (DomainState(LearningDomain.FINANCE, 0.5),)
    negative = HumanOptimizationEngine.evaluate(
        Intervention("bad", LearningDomain.FINANCE, 0.1, cost=1.0), states
    )
    blocked = HumanOptimizationEngine.evaluate(
        Intervention("danger", LearningDomain.FINANCE, 1.0, risk=8), states
    )
    assert negative.disposition is OptimizationDisposition.REVIEW
    assert blocked.disposition is OptimizationDisposition.BLOCK


def test_duplicate_domain_state_fails_closed() -> None:
    states = (
        DomainState(LearningDomain.CAREER, 0.5),
        DomainState(LearningDomain.CAREER, 0.6),
    )
    with pytest.raises(ValueError):
        HumanOptimizationEngine.find_bottlenecks(states)
