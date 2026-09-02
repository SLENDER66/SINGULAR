from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .autopilot import ApprovalRequest, ApprovalStatus, DelegationContract
from .audit import AuditEvent


class MissionStatus(str, Enum):
    CREATED = "CREATED"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


MISSION_TRANSITIONS: dict[MissionStatus, frozenset[MissionStatus]] = {
    MissionStatus.CREATED: frozenset({MissionStatus.PLANNED, MissionStatus.WAITING_APPROVAL, MissionStatus.BLOCKED, MissionStatus.CANCELLED}),
    MissionStatus.PLANNED: frozenset({MissionStatus.RUNNING, MissionStatus.WAITING_APPROVAL, MissionStatus.BLOCKED, MissionStatus.CANCELLED}),
    MissionStatus.RUNNING: frozenset({MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.CANCELLED}),
    MissionStatus.WAITING_APPROVAL: frozenset({MissionStatus.PLANNED, MissionStatus.BLOCKED, MissionStatus.CANCELLED}),
    MissionStatus.BLOCKED: frozenset(),
    MissionStatus.COMPLETED: frozenset(),
    MissionStatus.FAILED: frozenset({MissionStatus.PLANNED, MissionStatus.CANCELLED}),
    MissionStatus.CANCELLED: frozenset(),
}


