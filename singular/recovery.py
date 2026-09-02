from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .durable import DurableStore, MissionStatus


class RecoveryDecision(str, Enum):
    """Explicit operator decisions for an execution whose external outcome is unknown."""

    CONFIRM = "CONFIRM"
    FAIL = "FAIL"
    CANCEL = "CANCEL"


@dataclass(frozen=True)
class RecoveryResult:
    execution_key: str
    mission_id: str
    action_id: str
    execution_status: str
    mission_status: MissionStatus
    result: Any = None
    error: str | None = None


class RecoveryManager:
    """Fail-closed recovery boundary for stale executions.

    A quarantined execution can never be resumed automatically. CONFIRM records an
    externally reconciled success, while FAIL/CANCEL terminate the mission without
    invoking the original handler.
    """

    def __init__(self, store: DurableStore) -> None:
        self.store = store

    def resolve(
        self,
        execution_key: str,
        decision: RecoveryDecision,
        *,
        result: Any = None,
        reason: str | None = None,
    ) -> RecoveryResult:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.store.path, timeout=10.0) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            row = conn.execute(
                "SELECT execution_key,mission_id,action_id,status,result,error FROM executions WHERE execution_key=?",
                (execution_key,),
            ).fetchone()
            if row is None:
                raise KeyError(execution_key)
            if row["status"] != "RECOVERY_REQUIRED":
                raise ValueError("Seule une exécution RECOVERY_REQUIRED peut être résolue.")

            mission = conn.execute(
                "SELECT status FROM mission_states WHERE mission_id=?",
                (row["mission_id"],),
            ).fetchone()
            if mission is None:
                raise KeyError(row["mission_id"])
            if mission["status"] != MissionStatus.RUNNING.value:
                raise ValueError("La mission doit être RUNNING pendant une récupération.")

            if decision is RecoveryDecision.CONFIRM:
                execution_status = "COMPLETED"
                mission_status = MissionStatus.COMPLETED
                encoded_result = json.dumps(result, sort_keys=True, default=str)
                error = reason
            elif decision is RecoveryDecision.FAIL:
                execution_status = "FAILED"
                mission_status = MissionStatus.FAILED
                encoded_result = None
                error = reason or "Échec confirmé pendant la récupération."
            elif decision is RecoveryDecision.CANCEL:
                execution_status = "FAILED"
                mission_status = MissionStatus.CANCELLED
                encoded_result = None
                error = reason or "Exécution annulée pendant la récupération."
            else:
                raise ValueError(f"Décision de récupération inconnue: {decision}")

            conn.execute(
                "UPDATE executions SET status=?,result=?,error=?,finished_at=?,lease_until=NULL WHERE execution_key=? AND status='RECOVERY_REQUIRED'",
                (execution_status, encoded_result, error, now, execution_key),
            )
            if conn.total_changes != 1:
                raise RuntimeError("La résolution de récupération n'a pas été persistée.")
            conn.execute(
                "UPDATE mission_states SET status=?,updated_at=? WHERE mission_id=? AND status='RUNNING'",
                (mission_status.value, now, row["mission_id"]),
            )
            if conn.total_changes != 2:
                raise RuntimeError("La résolution de récupération n'a pas pu finaliser la mission.")

            stored_result = json.loads(encoded_result) if encoded_result is not None else None
            return RecoveryResult(
                row["execution_key"],
                row["mission_id"],
                row["action_id"],
                execution_status,
                mission_status,
                stored_result,
                error,
            )
