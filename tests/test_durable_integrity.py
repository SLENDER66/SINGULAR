from singular.autopilot import DelegationContract
from singular.durable import DurableStore
from singular.durable_integrity import DurableIntegrityChecker


def _store(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract(mission_id="MIS-INTEGRITY", objective="test", expected_result="done"))
    with store._connect() as conn:
        conn.execute("UPDATE mission_states SET status='RUNNING' WHERE mission_id='MIS-INTEGRITY'")
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at) VALUES(?,?,?,?,datetime('now'))",
            ("exec-integrity", "MIS-INTEGRITY", "ACT-1", "RUNNING"),
        )
    return store


def test_clean_durable_state_has_no_cross_table_violations(tmp_path):
    store = _store(tmp_path)
    assert DurableIntegrityChecker(store).check().clean


def test_checker_detects_recovery_mission_inconsistency(tmp_path):
    store = _store(tmp_path)
    with store._connect() as conn:
        conn.execute("UPDATE executions SET status='RECOVERY_REQUIRED' WHERE execution_key='exec-integrity'")
        conn.execute("UPDATE mission_states SET status='COMPLETED' WHERE mission_id='MIS-INTEGRITY'")

    report = DurableIntegrityChecker(store).check()
    assert any(item.rule == "RECOVERY-MISSION" for item in report.violations)


def test_checker_detects_orphan_external_effect(tmp_path):
    store = _store(tmp_path)
    with store._connect() as conn:
        conn.execute(
            "INSERT INTO external_effects(provider_idempotency_key,execution_key,provider,operation,payload_fingerprint,action_fingerprint,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            ("effect-orphan", "missing-execution", "provider", "write", "payload", "action", "UNKNOWN", "now", "now"),
        )

    report = DurableIntegrityChecker(store).check()
    assert any(item.rule == "EFFECT-EXECUTION" for item in report.violations)
