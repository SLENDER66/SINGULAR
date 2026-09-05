import pytest

from singular.domain_learning import LearningDomain
from singular.human_optimizer import HumanDomainState, HumanOptimizationEngine, OptimizationAction


def test_prioritizes_weak_high_leverage_bottleneck() -> None:
    plan = HumanOptimizationEngine.optimize((
        HumanDomainState(LearningDomain.SLEEP, level=0.25, confidence=0.9, leverage=0.9),
        HumanDomainState(LearningDomain.PRODUCTIVITY, level=0.7, confidence=0.9, leverage=0.6, dependencies=(LearningDomain.SLEEP,)),
        HumanDomainState(LearningDomain.FINANCE, level=0.6, confidence=0.9, leverage=0.7),
    ))
    assert plan.primary is not None
    assert plan.primary.domain is LearningDomain.SLEEP
    assert LearningDomain.SLEEP in plan.bottlenecks
    assert "CONSTRAINS_DEPENDENT_DOMAINS" in plan.primary.reasons


def test_low_confidence_becomes_review_not_false_certainty() -> None:
    plan = HumanOptimizationEngine.optimize((
        HumanDomainState(LearningDomain.PSYCHOLOGY, level=0.2, confidence=0.2, leverage=1.0),
    ))
    assert plan.primary is not None
    assert plan.primary.action is OptimizationAction.REVIEW
    assert plan.primary.human_review is True
    assert "LOW_CONFIDENCE_STATE_REQUIRES_MEASUREMENT" in plan.warnings


def test_missing_dependency_is_visible() -> None:
    plan = HumanOptimizationEngine.optimize((
        HumanDomainState(LearningDomain.BUSINESS, level=0.5, confidence=0.8, leverage=0.8, dependencies=(LearningDomain.COMMUNICATION,)),
    ))
    assert "MISSING_DEPENDENCY:business:communication" in plan.warnings


def test_duplicate_domain_is_rejected() -> None:
    with pytest.raises(ValueError):
        HumanOptimizationEngine.optimize((
            HumanDomainState(LearningDomain.FINANCE, level=0.4),
            HumanDomainState(LearningDomain.FINANCE, level=0.5),
        ))


def test_empty_state_fails_closed_to_no_priorities() -> None:
    plan = HumanOptimizationEngine.optimize(())
    assert plan.priorities == ()
    assert plan.global_readiness == 0.0
    assert plan.warnings == ("NO_HUMAN_STATE_DATA",)
