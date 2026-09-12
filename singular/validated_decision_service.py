"""High-level lifecycle facade for attested validated decisions.

This is the recommended integration surface for production callers. It combines
construction, durable attestation, optional revocation and strict execution so
callers do not have to manually sequence security-critical primitives.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .decision_attestation import DecisionAttestation, DecisionAttestationStore, ValidatedDecisionIssuer
from .effects import EffectProvider
from .execution import DurableExecutionEngine, ExecutionResult
from .validated_execution import ValidatedExecutionBoundary
from .validated_trajectory_decision import ValidatedTrajectoryDecision
from .validated_pipeline import ValidatedTrajectoryPipeline


class ValidatedDecisionService:
    """Single lifecycle surface: build -> attest -> execute/revoke."""

    def __init__(
        self,
        executor: DurableExecutionEngine,
        *,
        attestation_store: DecisionAttestationStore | None = None,
        issuer: str = "singular",
    ) -> None:
        if not issuer.strip():
            raise ValueError("issuer is required")
        self.executor = executor
        self.attestation_store = attestation_store or executor.attestation_store
        self.issuer = ValidatedDecisionIssuer(self.attestation_store, issuer=issuer)
        self.boundary = ValidatedExecutionBoundary(executor, self.attestation_store)

    def build(self, **kwargs: Any) -> ValidatedTrajectoryDecision:
        """Build the cryptographically self-consistent decision without issuing it."""
        return ValidatedTrajectoryPipeline.build(**kwargs)

    def build_and_attest(self, **kwargs: Any) -> tuple[ValidatedTrajectoryDecision, DecisionAttestation]:
        """Build and durably issue one executable decision as an atomic lifecycle step."""
        decision = self.build(**kwargs)
        return decision, self.issuer.issue(decision)

    def is_attested(self, decision: ValidatedTrajectoryDecision) -> bool:
        return self.attestation_store.verify(decision)

    def revoke(self, decision_id: str) -> DecisionAttestation:
        return self.attestation_store.revoke(decision_id)

    def execute(
        self,
        decision: ValidatedTrajectoryDecision,
        action_id: str,
        handler: Callable[[Any], Any],
    ) -> ExecutionResult:
        return self.boundary.execute(decision, action_id, handler)

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
        return self.boundary.execute_effect(
            decision,
            action_id,
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
        return self.boundary.reconcile_effect(
            decision,
            action_id,
            provider,
            provider_name=provider_name,
            operation=operation,
            payload=payload,
        )


__all__ = ["ValidatedDecisionService"]
