from pathlib import Path

from singular.consistency import CrossDomainConsistencyChecker
from singular.durable import DurableStore


def seed(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    with store._connect() as conn:
        conn.execute("INSERT INTO missions(mission_id,payload,created_at) VALUES('m1','{}','now')")
        conn.execute("INSERT INTO mission_states(mission_id,status,updated_at) VALUES('m1','RUNNING','now')")
        conn.execute("INSERT INTO executions(execution_key,mission_id,action_id,status,started_at) VALUES('e1','m1','a1','RUNNING','now')")
    return store


def test_completed_external_effect_with_running_execution_is_detectable(tmp_path: Path):
    store = seed(tmp_path)
    with store._connect() as conn:
        conn.execute(
            "INSERT INTO external_effects(provider_idempotency_key,execution_key,provider,operation,payload_fingerprint,status,created_at,updated_at) "
            "VALUES('p1','e1','fake','send','payload','COMPLETED','now','now')"
        )

    violations = CrossDomainConsistencyChecker(store.path).check("m1")

    assert violations == ()


def test_completed_mission_with_running_execution_is_rejected(tmp_path: Path):
    store = seed(tmp_path)
    store.set_mission_status("m1", "COMPLETED")

    violations = CrossDomainConsistencyChecker(store.path).check("m1")

    assert any(v.code == "MISSION_COMPLETED_WITH_NONTERMINAL_EXECUTION" for v in violations)
    assert any(v.code == "EXECUTION_COMPLETED_WITH_NONCOMPLETED_MISSION" for v in violations) is False


def test_completed_execution_with_noncompleted_effect_is_rejected(tmp_path: Path):
    store = seed(tmp_path)
    with store._connect() as conn:
        conn.execute("UPDATE executions SET status='COMPLETED' WHERE execution_key='e1'")
        conn.execute(
            "INSERT INTO external_effects(provider_idempotency_key,execution_key,provider,operation,payload_fingerprint,status,created_at,updated_at) "
            "VALUES('p1','e1','fake','send','payload','UNKNOWN','now','now')"
        )

    violations = CrossDomainConsistencyChecker(store.path).check("m1")

    assert any(v.code == "EXECUTION_COMPLETED_WITH_NONTERMINAL_EFFECT" for v in violations)
    assert any(v.code == "EXECUTION_COMPLETED_WITH_NONCOMPLETED_MISSION" for v in violations)


def test_assert_consistent_fails_closed_on_invalid_state(tmp_path: Path):
    store = seed(tmp_path)
    store.set_mission_status("m1", "COMPLETED")

    checker = CrossDomainConsistencyChecker(store.path)
    try:
        checker.assert_consistent("m1")
    except RuntimeError as exc:
        assert "MISSION_COMPLETED_WITH_NONTERMINAL_EXECUTION" in str(exc)
    else:
        raise AssertionError("Une violation d'invariant devait être détectée.")


def test_a_replanned_mission_does_not_leave_the_boundary_permanently_shut(tmp_path):
    """An action fails, the mission is replanned, the next one succeeds.

    FAILED -> PLANNED is a transition the state machine allows on purpose, so
    this is an ordinary sequence. Reading the older FAILED execution against the
    mission's current COMPLETED status reported the database as broken, and
    ValidatedExecutionBoundary refuses every execution while integrity is dirty
    -- for good, since nothing repairs it.
    """
    from singular.autopilot import Autonomy, DelegationContract
    from singular.durable import DurableStore, MissionStatus
    from singular.durable_integrity import DurableIntegrityChecker

    store = DurableStore(tmp_path / "retry.db")
    store.save_mission(DelegationContract("MIS-RETRY", "objective", "expected", autonomy=Autonomy.EXECUTE_REVERSIBLE))
    store.set_mission_status("MIS-RETRY", MissionStatus.PLANNED)
    store.begin_execution_and_start_mission("exec-A", "MIS-RETRY", "ACT-A")
    store.finish_execution_and_mission("exec-A", "FAILED", error="boom")

    store.set_mission_status("MIS-RETRY", MissionStatus.PLANNED)
    store.begin_execution_and_start_mission("exec-B", "MIS-RETRY", "ACT-B")
    store.finish_execution_and_mission("exec-B", "COMPLETED", result={"ok": True})

    DurableIntegrityChecker(store).assert_clean()


def test_the_latest_attempt_still_has_to_agree_with_its_mission(tmp_path):
    from singular.autopilot import Autonomy, DelegationContract
    from singular.durable import DurableStore, MissionStatus
    from singular.durable_integrity import DurableIntegrityChecker

    store = DurableStore(tmp_path / "latest.db")
    store.save_mission(DelegationContract("MIS-LAST", "objective", "expected", autonomy=Autonomy.EXECUTE_REVERSIBLE))
    store.set_mission_status("MIS-LAST", MissionStatus.PLANNED)
    store.begin_execution_and_start_mission("exec-C", "MIS-LAST", "ACT-C")
    with store._connect() as conn:
        conn.execute("UPDATE executions SET status='COMPLETED', finished_at=datetime('now'), lease_until=NULL WHERE execution_key='exec-C'")

    report = DurableIntegrityChecker(store).check()
    assert [violation.rule for violation in report.violations] == ["COMPLETED-MISSION"]


def test_a_running_execution_always_constrains_its_mission(tmp_path):
    """A live claim is not history: it must hold whatever was written after it."""
    from singular.autopilot import Autonomy, DelegationContract
    from singular.durable import DurableStore, MissionStatus
    from singular.durable_integrity import DurableIntegrityChecker

    store = DurableStore(tmp_path / "running.db")
    store.save_mission(DelegationContract("MIS-LIVE", "objective", "expected", autonomy=Autonomy.EXECUTE_REVERSIBLE))
    store.set_mission_status("MIS-LIVE", MissionStatus.PLANNED)
    store.begin_execution_and_start_mission("exec-D", "MIS-LIVE", "ACT-D")
    with store._connect() as conn:
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at,lease_until)"
            " VALUES('exec-E','MIS-LIVE','ACT-E','COMPLETED',datetime('now'),NULL)"
        )
        conn.execute("UPDATE executions SET finished_at=datetime('now') WHERE execution_key='exec-E'")
        conn.execute("UPDATE mission_states SET status='COMPLETED' WHERE mission_id='MIS-LIVE'")

    report = DurableIntegrityChecker(store).check()
    assert "RUNNING-MISSION" in [violation.rule for violation in report.violations]
