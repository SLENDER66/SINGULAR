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
