from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any

from .autopilot import Autonomy, GovernorDecision
from .decision_engine import DecisionRecommendation, DecisionStatus


class ExecutionStatus(str, Enum):
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    AUTHORIZED = "AUTHORIZED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ExecutionIntent:
    """A deterministic execution request; it does not perform side effects."""

    decision_id: str
    action_id: str
    idempotency_key: str
    authorization_id: str | None = None


@dataclass(frozen=True)
class ExecutionResult:
    """Immutable observation of an execution attempt."""

    decision_id: str
    action_id: str
    idempotency_key: str
    status: ExecutionStatus
    success: bool
    observed_value: float | bool | None = None
    error: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.decision_id.strip() or not self.action_id.strip():
            raise ValueError("decision_id and action_id are required")
        if not self.idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        if self.status == ExecutionStatus.SUCCEEDED and not self.success:
            raise ValueError("SUCCEEDED requires success=True")
        if self.status in (ExecutionStatus.FAILED, ExecutionStatus.REJECTED) and self.success:
            raise ValueError("FAILED/REJECTED require success=False")
        if self.status == ExecutionStatus.FAILED and not self.error:
            raise ValueError("FAILED requires an error")
        if tuple(sorted(self.metadata)) != self.metadata:
            raise ValueError("metadata must be deterministically sorted")


class ExecutionResultBridge:
    """Fail-closed boundary between recommendation, authorization and results.

    The idempotency ledger is deliberately process-local for now. Durable,
    transactional authorization/result storage belongs to the later audit-ledger
    layer; this class never claims durability it does not have.
    """

    def __init__(self) -> None:
        self._results: dict[str, ExecutionResult] = {}

    @staticmethod
    def _action_id(recommendation: DecisionRecommendation) -> str:
        if recommendation.selected_option_id is None:
            raise ValueError("recommendation has no selected action")
        return recommendation.selected_option_id

    def prepare(
        self,
        recommendation: DecisionRecommendation,
        *,
        idempotency_key: str,
    ) -> ExecutionIntent:
        if recommendation.status is not DecisionStatus.PROPOSED:
            raise PermissionError("Only a PROPOSED recommendation can be prepared")
        if recommendation.requires_human:
            raise PermissionError("Human review is required before preparation")
        if recommendation.selected_option_id is None:
            raise ValueError("Cannot prepare a recommendation without a selected option")
        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        return ExecutionIntent(
            recommendation.decision_id,
            recommendation.selected_option_id,
            idempotency_key,
        )

    @staticmethod
    def authorize(
        intent: ExecutionIntent,
        governor_decision: GovernorDecision,
    ) -> ExecutionIntent:
        if governor_decision.action_id != intent.action_id:
            raise PermissionError("Authorization does not match the requested action")
        if governor_decision.mode not in (
            Autonomy.EXECUTE_REVERSIBLE,
            Autonomy.EXECUTE_AUTHORIZED,
        ):
            raise PermissionError("Governor did not authorize execution")
        if governor_decision.mode is Autonomy.EXECUTE_AUTHORIZED and not governor_decision.approval_id:
            raise PermissionError("Authorized execution requires an approval reference")
        return ExecutionIntent(
            intent.decision_id,
            intent.action_id,
            intent.idempotency_key,
            governor_decision.approval_id,
        )

    def record(
        self,
        intent: ExecutionIntent,
        *,
        status: ExecutionStatus,
        success: bool,
        observed_value: float | bool | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        existing = self._results.get(intent.idempotency_key)
        if existing is not None:
            if self._fingerprint(existing) != self._fingerprint_values(
                intent, status, success, observed_value, error, metadata
            ):
                raise RuntimeError("Idempotency key was already used for a different result")
            return existing

        normalized = tuple(
            (str(key), self._stable_value(value))
            for key, value in sorted((metadata or {}).items(), key=lambda item: str(item[0]))
        )
        result = ExecutionResult(
            intent.decision_id,
            intent.action_id,
            intent.idempotency_key,
            status,
            success,
            observed_value,
            error,
            normalized,
        )
        self._results[intent.idempotency_key] = result
        return result

    def results(self) -> tuple[ExecutionResult, ...]:
        return tuple(self._results[key] for key in sorted(self._results))

    @staticmethod
    def _stable_value(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)

    @classmethod
    def _fingerprint(cls, result: ExecutionResult) -> str:
        payload = {
            "decision_id": result.decision_id,
            "action_id": result.action_id,
            "idempotency_key": result.idempotency_key,
            "status": result.status.value,
            "success": result.success,
            "observed_value": result.observed_value,
            "error": result.error,
            "metadata": result.metadata,
        }
        return sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    @classmethod
    def _fingerprint_values(
        cls,
        intent: ExecutionIntent,
        status: ExecutionStatus,
        success: bool,
        observed_value: float | bool | None,
        error: str | None,
        metadata: dict[str, Any] | None,
    ) -> str:
        normalized = tuple(
            (str(key), cls._stable_value(value))
            for key, value in sorted((metadata or {}).items(), key=lambda item: str(item[0]))
        )
        return cls._fingerprint(
            ExecutionResult(
                intent.decision_id,
                intent.action_id,
                intent.idempotency_key,
                status,
                success,
                observed_value,
                error,
                normalized,
            )
        )
