"""The integrity scan must read every table at one instant.

`ValidatedExecutionBoundary` refuses every execution while the durable state is
dirty, and this scan is what decides. It read the executions at one instant and
each mission's status at another, with no transaction holding the two together,
so an ordinary concurrent writer -- another worker finishing its own execution --
could show it a RUNNING row under an already COMPLETED mission. That
contradiction never existed in the database. It was assembled out of two
different moments, and it refused a legitimate execution.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any

from singular.autopilot import DelegationContract
from singular.durable import DurableStore, MissionStatus
from singular.durable_integrity import DurableIntegrityChecker

MISSION = "MIS-SNAPSHOT"
EXECUTION = "exec-snapshot"


class _RacingCursor:
    """Lets a writer commit at the exact moment the executions are in hand."""

    def __init__(self, cursor: sqlite3.Cursor, hook) -> None:
        self._cursor = cursor
        self._hook = hook

    def fetchall(self) -> list[Any]:
        rows = self._cursor.fetchall()
        self._hook()
        return rows

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)

    def __iter__(self):
        return iter(self._cursor)


class _RacingConnection:
    def __init__(self, conn: sqlite3.Connection, hook) -> None:
        self._conn = conn
        self._hook = hook
        self._fired = False

    def execute(self, sql: str, *args: Any) -> Any:
        cursor = self._conn.execute(sql, *args)
        if not self._fired and "FROM executions" in sql:
            self._fired = True

            def once() -> None:
                self._hook()

            return _RacingCursor(cursor, once)
        return cursor

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


class RacingStore(DurableStore):
    """A store whose integrity scan is interrupted by a real concurrent commit."""

    hook = staticmethod(lambda: None)
    racing = False

    @contextmanager
    def _connect(self):  # type: ignore[override]
        with super()._connect() as conn:
            if not self.racing:
                yield conn
                return
            self.racing = False  # only the scan's own connection, not the writer's
            yield _RacingConnection(conn, self.hook)


def _running_store(tmp_path) -> RacingStore:
    store = RacingStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract(mission_id=MISSION, objective="test", expected_result="done"))
    store.set_mission_status(MISSION, MissionStatus.PLANNED)
    claim = store.begin_execution_and_start_mission(EXECUTION, MISSION, "ACT-1", 300)
    assert claim["claimed"] is True
    return store


def test_a_concurrent_finish_does_not_invent_a_contradiction(tmp_path):
    """The scan sees the state as it was, not half of it before and half after."""
    store = _running_store(tmp_path)

    def finish() -> None:
        store.finish_execution_and_mission(EXECUTION, "COMPLETED", result={"ok": True})

    store.hook = finish
    store.racing = True
    report = DurableIntegrityChecker(store).check()

    assert report.clean, f"phantom violations from a torn read: {report.violations}"
    with store._connect() as conn:
        assert conn.execute("SELECT status FROM executions WHERE execution_key=?", (EXECUTION,)).fetchone()["status"] == "COMPLETED"


def test_the_same_scan_after_the_writer_is_still_clean(tmp_path):
    """And the committed state itself is consistent, so this is not luck."""
    store = _running_store(tmp_path)
    store.finish_execution_and_mission(EXECUTION, "COMPLETED", result={"ok": True})
    assert DurableIntegrityChecker(store).check().clean


def test_a_real_contradiction_is_still_reported(tmp_path):
    """A snapshot must not become a way of not looking."""
    store = _running_store(tmp_path)
    with store._connect() as conn:
        conn.execute("UPDATE mission_states SET status='COMPLETED' WHERE mission_id=?", (MISSION,))

    report = DurableIntegrityChecker(store).check()
    assert any(item.rule == "RUNNING-MISSION" for item in report.violations)
