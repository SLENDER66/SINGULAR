from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from .durable import DurableStore
from .execution_result import ExecutionIntent, ExecutionResult, ExecutionStatus


class DurableExecutionLedger:
    """Process-independent result ledger backed by ``DurableStore``.

    The ledger persists the terminal execution result under its idempotency key.
    Reusing a key with different execution content fails closed rather than
    silently replacing the first result.
    """

    def __init__(self, store: DurableStore) -> None:
        self.store = store

    def record(self, result: ExecutionResult) -> ExecutionResult:
        payload = self._serialize(result)
        persisted = self.store.put_idempotent(
            result.idempotency_key,
            payload,
            fingerprint=self._fingerprint(payload),
        )
        return self._deserialize(persisted)

    def record_intent(
        self,
        intent: ExecutionIntent,
        *,
        status: ExecutionStatus,
        success: bool,
        observed_value: float | bool | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        normalized = tuple(
            (str(key), json.dumps(value, sort_keys=True, separators=(",", ":"), default=str))
            for key, value in sorted((metadata or {}).items(), key=lambda item: str(item[0]))
        )
        return self.record(
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

    def get(self, idempotency_key: str) -> ExecutionResult | None:
        payload = self.store.get_idempotent(idempotency_key)
        if payload is None:
            return None
        fingerprint = self.store.get_idempotency_fingerprint(idempotency_key)
        if fingerprint != self._fingerprint(payload):
            raise RuntimeError("Persisted execution result failed integrity verification")
        return self._deserialize(payload)

    @staticmethod
    def _serialize(result: ExecutionResult) -> dict[str, Any]:
        return {
            "decision_id": result.decision_id,
            "action_id": result.action_id,
            "idempotency_key": result.idempotency_key,
            "status": result.status.value,
            "success": result.success,
            "observed_value": result.observed_value,
            "error": result.error,
            "metadata": [[key, value] for key, value in result.metadata],
        }

    @staticmethod
    def _deserialize(payload: dict[str, Any]) -> ExecutionResult:
        metadata = tuple((str(key), str(value)) for key, value in payload.get("metadata", []))
        return ExecutionResult(
            str(payload["decision_id"]),
            str(payload["action_id"]),
            str(payload["idempotency_key"]),
            ExecutionStatus(str(payload["status"])),
            bool(payload["success"]),
            payload.get("observed_value"),
            payload.get("error"),
            metadata,
        )

    @staticmethod
    def _fingerprint(payload: dict[str, Any]) -> str:
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return sha256(canonical).hexdigest()
