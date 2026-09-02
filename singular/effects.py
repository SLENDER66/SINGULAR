from __future__ import annotations

import hashlib
import json
import sqlite3
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


class EffectInProgress(RuntimeError):
    """Another worker currently owns the external-effect claim."""


@dataclass(frozen=True)
class EffectRequest:
    execution_key: str
    provider: str
    operation: str
    payload: Any
    action_fingerprint: str | None = None

    @property
    def payload_fingerprint(self) -> str:
        canonical = json.dumps(self.payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def provider_idempotency_key(self) -> str:
        material = "\x1f".join((self.execution_key, self.provider, self.operation))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProviderResult:
    status: str
    result: Any = None
    error: str | None = None


class EffectProvider(Protocol):
    def execute(self, request: EffectRequest, idempotency_key: str) -> ProviderResult: ...

    def reconcile(self, request: EffectRequest, idempotency_key: str) -> ProviderResult: ...


class ExternalEffectCoordinator:
    """Durable external-effect boundary; ambiguous outcomes never auto-retry."""

    _TRANSITIONS = {
        EffectStatus.INTENT.value: frozenset({EffectStatus.IN_FLIGHT.value}),
        EffectStatus.IN_FLIGHT.value: frozenset({EffectStatus.COMPLETED.value, EffectStatus.UNKNOWN.value, EffectStatus.FAILED.value}),
        EffectStatus.UNKNOWN.value: frozenset({EffectStatus.COMPLETED.value, EffectStatus.UNKNOWN.value, EffectStatus.FAILED.value}),
        EffectStatus.COMPLETED.value: frozenset(),
        EffectStatus.FAILED.value: frozenset(),
    }

    def __init__(self, store: DurableStore) -> None:
        self.store = store
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.store.path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS external_effects (
                    provider_idempotency_key TEXT PRIMARY KEY,
                    execution_key TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    action_fingerprint TEXT,
                    payload_fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(external_effects)")}
            if "action_fingerprint" not in columns:
                conn.execute("ALTER TABLE external_effects ADD COLUMN action_fingerprint TEXT")

    def prepare(self, request: EffectRequest) -> dict[str, Any]:
        key = request.provider_idempotency_key
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO external_effects "
                "(provider_idempotency_key,execution_key,provider,operation,action_fingerprint,payload_fingerprint,status,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (key, request.execution_key, request.provider, request.operation, request.action_fingerprint,
                 request.payload_fingerprint, EffectStatus.INTENT.value, now, now),
            )
            row = conn.execute("SELECT * FROM external_effects WHERE provider_idempotency_key=?", (key,)).fetchone()
        if row is None:
            raise RuntimeError("L'intention d'effet externe n'a pas pu être persistée.")
        existing = dict(row)
        for field in ("execution_key", "provider", "operation"):
            if existing[field] != getattr(request, field):
                raise ValueError("Clé d'idempotence fournisseur réutilisée avec un contexte différent.")
        if existing["action_fingerprint"] != request.action_fingerprint:
            raise ValueError("Effet externe réutilisé avec une identité d'action différente.")
        if existing["payload_fingerprint"] != request.payload_fingerprint:
            raise ValueError("Clé d'idempotence fournisseur réutilisée avec un payload différent.")
        existing["result"] = self._decode(existing.get("result"))
        return existing

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
        if status == EffectStatus.IN_FLIGHT.value:
            raise EffectInProgress(key)

        if not self._claim(key):
            current = self.prepare(request)
            if current["status"] == EffectStatus.COMPLETED.value:
                return ProviderResult("COMPLETED", current.get("result"))
            if current["status"] == EffectStatus.FAILED.value:
                return ProviderResult("FAILED", error=current.get("error"))
            if current["status"] == EffectStatus.UNKNOWN.value:
                raise RuntimeError("Effet externe ambigu : réconciliation explicite requise avant toute nouvelle exécution.")
            raise EffectInProgress(key)

        try:
            outcome = provider.execute(request, key)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            self._transition(key, EffectStatus.UNKNOWN.value, error=message)
            return ProviderResult("UNKNOWN", error=message)

        normalized = ProviderResult(str(outcome.status), outcome.result, outcome.error)
        if normalized.status == EffectStatus.COMPLETED.value:
            self._transition(key, EffectStatus.COMPLETED.value, result=normalized.result)
        elif normalized.status == EffectStatus.FAILED.value:
            self._transition(key, EffectStatus.FAILED.value, error=normalized.error)
        else:
            self._transition(key, EffectStatus.UNKNOWN.value, result=normalized.result, error=normalized.error or "Provider returned an ambiguous outcome")
            return ProviderResult("UNKNOWN", normalized.result, normalized.error)
        return normalized

    def recover_in_flight(self, request: EffectRequest, *, reason: str) -> dict[str, Any]:
        """Quarantine an abandoned claim without calling the external provider."""
        if not reason.strip():
            raise ValueError("Une raison de récupération explicite est obligatoire.")
        key = request.provider_idempotency_key
        row = self.prepare(request)
        if row["status"] == EffectStatus.UNKNOWN.value:
            return row
        if row["status"] != EffectStatus.IN_FLIGHT.value:
            raise ValueError(f"Récupération d'effet impossible depuis l'état {row['status']}.")
        self._transition(key, EffectStatus.UNKNOWN.value, error=f"Recovery required: {reason}")
        return self.prepare(request)

    def reconcile(self, request: EffectRequest, provider: EffectProvider) -> ProviderResult:
        key = request.provider_idempotency_key
        row = self.prepare(request)
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

    def get(self, request: EffectRequest) -> dict[str, Any]:
        return self.prepare(request)

    def _claim(self, key: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE external_effects SET status=?,updated_at=? WHERE provider_idempotency_key=? AND status=?",
                (EffectStatus.IN_FLIGHT.value, self._now(), key, EffectStatus.INTENT.value),
            )
            return cur.rowcount == 1

    def _transition(self, key: str, status: str, *, result: Any = None, error: str | None = None) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT status FROM external_effects WHERE provider_idempotency_key=?", (key,)).fetchone()
            if row is None:
                raise KeyError(key)
            current = row["status"]
            if status != current and status not in self._TRANSITIONS.get(current, frozenset()):
                raise ValueError(f"Transition d'effet interdite : {current} -> {status}")
            encoded = None if result is None else json.dumps(result, sort_keys=True, default=str)
            cur = conn.execute(
                "UPDATE external_effects SET status=?,result=?,error=?,updated_at=? WHERE provider_idempotency_key=? AND status=?",
                (status, encoded, error, self._now(), key, current),
            )
            if cur.rowcount != 1:
                raise RuntimeError("La transition d'effet a échoué à cause d'une concurrence d'état.")

    @staticmethod
    def _decode(value: Any) -> Any:
        if value is None or not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    @staticmethod
    def _now() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
