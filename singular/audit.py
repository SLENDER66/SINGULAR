from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any
from uuid import uuid4

#: Payload keys that describe where an event sits in the chain rather than what
#: happened. They are excluded from the event's own fingerprint, which is what
#: lets a trail re-anchor an event behind writes it had not seen without the
#: event becoming a different one.
CHAIN_KEYS = ("audit_fingerprint", "audit_sequence", "audit_prev_fingerprint", "audit_chain_fingerprint")
MAX_EVENT_BYTES = 64 * 1024


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    actor: str
    outcome: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    id: str = field(default_factory=lambda: "AUD-" + uuid4().hex)

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
        for key in (*CHAIN_KEYS, "related_ids", "correlation_id"):
            payload.pop(key, None)
        canonical = _canonical_json(
            {
                "id": self.id,
                "event_type": self.event_type,
                "actor": self.actor,
                "outcome": self.outcome,
                "payload": payload,
                "timestamp": self.timestamp,
            }
        )
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def chain_fingerprint(sequence: int, fingerprint: str, previous_fingerprint: str) -> str:
        canonical = _canonical_json(
            {
                "sequence": sequence,
                "fingerprint": fingerprint,
                "previous_fingerprint": previous_fingerprint,
            }
        )
        return hashlib.sha256(canonical).hexdigest()

    def durable_payload(self, sequence: int, previous_fingerprint: str = "") -> dict[str, Any]:
        payload = dict(self.payload)
        payload["correlation_id"] = self.correlation_id
        payload["related_ids"] = self.related_ids
        payload["audit_sequence"] = sequence
        payload["audit_fingerprint"] = self.fingerprint
        payload["audit_prev_fingerprint"] = previous_fingerprint
        payload["audit_chain_fingerprint"] = self.chain_fingerprint(sequence, self.fingerprint, previous_fingerprint)
        _canonical_json({**asdict(self), "payload": payload})
        return payload


def _canonical_json(value: dict[str, Any]) -> bytes:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise TypeError("Les données d'audit doivent être JSON strictement sérialisables.") from exc
    if len(encoded) > MAX_EVENT_BYTES:
        raise ValueError("L'événement d'audit dépasse la taille maximale autorisée.")
    return encoded


class AuditTrail:
    """Append-only audit trail with independently verifiable event and chain integrity."""

    def __init__(self, events: list[AuditEvent] | tuple[AuditEvent, ...] | None = None) -> None:
        initial = tuple(events or ())
        if initial and not self.verify_chain([asdict(event) for event in initial]):
            raise ValueError("L'intégrité de la chaîne d'audit ne peut pas être établie.")
        self._events: list[AuditEvent] = list(initial)
        self._lock = RLock()

    @classmethod
    def restore(cls, persisted_events: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> AuditTrail:
        if not cls.verify_chain(persisted_events):
            raise ValueError("L'intégrité de la chaîne d'audit ne peut pas être établie.")
        events = tuple(
            AuditEvent(
                event_type=event["event_type"],
                actor=event["actor"],
                outcome=event["outcome"],
                payload=dict(event["payload"]),
                timestamp=event["timestamp"],
                id=event["id"],
            )
            for event in persisted_events
        )
        return cls(events)

    def record(self, event_type: str, actor: str, outcome: str, payload: dict[str, Any] | None = None) -> AuditEvent:
        with self._lock:
            base = dict(payload or {})
            event = AuditEvent(event_type, actor, outcome, base)
            previous = self._events[-1].payload.get("audit_fingerprint", "") if self._events else ""
            persisted = event.durable_payload(len(self._events) + 1, str(previous))
            event = AuditEvent(event_type, actor, outcome, persisted, event.timestamp, event.id)
            self._events.append(event)
            return event

    def append(self, event: AuditEvent) -> AuditEvent:
        """Re-place an existing event at the head of this trail."""
        with self._lock:
            if any(existing.id == event.id for existing in self._events):
                raise ValueError("Un événement d'audit avec cet identifiant existe déjà.")
            payload = {key: value for key, value in event.payload.items() if key not in CHAIN_KEYS}
            previous = self._events[-1].payload.get("audit_fingerprint", "") if self._events else ""
            positioned = AuditEvent(event.event_type, event.actor, event.outcome, payload, event.timestamp, event.id)
            anchored = AuditEvent(
                event.event_type,
                event.actor,
                event.outcome,
                positioned.durable_payload(len(self._events) + 1, str(previous)),
                event.timestamp,
                event.id,
            )
            self._events.append(anchored)
            return anchored

    def events(self) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def export(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(event) for event in self._events]

    @staticmethod
    def verify_persisted_event(event: dict[str, Any]) -> bool:
        if not isinstance(event, dict):
            return False
        required = ("id", "event_type", "actor", "outcome", "timestamp", "payload")
        if any(key not in event for key in required):
            return False
        if any(not isinstance(event[key], str) or not event[key] for key in required if key != "payload"):
            return False
        if not isinstance(event["payload"], dict):
            return False
        payload = dict(event["payload"])
        expected = payload.get("audit_fingerprint")
        if not isinstance(expected, str) or not expected:
            return False
        try:
            candidate = AuditEvent(
                event_type=event["event_type"],
                actor=event["actor"],
                outcome=event["outcome"],
                payload=payload,
                timestamp=event["timestamp"],
                id=event["id"],
            )
            return candidate.fingerprint == expected
        except (TypeError, ValueError, UnicodeError):
            return False

    @classmethod
    def verify_chain(cls, events: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> bool:
        previous = ""
        expected_sequence = 1
        seen_ids: set[str] = set()
        for event in events:
            event_id = event.get("id") if isinstance(event, dict) else None
            if not isinstance(event_id, str) or not event_id or event_id in seen_ids:
                return False
            seen_ids.add(event_id)
            if not cls.verify_persisted_event(event):
                return False
            payload = dict(event["payload"])
            sequence = payload.get("audit_sequence")
            event_fingerprint = payload.get("audit_fingerprint")
            previous_fingerprint = payload.get("audit_prev_fingerprint")
            chain_fingerprint = payload.get("audit_chain_fingerprint")
            if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence != expected_sequence:
                return False
            if not isinstance(event_fingerprint, str) or not event_fingerprint:
                return False
            if previous_fingerprint != previous:
                return False
            if not isinstance(chain_fingerprint, str) or not chain_fingerprint:
                return False
            try:
                expected_chain = cls._chain_fingerprint(sequence, event_fingerprint, previous)
            except (TypeError, ValueError, UnicodeError):
                return False
            if expected_chain != chain_fingerprint:
                return False
            previous = event_fingerprint
            expected_sequence += 1
        return True

    @staticmethod
    def _chain_fingerprint(sequence: int, fingerprint: str, previous_fingerprint: str) -> str:
        return AuditEvent.chain_fingerprint(sequence, fingerprint, previous_fingerprint)


__all__ = ["AuditEvent", "AuditTrail", "CHAIN_KEYS", "MAX_EVENT_BYTES"]
