from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .approval_binding import ApprovalBindingStore
from .approval_integrity import ApprovalIntegrityStore
from .autopilot import ApprovalStatus, Autonomy
from .durable import DurableStore, MissionStatus
from .effects import EffectProvider, EffectRequest, EffectStatus, ExternalEffectCoordinator
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
    """A stale or externally ambiguous execution requires explicit recovery."""


class DurableExecutionEngine:
    """Execution transaction boundary: authorize, claim, run, persist outcome."""

    def __init__(self, runtime: DurableMissionRuntime, execution_lease_seconds: int = 300, effect_coordinator: ExternalEffectCoordinator | None = None) -> None:
        if execution_lease_seconds <= 0:
            raise ValueError("La durée du lease doit être positive.")
        self.runtime = runtime
        self.store: DurableStore = runtime.store
        self.execution_lease_seconds = execution_lease_seconds
        self.effect_coordinator = effect_coordinator
        self.store.init_execution_schema()

    @staticmethod
    def _execution_identity_fingerprint(action: Any, mission_id: str, governed: Any, contract: Any) -> str:
        """Stable authorization identity for a durable execution key."""
        payload = {
            "mission_id": mission_id,
            "action": {
                "id": getattr(action, "id", None),
                "name": getattr(action, "name", None),
                "payload": getattr(action, "payload", None),
                "risk": getattr(action, "risk", None),
                "reversibility": getattr(action, "reversibility", None),
                "sensitive": getattr(action, "sensitive", None),
                "capability": getattr(action, "capability", None),
            },
            "governance": {
                "policy_tier": getattr(governed, "policy_tier", None),
                "can_prepare": getattr(governed, "can_prepare", None),
                "can_execute": getattr(governed, "can_execute", None),
                "requires_human": getattr(governed, "requires_human", None),
                "reasons": list(getattr(governed, "reasons", ()) or ()),
                "mode": getattr(getattr(governed, "governor", None), "mode", None),
                "approval_id": getattr(getattr(governed, "governor", None), "approval_id", None),
            },
            "contract": None if contract is None else str(contract),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _bind_execution_identity(self, key: str, action: Any, mission_id: str, governed: Any) -> None:
        contract = self.store.load_mission(mission_id)
        fingerprint = self._execution_identity_fingerprint(action, mission_id, governed, contract)
        identity_key = self.store.idempotency_key("execution_identity", key)
        self.store.put_idempotent(identity_key, {"execution_key": key, "mission_id": mission_id, "action_id": action.id}, fingerprint=fingerprint)

    def _validate_execution_identity(self, key: str, action: Any, mission_id: str, governed: Any) -> None:
        identity_key = self.store.idempotency_key("execution_identity", key)
        expected = self._execution_identity_fingerprint(action, mission_id, governed, self.store.load_mission(mission_id))
        actual = self.store.get_idempotency_fingerprint(identity_key)
        if actual is None:
            raise PermissionError("Identité d'exécution absente : exécution/rejeu refusé par sécurité.")
        if actual != expected:
            raise PermissionError("Identité d'exécution réutilisée avec une autorité ou un contenu différent.")

    def _prepare_execution_identity(self, key: str, action: Any, mission_id: str, governed: Any) -> None:
        """Bind identity only for a new execution; never recreate trust for an existing one."""
        self._bind_execution_identity(key, action, mission_id, governed)

    def execute(self, action, mission_id: str, handler: Callable[[Any], Any]) -> ExecutionResult:
        governed = self._authorize(action, mission_id)
        action = governed.action
        key = self.store.idempotency_key("execute", mission_id, action.id)
        existing = self.store.get_execution(key)
        if existing is not None:
            self._validate_execution_identity(key, action, mission_id, governed)
            return self._handle_existing_execution(key, existing)
        self._prepare_execution_identity(key, action, mission_id, governed)
        claimed = self._claim(action, mission_id, key)
        if not claimed["claimed"]:
            self._validate_execution_identity(key, action, mission_id, governed)
            return self._handle_existing_execution(key, claimed)
        try:
            value = handler(action)
        except Exception as exc:
            return self._fail(key, mission_id, action.id, exc)
        return self._complete(key, mission_id, action.id, value)

    def execute_effect(self, action, mission_id: str, provider: EffectProvider, *, provider_name: str, operation: str, payload: Any) -> ExecutionResult:
        """Execute one governed external effect without ever auto-retrying ambiguity."""
        if self.effect_coordinator is None:
            raise RuntimeError("Aucun ExternalEffectCoordinator n'est configuré.")
        governed = self._authorize(action, mission_id)
        action = governed.action
        key = self.store.idempotency_key("execute", mission_id, action.id)
        request = EffectRequest(
            execution_key=key,
            provider=provider_name,
            operation=operation,
            payload=payload,
            action_fingerprint=self.runtime._action_fingerprint(action, mission_id),
        )
        existing = self.store.get_execution(key)
        if existing is not None:
            self._validate_execution_identity(key, action, mission_id, governed)
            try:
                effect = self.effect_coordinator.peek(request)
            except KeyError:
                effect = None
            if effect is not None:
                status = effect["status"]
                if status == EffectStatus.COMPLETED.value:
                    return self._complete(key, mission_id, action.id, effect.get("result"))
                if status == EffectStatus.FAILED.value:
                    return self._fail_result(key, mission_id, action.id, effect.get("error") or "Effet externe échoué.")
                if status == EffectStatus.UNKNOWN.value:
                    if existing["status"] == "RUNNING":
                        self.store.mark_execution_recovery_required(key)
                        self.runtime.audit.record("execution", "EXTERNAL_EFFECT", "RECOVERY_REQUIRED", {"execution_key": key, "mission_id": mission_id, "action_id": action.id, "provider": provider_name, "operation": operation, "reason": "Effet externe ambigu déjà persisté."})
                        self.runtime._persist_new_audit_events()
                        return ExecutionResult(key, mission_id, action.id, "RECOVERY_REQUIRED", result=effect.get("result"), error=effect.get("error"))
            return self._handle_existing_execution(key, existing)
        self._prepare_execution_identity(key, action, mission_id, governed)
        claimed = self._claim(action, mission_id, key)
        if not claimed["claimed"]:
            self._validate_execution_identity(key, action, mission_id, governed)
            try:
                effect = self.effect_coordinator.peek(request)
            except KeyError:
                effect = None
            if effect is not None and effect["status"] == EffectStatus.COMPLETED.value:
                return self._complete(key, mission_id, action.id, effect.get("result"))
            if effect is not None and effect["status"] == EffectStatus.FAILED.value:
                return self._fail_result(key, mission_id, action.id, effect.get("error") or "Effet externe échoué.")
            return self._handle_existing_execution(key, claimed)
        outcome = self.effect_coordinator.execute(request, provider)
        if outcome.status == EffectStatus.UNKNOWN.value:
            self.store.mark_execution_recovery_required(key)
            self.runtime.audit.record("execution", "EXTERNAL_EFFECT", "RECOVERY_REQUIRED", {"execution_key": key, "mission_id": mission_id, "action_id": action.id, "provider": provider_name, "operation": operation})
            self.runtime._persist_new_audit_events()
            return ExecutionResult(key, mission_id, action.id, "RECOVERY_REQUIRED", result=outcome.result, error=outcome.error)
        if outcome.status == EffectStatus.FAILED.value:
            return self._fail_result(key, mission_id, action.id, outcome.error or "Effet externe échoué.")
        if outcome.status != EffectStatus.COMPLETED.value:
            self.store.mark_execution_recovery_required(key)
            return ExecutionResult(key, mission_id, action.id, "RECOVERY_REQUIRED", result=outcome.result, error=outcome.error)
        return self._complete(key, mission_id, action.id, outcome.result)

    def reconcile_effect(self, action, mission_id: str, provider: EffectProvider, *, provider_name: str, operation: str, payload: Any) -> ExecutionResult:
        """Reconcile an ambiguous external effect; never invokes provider.execute."""
        if self.effect_coordinator is None:
            raise RuntimeError("Aucun ExternalEffectCoordinator n'est configuré.")
        governed = self._authorize_reconciliation(action, mission_id)
        action = governed.action
        key = self.store.idempotency_key("execute", mission_id, action.id)
        existing = self.store.get_execution(key)
        if existing is None or existing["status"] != "RECOVERY_REQUIRED":
            raise ValueError("L'exécution doit être RECOVERY_REQUIRED pour une réconciliation.")
        self._validate_execution_identity(key, action, mission_id, governed)
        request = EffectRequest(execution_key=key, provider=provider_name, operation=operation, payload=payload, action_fingerprint=self.runtime._action_fingerprint(action, mission_id))
        outcome = self.effect_coordinator.reconcile(request, provider)
        if outcome.status == EffectStatus.COMPLETED.value:
            return self._result_from_row(self.store.resolve_execution_recovery(key, "CONFIRM", result=outcome.result))
        if outcome.status == EffectStatus.FAILED.value:
            return self._result_from_row(self.store.resolve_execution_recovery(key, "FAIL", reason=outcome.error))
        return ExecutionResult(key, mission_id, action.id, "RECOVERY_REQUIRED", result=outcome.result, error=outcome.error)

    def _authorize(self, action, mission_id: str):
        governed = self.runtime.route(action, mission_id)
        self._validate_governance(governed, action, mission_id)
        return governed

    def _authorize_reconciliation(self, action, mission_id: str):
        governed = self.runtime.route(action, mission_id)
        if governed.governor.mode == Autonomy.BLOCK or not governed.can_prepare:
            raise PermissionError("Action bloquée par la gouvernance.")
        if governed.governor.mode == Autonomy.ESCALATE:
            approval_id = governed.governor.approval_id
            if not approval_id:
                raise PermissionError("Action escaladée sans approbation identifiable.")
            approval = self.store.get_approval(approval_id)
            if approval.status != ApprovalStatus.APPROVED:
                raise PermissionError("Action en attente d'une approbation humaine valide.")
            self._validate_approval_binding(approval_id, governed.action, mission_id)
        return governed

    def _validate_governance(self, governed, action, mission_id: str) -> None:
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
            self._validate_approval_binding(approval_id, governed.action, mission_id)
        if governed.governor.mode not in (Autonomy.EXECUTE_REVERSIBLE, Autonomy.EXECUTE_AUTHORIZED, Autonomy.ESCALATE):
            raise PermissionError("Mode de gouvernance non exécutable.")
        status = self.store.get_mission_status(mission_id)
        if status == MissionStatus.RUNNING:
            key = self.store.idempotency_key("execute", mission_id, action.id)
            existing = self.store.get_execution(key)
            if existing is not None and existing["status"] == "RUNNING":
                return
        if status != MissionStatus.PLANNED:
            raise ValueError("La mission doit être PLANNED avant exécution.")

    def _claim(self, action, mission_id: str, key: str) -> dict[str, Any]:
        return self.store.begin_execution_and_start_mission(key, mission_id, action.id, self.execution_lease_seconds)

    def _fail(self, key: str, mission_id: str, action_id: str, exc: Exception) -> ExecutionResult:
        return self._fail_result(key, mission_id, action_id, f"{type(exc).__name__}: {exc}")

    def _fail_result(self, key: str, mission_id: str, action_id: str, message: str) -> ExecutionResult:
        self.store.finish_execution_and_mission(key, "FAILED", error=message)
        self.runtime.audit.record("execution", "EXECUTION", "FAILED", {"execution_key": key, "mission_id": mission_id, "action_id": action_id, "error": message})
        self.runtime._persist_new_audit_events()
        return ExecutionResult(key, mission_id, action_id, "FAILED", error=message)

    def _complete(self, key: str, mission_id: str, action_id: str, value: Any) -> ExecutionResult:
        encoded = json.loads(json.dumps(value, default=str))
        self.store.finish_execution_and_mission(key, "COMPLETED", result=encoded)
        self.runtime.audit.record("execution", "EXECUTION", "COMPLETED", {"execution_key": key, "mission_id": mission_id, "action_id": action_id})
        self.runtime._persist_new_audit_events()
        return ExecutionResult(key, mission_id, action_id, "COMPLETED", result=encoded)

    def _validate_approval_binding(self, approval_id: str, action, mission_id: str) -> None:
        contract = self.store.load_mission(mission_id)
        ApprovalIntegrityStore(self.store.path).validate(approval_id, action, mission_id, contract)
        expected = self.runtime._action_fingerprint(action, mission_id)
        actual = ApprovalBindingStore(self.store.path).fingerprint(approval_id)
        if actual is None or actual != expected:
            raise PermissionError("L'action ou son contexte a changé depuis l'approbation : liaison d'identité invalide.")

    def _handle_existing_execution(self, key: str, existing: dict[str, Any]) -> ExecutionResult:
        if existing["status"] == "RUNNING":
            recovered = self.store.recover_stale_execution(key)
            if recovered is not None and recovered["status"] == "RECOVERY_REQUIRED":
                self.runtime.audit.record("execution", "RECOVERY", "RECOVERY_REQUIRED", {"execution_key": key, "mission_id": existing["mission_id"], "action_id": existing["action_id"]})
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
        return ExecutionResult(row["execution_key"], row["mission_id"], row["action_id"], row["status"], result=result, error=row.get("error"))
