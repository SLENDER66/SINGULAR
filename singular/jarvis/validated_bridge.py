"""Bridge JARVIS proposals into SINGULAR's existing validated lifecycle.

This module deliberately contains no new authority. JARVIS supplies a proposal;
SINGULAR creates the mission, performs trajectory/governance validation, binds the
registered execution capability and durably attests the resulting decision.
"""
from __future__ import annotations

from typing import Any

from ..autopilot import ActionRequest
from ..mission_runtime import DurableMissionRuntime
from .runtime import MissionProposal


class JarvisValidatedBridge:
    """Translate exactly one proposal action into SINGULAR's validated pipeline.

    The validated decision service is dependency-injected rather than imported
    here. SINGULAR's boundary audit intentionally forbids orchestration modules
    from importing execution-causing modules; this bridge therefore depends only
    on the injected service's public ``build_and_attest`` contract.
    """

    def __init__(self, mission_runtime: DurableMissionRuntime, decision_service: Any) -> None:
        self.missions = mission_runtime
        self.decisions = decision_service

    def build_and_attest(
        self,
        proposal: MissionProposal,
        *,
        execution_target: str,
        intervention_id: str,
        domain_states: tuple[Any, ...],
        interventions: tuple[Any, ...],
        trajectory_profile: Any,
        trajectory_dimensions: dict[str, float],
        capacity_budget: float,
        decision_id: str,
        action_index: int = 0,
        **kwargs: Any,
    ) -> Any:
        """Build and attest without granting JARVIS execution authority.

        The execution target must already be an opaque registered capability.
        The bridge never registers capabilities, changes policy, approves an
        action, or calls an execution handler.
        """
        if not 0 <= action_index < len(proposal.actions):
            raise IndexError("action_index out of range")
        if not execution_target.startswith("cap_"):
            raise ValueError("execution_target must be an opaque capability id")
        if not intervention_id.strip():
            raise ValueError("intervention_id is required")
        if not decision_id.strip():
            raise ValueError("decision_id is required")

        selected = proposal.actions[action_index]
        contract = self.missions.create_mission(
            proposal.objective,
            proposal.expected_result,
        )
        action = ActionRequest(
            name=selected.name,
            description=selected.description,
            impact=selected.impact,
            risk=selected.risk,
            reversibility=selected.reversibility,
            requires_human=selected.requires_human,
            sensitive=selected.sensitive,
            contract_id=contract.mission_id,
            capability=selected.capability,
            execution_capability=execution_target,
        )
        return self.decisions.build_and_attest(
            objective=contract.objective,
            actions=(action,),
            action_to_intervention=((action.id, intervention_id),),
            domain_states=domain_states,
            interventions=interventions,
            trajectory_profile=trajectory_profile,
            trajectory_dimensions=trajectory_dimensions,
            contract=contract,
            execution_target=execution_target,
            decision_id=decision_id,
            capacity_budget=capacity_budget,
            **kwargs,
        )


__all__ = ["JarvisValidatedBridge"]
