import sqlite3

import pytest

from singular.coherence import GlobalCoherenceGuard
from singular.consistency import CrossDomainConsistencyChecker


def _db(path):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE mission_states (mission_id TEXT PRIMARY KEY, status TEXT NOT NULL)")
        conn.execute("CREATE TABLE executions (execution_key TEXT PRIMARY KEY, mission_id TEXT NOT NULL, action_id TEXT, status TEXT NOT NULL)")
        conn.execute("CREATE TABLE external_effects (provider_idempotency_key TEXT PRIMARY KEY, execution_key TEXT NOT NULL, status TEXT NOT NULL)")
        conn.execute("INSERT INTO mission_states VALUES ('M1', 'COMPLETED')")
        conn.execute("INSERT INTO executions VALUES ('E1', 'M1', 'A1', 'RUNNING')")
        conn.commit()


def test_guard_reports_coherent_state(tmp_path):
    db = tmp_path / "state.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE mission_states (mission_id TEXT PRIMARY KEY, status TEXT NOT NULL)")
        conn.execute("CREATE TABLE executions (execution_key TEXT PRIMARY KEY, mission_id TEXT NOT NULL, action_id TEXT, status TEXT NOT NULL)")
        conn.execute("CREATE TABLE external_effects (provider_idempotency_key TEXT PRIMARY KEY, execution_key TEXT NOT NULL, status TEXT NOT NULL)")
        conn.commit()

    report = GlobalCoherenceGuard(CrossDomainConsistencyChecker(db)).inspect()
    assert report.coherent is True
    assert report.blockers == ()


def test_guard_fails_closed_on_invariant_violation(tmp_path):
    db = tmp_path / "state.db"
    _db(db)
    guard = GlobalCoherenceGuard(CrossDomainConsistencyChecker(db))

    report = guard.inspect('M1')
    assert report.coherent is False
    assert 'MISSION_COMPLETED_WITH_NONTERMINAL_EXECUTION' in report.blockers

    with pytest.raises(RuntimeError, match='État global incohérent'):
        guard.require_coherent('M1')
