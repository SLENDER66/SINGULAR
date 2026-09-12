from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from .decision_attestation import DecisionAttestation, DecisionAttestationStore
from .execution import DurableExecutionEngine, ExecutionResult
from .validated_execution import ValidatedExecutionBoundary
from .validated_pipeline import ValidatedTrajectoryPipeline
from .validated_trajectory_decision import ValidatedTrajectoryDecision


class VerificationFailed(PermissionError):
    """Raised when an independently verified execution result is not acceptable."""


def _result_fingerprint(result: ExecutionResult) -> str:
    """Hash stable execution-result metadata without persisting the result payload."""
    material = repr(
        (
            result.execution_key,
            result.status,
            result.action_id,
            result.error,
        )
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


class ValidatedDecisionService:
    """Canonical façade for validated decision construction and execution lifecycle."""

    def __init__(
        self,
        executor: DurableExecutionEngine,
        *,
        attestation_store: DecisionAttestationStore | None = None,
        issuer: str = "singular",
    ) -> None:
        self.executor = executor
        self.attestation_store = attestation_store or DecisionAttestationStore(executor.runtime.store.path)
        self.issuer = issuer
        self.boundary = ValidatedExecutionBoundary(
            executor,
            attestation_store=self.attestation_store,
        )

    def build(self, **kwargs: Any) -> ValidatedTrajectoryDecision:
        return ValidatedTrajectoryPipeline.build(**kwargs)

    def build_and_attest(self, **kwargs: Any) -> tuple[ValidatedTrajectoryDecision, DecisionAttestation]:
        decision = self.build(**kwargs)
        attestation = self.attestation_store.issue(decision, issuer=self.issuer)
        return decision, attestation

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
        provider: Any,
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

    def reconcile_effect(self, *args: Any, **kwargs: Any) -> ExecutionResult:
        return self.boundary.reconcile_effect(*args, **kwargs)

    def execute_verified(
        self,
        decision: ValidatedTrajectoryDecision,
        action_id: str,
        handler: Callable[[Any], Any],
        verifier: Callable[[Any, Any], bool],
    ) -> ExecutionResult:
        """Execute and require an independent verifier before declaring the lifecycle verified."""
        if not callable(verifier):
            raise TypeError("verifier must be callable")
        result = self.boundary.execute(decision, action_id, handler)
        action = next((item.to_action() for item in decision.authorized_actions if item.id == action_id), None)
        if action is None:
            raise PermissionError("Validated decision does not authorize the requested action.")
        if result.status != "COMPLETED":
            self._record_verification(decision, action_id, result, "FAILED", "execution_not_completed")
            raise VerificationFailed("Independent execution-result verification failed.")
        try:
            verified = bool(verifier(action, result))
        except Exception as exc:
            self._record_verification(decision, action_id, result, "FAILED", type(exc).__name__)
            raise VerificationFailed("Independent execution-result verification failed.") from None
        outcome = "VERIFIED" if verified else "FAILED"
        self._record_verification(decision, action_id, result, outcome)
        if not verified:
            raise VerificationFailed("Independent execution-result verification failed.")
        return result

    def _record_verification(
        self,
        decision: ValidatedTrajectoryDecision,
        action_id: str,
        result: ExecutionResult,
        outcome: str,
        reason: str | None = None,
    ) -> None:
        payload = {
            "decision_id": decision.decision_id,
            "decision_fingerprint": decision.context_fingerprint,
            "action_id": action_id,
            "execution_key": result.execution_key,
            "result_fingerprint": _result_fingerprint(result),
        }
        if reason is not None:
            payload["reason"] = reason
        self.executor.runtime.audit.record("verification", "EXECUTION_RESULT", outcome, payload)
        self.executor.runtime._persist_new_audit_events()
