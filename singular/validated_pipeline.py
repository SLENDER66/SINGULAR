"""Mandatory construction pipeline for executable trajectory decisions."""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
from time import time
from typing import Any

from .autopilot import ActionRequest, DelegationContract, Governor
from .global_control import GlobalDecisionGate, GlobalDecisionReport
from .human_optimization import DomainInteraction, DomainState, HumanOptimizationEngine, Intervention
from .security import ActionPolicy
from .state import CapacitySnapshot
from .trajectory import TrajectoryEngine, TrajectoryProfile
from .trajectory_optimization import TrajectoryInteraction, TrajectoryOptimizationEngine
from .validated_trajectory_decision import ValidatedTrajectoryDecision, payload_fingerprint
from .values import ValueAssessmentResult


class ValidatedTrajectoryPipeline:
    """Build the only artifact accepted by the strict execution boundary."""

    @staticmethod
    def build(
        *, objective: str, actions: tuple[ActionRequest, ...], action_to_intervention: tuple[tuple[str, str], ...],
        domain_states: Sequence[DomainState], interventions: Sequence[Intervention], trajectory_profile: TrajectoryProfile,
        trajectory_dimensions: dict[str, float], contract: DelegationContract, execution_target: str,
        execution_kind: str = "handler", provider_name: str | None = None, provider_target: str | None = None,
        operation: str | None = None, execution_payload: Any = None, human_interactions: tuple[DomainInteraction, ...] = (),
        trajectory_interactions: tuple[TrajectoryInteraction, ...] = (), value_results: tuple[ValueAssessmentResult, ...] = (),
        capacity: CapacitySnapshot | None = None, effort: float | None = None, risks: list[Any] | None = None,
        shared_signals: tuple[Any, ...] = (), calibration: dict[str, float] | None = None,
        gate: GlobalDecisionGate | None = None, capacity_budget: float | None = None, max_portfolio_candidates: int = 5,
        decision_id: str = "", issued_at: float | None = None, expires_at: float | None = None,
        decision_ttl_seconds: float = 300.0,
    ) -> ValidatedTrajectoryDecision:
        if not objective.strip():
            raise ValueError("objective cannot be empty")
        if len(actions) != 1:
            raise ValueError("the executable validated pipeline currently authorizes exactly one action")
        if not decision_id.strip():
            raise ValueError("decision_id is required")
        if contract.objective != objective:
            raise ValueError("objective must match the execution contract")
        if execution_kind not in {"handler", "external_effect"}:
            raise ValueError("execution_kind must be handler or external_effect")
        if not execution_target.startswith("cap_"):
            raise ValueError("executable validation requires an opaque execution capability id")
        if not isfinite(decision_ttl_seconds) or decision_ttl_seconds <= 0:
            raise ValueError("decision_ttl_seconds must be finite and positive")
        now = time()
        if issued_at is None and expires_at is None:
            issued_at = now
            expires_at = now + decision_ttl_seconds
        elif issued_at is None or expires_at is None:
            raise ValueError("issued_at and expires_at must be supplied together")
        if not isfinite(issued_at) or not isfinite(expires_at) or expires_at <= issued_at:
            raise ValueError("decision validity interval is invalid")
        if issued_at > now:
            raise ValueError("issued_at cannot be in the future")
        if expires_at <= now:
            raise ValueError("expires_at must be in the future")
        if capacity_budget is None or not isfinite(capacity_budget) or capacity_budget < 0:
            raise ValueError("a finite non-negative capacity_budget is required for executable validation")
        if max_portfolio_candidates < 1:
            raise ValueError("max_portfolio_candidates must be positive")

        intervention_map = {item.id: item for item in interventions}
        if len(intervention_map) != len(interventions):
            raise ValueError("intervention ids must be unique")

        human = HumanOptimizationEngine.optimize(tuple(domain_states), tuple(interventions), human_interactions, capacity_budget=capacity_budget)
        portfolio = TrajectoryOptimizationEngine.optimize(
            human.candidates, intervention_map, trajectory_interactions,
            capacity_budget=capacity_budget, max_candidates=max_portfolio_candidates,
        )
        if not portfolio.candidates:
            raise PermissionError("No executable trajectory portfolio was produced.")

        assessment = TrajectoryEngine.assess(
            trajectory_profile, dimensions=trajectory_dimensions, value_results=value_results,
            capacity=capacity, portfolio=portfolio,
        )
        action = actions[0]
        global_report: GlobalDecisionReport = (gate or GlobalDecisionGate()).evaluate(
            objective, action, values=list(value_results), capacity=capacity, effort=effort, risks=risks,
            mission_id=contract.mission_id, contract=contract, shared_signals=shared_signals,
            calibration=calibration, trajectory_profile=trajectory_profile,
            trajectory_dimensions=trajectory_dimensions, trajectory_portfolio=portfolio,
            human_optimization=human,
        )

        if global_report.trajectory != assessment:
            raise PermissionError("Global decision gate trajectory does not match the freshly assessed trajectory.")
        if global_report.human_optimization != human:
            raise PermissionError("Global decision gate human optimization does not match the freshly optimized state.")
        if global_report.decision != "PROCEED":
            raise PermissionError(f"Global decision gate refused execution: {global_report.decision}.")
        if assessment.human_review:
            raise PermissionError("Trajectory requires human review.")

        mapping = dict(action_to_intervention)
        if len(mapping) != len(action_to_intervention) or set(mapping) != {action.id}:
            raise ValueError("the executable action must have exactly one intervention mapping")
        selected_ids = {candidate.intervention_id for candidate in portfolio.candidates}
        if mapping[action.id] not in selected_ids:
            raise PermissionError("The authorized action is outside the selected trajectory portfolio.")

        if execution_kind == "handler":
            if any(value is not None for value in (provider_name, provider_target, operation, execution_payload)):
                raise ValueError("handler execution cannot carry external-effect binding fields")
            payload_hash = None
        else:
            if not provider_name or not provider_target or not operation:
                raise ValueError("external-effect execution requires provider binding")
            payload_hash = payload_fingerprint(execution_payload)

        return ValidatedTrajectoryDecision.create(
            decision_id=decision_id, issued_at=issued_at, expires_at=expires_at, actions=actions,
            action_to_intervention=action_to_intervention, domain_states=tuple(domain_states), interventions=tuple(interventions),
            human_interactions=human_interactions, trajectory_interactions=trajectory_interactions,
            portfolio_capacity_budget=capacity_budget, portfolio_max_candidates=max_portfolio_candidates,
            human_optimization=human, trajectory_portfolio=portfolio, trajectory_assessment=assessment,
            global_report=global_report, contract=contract, policy=ActionPolicy.evaluate(action),
            red_team_findings=global_report.red_team_findings, governor=Governor.evaluate(action, contract),
            execution_target=execution_target, execution_kind=execution_kind, provider_name=provider_name,
            provider_target=provider_target, operation=operation, payload_fingerprint=payload_hash,
        )


__all__ = ["ValidatedTrajectoryPipeline"]
