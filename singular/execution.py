from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

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


class DurableExecutionEngine:
    """Execution transaction boundary: authorize, claim, run, persist outcome."""

    def __init__(self, runtime: DurableMissionRuntime) -> None:
        self.runtime = runtime
        self.store: DurableStore = runtime.store
        self.store.init_execution_schema()

    def execute(
        self,
        action,
        mission_id: str,
        handler: Callable[[Any], Any],
    ) -> ExecutionResult:
        governed = self.runtime.route(action, mission_id)
        contract = self.store.load_mission(mission_id)
        if contract is None:
            raise KeyError(mission_id)

        if governed.governor.mode == Autonomy.BLOCK:
            raise PermissionError("Action bloquée par la gouvernance.")
        if governed.governor.mode == Autonomy.PREPARE:
            raise PermissionError("Action préparée mais non autorisée à l'exécution.")

        if governed.governor.mode == Autonomy.ESCALATE:
            approval_id = governed.governor.approval_id
            if not approval_id:
                raise PermissionError("Action escaladée sans approbation identifiable.")
            approval = self.store.get_approval(approval_id)
            if approval.status != ApprovalStatus.APPROVED:
                raise PermissionError("Action en attente d'une approbation humaine valide.")

        if governed.governor.mode not in (
            Autonomy.EXECUTE_REVERSIBLE,
            Autonomy.EXECUTE_AUTHORIZED,
            Autonomy.ESCALATE,
        ):
            raise PermissionError("Mode de gouvernance non exécutable.")
        if self.store.get_mission_status(mission_id) != MissionStatus.PLANNED:
            raise ValueError("La mission doit être PLANNED avant exécution.")

        key = self.store.idempotency_key("execute", mission_id, action.id)
        claimed = self.store.begin_execution(key, mission_id, action.id)
        if not claimed["claimed"]:
            if claimed["status"] == "RUNNING":
                raise ExecutionInProgress(key)
            return self._result_from_row(claimed)

        self.runtime._set_status(mission_id, MissionStatus.RUNNING)
        try:
            value = handler(action)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            self.store.finish_execution(key, "FAILED", error=message)
            self.runtime._set_status(mission_id, MissionStatus.FAILED)
            self.runtime.audit.record(
                "execution",
                "EXECUTION",
                "FAILED",
                {"execution_key": key, "mission_id": mission_id, "action_id": action.id, "error": message},
            )
            self.runtime._persist_new_audit_events()
            return ExecutionResult(key, mission_id, action.id, "FAILED", error=message)

        encoded = json.loads(json.dumps(value, default=str))
        self.store.finish_execution(key, "COMPLETED", result=encoded)
        self.runtime._set_status(mission_id, MissionStatus.COMPLETED)
        self.runtime.audit.record(
            "execution",
            "EXECUTION",
            "COMPLETED",
            {"execution_key": key, "mission_id": mission_id, "action_id": action.id},
        )
        self.runtime._persist_new_audit_events()
        return ExecutionResult(key, mission_id, action.id, "COMPLETED", result=encoded)

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
