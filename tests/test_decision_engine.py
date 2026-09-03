from singular.autopilot import ActionRequest
from singular.decision_engine import DecisionContext, DecisionEngine, DecisionOption, DecisionStatus
from singular.learning import Forecast, ForecastKind
from singular.world_model import WorldFact, WorldModel, EpistemicType, TemporalState


def action(name: str, impact: float, risk: float, reversibility: float, **kwargs) -> ActionRequest:
    return ActionRequest(
        name=name,
        description=name,
        impact=impact,
        risk=risk,
        reversibility=reversibility,
        **kwargs,
    )


def test_selects_best_non_blocked_option_without_authorizing() -> None:
    context = DecisionContext(
        "DEC-1",
        "advance objective",
        (
            DecisionOption("A", action("low_value", 4, 1, 8)),
            DecisionOption("B", action("high_value", 9, 1, 9)),
        ),
    )
    result = DecisionEngine().recommend(context)
    assert result.selected_option_id == "B"
    assert result.status is DecisionStatus.PROPOSED
    assert result.authorized is False


def test_sensitive_option_is_not_executable_and_is_reviewed_or_blocked() -> None:
    context = DecisionContext(
        "DEC-2",
        "handle sensitive action",
        (DecisionOption("A", action("sign_contract", 10, 2, 8, sensitive=True)),),
    )
    result = DecisionEngine().recommend(context)
    assert result.status is DecisionStatus.BLOCKED
    assert result.selected_option_id is None
    assert result.authorized is False


def test_unknown_world_model_forces_review() -> None:
    world = WorldModel()
    world.facts["missing"] = WorldFact(
        "missing", None, EpistemicType.UNKNOWN, TemporalState.CURRENT, 0.0
    )
    context = DecisionContext(
        "DEC-3",
        "decide with incomplete information",
        (DecisionOption("A", action("research", 7, 1, 9)),),
        forecasts=(Forecast("F-1", ForecastKind.BINARY, probability=0.7, confidence=0.8),),
        world_model=world,
    )
    result = DecisionEngine().recommend(context)
    assert result.status is DecisionStatus.REVIEW
    assert any("WORLD_MODEL:UNKNOWN" in item for item in result.unresolved_questions)


def test_invalid_context_is_rejected() -> None:
    try:
        DecisionContext("DEC-4", "objective", ())
    except ValueError as exc:
        assert "at least one" in str(exc)
    else:
        raise AssertionError("empty option set must be rejected")
