import math

import pytest

from singular.domain_learning import DomainHypothesis, LearningDomain
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
    interaction = DomainInteraction(LearningDomain.SLEEP, LearningDomain.CAREER, multiplier=2.0, confidence=1.0, causal_strength=1.0)
    report = HumanOptimizationEngine.optimize(
        states,
        (Intervention("career", LearningDomain.CAREER, 0.5, evidence=0.9, causal_confidence=0.9),
         Intervention("sleep", LearningDomain.SLEEP, 0.4, evidence=0.9, causal_confidence=0.9)),
        (interaction,),
    )
    assert report.candidates[0].intervention_id == "career"
    assert "CROSS_DOMAIN_EFFECT" in report.candidates[0].reasons


def test_sensitive_domain_requires_human_review() -> None:
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
    negative = HumanOptimizationEngine.evaluate(Intervention("bad", LearningDomain.FINANCE, 0.1, cost=1.0), states)
    blocked = HumanOptimizationEngine.evaluate(Intervention("danger", LearningDomain.FINANCE, 1.0, risk=8), states)
    assert negative.disposition is OptimizationDisposition.REVIEW
    assert blocked.disposition is OptimizationDisposition.BLOCK


def test_duplicate_domain_state_fails_closed() -> None:
    states = (DomainState(LearningDomain.CAREER, 0.5), DomainState(LearningDomain.CAREER, 0.6))
    with pytest.raises(ValueError):
        HumanOptimizationEngine.find_bottlenecks(states)


def test_capacity_is_accounted_for_in_selected_portfolio() -> None:
    states = (
        DomainState(LearningDomain.CAREER, 0.2, confidence=0.9, leverage=1.0),
        DomainState(LearningDomain.BUSINESS, 0.2, confidence=0.9, leverage=1.0),
    )
    report = HumanOptimizationEngine.optimize(
        states,
        (
            Intervention("career", LearningDomain.CAREER, 0.9, evidence=0.9, causal_confidence=0.9, capacity=3),
            Intervention("business", LearningDomain.BUSINESS, 0.8, evidence=0.9, causal_confidence=0.9, capacity=3),
        ),
        capacity_budget=4,
    )
    assert len(report.candidates) == 1
    assert report.capacity_used == 3
    assert report.capacity_remaining == 1


def test_hypothesis_bridge_preserves_learning_signal() -> None:
    hypothesis = DomainHypothesis(
        LearningDomain.CAREER,
        "testing improves interview conversion",
        "run interview experiments",
        expected_improvement=0.7,
        cost=0.1,
        risk=0.2,
        reversibility=0.9,
        evidence_strength=0.8,
    )
    intervention = Intervention.from_hypothesis(hypothesis)
    assert intervention.domain is LearningDomain.CAREER
    assert intervention.expected_improvement == 0.7
    assert intervention.evidence == 0.8
    assert intervention.causal_confidence == 0.8


def test_non_finite_and_self_interaction_fail_closed() -> None:
    with pytest.raises(ValueError):
        DomainState(LearningDomain.CAREER, math.nan)
    with pytest.raises(ValueError):
        DomainInteraction(LearningDomain.CAREER, LearningDomain.CAREER)


def test_uncertainty_is_explicit_in_report() -> None:
    report = HumanOptimizationEngine.optimize(
        (DomainState(LearningDomain.CAREER, 0.4, confidence=0.2),),
        (Intervention("career", LearningDomain.CAREER, 0.8, evidence=0.2, causal_confidence=0.3),),
    )
    assert "LOW_STATE_CONFIDENCE" in report.uncertainties
    assert "LOW_EVIDENCE_OR_CAUSAL_CONFIDENCE" in report.uncertainties
