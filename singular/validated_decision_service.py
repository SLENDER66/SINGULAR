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


def default_execution_result_verifier(action: Any, result: ExecutionResult) -> bool:
    """Trusted structural verifier used by the canonical control-plane composition.

    It deliberately does not inspect or execute handler code and does not trust a
    caller-supplied verifier. Domain-specific verification can be composed above
    this boundary by trusted application code, but JARVIS/LLM request data cannot
    select or replace this dependency.
    """
    return (
        result.status == "COMPLETED"
        and result.mission_id == action.contract_id
        and result.action_id == action.id
        and result.error is None
    )


class ValidatedDecisionService:
    """Canonical façade for validated decision construction and execution lifecycle.

    The verifier is a trusted-composition dependency, not a per-request input.
    JARVIS/LLM callers receive no API by which they can select or replace the
    verifier for an execution. A caller that needs multiple verification rules
    must compose one trusted dispatcher at construction time.
    """

    def __init__(
        self,
        executor: DurableExecutionEngine,
        *,
        attestation_store: DecisionAttestationStore | None = None,
        issuer: str = "singular",
        verifier: Callable[[Any, Any], bool] | None = None,
    ) -> None:
        if verifier is None or not callable(verifier):
            raise TypeError("a trusted verifier must be supplied at service composition time")
        self.executor = executor
        self.attestation_store = attestation_store or DecisionAttestationStore(executor.runtime.store.path)
        self.issuer = issuer
        self._verifier = verifier
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
    ) -> ExecutionResult:
        """Execute and require the service's trusted verifier before accepting the result."""
        result = self.boundary.execute(decision, action_id, handler)
        action = next((item.to_action() for item in decision.authorized_actions if item.id == action_id), None)
        if action is None:
            raise PermissionError("Validated decision does not authorize the requested action.")
        if result.status != "COMPLETED":
            self._record_verification(decision, action_id, result, "FAILED", "execution_not_completed")
            raise VerificationFailed("Independent execution-result verification failed.")
        try:
            verified = bool(self._verifier(action, result))
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


__all__ = ["ValidatedDecisionService", "VerificationFailed", "default_execution_result_verifier"]
