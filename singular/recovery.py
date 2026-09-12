from __future__ import annotations

import json
from dataclasses import dataclass
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

    A quarantined execution can never be resumed automatically. A successful
    outcome must be established through the external-effect reconciliation
    protocol, not asserted by an operator through this generic recovery API.
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
        if decision is RecoveryDecision.CONFIRM:
            raise ValueError(
                "Une exécution RECOVERY_REQUIRED ne peut être confirmée comme réussie sans preuve externe. "
                "Utilisez la réconciliation du fournisseur."
            )
        persisted = self.store.resolve_execution_recovery(
            execution_key,
            decision.value,
            result=result,
            reason=reason,
        )
        encoded_result = persisted.get("result")
        stored_result = json.loads(encoded_result) if encoded_result is not None else None
        return RecoveryResult(
            persisted["execution_key"],
            persisted["mission_id"],
            persisted["action_id"],
            persisted["status"],
            self.store.get_mission_status(persisted["mission_id"]),
            stored_result,
            persisted.get("error"),
        )
