from singular.values import CoreValue, ValueAssessment, ValuesEngine, Vision


def test_value_rejects_empty_name_and_non_positive_weight():
    import pytest

    with pytest.raises(ValueError):
        CoreValue("")
    with pytest.raises(ValueError):
        CoreValue("Freedom", weight=0)


def test_violated_value_blocks_action_and_requires_human_review():
    value = CoreValue("Integrity")
    result = ValuesEngine.assess(value, ValueAssessment.VIOLATED, "Conflicts with the proposed action.")
    summary = ValuesEngine.summarize([result])
    assert summary["allowed"] is False
    assert summary["human_review"] is True
    assert summary["violated"] == ["Integrity"]


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
