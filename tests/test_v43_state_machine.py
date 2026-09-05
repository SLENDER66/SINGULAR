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


def test_begin_execution_and_start_mission_uses_unified_transition_guard(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    contract = runtime.create_mission("atomic start", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    store.set_mission_status(contract.mission_id, MissionStatus.PLANNED)

    result = store.begin_execution_and_start_mission("exec-1", contract.mission_id, "action-1")

    assert result["claimed"] is True
    assert result["status"] == "RUNNING"
    assert store.get_mission_status(contract.mission_id) == MissionStatus.RUNNING


def test_begin_execution_and_start_mission_rejects_non_planned_without_partial_execution(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    contract = runtime.create_mission("atomic start guard", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)

    with pytest.raises(ValueError, match="État courant inattendu"):
        store.begin_execution_and_start_mission("exec-2", contract.mission_id, "action-2")

    assert store.get_mission_status(contract.mission_id) == MissionStatus.CREATED
    assert store.get_execution("exec-2") is None


def test_finish_execution_and_mission_uses_unified_transition_guard(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    contract = runtime.create_mission("atomic finish", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    store.set_mission_status(contract.mission_id, MissionStatus.PLANNED)
    store.begin_execution_and_start_mission("exec-3", contract.mission_id, "action-3")

    result = store.finish_execution_and_mission("exec-3", "COMPLETED", {"ok": True})

    assert result["status"] == "COMPLETED"
    assert store.get_mission_status(contract.mission_id) == MissionStatus.COMPLETED


def test_finish_execution_and_mission_rolls_back_execution_if_mission_transition_is_illegal(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    contract = runtime.create_mission("atomic rollback", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    store.set_mission_status(contract.mission_id, MissionStatus.PLANNED)
    store.begin_execution_and_start_mission("exec-4", contract.mission_id, "action-4")

    # Tamper with the mission state outside the public transition API to simulate corruption/concurrency.
    with store._connect() as conn:
        conn.execute(
            "UPDATE mission_states SET status=? WHERE mission_id=?",
            (MissionStatus.COMPLETED.value, contract.mission_id),
        )

    with pytest.raises(ValueError, match="État courant inattendu"):
        store.finish_execution_and_mission("exec-4", "COMPLETED", {"ok": True})

    execution = store.get_execution("exec-4")
    assert execution is not None
    assert execution["status"] == "RUNNING"
    assert execution["result"] is None


def test_there_is_only_one_way_into_a_terminal_execution_state(tmp_path: Path):
    """finish_execution wrote COMPLETED without touching the mission, and nothing called it.

    An unused door into the terminal state is still a door: it recorded a
    successful execution outside the single transition that keeps execution and
    mission state consistent.
    """
    finalizers = [name for name in dir(DurableStore) if name.startswith("finish_execution")]
    assert finalizers == ["finish_execution_and_mission"]


def test_there_is_only_one_way_to_claim_an_execution(tmp_path: Path):
    """begin_execution claimed a key while leaving the mission unstarted.

    That state is one the integrity checker reports as impossible, and the
    claim it leaves behind blocks the guarded path from ever taking that key.
    """
    claimers = [name for name in dir(DurableStore) if name.startswith("begin_execution")]
    assert claimers == ["begin_execution_and_start_mission"]
