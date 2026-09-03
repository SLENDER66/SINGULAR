"""Strict execution adapter for validated trajectory decisions.

This module provides the only supported adapter from a validated trajectory
artifact to the existing durable executor.  It performs integrity and identity
checks before delegating to the durable transaction boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .autopilot import ActionRequest
from .execution import DurableExecutionEngine, ExecutionResult
from .validated_trajectory_decision import ValidatedActionRequest, ValidatedTrajectoryDecision


class ValidatedExecutionBoundary:
    """Fail-closed adapter from validated decisions to durable execution."""

    def __init__(self, executor: DurableExecutionEngine) -> None:
        self.executor = executor

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
        return action

    @staticmethod
    def _materialize_action(action: ValidatedActionRequest) -> ActionRequest:
        return ActionRequest(
            name=action.name,
            description=action.description,
            impact=action.impact,
            risk=action.risk,
            reversibility=action.reversibility,
            requires_human=action.requires_human,
            sensitive=action.sensitive,
            contract_id=action.contract_id,
            id=action.id,
            capability=action.capability,
        )

    def execute(
        self,
        decision: ValidatedTrajectoryDecision,
        action_id: str,
        handler: Callable[[ActionRequest], Any],
    ) -> ExecutionResult:
        if not isinstance(decision, ValidatedTrajectoryDecision):
            raise TypeError("l'exécution exige une ValidatedTrajectoryDecision")
        if not decision.verify():
            raise PermissionError("La décision validée est invalide ou a été altérée.")
        if decision.global_report.decision != "PROCEED":
            raise PermissionError("Seule une décision globale PROCEED peut être exécutée.")
        action = self._materialize_action(self._action(decision, action_id))
        if action.contract_id != decision.contract.mission_id:
            raise PermissionError("L'action et le contrat de décision ne sont pas liés.")
        if decision.global_report.action_id != action.id:
            raise PermissionError("L'action demandée ne correspond pas à l'action globale autorisée.")
        if decision.governor.action_id != action.id:
            raise PermissionError("L'action demandée ne correspond pas au gouverneur validé.")
        return self.executor.execute(action, decision.contract.mission_id, handler)


__all__ = ["ValidatedExecutionBoundary"]
