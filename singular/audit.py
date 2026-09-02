from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    actor: str
    outcome: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    id: str = field(default_factory=lambda: "AUD-" + uuid4().hex[:10])

    @property
    def correlation_id(self) -> str:
        for key in ("correlation_id", "mission_id", "execution_key", "action_id", "approval_id"):
            value = self.payload.get(key)
            if value:
                return str(value)
        return self.id

    @property
    def related_ids(self) -> dict[str, str]:
        return {
            key: str(self.payload[key])
            for key in ("mission_id", "action_id", "execution_key", "approval_id")
            if self.payload.get(key) is not None
        }

    @property
    def fingerprint(self) -> str:
        payload = dict(self.payload)
        for key in ("audit_fingerprint", "audit_sequence", "related_ids", "correlation_id"):
            payload.pop(key, None)
        canonical = json.dumps(
            {
                "id": self.id,
                "event_type": self.event_type,
                "actor": self.actor,
                "outcome": self.outcome,
                "payload": payload,
                "timestamp": self.timestamp,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def durable_payload(self, sequence: int) -> dict[str, Any]:
        payload = dict(self.payload)
        payload.setdefault("correlation_id", self.correlation_id)
        payload.setdefault("related_ids", self.related_ids)
        payload.setdefault("audit_sequence", sequence)
        payload.setdefault("audit_fingerprint", self.fingerprint)
        return payload


class AuditTrail:
    """Append-only audit trail for the runtime; persisted copies remain independently verifiable."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(self, event_type: str, actor: str, outcome: str, payload: dict[str, Any] | None = None) -> AuditEvent:
        base = dict(payload or {})
        event = AuditEvent(event_type, actor, outcome, base)
        persisted = event.durable_payload(len(self._events) + 1)
        event = AuditEvent(event_type, actor, outcome, persisted, event.timestamp, event.id)
        self._events.append(event)
        return event

    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def export(self) -> list[dict[str, Any]]:
        return [asdict(event) for event in self._events]

    @staticmethod
    def verify_persisted_event(event: dict[str, Any]) -> bool:
        payload = dict(event.get("payload") or {})
        expected = payload.get("audit_fingerprint")
        if not expected:
            return True
        candidate = AuditEvent(
            event_type=str(event["event_type"]),
            actor=str(event["actor"]),
            outcome=str(event["outcome"]),
            payload=payload,
            timestamp=str(event["timestamp"]),
            id=str(event["id"]),
        )
        return candidate.fingerprint == expected
