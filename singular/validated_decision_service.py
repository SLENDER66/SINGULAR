"""High-level lifecycle facade for attested validated decisions.

This is the recommended integration surface for production callers. It combines
construction, durable attestation, optional revocation and strict execution so
callers do not have to manually sequence security-critical primitives.
"""
from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
import json
from typing import Any

from .decision_attestation import DecisionAttestation, DecisionAttestationStore, ValidatedDecisionIssuer
from .effects import EffectProvider
from .execution import DurableExecutionEngine, ExecutionResult
from .validated_execution import ValidatedExecutionBoundary
from .validated_pipeline import ValidatedTrajectoryPipeline
from .validated_trajectory_decision import ValidatedTrajectoryDecision


class VerificationFailed(PermissionError):
    """Raised when an independently supplied execution verifier rejects a result."""


def _result_fingerprint(result: Any) -> str:
    """Hash only the result representation used for audit correlation; never persist its payload."""
    if hasattr(result, "__dataclass_fields__"):
        from dataclasses import asdict

        material: Any = asdict(result)
    elif isinstance(result, dict):
        material = result
    else:
        material = repr(result)
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return sha256(encoded).hexdigest()


class ValidatedDecisionService:
    """Single lifecycle surface: build -> attest -> execute/revoke/verify."""

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
        result = self.execute(decision, action_id, handler)
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
            "execution_key": result.key,
            "result_fingerprint": _result_fingerprint(result),
        }
        if reason is not None:
            payload["reason"] = reason
        self.executor.runtime.audit.record("verification", "EXECUTION_RESULT", outcome, payload)
        self.executor.runtime._persist_new_audit_events()

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


__all__ = ["ValidatedDecisionService", "VerificationFailed"]