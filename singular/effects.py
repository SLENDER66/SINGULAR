from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .durable import DurableStore


class EffectStatus(str, Enum):
    INTENT = "INTENT"
    IN_FLIGHT = "IN_FLIGHT"
    COMPLETED = "COMPLETED"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"


@dataclass(frozen=True)
class EffectRequest:
    execution_key: str
    provider: str
    operation: str
    payload: Any

    @property
    def payload_fingerprint(self) -> str:
        canonical = json.dumps(self.payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def provider_idempotency_key(self) -> str:
        material = "\x1f".join((self.execution_key, self.provider, self.operation, self.payload_fingerprint))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProviderResult:
    status: str
    result: Any = None
    error: str | None = None


class EffectProvider(Protocol):
    def execute(self, request: EffectRequest, idempotency_key: str) -> ProviderResult:
        """Perform one external effect using the supplied provider idempotency key."""

    def reconcile(self, request: EffectRequest, idempotency_key: str) -> ProviderResult:
        """Resolve whether the externally addressed effect exists."""


class ExternalEffectCoordinator:
    """Durable boundary for external side effects; ambiguous outcomes never auto-retry."""

    def __init__(self, store: DurableStore) -> None:
        self.store = store
        self.store.init_effect_schema()

    def prepare(self, request: EffectRequest) -> dict[str, Any]:
        key = request.provider_idempotency_key
        return self.store.begin_effect(
            key,
            request.execution_key,
            request.provider,
            request.operation,
            request.payload_fingerprint,
        )

    def execute(self, request: EffectRequest, provider: EffectProvider) -> ProviderResult:
        key = request.provider_idempotency_key
        existing = self.prepare(request)
        status = existing["status"]
        if status == EffectStatus.COMPLETED.value:
            return ProviderResult("COMPLETED", existing.get("result"))
        if status == EffectStatus.UNKNOWN.value:
            raise RuntimeError("Effet externe ambigu : réconciliation explicite requise avant toute nouvelle exécution.")
        if status == EffectStatus.FAILED.value:
            return ProviderResult("FAILED", error=existing.get("error"))

        self.store.mark_effect_in_flight(key)
        try:
            outcome = provider.execute(request, key)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            self.store.mark_effect_unknown(key, message)
            return ProviderResult("UNKNOWN", error=message)

        normalized = ProviderResult(str(outcome.status), outcome.result, outcome.error)
        if normalized.status == EffectStatus.COMPLETED.value:
            self.store.finish_effect(key, "COMPLETED", result=normalized.result)
        elif normalized.status == EffectStatus.FAILED.value:
            self.store.finish_effect(key, "FAILED", error=normalized.error)
        else:
            self.store.mark_effect_unknown(key, normalized.error or "Provider returned an ambiguous outcome")
            return ProviderResult("UNKNOWN", normalized.result, normalized.error)
        return normalized

    def reconcile(self, request: EffectRequest, provider: EffectProvider) -> ProviderResult:
        key = request.provider_idempotency_key
        row = self.store.get_effect(key)
        if row is None:
            raise KeyError(key)
        if row["status"] == EffectStatus.COMPLETED.value:
            return ProviderResult("COMPLETED", row.get("result"))
        if row["status"] != EffectStatus.UNKNOWN.value:
            return ProviderResult(row["status"], row.get("result"), row.get("error"))

        outcome = provider.reconcile(request, key)
        normalized = ProviderResult(str(outcome.status), outcome.result, outcome.error)
        if normalized.status == EffectStatus.COMPLETED.value:
            self.store.finish_effect(key, "COMPLETED", result=normalized.result)
        elif normalized.status == EffectStatus.FAILED.value:
            self.store.finish_effect(key, "FAILED", error=normalized.error)
        else:
            self.store.mark_effect_unknown(key, normalized.error or "Provider reconciliation remains ambiguous")
            return ProviderResult("UNKNOWN", normalized.result, normalized.error)
        return normalized
