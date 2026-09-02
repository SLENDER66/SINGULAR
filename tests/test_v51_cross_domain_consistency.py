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
