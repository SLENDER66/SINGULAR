from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .autopilot import ApprovalStatus, Autonomy
from .durable import DurableStore, MissionStatus
from .mission_runtime import DurableMissionRuntime


@dataclass(frozen=True)
class ExecutionResult:
    execution_key: str
    mission_id: str
    action_id: str
    status: str
    result: Any = None
    error: str | None = None


class ExecutionInProgress(RuntimeError):
    """Another worker owns the durable execution lease."""


class ExecutionRecoveryRequired(RuntimeError):
    """A stale execution was quarantined and requires an explicit recovery decision."""


class DurableExecutionEngine:
    """Execution transaction boundary: authorize, claim, run, persist outcome."""

    def __init__(self, runtime: DurableMissionRuntime, execution_lease_seconds: int = 300) -> None:
        if execution_lease_seconds <= 0:
            raise ValueError("La durée du lease doit être positive.")
        self.runtime = runtime
        self.store: DurableStore = runtime.store
        self.execution_lease_seconds = execution_lease_seconds
        self.store.init_execution_schema()

    def execute(
        self,
        action,
        mission_id: str,
        handler: Callable[[Any], Any],
    ) -> ExecutionResult:
        key = self.store.idempotency_key("execute", mission_id, action.id)
        existing = self.store.get_execution(key)
        if existing is not None:
            return self._handle_existing_execution(key, existing)

        try:
            governed = self.runtime.route(action, mission_id)
        except ValueError:
            existing = self.store.get_execution(key)
            if existing is not None:
                return self._handle_existing_execution(key, existing)
            raise

        contract = self.store.load_mission(mission_id)
        if contract is None:
            raise KeyError(mission_id)

        # Runtime routing canonicalizes the action identity by binding it to the
        # mission contract. Approval fingerprints are computed over that canonical
        # action, so validation and execution must use the same representation.
        action = governed.action

        if governed.governor.mode == Autonomy.BLOCK or not governed.can_prepare:
            raise PermissionError("Action bloquée par la gouvernance.")
        if governed.governor.mode == Autonomy.PREPARE:
            raise PermissionError("Action is not executable: préparée mais non autorisée à l'exécution.")
        if not governed.can_execute:
            raise PermissionError("Action non autorisée à l'exécution par la politique de sécurité.")

        if governed.governor.mode == Autonomy.ESCALATE:
            approval_id = governed.governor.approval_id
            if not approval_id:
                raise PermissionError("Action escaladée sans approbation identifiable.")
            approval = self.store.get_approval(approval_id)
            if approval.status != ApprovalStatus.APPROVED:
                raise PermissionError("Action en attente d'une approbation humaine valide.")
            self._validate_approval_binding(approval_id, action, mission_id)

        if governed.governor.mode not in (
            Autonomy.EXECUTE_REVERSIBLE,
            Autonomy.EXECUTE_AUTHORIZED,
            Autonomy.ESCALATE,
        ):
            raise PermissionError("Mode de gouvernance non exécutable.")

        if self.store.get_mission_status(mission_id) != MissionStatus.PLANNED:
            raise ValueError("La mission doit être PLANNED avant exécution.")

        claimed = self.store.begin_execution_and_start_mission(
            key,
            mission_id,
            action.id,
            self.execution_lease_seconds,
        )
        if not claimed["claimed"]:
            return self._handle_existing_execution(key, claimed)

        try:
            value = handler(action)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            self.store.finish_execution_and_mission(key, "FAILED", error=message)
            self.runtime.audit.record(
                "execution",
                "EXECUTION",
                "FAILED",
                {"execution_key": key, "mission_id": mission_id, "action_id": action.id, "error": message},
            )
            self.runtime._persist_new_audit_events()
            return ExecutionResult(key, mission_id, action.id, "FAILED", error=message)

        encoded = json.loads(json.dumps(value, default=str))
        self.store.finish_execution_and_mission(key, "COMPLETED", result=encoded)
        self.runtime.audit.record(
            "execution",
            "EXECUTION",
            "COMPLETED",
            {"execution_key": key, "mission_id": mission_id, "action_id": action.id},
        )
        self.runtime._persist_new_audit_events()
        return ExecutionResult(key, mission_id, action.id, "COMPLETED", result=encoded)

    def _validate_approval_binding(self, approval_id: str, action, mission_id: str) -> None:
        expected = self.runtime._action_fingerprint(action, mission_id)
        actual = self.runtime.approval_fingerprint(approval_id, self.store)
        if actual is None:
            raise PermissionError("Approbation sans liaison d'identité d'action : exécution refusée.")
        if actual != expected:
            raise PermissionError("Approbation invalide : l'action ou son contexte a changé depuis la validation humaine.")

    def _handle_existing_execution(self, key: str, existing: dict[str, Any]) -> ExecutionResult:
        if existing["status"] == "RUNNING":
            recovered = self.store.recover_stale_execution(key)
            if recovered is not None and recovered["status"] == "RECOVERY_REQUIRED":
                self.runtime.audit.record(
                    "execution",
                    "RECOVERY",
                    "RECOVERY_REQUIRED",
                    {
                        "execution_key": key,
                        "mission_id": existing["mission_id"],
                        "action_id": existing["action_id"],
                    },
                )
                self.runtime._persist_new_audit_events()
                raise ExecutionRecoveryRequired(key)
            raise ExecutionInProgress(key)
        if existing["status"] in {"COMPLETED", "FAILED"}:
            return self._result_from_row(existing)
        if existing["status"] == "RECOVERY_REQUIRED":
            raise ExecutionRecoveryRequired(key)
        raise RuntimeError(f"État d'exécution inconnu: {existing['status']}")

    @staticmethod
    def _result_from_row(row: dict[str, Any]) -> ExecutionResult:
        result = row.get("result")
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                pass
        return ExecutionResult(
            row["execution_key"],
            row["mission_id"],
            row["action_id"],
            row["status"],
            result=result,
            error=row.get("error"),
        )
