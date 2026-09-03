from __future__ import annotations

from typing import Any

from .effects import EffectStatus, ExternalEffectCoordinator, EffectRequest, ProviderResult


def recover_in_flight(self: ExternalEffectCoordinator, request: EffectRequest, *, reason: str) -> dict[str, Any]:
    """Quarantine an existing abandoned claim without creating a new effect intent."""
    if not reason.strip():
        raise ValueError("Une raison de récupération explicite est obligatoire.")
    key = request.provider_idempotency_key
    try:
        row = self.peek(request)
    except KeyError:
        raise KeyError(key) from None
    if row["status"] == EffectStatus.UNKNOWN.value:
        return row
    if row["status"] != EffectStatus.IN_FLIGHT.value:
        raise ValueError(f"Récupération d'effet impossible depuis l'état {row['status']}.")
    self._transition(key, EffectStatus.UNKNOWN.value, error=f"Recovery required: {reason}")
    return self.peek(request)


def reconcile(self: ExternalEffectCoordinator, request: EffectRequest, provider: Any) -> ProviderResult:
    """Reconcile only an already-persisted effect; never create an intent during recovery."""
    self._authorize_reconciliation(request)
    key = request.provider_idempotency_key
    try:
        row = self.peek(request)
    except KeyError:
        raise RuntimeError("Aucune preuve durable de l'effet externe n'existe pour cette réconciliation.") from None
    if row["status"] == EffectStatus.COMPLETED.value:
        return ProviderResult("COMPLETED", row.get("result"))
    if row["status"] != EffectStatus.UNKNOWN.value:
        return ProviderResult(row["status"], row.get("result"), row.get("error"))
    outcome = provider.reconcile(request, key)
    normalized = ProviderResult(str(outcome.status), outcome.result, outcome.error)
    if normalized.status == EffectStatus.COMPLETED.value:
        self._transition(key, EffectStatus.COMPLETED.value, result=normalized.result)
    elif normalized.status == EffectStatus.FAILED.value:
        self._transition(key, EffectStatus.FAILED.value, error=normalized.error)
    else:
        self._transition(key, EffectStatus.UNKNOWN.value, result=normalized.result, error=normalized.error or "Provider reconciliation remains ambiguous")
        return ProviderResult("UNKNOWN", normalized.result, normalized.error)
    return normalized


ExternalEffectCoordinator.recover_in_flight = recover_in_flight
ExternalEffectCoordinator.reconcile = reconcile
