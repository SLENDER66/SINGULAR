"""Top-level governed control plane for SINGULAR.

The control plane is intentionally boring at the authority boundary: it exposes
one orchestration surface but delegates authorization to the validated decision
pipeline and durable attestation store. Cognition, execution and learning stay
separate phases.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .continuous_learning import ContinuousLearningCycle, LearningCycleResult
from .decision_attestation import DecisionAttestation, DecisionAttestationStore
from .execution import DurableExecutionEngine, ExecutionResult
from .learning import Forecast
from .mission_runtime import DurableMissionRuntime
from .validated_decision_service import ValidatedDecisionService
from .validated_trajectory_decision import ValidatedTrajectoryDecision


@dataclass(frozen=True)
class ControlPlaneDecision:
    decision: ValidatedTrajectoryDecision
    attestation: DecisionAttestation


class SingularControlPlane:
    """Canonical orchestration surface for decision, execution and learning."""

    def __init__(
        self,
        runtime: DurableMissionRuntime,
        *,
        attestation_store: DecisionAttestationStore | None = None,
        issuer: str = "singular",
        learning_path: str | Path | None = None,
    ) -> None:
        self.runtime = runtime
        self.attestation_store = attestation_store or DecisionAttestationStore(runtime.store.path)
        self.executor = DurableExecutionEngine(runtime, attestation_store=self.attestation_store)
        self.decisions = ValidatedDecisionService(
            self.executor,
            attestation_store=self.attestation_store,
            issuer=issuer,
        )
        self.learning = ContinuousLearningCycle(
            learning_path or runtime.store.path,
            attestation_store=self.attestation_store,
        )

    def construct_and_attest(self, **kwargs: Any) -> ControlPlaneDecision:
        """Construct every deterministic safety layer before durable issuance."""
        decision, attestation = self.decisions.build_and_attest(**kwargs)
        self.runtime.store.save_mission(decision.contract)
        return ControlPlaneDecision(decision, attestation)

    def execute(
        self,
        control_decision: ControlPlaneDecision,
        action_id: str,
        handler: Callable[[Any], Any],
    ) -> ExecutionResult:
        if not isinstance(control_decision, ControlPlaneDecision):
            raise TypeError("control plane execution requires a ControlPlaneDecision")
        return self.decisions.execute(control_decision.decision, action_id, handler)

    def execute_effect(
        self,
        control_decision: ControlPlaneDecision,
        action_id: str,
        provider: Any,
        *,
        provider_name: str,
        operation: str,
        payload: Any,
    ) -> ExecutionResult:
        if not isinstance(control_decision, ControlPlaneDecision):
            raise TypeError("control plane execution requires a ControlPlaneDecision")
        return self.decisions.execute_effect(
            control_decision.decision,
            action_id,
            provider,
            provider_name=provider_name,
            operation=operation,
            payload=payload,
        )

    def observe_outcome(
        self,
        control_decision: ControlPlaneDecision,
        *,
        forecast: Forecast,
        actual: bool | float,
        execution_key: str,
        execution_status: str,
        repeated_pattern: bool = False,
        observed_at: str | None = None,
    ) -> LearningCycleResult:
        if not isinstance(control_decision, ControlPlaneDecision):
            raise TypeError("outcome observation requires a ControlPlaneDecision")
        return self.learning.observe(
            decision=control_decision.decision,
            forecast=forecast,
            actual=actual,
            execution_key=execution_key,
            execution_status=execution_status,
            repeated_pattern=repeated_pattern,
            observed_at=observed_at,
        )

    def revoke(self, control_decision: ControlPlaneDecision) -> DecisionAttestation:
        if not isinstance(control_decision, ControlPlaneDecision):
            raise TypeError("revocation requires a ControlPlaneDecision")
        return self.decisions.revoke(control_decision.decision.decision_id)


__all__ = ["ControlPlaneDecision", "SingularControlPlane"]
