"""Evidence-backed finalization for externally reconciled executions.

This module extends the durable store with one narrowly scoped transition:
RECOVERY_REQUIRED -> COMPLETED is permitted only when the persisted external
effect is already COMPLETED and belongs to the same execution.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .durable import DurableStore, MissionStatus


def confirm_execution_recovery_from_effect(
    self: DurableStore,
    execution_key: str,
    provider_idempotency_key: str,
) -> dict[str, Any]:
    """Atomically finalize recovery from persisted provider completion evidence."""
    now = datetime.now(UTC).isoformat()
    with self._connect() as conn:
        execution = conn.execute(
            "SELECT execution_key,mission_id,action_id,status,result,error,started_at,finished_at,lease_until "
            "FROM executions WHERE execution_key=?",
            (execution_key,),
        ).fetchone()
        if execution is None:
            raise KeyError(execution_key)
        if execution["status"] != "RECOVERY_REQUIRED":
            raise ValueError("Seule une exécution RECOVERY_REQUIRED peut être confirmée par preuve externe.")
        mission = conn.execute(
            "SELECT status FROM mission_states WHERE mission_id=?",
            (execution["mission_id"],),
        ).fetchone()
        if mission is None:
            raise KeyError(execution["mission_id"])
        if mission["status"] != MissionStatus.RUNNING.value:
            raise ValueError("La mission doit être RUNNING pendant une récupération.")
        effect = conn.execute(
            "SELECT provider_idempotency_key,execution_key,status,result,error "
            "FROM external_effects WHERE provider_idempotency_key=?",
            (provider_idempotency_key,),
        ).fetchone()
        if effect is None:
            raise ValueError("Aucune preuve durable d'effet externe correspondante n'est disponible.")
        if effect["execution_key"] != execution_key:
            raise ValueError("La preuve d'effet externe appartient à une autre exécution.")
        if effect["status"] != "COMPLETED":
            raise ValueError("La preuve d'effet externe n'est pas dans un état COMPLETED.")
        cur = conn.execute(
            "UPDATE executions SET status='COMPLETED',result=?,error=NULL,finished_at=?,lease_until=NULL "
            "WHERE execution_key=? AND status='RECOVERY_REQUIRED'",
            (effect["result"], now, execution_key),
        )
        if cur.rowcount != 1:
            raise RuntimeError("La finalisation de récupération a échoué à cause d'une concurrence d'état.")
        self._transition_mission_status(
            conn,
            execution["mission_id"],
            MissionStatus.COMPLETED,
            expected_current=MissionStatus.RUNNING,
        )
        final = conn.execute(
            f"SELECT {self._execution_fields()} FROM executions WHERE execution_key=?",
            (execution_key,),
        ).fetchone()
    if final is None:
        raise RuntimeError("Execution record could not be persisted")
    return dict(final)


if not hasattr(DurableStore, "confirm_execution_recovery_from_effect"):
    setattr(DurableStore, "confirm_execution_recovery_from_effect", confirm_execution_recovery_from_effect)


__all__ = ["confirm_execution_recovery_from_effect"]
