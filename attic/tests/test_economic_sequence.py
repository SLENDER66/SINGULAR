from singular.economic_sequence import EconomicStage, EconomicStep, EconomicSequenceEngine


def test_cash_stage_precedes_higher_value_later_stage() -> None:
    steps = [EconomicStep("ownership", EconomicStage.OWNERSHIP, expected_value=1000, probability=1), EconomicStep("cash", EconomicStage.CASH, expected_cash=100, probability=0.9)]
    plan = EconomicSequenceEngine.plan(steps, available_capacity=10)
    assert plan.steps[0].id == "cash"
    assert plan.steps[0].stage is EconomicStage.CASH


def test_missing_prerequisite_blocks_step() -> None:
    step = EconomicStep("recurring", EconomicStage.RECURRING, expected_value=100, probability=1, prerequisites=(EconomicStage.CASH.value,))
    plan = EconomicSequenceEngine.plan([step], available_capacity=10)
    assert plan.steps == ()
    assert plan.blocked_steps == ("recurring",)


def test_completed_stage_satisfies_prerequisite() -> None:
    step = EconomicStep("recurring", EconomicStage.RECURRING, expected_value=100, probability=1, prerequisites=(EconomicStage.CASH.value,))
    plan = EconomicSequenceEngine.plan([step], available_capacity=10, completed_stages=(EconomicStage.CASH,))
    assert plan.steps[0].id == "recurring"


def test_failure_lesson_prioritizes_related_next_test_without_mutating_rules() -> None:
    steps = [EconomicStep("a", EconomicStage.CASH, expected_cash=100, probability=1, lesson_ids=("lesson-1",)), EconomicStep("b", EconomicStage.CASH, expected_cash=100, probability=1)]
    plan = EconomicSequenceEngine.plan(steps, available_capacity=10, failure_lesson_ids=("lesson-1",))
    assert plan.steps[0].id == "a"
    assert "RECOMMENDATION_ONLY" in plan.rationale


def test_order_is_deterministic() -> None:
    steps = [EconomicStep("b", EconomicStage.CASH, expected_cash=10, probability=1), EconomicStep("a", EconomicStage.CASH, expected_cash=10, probability=1)]
    first = EconomicSequenceEngine.plan(steps, available_capacity=10)
    second = EconomicSequenceEngine.plan(list(reversed(steps)), available_capacity=10)
    assert first == second
