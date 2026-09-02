from pathlib import Path

import pytest

from singular.autopilot import ActionRequest, Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.execution import DurableExecutionEngine
from singular.mission_runtime import DurableMissionRuntime
from singular.security import ActionPolicy, ActionTier


def test_known_low_risk_capability_allows_execution(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("calendar", "event created", autonomy=Autonomy.EXECUTE_AUTHORIZED)
    action = ActionRequest(
        "create_calendar_event",
        "create event",
        2,
        1,
        9,
        capability="create_calendar_event",
    )

    decision = ActionPolicy.evaluate(action)
    assert decision.tier == ActionTier.GREEN
    result = DurableExecutionEngine(runtime).execute(action, contract.mission_id, lambda _: "created")
    assert result.status == "COMPLETED"


def test_human_capability_is_escalated_even_when_action_risk_looks_low():
    action = ActionRequest(
        "send_email",
        "send message",
        2,
        1,
        9,
        capability="send_email",
    )
    decision = ActionPolicy.evaluate(action)
    assert decision.tier == ActionTier.ORANGE
    assert decision.requires_human is True
    assert decision.can_execute is True


def test_unknown_capability_fails_closed():
    action = ActionRequest("do_thing", "unknown", 1, 1, 10, capability="unknown_capability")
    decision = ActionPolicy.evaluate(action)
    assert decision.tier == ActionTier.BLACK
    assert decision.can_prepare is False
    assert decision.can_execute is False
    assert decision.requires_human is True


def test_capability_action_mismatch_fails_closed():
    action = ActionRequest(
        "transfer_money",
        "send money",
        2,
        1,
        9,
        capability="send_email",
    )
    decision = ActionPolicy.evaluate(action)
    assert decision.tier == ActionTier.BLACK
    assert decision.can_execute is False


def test_capability_risk_ceiling_fails_closed():
    action = ActionRequest(
        "send_email",
        "send message",
        2,
        7,
        6,
        capability="send_email",
    )
    decision = ActionPolicy.evaluate(action)
    assert decision.tier == ActionTier.RED
    assert decision.can_prepare is False
    assert decision.can_execute is False


def test_capability_normalization_is_deterministic():
    action = ActionRequest(
        "send_email",
        "send message",
        2,
        1,
        9,
        capability=" Send-Email ",
    )
    decision = ActionPolicy.evaluate(action)
    assert decision.tier == ActionTier.ORANGE


def test_capability_is_part_of_approval_identity(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("email", "sent", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_email", "send", 2, 5, 6, capability="send_email")
    runtime.route(action, contract.mission_id)
    approval = runtime.store.pending_approvals(contract.mission_id)[0]
    runtime.approve(approval.id)

    tampered = ActionRequest(
        action.name,
        action.description,
        action.impact,
        action.risk,
        action.reversibility,
        capability="modify_github",
        id=action.id,
    )

    with pytest.raises(ValueError, match="contenu différent"):
        DurableExecutionEngine(runtime).execute(tampered, contract.mission_id, lambda _: "must not run")

    assert runtime.store.get_execution(
        runtime.store.idempotency_key("execute", contract.mission_id, action.id)
    ) is None
