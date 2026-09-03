from dataclasses import replace

import pytest

from singular.execution import ExecutionResult
from singular.validated_execution import ValidatedExecutionBoundary
from tests.test_validated_trajectory_decision import artifacts, build


class FakeDurableExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, action, mission_id, handler):
        self.calls.append((action, mission_id, handler))
        return ExecutionResult("EXEC-1", mission_id, action.id, "COMPLETED", result=handler(action))


def test_boundary_accepts_only_validated_decision_and_authorized_action():
    executor = FakeDurableExecutor()
    boundary = ValidatedExecutionBoundary(executor)  # type: ignore[arg-type]
    decision = build()
    result = boundary.execute(decision, decision.global_report.action_id, lambda action: action.name)
    assert result.status == "COMPLETED"
    assert result.result == "career_test"
    assert len(executor.calls) == 1
    assert executor.calls[0][0].id == decision.global_report.action_id
    assert executor.calls[0][1] == decision.contract.mission_id


def test_boundary_rejects_raw_action():
    executor = FakeDurableExecutor()
    boundary = ValidatedExecutionBoundary(executor)  # type: ignore[arg-type]
    action = artifacts()[0]
    with pytest.raises(TypeError, match="ValidatedTrajectoryDecision"):
        boundary.execute(action, action.id, lambda _: None)  # type: ignore[arg-type]
    assert executor.calls == []


def test_boundary_rejects_tampered_decision():
    executor = FakeDurableExecutor()
    boundary = ValidatedExecutionBoundary(executor)  # type: ignore[arg-type]
    decision = build()
    object.__setattr__(decision, "global_report", artifacts(global_decision="BLOCK")[4])
    with pytest.raises(PermissionError, match="altérée"):
        boundary.execute(decision, decision.global_report.action_id, lambda _: None)
    assert executor.calls == []


def test_boundary_rejects_unauthorized_action_id():
    executor = FakeDurableExecutor()
    boundary = ValidatedExecutionBoundary(executor)  # type: ignore[arg-type]
    decision = build()
    with pytest.raises(PermissionError, match="autorisée"):
        boundary.execute(decision, "UNKNOWN-ACTION", lambda _: None)
    assert executor.calls == []
