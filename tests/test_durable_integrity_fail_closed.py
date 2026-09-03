from singular.autopilot import DelegationContract
from singular.durable import DurableStore
from singular.durable_integrity import DurableIntegrityChecker


def test_corrupted_cross_table_state_fails_closed(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract(mission_id="MIS-CORRUPT", objective="test", expected_result="done"))
    with store._connect() as conn:
        conn.execute("UPDATE mission_states SET status='COMPLETED' WHERE mission_id='MIS-CORRUPT'")
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at) VALUES(?,?,?,?,datetime('now'))",
            ("exec-corrupt", "MIS-CORRUPT", "ACT-1", "RUNNING"),
        )

    checker = DurableIntegrityChecker(store)
    assert not checker.check().clean


def test_running_execution_with_finished_at_is_rejected(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract(mission_id="MIS-RUNNING", objective="test", expected_result="done"))
    with store._connect() as conn:
        conn.execute("UPDATE mission_states SET status='RUNNING' WHERE mission_id='MIS-RUNNING'")
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at,finished_at) VALUES(?,?,?,?,datetime('now'),datetime('now'))",
            ("exec-running-corrupt", "MIS-RUNNING", "ACT-1", "RUNNING"),
        )

    report = DurableIntegrityChecker(store).check()
    assert any(item.rule == "RUNNING-FINISHED" for item in report.violations)


def test_recovery_execution_with_active_lease_is_rejected(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract(mission_id="MIS-RECOVERY", objective="test", expected_result="done"))
    with store._connect() as conn:
        conn.execute("UPDATE mission_states SET status='RUNNING' WHERE mission_id='MIS-RECOVERY'")
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at,finished_at,lease_until) VALUES(?,?,?,?,datetime('now'),datetime('now'),datetime('now','+1 hour'))",
            ("exec-recovery-corrupt", "MIS-RECOVERY", "ACT-1", "RECOVERY_REQUIRED"),
        )

    report = DurableIntegrityChecker(store).check()
    assert any(item.rule == "RECOVERY-LEASE" for item in report.violations)
