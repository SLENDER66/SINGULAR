from pathlib import Path

import pytest

from singular.autopilot import ActionRequest, Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.execution import DurableExecutionEngine
from singular.mission_runtime import DurableMissionRuntime


def setup(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("external effect", "provider outcome", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    engine = DurableExecutionEngine(runtime)
    action = ActionRequest("safe_action", "send", 1, 1, 10)
    return runtime, contract, engine, action


def test_raw_effect_repair_entry_point_is_closed(tmp_path: Path):
    runtime, contract, engine, action = setup(tmp_path)

    with pytest.raises(PermissionError, match="ValidatedTrajectoryDecision"):
        engine.execute_effect(action, contract.mission_id, object(), provider_name="fake", operation="send", payload={"to": "a"})

    assert runtime.state(contract.mission_id).status == MissionStatus.CREATED


def test_raw_reconciliation_entry_point_is_closed(tmp_path: Path):
    runtime, contract, engine, action = setup(tmp_path)

    with pytest.raises(PermissionError, match="ValidatedTrajectoryDecision"):
        engine.reconcile_effect(action, contract.mission_id, object(), provider_name="fake", operation="send", payload={"to": "a"})

    assert runtime.state(contract.mission_id).status == MissionStatus.CREATED