class DurableStore:
    """Small SQLite persistence boundary for mission, approval, audit and replay state."""

    def __init__(self, path: str | Path = "data/singular.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS missions (
                    mission_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mission_states (
                    mission_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    mission_id TEXT,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS idempotency (
                    key TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL DEFAULT '',
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS executions (
                    execution_key TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    lease_until TEXT,
                    FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
                );
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(approvals)")}
            if "mission_id" not in columns:
                conn.execute("ALTER TABLE approvals ADD COLUMN mission_id TEXT")
            idempotency_columns = {row[1] for row in conn.execute("PRAGMA table_info(idempotency)")}
            if "fingerprint" not in idempotency_columns:
                conn.execute("ALTER TABLE idempotency ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''")
            execution_columns = {row[1] for row in conn.execute("PRAGMA table_info(executions)")}
            if "lease_until" not in execution_columns:
                conn.execute("ALTER TABLE executions ADD COLUMN lease_until TEXT")

    def init_execution_schema(self) -> None:
        return None

    def save_mission(self, contract: DelegationContract) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(asdict(contract), sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO missions(mission_id,payload,created_at) VALUES(?,?,?)",
                (contract.mission_id, payload, now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO mission_states(mission_id,status,updated_at) VALUES(?,?,?)",
                (contract.mission_id, MissionStatus.CREATED.value, now),
            )

    def load_mission(self, mission_id: str) -> DelegationContract | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM missions WHERE mission_id=?", (mission_id,)).fetchone()
        if not row:
            return None
        from .autopilot import Autonomy
        data = json.loads(row["payload"])
        data["autonomy"] = Autonomy(data["autonomy"])
        return DelegationContract(**data)

    @staticmethod
    def _transition_mission_status(conn: sqlite3.Connection, mission_id: str, status: MissionStatus, *, expected_current: MissionStatus | None = None) -> MissionStatus:
        """Single connection-aware authority for every mission state transition."""
        if not isinstance(status, MissionStatus):
            status = MissionStatus(status)
        if expected_current is not None and not isinstance(expected_current, MissionStatus):
            expected_current = MissionStatus(expected_current)
        row = conn.execute("SELECT status FROM mission_states WHERE mission_id=?", (mission_id,)).fetchone()
        if row is None:
            raise KeyError(mission_id)
        current = MissionStatus(row["status"])
        if expected_current is not None and current != expected_current:
            raise ValueError(f"État courant inattendu : {current.value}; attendu : {expected_current.value}.")
        if current == status:
            return current
        if status not in MISSION_TRANSITIONS[current]:
            raise ValueError(f"Transition de mission interdite : {current.value} -> {status.value}")
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute("UPDATE mission_states SET status=?, updated_at=? WHERE mission_id=? AND status=?", (status.value, now, mission_id, current.value))
        if cur.rowcount != 1:
            raise RuntimeError("La transition de mission a échoué à cause d'une concurrence d'état.")
        return status

    def set_mission_status(self, mission_id: str, status: MissionStatus) -> None:
        with self._connect() as conn:
            self._transition_mission_status(conn, mission_id, status)

    def get_mission_status(self, mission_id: str) -> MissionStatus:
        with self._connect() as conn:
            row = conn.execute("SELECT status FROM mission_states WHERE mission_id=?", (mission_id,)).fetchone()
        if not row:
            raise KeyError(mission_id)
        return MissionStatus(row["status"])

    def save_approval(self, approval: ApprovalRequest, mission_id: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO approvals(approval_id,action_id,mission_id,reason,status,created_at,updated_at) VALUES(?,?,?,?,?,COALESCE((SELECT created_at FROM approvals WHERE approval_id=?),?),?)", (approval.id, approval.action_id, mission_id, approval.reason, approval.status.value, approval.id, now, now))

    def get_approval(self, approval_id: str) -> ApprovalRequest:
        with self._connect() as conn:
            row = conn.execute("SELECT approval_id,action_id,reason,status FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        if not row:
            raise KeyError(approval_id)
        return ApprovalRequest(row["action_id"], row["reason"], ApprovalStatus(row["status"]), row["approval_id"])

    def get_approval_mission(self, approval_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT mission_id FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        if not row:
            raise KeyError(approval_id)
        return row["mission_id"]

    def update_approval(self, approval_id: str, status: ApprovalStatus) -> ApprovalRequest:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute("UPDATE approvals SET status=?, updated_at=? WHERE approval_id=?", (status.value, now, approval_id))
            if cur.rowcount != 1:
                raise KeyError(approval_id)
            row = conn.execute("SELECT approval_id,action_id,reason,status FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        return ApprovalRequest(row["action_id"], row["reason"], ApprovalStatus(row["status"]), row["approval_id"])

    def pending_approvals(self, mission_id: str | None = None) -> tuple[ApprovalRequest, ...]:
        with self._connect() as conn:
            if mission_id is None:
                rows = conn.execute("SELECT approval_id,action_id,reason,status FROM approvals WHERE status=? ORDER BY created_at", (ApprovalStatus.PENDING.value,)).fetchall()
            else:
                rows = conn.execute("SELECT approval_id,action_id,reason,status FROM approvals WHERE status=? AND mission_id=? ORDER BY created_at", (ApprovalStatus.PENDING.value, mission_id)).fetchall()
        return tuple(ApprovalRequest(r["action_id"], r["reason"], ApprovalStatus(r["status"]), r["approval_id"]) for r in rows)

    def record_audit(self, event: AuditEvent) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO audit_events(event_id,event_type,actor,outcome,payload,timestamp) VALUES(?,?,?,?,?,?)", (event.id, event.event_type, event.actor, event.outcome, json.dumps(event.payload, sort_keys=True), event.timestamp))

    def audit_events(self) -> tuple[dict[str, Any], ...]:
        with self._connect() as conn:
            rows = conn.execute("SELECT event_id,event_type,actor,outcome,payload,timestamp FROM audit_events ORDER BY timestamp,event_id").fetchall()
        return tuple({"id": r["event_id"], "event_type": r["event_type"], "actor": r["actor"], "outcome": r["outcome"], "payload": json.loads(r["payload"]), "timestamp": r["timestamp"]} for r in rows)

    @staticmethod
    def idempotency_key(*parts: str) -> str:
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()

    def get_idempotent(self, key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT result FROM idempotency WHERE key=?", (key,)).fetchone()
        return json.loads(row["result"]) if row else None

    def get_idempotency_fingerprint(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT fingerprint FROM idempotency WHERE key=?", (key,)).fetchone()
        return row["fingerprint"] if row else None

    def put_idempotent(self, key: str, result: dict[str, Any], fingerprint: str = "") -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        encoded = json.dumps(result, sort_keys=True)
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO idempotency(key,fingerprint,result,created_at) VALUES(?,?,?,?)", (key, fingerprint, encoded, now))
            row = conn.execute("SELECT fingerprint,result FROM idempotency WHERE key=?", (key,)).fetchone()
        if row is None:
            raise RuntimeError("Idempotency record could not be persisted")
        if row["fingerprint"] != fingerprint:
            raise ValueError("Identité d'action réutilisée avec un contenu différent.")
        return json.loads(row["result"])

    @staticmethod
    def _validate_execution_identity(row: sqlite3.Row, mission_id: str, action_id: str) -> None:
        if row["mission_id"] != mission_id or row["action_id"] != action_id:
            raise ValueError("Identité d'exécution réutilisée pour une autre mission ou action.")

    def begin_execution(self, execution_key: str, mission_id: str, action_id: str, lease_seconds: int = 300) -> dict[str, Any]:
        if lease_seconds <= 0:
            raise ValueError("La durée du lease doit être positive.")
        now = datetime.now(timezone.utc)
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        with self._connect() as conn:
            cur = conn.execute("INSERT OR IGNORE INTO executions(execution_key,mission_id,action_id,status,started_at,lease_until) VALUES(?,?,?,?,?,?)", (execution_key, mission_id, action_id, "RUNNING", now.isoformat(), lease_until))
            row = conn.execute("SELECT execution_key,mission_id,action_id,status,result,error,started_at,finished_at,lease_until FROM executions WHERE execution_key=?", (execution_key,)).fetchone()
        if row is None:
            raise RuntimeError("Execution record could not be persisted")
        self._validate_execution_identity(row, mission_id, action_id)
        result = dict(row)
        result["claimed"] = cur.rowcount == 1
        return result

    def begin_execution_and_start_mission(self, execution_key: str, mission_id: str, action_id: str, lease_seconds: int = 300) -> dict[str, Any]:
        if lease_seconds <= 0:
            raise ValueError("La durée du lease doit être positive.")
        now = datetime.now(timezone.utc)
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        with self._connect() as conn:
            existing = conn.execute("SELECT execution_key,mission_id,action_id,status,result,error,started_at,finished_at,lease_until FROM executions WHERE execution_key=?", (execution_key,)).fetchone()
            if existing is not None:
                self._validate_execution_identity(existing, mission_id, action_id)
                result = dict(existing)
                result["claimed"] = False
                return result
            self._transition_mission_status(conn, mission_id, MissionStatus.RUNNING, expected_current=MissionStatus.PLANNED)
            conn.execute("INSERT INTO executions(execution_key,mission_id,action_id,status,started_at,lease_until) VALUES(?,?,?,?,?,?)", (execution_key, mission_id, action_id, "RUNNING", now.isoformat(), lease_until))
            row = conn.execute("SELECT execution_key,mission_id,action_id,status,result,error,started_at,finished_at,lease_until FROM executions WHERE execution_key=?", (execution_key,)).fetchone()
        if row is None:
            raise RuntimeError("Execution record could not be persisted")
        self._validate_execution_identity(row, mission_id, action_id)
        result = dict(row)
        result["claimed"] = True
        return result

    def heartbeat_execution(self, execution_key: str, lease_seconds: int = 300) -> dict[str, Any]:
        if lease_seconds <= 0:
            raise ValueError("La durée du lease doit être positive.")
        now = datetime.now(timezone.utc)
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        with self._connect() as conn:
            cur = conn.execute("UPDATE executions SET lease_until=? WHERE execution_key=? AND status='RUNNING'", (lease_until, execution_key))
        if cur.rowcount != 1:
            raise RuntimeError("Execution inexistante ou non active")
        row = self.get_execution(execution_key)
        if row is None:
            raise KeyError(execution_key)
        return row

    def mark_execution_recovery_required(self, execution_key: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute("UPDATE executions SET status='RECOVERY_REQUIRED', finished_at=? WHERE execution_key=? AND status='RUNNING'", (now, execution_key))
            row = conn.execute("SELECT execution_key,mission_id,action_id,status,result,error,started_at,finished_at,lease_until FROM executions WHERE execution_key=?", (execution_key,)).fetchone()
        if row is None:
            raise KeyError(execution_key)
        if cur.rowcount != 1 and row["status"] == "RUNNING":
            raise RuntimeError("Execution state could not enter recovery")
        return dict(row)

    def recover_stale_execution(self, execution_key: str) -> dict[str, Any] | None:
        row = self.get_execution(execution_key)
        if row is None or row["status"] != "RUNNING" or not row.get("lease_until"):
            return row
        lease_until = datetime.fromisoformat(row["lease_until"])
        if lease_until > datetime.now(timezone.utc):
            return row
        return self.mark_execution_recovery_required(execution_key)

    def resolve_execution_recovery(self, execution_key: str, decision: str, *, result: Any = None, reason: str | None = None) -> dict[str, Any]:
        if decision not in {"CONFIRM", "FAIL", "CANCEL"}:
            raise ValueError(f"Décision de récupération inconnue: {decision}")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute("SELECT execution_key,mission_id,action_id,status,result,error FROM executions WHERE execution_key=?", (execution_key,)).fetchone()
            if row is None:
                raise KeyError(execution_key)
            if row["status"] != "RECOVERY_REQUIRED":
                raise ValueError("Seule une exécution RECOVERY_REQUIRED peut être résolue.")
            mission = conn.execute("SELECT status FROM mission_states WHERE mission_id=?", (row["mission_id"],)).fetchone()
            if mission is None:
                raise KeyError(row["mission_id"])
            if mission["status"] != MissionStatus.RUNNING.value:
                raise ValueError("La mission doit être RUNNING pendant une récupération.")
            if decision == "CONFIRM":
                execution_status = "COMPLETED"
                mission_status = MissionStatus.COMPLETED
                encoded_result = json.dumps(result, sort_keys=True, default=str)
                error = reason
            elif decision == "FAIL":
                execution_status = "FAILED"
                mission_status = MissionStatus.FAILED
                encoded_result = None
                error = reason or "Échec confirmé pendant la récupération."
            else:
                execution_status = "FAILED"
                mission_status = MissionStatus.CANCELLED
                encoded_result = None
                error = reason or "Exécution annulée pendant la récupération."
            execution_cur = conn.execute("UPDATE executions SET status=?,result=?,error=?,finished_at=?,lease_until=NULL WHERE execution_key=? AND status='RECOVERY_REQUIRED'", (execution_status, encoded_result, error, now, execution_key))
            if execution_cur.rowcount != 1:
                raise RuntimeError("La résolution de récupération n'a pas été persistée.")
            self._transition_mission_status(conn, row["mission_id"], mission_status, expected_current=MissionStatus.RUNNING)
            final = conn.execute("SELECT execution_key,mission_id,action_id,status,result,error,started_at,finished_at,lease_until FROM executions WHERE execution_key=?", (execution_key,)).fetchone()
        if final is None:
            raise RuntimeError("Execution record could not be persisted")
        return dict(final)

    def finish_execution(self, execution_key: str, status: str, result: Any = None, error: str | None = None) -> dict[str, Any]:
        if status not in {"COMPLETED", "FAILED"}:
            raise ValueError("Un résultat d'exécution doit être COMPLETED ou FAILED.")
        now = datetime.now(timezone.utc).isoformat()
        encoded = None if result is None else json.dumps(result, sort_keys=True)
        with self._connect() as conn:
            cur = conn.execute("UPDATE executions SET status=?,result=?,error=?,finished_at=?,lease_until=NULL WHERE execution_key=? AND status='RUNNING'", (status, encoded, error, now, execution_key))
            row = conn.execute("SELECT execution_key,mission_id,action_id,status,result,error,started_at,finished_at,lease_until FROM executions WHERE execution_key=?", (execution_key,)).fetchone()
        if row is None:
            raise KeyError(execution_key)
        if cur.rowcount != 1 and row["status"] not in {"COMPLETED", "FAILED"}:
            raise RuntimeError("Execution state could not be finalized")
        return dict(row)

    def finish_execution_and_mission(self, execution_key: str, status: str, result: Any = None, error: str | None = None) -> dict[str, Any]:
        if status not in {"COMPLETED", "FAILED"}:
            raise ValueError("Un résultat d'exécution doit être COMPLETED ou FAILED.")
        now = datetime.now(timezone.utc).isoformat()
        encoded = None if result is None else json.dumps(result, sort_keys=True)
        with self._connect() as conn:
            cur = conn.execute("UPDATE executions SET status=?,result=?,error=?,finished_at=?,lease_until=NULL WHERE execution_key=? AND status='RUNNING'", (status, encoded, error, now, execution_key))
            if cur.rowcount != 1:
                row = conn.execute("SELECT execution_key,mission_id,action_id,status,result,error,started_at,finished_at,lease_until FROM executions WHERE execution_key=?", (execution_key,)).fetchone()
                if row is None:
                    raise KeyError(execution_key)
                return dict(row)
            row = conn.execute("SELECT mission_id FROM executions WHERE execution_key=?", (execution_key,)).fetchone()
            if row is None:
                raise KeyError(execution_key)
            mission_status = MissionStatus.COMPLETED if status == "COMPLETED" else MissionStatus.FAILED
            self._transition_mission_status(conn, row["mission_id"], mission_status, expected_current=MissionStatus.RUNNING)
            final = conn.execute("SELECT execution_key,mission_id,action_id,status,result,error,started_at,finished_at,lease_until FROM executions WHERE execution_key=?", (execution_key,)).fetchone()
        if final is None:
            raise RuntimeError("Execution record could not be persisted")
        return dict(final)

    def get_execution(self, execution_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT execution_key,mission_id,action_id,status,result,error,started_at,finished_at,lease_until FROM executions WHERE execution_key=?", (execution_key,)).fetchone()
        return dict(row) if row else None
