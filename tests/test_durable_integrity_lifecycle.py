from singular.autopilot import DelegationContract
from singular.durable import DurableStore
from singular.durable_integrity import DurableIntegrityChecker


def _store(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract(mission_id="MIS-LIFECYCLE", objective="test", expected_result="done"))
    with store._connect() as conn:
        conn.execute("UPDATE mission_states SET status='COMPLETED' WHERE mission_id='MIS-LIFECYCLE'")
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at,finished_at) VALUES(?,?,?,?,datetime('now'),datetime('now'))",
            ("exec-lifecycle", "MIS-LIFECYCLE", "ACT-1", "COMPLETED"),
        )
    return store


def test_checker_rejects_terminal_execution_without_finished_at(tmp_path):
    store = _store(tmp_path)
    with store._connect() as conn:
        conn.execute("UPDATE executions SET finished_at=NULL WHERE execution_key='exec-lifecycle'")

    report = DurableIntegrityChecker(store).check()
    assert any(item.rule == "COMPLETED-FINISHED" for item in report.violations)


def test_checker_rejects_terminal_execution_with_active_lease(tmp_path):
    store = _store(tmp_path)
    with store._connect() as conn:
        conn.execute("UPDATE executions SET lease_until=datetime('now','+5 minutes') WHERE execution_key='exec-lifecycle'")

    report = DurableIntegrityChecker(store).check()
    assert any(item.rule == "COMPLETED-LEASE" for item in report.violations)


def test_sqlite_connection_has_busy_timeout_and_foreign_keys_enabled(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    with store._connect() as conn:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 10000
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
