import pytest

from singular.patrimony_engine import (
    FailureDisposition,
    FailureRecord,
    PatrimonyEngine,
)


def test_reversible_failure_becomes_learning_and_low_cost_retest():
    result = PatrimonyEngine.convert_failure(
        FailureRecord("f1", "launch", 10, 4, 2, True)
    )
    assert result.disposition is FailureDisposition.LEARN
    assert result.learning_asset == "CAPTURE_CAUSE_AND_UPDATE_FORECAST"
    assert result.next_test == "DESIGN_LOW_COST_VALIDATION_TEST"


def test_validated_failure_can_become_a_controlled_retest():
    result = PatrimonyEngine.convert_failure(
        FailureRecord("f2", "test", 10, 8, 1, True, "pricing assumption was wrong", True)
    )
    assert result.disposition is FailureDisposition.TEST_AGAIN
    assert result.learning_asset == "pricing assumption was wrong"


def test_irreversible_failure_is_contained_before_retry():
    result = PatrimonyEngine.convert_failure(
        FailureRecord("f3", "acquisition", 100, 0, 50, False)
    )
    assert result.disposition is FailureDisposition.CONTAIN
    assert result.next_test is None


def test_patrimony_prioritizes_continuity_weaknesses():
    result = PatrimonyEngine.assess(
        generations=1,
        ownership_continuity=0.5,
        governance=0.4,
        systemization=0.6,
        succession=0.3,
        resilience=0.5,
    )
    assert "PROTECT_OWNERSHIP_CONTINUITY" in result.priorities
    assert "PREPARE_SUCCESSION" in result.priorities


def test_mature_patrimony_can_compound_and_transmit():
    result = PatrimonyEngine.assess(
        generations=2,
        ownership_continuity=0.9,
        governance=0.9,
        systemization=0.9,
        succession=0.9,
        resilience=0.9,
    )
    assert result.score == 0.9
    assert result.priorities == ("COMPOUND_AND_TRANSMIT",)


def test_validated_failure_requires_a_lesson():
    with pytest.raises(ValueError):
        FailureRecord("f4", "test", 1, 0, 1, True, validated=True)
