from singular.values import CoreValue, ValueAssessment, ValueMode, ValuesEngine, Vision


def test_value_rejects_empty_name_and_non_positive_weight():
    import pytest

    with pytest.raises(ValueError):
        CoreValue("")
    with pytest.raises(ValueError):
        CoreValue("Freedom", weight=0)


def test_violated_hard_constraint_blocks_outright_without_asking_a_human():
    """A hard constraint is not a question put to a human; it is a refusal.

    This test demanded human_review for a HARD_CONSTRAINT violation. Review is
    reserved for what a human could still decide -- UNKNOWN assessments and
    violations of GUIDING or OVERRIDEABLE values. Asking for review on something
    already blocked would invite it to be overridden, which is exactly what a
    hard constraint must not allow.
    """
    value = CoreValue("Integrity")
    result = ValuesEngine.assess(value, ValueAssessment.VIOLATED, "Conflicts with the proposed action.")
    summary = ValuesEngine.summarize([result])
    assert summary["allowed"] is False
    assert summary["human_review"] is False
    assert summary["violated"] == ["Integrity"]
    assert summary["hard_violations"] == ["Integrity"]
    assert summary["overrideable_violations"] == []


def test_violated_overrideable_value_does_not_block_but_requires_review():
    """The other side of the distinction, so relaxing one is not relaxing both."""
    value = CoreValue("Ambition", mode=ValueMode.OVERRIDEABLE)
    result = ValuesEngine.assess(value, ValueAssessment.VIOLATED, "In tension with the proposed action.")
    summary = ValuesEngine.summarize([result])
    assert summary["allowed"] is True
    assert summary["human_review"] is True
    assert summary["hard_violations"] == []
    assert summary["overrideable_violations"] == ["Ambition"]


def test_unknown_value_requires_human_but_does_not_auto_block():
    result = ValuesEngine.assess(CoreValue("Family"), ValueAssessment.UNKNOWN)
    assert ValuesEngine.allows_action([result]) is True
    assert ValuesEngine.requires_human_review([result]) is True


def test_tension_is_visible_without_being_treated_as_violation():
    result = ValuesEngine.assess(CoreValue("Freedom"), ValueAssessment.TENSION)
    summary = ValuesEngine.summarize([result])
    assert summary["allowed"] is True
    assert summary["human_review"] is False
    assert summary["tensions"] == ["Freedom"]


def test_vision_requires_statement():
    import pytest

    with pytest.raises(ValueError):
        Vision("")
