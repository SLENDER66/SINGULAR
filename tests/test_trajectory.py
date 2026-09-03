import pytest

from singular.state import CapacitySnapshot
from singular.trajectory import TrajectoryDecision, TrajectoryEngine, TrajectoryProfile
from singular.values import CoreValue, ValueAssessment, ValueAssessmentResult, Vision


def profile() -> TrajectoryProfile:
    return TrajectoryProfile(Vision("Build durable freedom, ownership and transmission."))


def test_global_trajectory_can_proceed_when_all_dimensions_are_positive() -> None:
    result = TrajectoryEngine.assess(
        profile(),
        dimensions={
            "money": 0.8, "time": 0.7, "capability": 0.8, "energy": 0.7,
            "freedom": 0.8, "ownership": 0.9, "learning": 0.8,
            "resilience": 0.7, "transmission": 0.6,
        },
    )
    assert result.decision is TrajectoryDecision.PROCEED
    assert result.score > 0.7


def test_value_violation_blocks_even_when_economics_look_good() -> None:
    value = CoreValue("freedom")
    result = TrajectoryEngine.assess(
        profile(),
        dimensions={name: 1.0 for name in profile().weights},
        value_results=(ValueAssessmentResult(value, ValueAssessment.VIOLATED, "conflict"),),
    )
    assert result.decision is TrajectoryDecision.BLOCK
    assert result.human_review is True
    assert "CORE_VALUE_VIOLATION" in result.rationale


def test_missing_dimension_requires_review_instead_of_silent_optimization() -> None:
    result = TrajectoryEngine.assess(profile(), dimensions={"money": 0.9})
    assert result.decision is TrajectoryDecision.REVIEW
    assert result.human_review is True
    assert "MISSING_DIMENSION:time" in result.rationale


def test_low_capacity_confidence_is_visible_and_never_upgrades_to_proceed() -> None:
    result = TrajectoryEngine.assess(
        profile(),
        dimensions={name: 0.8 for name in profile().weights},
        capacity=CapacitySnapshot(0.8, 0.1, 0.0, 0.4),
    )
    assert result.decision is TrajectoryDecision.REVIEW
    assert "LOW_CAPACITY_CONFIDENCE" in result.rationale


def test_unknown_dimension_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown trajectory dimensions"):
        TrajectoryEngine.assess(profile(), dimensions={"money": 1.0, "unknown": 1.0})
