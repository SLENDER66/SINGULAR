"""Strict execution adapter for validated trajectory decisions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .autopilot import ActionRequest
from .decision_attestation import DecisionAttestationStore
from .effects import EffectProvider
from .execution import DurableExecutionEngine, ExecutionResult
from .validated_trajectory_decision import ValidatedActionRequest, ValidatedTrajectoryDecision


class ValidatedExecutionBoundary:
    """Fail-closed adapter from validated decisions to durable execution."""

    def __init__(self, executor: DurableExecutionEngine, attestation_store: DecisionAttestationStore | None = None) -> None:
        self.executor = executor
        if attestation_store is not None:
            self.attestation_store = attestation_store
        else:
            store = getattr(executor, "store", None)
            if store is None or not hasattr(store, "path"):
                raise TypeError("an explicit DecisionAttestationStore is required for this executor")
            self.attestation_store = DecisionAttestationStore(store.path)

    def _validate_common(self, decision: ValidatedTrajectoryDecision) -> None:
        if not isinstance(decision, ValidatedTrajectoryDecision):
            raise TypeError("l'exécution exige une ValidatedTrajectoryDecision")
        if not decision.verify():
            raise PermissionError("La décision validée est invalide ou a été altérée.")
        if not self.attestation_store.verify(decision):
            raise PermissionError("La décision validée n'est pas durablement attestée, est révoquée ou a expiré.")
        if decision.global_report.decision != "PROCEED":
            raise PermissionError("Seule une décision globale PROCEED peut être exécutée.")

    @staticmethod
    def _action(decision: ValidatedTrajectoryDecision, action_id: str) -> ValidatedActionRequest:
        matches = [action for action in decision.authorized_actions if action.id == action_id]
        if len(matches) != 1:
            raise PermissionError("L'action demandée n'est pas une action autorisée unique.")
        action = matches[0]
        mapping = dict(decision.action_to_intervention)
        if action.id not in mapping:
            raise PermissionError("L'action demandée n'est pas reliée au portefeuille validé.")
        selected = {candidate.intervention_id for candidate in decision.trajectory_portfolio.candidates}
        if mapping[action.id] not in selected:
            raise PermissionError("L'action demandée n'appartient pas au portefeuille validé.")
        if decision.global_report.action_id != action.id:
            raise PermissionError("L'action demandée ne correspond pas à l'action globale autorisée.")
        if decision.governor.action_id != action.id:
            raise PermissionError("L'action demandée ne correspond pas au gouverneur validé.")
        return action

    @staticmethod
    def _materialize_action(action: ValidatedActionRequest) -> ActionRequest:
        return ActionRequest(name=action.name, description=action.description, impact=action.impact, risk=action.risk,
                             reversibility=action.reversibility, requires_human=action.requires_human,
                             sensitive=action.sensitive, contract_id=action.contract_id, id=action.id, capability=action.capability)

    def _validated_action(self, decision: ValidatedTrajectoryDecision, action_id: str) -> ActionRequest:
        self._validate_common(decision)
        action = self._materialize_action(self._action(decision, action_id))
        if action.contract_id != decision.contract.mission_id:
            raise PermissionError("L'action et le contrat de décision ne sont pas liés.")
        return action

    def execute(self, decision: ValidatedTrajectoryDecision, action_id: str, handler: Callable[[ActionRequest], Any]) -> ExecutionResult:
        action = self._validated_action(decision, action_id)
        if decision.execution_kind != "handler":
            raise PermissionError("La décision validée n'autorise pas un handler.")
        return self.executor.execute_validated(decision, handler)

    def execute_effect(
        self,
        decision: ValidatedTrajectoryDecision,
        action_id: str,
        provider: EffectProvider,
        *,
        provider_name: str,
        operation: str,
        payload: Any,
    ) -> ExecutionResult:
        """Execute an externally visible effect only through a validated decision."""
        self._validated_action(decision, action_id)
        if decision.execution_kind != "external_effect":
            raise PermissionError("La décision validée n'autorise pas un effet externe.")
        if decision.provider_name != provider_name or decision.operation != operation:
            raise PermissionError("Le fournisseur ou l'opération ne correspondent pas à la décision validée.")
        return self.executor.execute_effect_validated(
            decision,
            provider,
            provider_name=provider_name,
            operation=operation,
            payload=payload,
        )

    def reconcile_effect(
        self,
        decision: ValidatedTrajectoryDecision,
        action_id: str,
        provider: EffectProvider,
        *,
        provider_name: str,
        operation: str,
        payload: Any,
    ) -> ExecutionResult:
        """Reconcile an ambiguous external effect under the same validated authority."""
        self._validated_action(decision, action_id)
        if decision.execution_kind != "external_effect":
            raise PermissionError("La décision validée n'autorise pas la réconciliation d'un effet externe.")
        if decision.provider_name != provider_name or decision.operation != operation:
            raise PermissionError("Le fournisseur ou l'opération ne correspondent pas à la décision validée.")
        return self.executor.reconcile_effect_validated(
            decision,
            provider,
            provider_name=provider_name,
            operation=operation,
            payload=payload,
        )


__all__ = ["ValidatedExecutionBoundary"]
