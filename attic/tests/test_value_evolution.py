from singular.value_evolution import (
    ValueEvolutionDisposition,
    ValueEvolutionEngine,
    ValueHypothesis,
)


def test_current_preference_can_be_questioned_without_auto_rewrite() -> None:
    result = ValueEvolutionEngine.assess(
        ValueHypothesis("freedom", "current", "alternative", expected_gain=2.0, evidence_strength=0.6)
    )
    assert result.disposition is ValueEvolutionDisposition.TEST
    assert "BOUNDED_TEST_RECOMMENDED" in result.reasons


def test_strong_alternative_requires_review_not_automatic_replacement() -> None:
    result = ValueEvolutionEngine.compare(0.5, 0.9)
    assert result.disposition is ValueEvolutionDisposition.REVIEW
    assert result.human_review is True


def test_current_position_is_kept_when_alternative_is_worse() -> None:
    result = ValueEvolutionEngine.compare(0.9, 0.5)
    assert result.disposition is ValueEvolutionDisposition.KEEP
    assert result.human_review is False


def test_low_reversibility_requires_human_review() -> None:
    result = ValueEvolutionEngine.assess(
        ValueHypothesis("preference", "current", "alternative", expected_gain=3.0, reversibility=0.1, evidence_strength=0.9)
    )
    assert result.human_review is True
    assert "LOW_REVERSIBILITY" in result.reasons
