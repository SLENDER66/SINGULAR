from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .approval_binding import ApprovalBindingStore
from .approval_integrity import ApprovalIntegrityStore
from .autopilot import ApprovalStatus, Autonomy
from .decision_attestation import DecisionAttestationStore
from .durable import DurableStore, MissionStatus
from .effects import EffectProvider, EffectRequest, EffectStatus, ExternalEffectCoordinator
from .execution_capability import execution_capability_matches
from .mission_runtime import DurableMissionRuntime
from .validated_trajectory_decision import ValidatedTrajectoryDecision, payload_fingerprint


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
    """Durable execution boundary; raw actions and unattested decisions are never executable."""

    def __init__(self, runtime: DurableMissionRuntime, execution_lease_seconds: int = 300, effect_coordinator: ExternalEffectCoordinator | None = None, attestation_store: DecisionAttestationStore | None = None) -> None:
        if execution_lease_seconds <= 0:
            raise ValueError("La durée du lease doit être positive.")
        self.runtime = runtime
        self.store: DurableStore = runtime.store
        self.execution_lease_seconds = execution_lease_seconds
        self.effect_coordinator = effect_coordinator
        self.attestation_store = attestation_store or DecisionAttestationStore(self.store.path)
        self.store.init_execution_schema()

    @staticmethod
    def _execution_identity_fingerprint(action: Any, mission_id: str, governed: Any, contract: Any, decision_id: str | None = None, decision_fingerprint: str | None = None) -> str:
        payload = {"mission_id": mission_id, "decision_id": decision_id, "decision_context_fingerprint": decision_fingerprint, "action": {"id": getattr(action, "id", None), "name": getattr(action, "name", None), "payload": getattr(action, "payload", None), "risk": getattr(action, "risk", None), "reversibility": getattr(action, "reversibility", None), "sensitive": getattr(action, "sensitive", None), "capability": getattr(action, "capability", None)}, "governance": {"policy_tier": getattr(governed, "policy_tier", None), "can_prepare": getattr(governed, "can_prepare", None), "can_execute": getattr(governed, "can_execute", None), "requires_human": getattr(governed, "requires_human", None), "reasons": list(getattr(governed, "reasons", ()) or ()), "mode": getattr(getattr(governed, "governor", None), "mode", None), "approval_id": getattr(getattr(governed, "governor", None), "approval_id", None)}, "contract": None if contract is None else str(contract)}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _callable_target(handler: Callable[[Any], Any]) -> str:
        module = getattr(handler, "__module__", None)
        qualname = getattr(handler, "__qualname__", None)
        if module and qualname:
            return f"{module}:{qualname}"
        handler_type = type(handler)
        return f"{handler_type.__module__}:{handler_type.__qualname__}.__call__"

    @staticmethod
    def _provider_target(provider: EffectProvider) -> str:
        provider_type = type(provider)
        return f"{provider_type.__module__}:{provider_type.__qualname__}"

    def _require_attestation(self, decision: ValidatedTrajectoryDecision) -> None:
        if not self.attestation_store.verify(decision):
            raise PermissionError("La décision validée n'est pas durablement attestée, est révoquée ou a expiré.")

    def _bind_execution_identity(self, key: str, action: Any, mission_id: str, governed: Any, decision_id: str | None = None, decision_fingerprint: str | None = None) -> None:
        contract = self.store.load_mission(mission_id)
        fingerprint = self._execution_identity_fingerprint(action, mission_id, governed, contract, decision_id, decision_fingerprint)
        identity_key = self.store.idempotency_key("execution_identity", key)
        self.store.put_idempotent(identity_key, {"execution_key": key, "mission_id": mission_id, "action_id": action.id}, fingerprint=fingerprint)

    def _validate_execution_identity(self, key: str, action: Any, mission_id: str, governed: Any, decision_id: str | None = None, decision_fingerprint: str | None = None) -> None:
        identity_key = self.store.idempotency_key("execution_identity", key)
        expected = self._execution_identity_fingerprint(action, mission_id, governed, self.store.load_mission(mission_id), decision_id, decision_fingerprint)
        actual = self.store.get_idempotency_fingerprint(identity_key)
        if actual is None:
            raise PermissionError("Identité d'exécution absente : exécution/rejeu refusé par sécurité.")
        if actual != expected:
            raise PermissionError("Identité d'exécution réutilisée avec une autorité, une décision ou un contenu différent.")

    def _prepare_execution_identity(self, key: str, action: Any, mission_id: str, governed: Any, decision_id: str | None = None, decision_fingerprint: str | None = None) -> None:
        self._bind_execution_identity(key, action, mission_id, governed, decision_id, decision_fingerprint)

    def execute(self, action, mission_id: str, handler: Callable[[Any], Any]) -> ExecutionResult:
        raise PermissionError("Raw ActionRequest execution is disabled: a ValidatedTrajectoryDecision is required.")

    def execute_validated(self, decision: ValidatedTrajectoryDecision, handler: Callable[[Any], Any]) -> ExecutionResult:
        if not isinstance(decision, ValidatedTrajectoryDecision) or not decision.verify():
            raise PermissionError("Validated trajectory decision is missing or invalid.")
        self._require_attestation(decision)
        if decision.execution_kind != "handler":
            raise PermissionError("Validated decision is bound to an external effect, not a handler.")
        if not decision.execution_target.startswith("cap_") or not execution_capability_matches(decision.execution_target, handler):
            raise PermissionError("Handler capability does not match the exact executable target authorized by the validated decision.")
        mission_id = decision.contract.mission_id
        action = next((item.to_action() for item in decision.authorized_actions if item.id == decision.global_report.action_id), None)
        if action is None:
            raise PermissionError("Validated decision does not authorize an executable action.")
        if action.contract_id != mission_id:
            raise PermissionError("Validated action is not bound to the validated contract.")
        governed = self._authorize(action, mission_id)
        if governed.governor != decision.governor:
            raise PermissionError("Current governance no longer matches the validated decision.")
        if getattr(governed, "policy", None) != decision.policy:
            raise PermissionError("Current policy no longer matches the validated decision.")
        return self._execute_authorized(action, mission_id, handler, governed, decision_id=decision.decision_id, decision_fingerprint=decision.context_fingerprint)

    def _execute_authorized(self, action, mission_id: str, handler: Callable[[Any], Any], governed: Any, *, decision_id: str | None = None, decision_fingerprint: str | None = None) -> ExecutionResult:
        action = governed.action
        key = self.store.idempotency_key("execute", mission_id, action.id)
        existing = self.store.get_execution(key)
        if existing is not None:
            if existing["status"] in {"COMPLETED", "FAILED"}:
                self._validate_execution_identity(key, action, mission_id, governed, decision_id, decision_fingerprint)
            return self._handle_existing_execution(key, existing)
        self._prepare_execution_identity(key, action, mission_id, governed, decision_id, decision_fingerprint)
        claimed = self._claim(action, mission_id, key)
        if not claimed["claimed"]:
            self._validate_execution_identity(key, action, mission_id, governed, decision_id, decision_fingerprint)
            return self._handle_existing_execution(key, claimed)
        try:
            value = handler(action)
        except Exception as exc:
            return self._fail(key, mission_id, action.id, exc)
        return self._complete(key, mission_id, action.id, value)

    def execute_effect(self, action, mission_id: str, provider: EffectProvider, *, provider_name: str, operation: str, payload: Any) -> ExecutionResult:
        raise PermissionError("Raw external-effect execution is disabled: a ValidatedTrajectoryDecision is required.")

    def execute_effect_validated(self, decision: ValidatedTrajectoryDecision, provider: EffectProvider, *, provider_name: str, operation: str, payload: Any) -> ExecutionResult:
        if not isinstance(decision, ValidatedTrajectoryDecision) or not decision.verify():
            raise PermissionError("Validated trajectory decision is missing or invalid.")
        self._require_attestation(decision)
        if decision.execution_kind != "external_effect":
            raise PermissionError("Validated decision is not bound to an external effect.")
        if not decision.execution_target.startswith("cap_") or not execution_capability_matches(decision.execution_target, provider):
            raise PermissionError("Provider capability does not match the exact executable target authorized by the validated decision.")
        if decision.provider_name != provider_name or decision.operation != operation:
            raise PermissionError("Provider or operation does not match the validated decision.")
        if decision.payload_fingerprint != payload_fingerprint(payload):
            raise PermissionError("External-effect payload does not match the validated decision.")
        action = next((item.to_action() for item in decision.authorized_actions if item.id == decision.global_report.action_id), None)
        if action is None:
            raise PermissionError("Validated decision does not authorize an executable action.")
        governed = self._authorize(action, decision.contract.mission_id)
        if governed.governor != decision.governor or getattr(governed, "policy", None) != decision.policy:
            raise PermissionError("Current governance or policy no longer matches the validated decision.")
        return self._execute_effect_authorized(action, decision.contract.mission_id, provider, provider_name=provider_name, operation=operation, payload=payload, governed=governed, decision_id=decision.decision_id, decision_fingerprint=decision.context_fingerprint)

    def _execute_effect_authorized(self, action, mission_id: str, provider: EffectProvider, *, provider_name: str, operation: str, payload: Any, governed: Any, decision_id: str | None = None, decision_fingerprint: str | None = None) -> ExecutionResult:
        if self.effect_coordinator is None:
            raise RuntimeError("Aucun ExternalEffectCoordinator n'est configuré.")
        action = governed.action
        key = self.store.idempotency_key("execute", mission_id, action.id)
        request = EffectRequest(execution_key=key, provider=provider_name, operation=operation, payload=payload, action_fingerprint=self.runtime._action_fingerprint(action, mission_id))
        existing = self.store.get_execution(key)
        if existing is not None:
            self._validate_execution_identity(key, action, mission_id, governed, decision_id, decision_fingerprint)
            try:
                effect = self.effect_coordinator.peek(request)
            except KeyError:
                effect = None
            if effect is not None:
                status = effect["status"]
                if status == EffectStatus.COMPLETED.value:
                    if existing["status"] == "RECOVERY_REQUIRED":
                        return self._result_from_row(self.store.confirm_execution_recovery_from_effect(key, request.provider_idempotency_key))
                    if existing["status"] in {"COMPLETED", "FAILED"}:
                        return self._handle_existing_execution(key, existing)
                    return self._complete(key, mission_id, action.id, effect.get("result"))
                if status == EffectStatus.FAILED.value:
                    if existing["status"] == "RECOVERY_REQUIRED":
                        return self._result_from_row(self.store.resolve_execution_recovery(key, "FAIL", reason=effect.get("error") or "Effet externe échoué."))
                    if existing["status"] in {"COMPLETED", "FAILED"}:
                        return self._handle_existing_execution(key, existing)
                    return self._fail_result(key, mission_id, action.id, effect.get("error") or "Effet externe échoué.")
                if status == EffectStatus.UNKNOWN.value and existing["status"] == "RUNNING":
                    self.store.mark_execution_recovery_required(key)
                    self.runtime.audit.record("execution", "EXTERNAL_EFFECT", "RECOVERY_REQUIRED", {"execution_key": key, "mission_id": mission_id, "action_id": action.id, "provider": provider_name, "operation": operation, "reason": "Effet externe ambigu déjà persisté."})
                    self.runtime._persist_new_audit_events()
                    return ExecutionResult(key, mission_id, action.id, "RECOVERY_REQUIRED", result=effect.get("result"), error=effect.get("error"))
            return self._handle_existing_execution(key, existing)
        self._prepare_execution_identity(key, action, mission_id, governed, decision_id, decision_fingerprint)
        claimed = self._claim(action, mission_id, key)
        if not claimed["claimed"]:
            self._validate_execution_identity(key, action, mission_id, governed, decision_id, decision_fingerprint)
            try:
                effect = self.effect_coordinator.peek(request)
            except KeyError:
                effect = None
            if effect is not None and effect["status"] == EffectStatus.COMPLETED.value:
                if claimed["status"] == "RECOVERY_REQUIRED":
                    return self._result_from_row(self.store.confirm_execution_recovery_from_effect(key, request.provider_idempotency_key))
                if claimed["status"] in {"COMPLETED", "FAILED"}:
                    return self._handle_existing_execution(key, claimed)
                return self._complete(key, mission_id, action.id, effect.get("result"))
            if effect is not None and effect["status"] == EffectStatus.FAILED.value:
                if claimed["status"] == "RECOVERY_REQUIRED":
                    return self._result_from_row(self.store.resolve_execution_recovery(key, "FAIL", reason=effect.get("error") or "Effet externe échoué."))
                if claimed["status"] in {"COMPLETED", "FAILED"}:
                    return self._handle_existing_execution(key, claimed)
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
        raise PermissionError("Raw effect reconciliation is disabled: a ValidatedTrajectoryDecision is required.")

    def reconcile_effect_validated(self, decision: ValidatedTrajectoryDecision, provider: EffectProvider, *, provider_name: str, operation: str, payload: Any) -> ExecutionResult:
        if not isinstance(decision, ValidatedTrajectoryDecision) or not decision.verify():
            raise PermissionError("Validated trajectory decision is missing or invalid.")
        self._require_attestation(decision)
        if decision.execution_kind != "external_effect":
            raise PermissionError("Validated decision is not bound to an external effect.")
        if not decision.execution_target.startswith("cap_") or not execution_capability_matches(decision.execution_target, provider):
            raise PermissionError("Provider capability does not match the exact executable target authorized by the validated decision.")
        if decision.provider_name != provider_name or decision.operation != operation:
            raise PermissionError("Provider or operation does not match the validated decision.")
        if decision.payload_fingerprint != payload_fingerprint(payload):
            raise PermissionError("External-effect payload does not match the validated decision.")
        action = next((item.to_action() for item in decision.authorized_actions if item.id == decision.global_report.action_id), None)
        if action is None:
            raise PermissionError("Validated decision does not authorize an executable action.")
        governed = self._authorize_reconciliation(action, decision.contract.mission_id)
        if governed.governor != decision.governor:
            raise PermissionError("Current governance no longer matches the validated decision.")
        return self._reconcile_effect_authorized(action, decision.contract.mission_id, provider, provider_name=provider_name, operation=operation, payload=payload, governed=governed, decision_id=decision.decision_id, decision_fingerprint=decision.context_fingerprint)

    def _reconcile_effect_authorized(self, action, mission_id: str, provider: EffectProvider, *, provider_name: str, operation: str, payload: Any, governed: Any, decision_id: str | None = None, decision_fingerprint: str | None = None) -> ExecutionResult:
        if self.effect_coordinator is None:
            raise RuntimeError("Aucun ExternalEffectCoordinator n'est configuré.")
        action = governed.action
        key = self.store.idempotency_key("execute", mission_id, action.id)
        existing = self.store.get_execution(key)
        if existing is None or existing["status"] != "RECOVERY_REQUIRED":
            raise ValueError("L'exécution doit être RECOVERY_REQUIRED pour une réconciliation.")
        self._validate_execution_identity(key, action, mission_id, governed, decision_id, decision_fingerprint)
        request = EffectRequest(execution_key=key, provider=provider_name, operation=operation, payload=payload, action_fingerprint=self.runtime._action_fingerprint(action, mission_id))
        outcome = self.effect_coordinator.reconcile(request, provider)
        if outcome.status == EffectStatus.COMPLETED.value:
            effect = self.effect_coordinator.peek(request)
            if effect["status"] != EffectStatus.COMPLETED.value:
                raise RuntimeError("La preuve durable de l'effet externe est absente ou incohérente.")
            return self._result_from_row(self.store.confirm_execution_recovery_from_effect(key, request.provider_idempotency_key))
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
        key = self.store.idempotency_key("execute", mission_id, action.id)
        existing = self.store.get_execution(key)
        if existing is not None and existing["status"] in {"RUNNING", "RECOVERY_REQUIRED", "COMPLETED", "FAILED"}:
            return
        if status == MissionStatus.RUNNING:
            return
        if status not in {MissionStatus.PLANNED, MissionStatus.CREATED}:
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
