from dataclasses import replace

import pytest

from singular.durable import DurableStore
from singular.execution import DurableExecutionEngine
from singular.mission_runtime import DurableMissionRuntime
from singular.tool_fabric import ToolFabric
from singular.validated_trajectory_decision import ValidatedTrajectoryDecision

from tests.test_validated_pipeline import _build_decision, authorized_handler


def test_tampering_with_action_risk_invalidates_decision():
    decision = _build_decision()
    action = replace(decision.authorized_actions[0], risk=decision.authorized_actions[0].risk + 0.1)
    object.__setattr__(decision, "authorized_actions", (action,))
    assert not decision.verify()


def test_tampering_with_portfolio_interaction_effect_is_rejected():
    decision = _build_decision()
    altered_portfolio = replace(
        decision.trajectory_portfolio,
        interaction_effect=decision.trajectory_portfolio.interaction_effect + 1.0,
    )
    object.__setattr__(decision, "trajectory_portfolio", altered_portfolio)
    assert not decision.verify()


def test_tampering_with_global_verdict_is_rejected():
    decision = _build_decision()
    report = replace(decision.global_report, decision="BLOCK")
    object.__setattr__(decision, "global_report", report)
    assert not decision.verify()


def test_tampering_with_action_mapping_is_rejected():
    decision = _build_decision()
    object.__setattr__(
        decision,
        "action_to_intervention",
        ((decision.authorized_actions[0].id, "unknown-intervention"),),
    )
    assert not decision.verify()


def test_executor_requires_the_exact_validated_artifact():
    decision = _build_decision()
    store = DurableStore(":memory:")
    runtime = DurableMissionRuntime(store)
    engine = DurableExecutionEngine(runtime)
    with pytest.raises(PermissionError):
        engine.execute(decision.authorized_actions[0].to_action(), "MIS-PIPE", authorized_handler)


def test_tool_fabric_raw_execution_is_closed():
    fabric = ToolFabric()
    with pytest.raises(PermissionError):
        fabric.execute_autonomous("missing-tool")


def test_validated_artifact_type_is_explicit():
    decision = _build_decision()
    assert isinstance(decision, ValidatedTrajectoryDecision)
    assert decision.verify()
