from pathlib import Path

import pytest

from singular.autopilot import Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.mission_runtime import DurableMissionRuntime


def test_durable_store_rejects_illegal_state_jump(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    contract = runtime.create_mission("state machine", "done", autonomy=Autonomy.PREPARE)

    with pytest.raises(ValueError, match="Transition de mission interdite"):
        store.set_mission_status(contract.mission_id, MissionStatus.COMPLETED)

    assert store.get_mission_status(contract.mission_id) == MissionStatus.CREATED


def test_durable_store_blocks_terminal_state_reopening(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    contract = runtime.create_mission("terminal state", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)

    store.set_mission_status(contract.mission_id, MissionStatus.PLANNED)
    store.set_mission_status(contract.mission_id, MissionStatus.RUNNING)
    store.set_mission_status(contract.mission_id, MissionStatus.COMPLETED)

    with pytest.raises(ValueError, match="Transition de mission interdite"):
        store.set_mission_status(contract.mission_id, MissionStatus.PLANNED)

    assert store.get_mission_status(contract.mission_id) == MissionStatus.COMPLETED


def test_durable_store_same_state_is_idempotent(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    contract = runtime.create_mission("idempotent state", "done", autonomy=Autonomy.PREPARE)

    store.set_mission_status(contract.mission_id, MissionStatus.CREATED)
    store.set_mission_status(contract.mission_id, MissionStatus.PLANNED)
    store.set_mission_status(contract.mission_id, MissionStatus.PLANNED)

    assert store.get_mission_status(contract.mission_id) == MissionStatus.PLANNED
