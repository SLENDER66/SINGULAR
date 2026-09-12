import pytest

from singular.autopilot import ActionRequest, Autonomy, DelegationContract
from singular.empire import AgentRegistry, AgentSpec, AutopilotSupervisor
from singular.execution import DurableExecutionEngine
from singular.mission_autopilot import Mission, MissionAutopilot
from singular.tool_fabric import ToolFabric, ToolSpec


def _contract():
    return DelegationContract(
        mission_id="MIS-TEST",
        objective="test objective",
        expected_result="test result",
        autonomy=Autonomy.EXECUTE_AUTHORIZED,
    )


def test_durable_executor_cannot_execute_raw_action():
    executor = object.__new__(DurableExecutionEngine)
    with pytest.raises(PermissionError, match="ValidatedTrajectoryDecision"):
        executor.execute(ActionRequest("raw", "raw", 1, 1, 9), "MIS-TEST", lambda _: None)


def test_durable_executor_cannot_execute_raw_external_effect():
    executor = object.__new__(DurableExecutionEngine)
    with pytest.raises(PermissionError, match="ValidatedTrajectoryDecision"):
        executor.execute_effect(None, "MIS-TEST", object(), provider_name="p", operation="op", payload={})


def test_durable_executor_cannot_reconcile_raw_external_effect():
    executor = object.__new__(DurableExecutionEngine)
    with pytest.raises(PermissionError, match="ValidatedTrajectoryDecision"):
        executor.reconcile_effect(None, "MIS-TEST", object(), provider_name="p", operation="op", payload={})


def test_tool_fabric_cannot_execute_autonomous_raw_action():
    fabric = ToolFabric()
    called = []
    fabric.register(
        ToolSpec(
            name="safe_tool", description="safe", risk=1, reversibility=9,
            handler=lambda **kwargs: called.append(kwargs),
        )
    )

    with pytest.raises(PermissionError, match="ValidatedTrajectoryDecision"):
        fabric.execute_autonomous("safe_tool", _contract(), value=1)
    assert called == []


def test_tool_fabric_cannot_swap_approved_tool_name():
    fabric = ToolFabric()
    called = []
    fabric.register(ToolSpec("approved", "approved", 1, 9, sensitive=True, handler=lambda **kw: called.append("approved")))
    fabric.register(ToolSpec("other", "other", 1, 9, handler=lambda **kw: called.append("other")))
    _, decision = fabric.plan("approved", "approved", _contract())
    approval_id = decision.approval_id
    assert approval_id is not None
    fabric.bus.approve(approval_id)

    with pytest.raises(PermissionError, match="ValidatedTrajectoryDecision"):
        fabric.execute_approved(approval_id, "other")
    assert called == []


def test_mission_autopilot_cannot_call_handler_without_validated_decision():
    calls = []
    autopilot = MissionAutopilot()
    autopilot.register_handler("do_work", lambda action: calls.append(action.id))
    action = ActionRequest("do_work", "do work", 5, 1, 9, contract_id="MIS-TEST")
    mission = Mission("test objective", "test result", _contract())
    autopilot.plan(mission, [(action, ())])

    result = autopilot.run(mission)

    assert result.status.name == "BLOCKED"
    assert calls == []


def test_empire_supervisor_cannot_call_agent_handler_without_validated_decision():
    calls = []
    registry = AgentRegistry()
    registry.register(AgentSpec(name="worker", mission="work", capabilities=("work",), handler=lambda payload: calls.append(payload)))
    supervisor = AutopilotSupervisor(registry)
    run = supervisor.create_run("test")

    result = supervisor.route(run, "work", {"x": 1})

    assert result is None
    assert calls == []
    assert run.status in {"BLOCKED", "WAITING_HUMAN"}
