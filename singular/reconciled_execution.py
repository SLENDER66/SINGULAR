from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .durable import DurableStore, MissionStatus
from .effects import EffectStatus


@dataclass(frozen=True)
class ReconciledExecution:
    execution_key: str
    mission_id: str
    action_id: str
    result: Any


class ReconciledExecutionFinalizer:
    """Finalize quarantined executions only from durable reconciled evidence.

    Operator assertions are deliberately not accepted here. The external-effect
    record must already be terminal COMPLETED and must belong to the execution
    being finalized. Execution and mission state are then advanced atomically.
    """

    def __init__(self, store: DurableStore) -> None:
        self.store = store

    def finalize(
        self,
        execution_key: str,
        *,
        provider: str,
        operation: str,
        payload_fingerprint: str,
        action_fingerprint: str | None = None,
    ) -> ReconciledExecution:
        if not execution_key.strip():
            raise ValueError("execution_key cannot be blank")
        if not provider.strip() or not operation.strip() or not payload_fingerprint.strip():
            raise ValueError("provider, operation and payload_fingerprint are required")

        now = datetime.now(UTC).isoformat()
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            execution = conn.execute(
                "SELECT execution_key,mission_id,action_id,status,result FROM executions WHERE execution_key=?",
                (execution_key,),
            ).fetchone()
            if execution is None:
                raise KeyError(execution_key)
            if execution["status"] != "RECOVERY_REQUIRED":
                raise ValueError("Seule une exécution RECOVERY_REQUIRED peut être finalisée par réconciliation.")

            effect_key = self._effect_key(execution_key, provider, operation)
            effect = conn.execute(
                "SELECT execution_key,provider,operation,payload_fingerprint,action_fingerprint,status,result,error "
                "FROM external_effects WHERE provider_idempotency_key=?",
                (effect_key,),
            ).fetchone()
            if effect is None:
                raise ValueError("Aucune preuve durable de réconciliation ne correspond à cette exécution.")
            if effect["execution_key"] != execution_key:
                raise ValueError("La preuve de réconciliation appartient à une autre exécution.")
            if effect["provider"] != provider or effect["operation"] != operation:
                raise ValueError("La preuve de réconciliation ne correspond pas au fournisseur ou à l'opération.")
            if effect["payload_fingerprint"] != payload_fingerprint:
                raise ValueError("La preuve de réconciliation ne correspond pas au payload.")
            if effect["action_fingerprint"] != action_fingerprint:
                raise ValueError("La preuve de réconciliation ne correspond pas à l'action.")
            if effect["status"] != EffectStatus.COMPLETED.value:
                raise ValueError("Une preuve externe non terminale ne peut pas finaliser l'exécution.")

            mission = conn.execute(
                "SELECT status FROM mission_states WHERE mission_id=?",
                (execution["mission_id"],),
            ).fetchone()
            if mission is None or mission["status"] != MissionStatus.RUNNING.value:
                raise ValueError("La mission doit être RUNNING pendant la finalisation par réconciliation.")

            result = json.loads(effect["result"]) if effect["result"] is not None else None
            cur = conn.execute(
                "UPDATE executions SET status='COMPLETED',result=?,error=NULL,finished_at=?,lease_until=NULL "
                "WHERE execution_key=? AND status='RECOVERY_REQUIRED'",
                (json.dumps(result, sort_keys=True, default=str), now, execution_key),
            )
            if cur.rowcount != 1:
                raise RuntimeError("La finalisation de l'exécution a échoué à cause d'une concurrence d'état.")

            # Through the store's own guard rather than a hand-written UPDATE.
            # This one happens to move RUNNING -> COMPLETED, which is legal, so
            # the raw statement was correct -- but it is the guard that knows
            # which transitions are legal, and a copy of this block aimed at a
            # different status would not have asked it.
            self.store._transition_mission_status(
                conn,
                execution["mission_id"],
                MissionStatus.COMPLETED,
                expected_current=MissionStatus.RUNNING,
            )

        return ReconciledExecution(
            execution_key=execution_key,
            mission_id=execution["mission_id"],
            action_id=execution["action_id"],
            result=result,
        )

    @staticmethod
    def _effect_key(execution_key: str, provider: str, operation: str) -> str:
        import hashlib

        material = "\x1f".join((execution_key, provider, operation))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


__all__ = ["ReconciledExecution", "ReconciledExecutionFinalizer"]
