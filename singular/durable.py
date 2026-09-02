from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .autopilot import ApprovalRequest, ApprovalStatus, DelegationContract
from .audit import AuditEvent


class DurableStore:
    """Small SQLite persistence boundary for mission, approval and audit state.

    SQLite is deliberately used first: zero infrastructure, transactional writes,
    deterministic local development, and a clean seam for a future managed store.
    """

    def __init__(self, path: str | Path = "data/singular.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
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
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
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
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def save_mission(self, contract: DelegationContract) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(asdict(contract), sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO missions(mission_id,payload,created_at) VALUES(?,?,?)",
                (contract.mission_id, payload, now),
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

    def save_approval(self, approval: ApprovalRequest) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO approvals(approval_id,action_id,reason,status,created_at,updated_at) VALUES(?,?,?,?,COALESCE((SELECT created_at FROM approvals WHERE approval_id=?),?),?)",
                (approval.id, approval.action_id, approval.reason, approval.status.value, approval.id, now, now),
            )

    def update_approval(self, approval_id: str, status: ApprovalStatus) -> ApprovalRequest:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute("UPDATE approvals SET status=?, updated_at=? WHERE approval_id=?", (status.value, now, approval_id))
            if cur.rowcount != 1:
                raise KeyError(approval_id)
            row = conn.execute("SELECT approval_id,action_id,reason,status FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        return ApprovalRequest(row["action_id"], row["reason"], ApprovalStatus(row["status"]), row["approval_id"])

    def pending_approvals(self) -> tuple[ApprovalRequest, ...]:
        with self._connect() as conn:
            rows = conn.execute("SELECT approval_id,action_id,reason,status FROM approvals WHERE status=? ORDER BY created_at", (ApprovalStatus.PENDING.value,)).fetchall()
        return tuple(ApprovalRequest(r["action_id"], r["reason"], ApprovalStatus(r["status"]), r["approval_id"]) for r in rows)

    def record_audit(self, event: AuditEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO audit_events(event_id,event_type,actor,outcome,payload,timestamp) VALUES(?,?,?,?,?,?)",
                (event.id, event.event_type, event.actor, event.outcome, json.dumps(event.payload, sort_keys=True), event.timestamp),
            )

    def audit_events(self) -> tuple[dict[str, Any], ...]:
        with self._connect() as conn:
            rows = conn.execute("SELECT event_id,event_type,actor,outcome,payload,timestamp FROM audit_events ORDER BY timestamp,event_id").fetchall()
        return tuple({"id": r["event_id"], "event_type": r["event_type"], "actor": r["actor"], "outcome": r["outcome"], "payload": json.loads(r["payload"]), "timestamp": r["timestamp"]} for r in rows)

    @staticmethod
    def idempotency_key(*parts: str) -> str:
        canonical = "\x1f".join(parts).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def get_idempotent(self, key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT result FROM idempotency WHERE key=?", (key,)).fetchone()
        return json.loads(row["result"]) if row else None

    def put_idempotent(self, key: str, result: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO idempotency(key,result,created_at) VALUES(?,?,?)", (key, json.dumps(result, sort_keys=True), now))
