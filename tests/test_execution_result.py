import pytest

from singular.autopilot import Autonomy, GovernorDecision
from singular.decision_engine import DecisionRecommendation, DecisionStatus
from singular.execution_result import ExecutionIntent, ExecutionResultBridge, ExecutionStatus


def recommendation(status: DecisionStatus = DecisionStatus.PROPOSED) -> DecisionRecommendation:
    return DecisionRecommendation(
        decision_id="d1",
        objective="build wealth",
        status=status,
        selected_option_id="a1",
        reports=(),
        rationale="test",
        confidence=0.9,
    )


def test_prepare_is_fail_closed_for_review() -> None:
    bridge = ExecutionResultBridge()
    with pytest.raises(PermissionError):
        bridge.prepare(recommendation(DecisionStatus.REVIEW), idempotency_key="k1")


def test_prepare_then_authorize_reversible() -> None:
    bridge = ExecutionResultBridge()
    intent = bridge.prepare(recommendation(), idempotency_key="k1")
    authorized = bridge.authorize(
        intent,
        GovernorDecision("a1", Autonomy.EXECUTE_REVERSIBLE, ("low risk",)),
    )
    assert authorized.authorization_id is None
    assert authorized.action_id == "a1"


def test_authorized_execution_requires_approval_reference() -> None:
    bridge = ExecutionResultBridge()
    intent = bridge.prepare(recommendation(), idempotency_key="k1")
    with pytest.raises(PermissionError):
        bridge.authorize(
            intent,
            GovernorDecision("a1", Autonomy.EXECUTE_AUTHORIZED, ("approved class",)),
        )


def test_terminal_result_validates_success_flag() -> None:
    with pytest.raises(ValueError):
        from singular.execution_result import ExecutionResult

        ExecutionResult("d1", "a1", "k1", ExecutionStatus.SUCCEEDED, False)


def test_idempotency_returns_first_result_and_rejects_replay_mismatch() -> None:
    bridge = ExecutionResultBridge()
    intent = ExecutionIntent("d1", "a1", "k1")
    first = bridge.record(
        intent,
        status=ExecutionStatus.SUCCEEDED,
        success=True,
        observed_value=42.0,
        metadata={"source": "system", "attempt": 1},
    )
    same = bridge.record(
        intent,
        status=ExecutionStatus.SUCCEEDED,
        success=True,
        observed_value=42.0,
        metadata={"attempt": 1, "source": "system"},
    )
    assert same is first
    with pytest.raises(RuntimeError):
        bridge.record(
            intent,
            status=ExecutionStatus.SUCCEEDED,
            success=True,
            observed_value=99.0,
            metadata={"attempt": 1, "source": "system"},
        )


def test_results_are_sorted_by_idempotency_key() -> None:
    bridge = ExecutionResultBridge()
    bridge.record(ExecutionIntent("d", "a", "z"), status=ExecutionStatus.FAILED, success=False, error="x")
    bridge.record(ExecutionIntent("d", "b", "a"), status=ExecutionStatus.SUCCEEDED, success=True, observed_value=True)
    assert [item.idempotency_key for item in bridge.results()] == ["a", "z"]
