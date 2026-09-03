import pytest

from singular.execution import ExecutionResult
from singular.execution_capability import register_execution_capability
from singular.validated_execution import ValidatedExecutionBoundary
from test_validated_trajectory_decision import artifacts, build


def authorized_handler(action):
    return action.name


AUTHORIZED_HANDLER_CAPABILITY = register_execution_capability(authorized_handler, "cap_test_boundary_handler")


class FakeDurableExecutor:
    def __init__(self):
        self.calls = []

    def execute_validated(self, decision, handler):
        self.calls.append((decision, handler))
        return ExecutionResult("EXEC-1", decision.contract.mission_id, decision.global_report.action_id, "COMPLETED", result=handler(decision.authorized_actions[0].to_action()))


def test_boundary_accepts_only_validated_decision_and_authorized_action():
    executor = FakeDurableExecutor()
    boundary = ValidatedExecutionBoundary(executor)  # type: ignore[arg-type]
    decision = build(execution_target=AUTHORIZED_HANDLER_CAPABILITY)
    result = boundary.execute(decision, decision.global_report.action_id, authorized_handler)
    assert result.status == "COMPLETED"
    assert result.result == "career_test"
    assert len(executor.calls) == 1
    assert executor.calls[0][0] is decision


def test_boundary_rejects_raw_action():
    executor = FakeDurableExecutor()
    boundary = ValidatedExecutionBoundary(executor)  # type: ignore[arg-type]
    action = artifacts()[0]
    with pytest.raises(TypeError, match="ValidatedTrajectoryDecision"):
        boundary.execute(action, action.id, authorized_handler)  # type: ignore[arg-type]
    assert executor.calls == []


def test_boundary_rejects_tampered_decision():
    executor = FakeDurableExecutor()
    boundary = ValidatedExecutionBoundary(executor)  # type: ignore[arg-type]
    decision = build(execution_target=AUTHORIZED_HANDLER_CAPABILITY)
    object.__setattr__(decision, "global_report", artifacts(global_decision="BLOCK")[8])
    with pytest.raises(PermissionError, match="altérée"):
        boundary.execute(decision, decision.global_report.action_id, authorized_handler)
    assert executor.calls == []


def test_boundary_rejects_unauthorized_action_id():
    executor = FakeDurableExecutor()
    boundary = ValidatedExecutionBoundary(executor)  # type: ignore[arg-type]
    decision = build(execution_target=AUTHORIZED_HANDLER_CAPABILITY)
    with pytest.raises(PermissionError, match="autorisée"):
        boundary.execute(decision, "UNKNOWN-ACTION", authorized_handler)
    assert executor.calls == []
