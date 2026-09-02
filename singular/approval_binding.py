from __future__ import annotations

import sqlite3
from pathlib import Path


class ApprovalBindingStore:
    """Durable immutable approval -> exact action identity binding."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS approval_bindings (
                    approval_id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    mission_id TEXT,
                    action_fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def bind(
        self,
        approval_id: str,
        action_id: str,
        mission_id: str | None,
        action_fingerprint: str,
    ) -> None:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT action_id, mission_id, action_fingerprint FROM approval_bindings WHERE approval_id=?",
                (approval_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["action_id"] != action_id
                    or existing["mission_id"] != mission_id
                    or existing["action_fingerprint"] != action_fingerprint
                ):
                    raise ValueError("Une approbation ne peut pas être rebondie vers une autre identité.")
                return
            conn.execute(
                "INSERT INTO approval_bindings(approval_id,action_id,mission_id,action_fingerprint) VALUES(?,?,?,?)",
                (approval_id, action_id, mission_id, action_fingerprint),
            )

    def get(self, approval_id: str) -> dict[str, str | None] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT approval_id, action_id, mission_id, action_fingerprint FROM approval_bindings WHERE approval_id=?",
                (approval_id,),
            ).fetchone()
        return dict(row) if row else None

    def fingerprint(self, approval_id: str) -> str | None:
        binding = self.get(approval_id)
        return binding["action_fingerprint"] if binding else None
