from dataclasses import replace

import pytest

from singular.autopilot import Autonomy
from singular.execution import DurableExecutionEngine
from singular.mission_runtime import DurableMissionRuntime
from singular.durable import DurableStore
from singular.validated_trajectory_decision import ValidatedTrajectoryDecision
from singular.tool_fabric import ToolFabric

from tests.test_validated_pipeline import _build_decision, authorized_handler


def test_tampering_with_action_risk_invalidates_decision():
    decision = _build_decision()
    action = replace(decision.authorized_actions[0], risk=decision.authorized_actions[0].risk + 0.1)
    tampered = replace(decision, authorized_actions=(action,))
    assert not tampered.verify()


def test_tampering_with_interaction_cannot_disappear_from_fingerprint():
    decision = _build_decision()
    tampered = replace(decision, trajectory_interactions=decision.trajectory_interactions + ())
    assert tampered.verify()
    altered_portfolio = replace(decision.trajectory_portfolio, interaction_effect=decision.trajectory_portfolio.interaction_effect + 1.0)
    tampered = replace(decision, trajectory_portfolio=altered_portfolio)
    assert not tampered.verify()


def test_tampering_with_global_verdict_is_rejected():
    decision = _build_decision()
    report = replace(decision.global_report, decision="BLOCK")
    tampered = replace(decision, global_report=report)
    assert not tampered.verify()


def test_tampering_with_action_mapping_is_rejected():
    decision = _build_decision()
    tampered = replace(decision, action_to_intervention=((decision.authorized_actions[0].id, "unknown-intervention"),))
    assert not tampered.verify()


def test_executor_requires_the_exact_validated_artifact():
    store = DurableStore(":memory:")
    runtime = DurableMissionRuntime(store)
    engine = DurableExecutionEngine(runtime)
    with pytest.raises(PermissionError):
        engine.execute(decision_action(decision=_build_decision()), "MIS-PIPE", authorized_handler)


def test_tool_fabric_raw_execution_is_closed():
    fabric = ToolFabric()
    with pytest.raises(PermissionError):
        fabric.execute_autonomous("missing-tool", {})


def decision_action(*, decision: ValidatedTrajectoryDecision):
    return decision.authorized_actions[0].to_action()
