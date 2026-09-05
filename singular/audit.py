from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


#: Payload keys that describe where an event sits in the chain rather than what
#: happened. They are excluded from the event's own fingerprint, which is what
#: lets a trail re-anchor an event behind writes it had not seen without the
#: event becoming a different one.
CHAIN_KEYS = ("audit_fingerprint", "audit_sequence", "audit_prev_fingerprint", "audit_chain_fingerprint")


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
        for key in (*CHAIN_KEYS, "related_ids", "correlation_id"):
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

    @staticmethod
    def chain_fingerprint(sequence: int, fingerprint: str, previous_fingerprint: str) -> str:
        canonical = json.dumps(
            {
                "sequence": sequence,
                "fingerprint": fingerprint,
                "previous_fingerprint": previous_fingerprint,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def durable_payload(self, sequence: int, previous_fingerprint: str = "") -> dict[str, Any]:
        payload = dict(self.payload)
        payload.setdefault("correlation_id", self.correlation_id)
        payload.setdefault("related_ids", self.related_ids)
        payload.setdefault("audit_sequence", sequence)
        payload.setdefault("audit_fingerprint", self.fingerprint)
        payload.setdefault("audit_prev_fingerprint", previous_fingerprint)
        payload.setdefault(
            "audit_chain_fingerprint",
            self.chain_fingerprint(sequence, self.fingerprint, previous_fingerprint),
        )
        return payload


class AuditTrail:
    """Append-only audit trail with independently verifiable event and chain integrity."""

    def __init__(self, events: list[AuditEvent] | tuple[AuditEvent, ...] | None = None) -> None:
        self._events: list[AuditEvent] = list(events or ())

    @classmethod
    def restore(cls, persisted_events: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> "AuditTrail":
        if not cls.verify_chain(persisted_events):
            raise ValueError("L'intégrité de la chaîne d'audit ne peut pas être établie.")
        events = tuple(
            AuditEvent(
                event_type=str(event["event_type"]),
                actor=str(event["actor"]),
                outcome=str(event["outcome"]),
                payload=dict(event["payload"]),
                timestamp=str(event["timestamp"]),
                id=str(event["id"]),
            )
            for event in persisted_events
        )
        return cls(events)

    def record(self, event_type: str, actor: str, outcome: str, payload: dict[str, Any] | None = None) -> AuditEvent:
        base = dict(payload or {})
        event = AuditEvent(event_type, actor, outcome, base)
        previous = self._events[-1].payload.get("audit_fingerprint", "") if self._events else ""
        persisted = event.durable_payload(len(self._events) + 1, str(previous))
        event = AuditEvent(event_type, actor, outcome, persisted, event.timestamp, event.id)
        self._events.append(event)
        return event

    def append(self, event: AuditEvent) -> AuditEvent:
        """Re-place an existing event at the head of this trail.

        An event's own fingerprint deliberately excludes its chain position, so
        an event recorded by a trail that turned out to be behind can be moved
        behind whatever really came first without becoming a different event:
        same id, same timestamp, same content, new position. Rebuilding it with
        record() would mint a new id and timestamp, which would make the trail
        lie about when the thing happened.
        """
        payload = {key: value for key, value in event.payload.items() if key not in CHAIN_KEYS}
        previous = self._events[-1].payload.get("audit_fingerprint", "") if self._events else ""
        positioned = AuditEvent(event.event_type, event.actor, event.outcome, payload, event.timestamp, event.id)
        anchored = AuditEvent(
            event.event_type, event.actor, event.outcome,
            positioned.durable_payload(len(self._events) + 1, str(previous)), event.timestamp, event.id,
        )
        self._events.append(anchored)
        return anchored

    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def export(self) -> list[dict[str, Any]]:
        return [asdict(event) for event in self._events]

    @staticmethod
    def verify_persisted_event(event: dict[str, Any]) -> bool:
        payload = dict(event.get("payload") or {})
        expected = payload.get("audit_fingerprint")
        if not expected:
            return False
        required = ("id", "event_type", "actor", "outcome", "timestamp")
        if any(key not in event for key in required):
            return False
        candidate = AuditEvent(
            event_type=str(event["event_type"]),
            actor=str(event["actor"]),
            outcome=str(event["outcome"]),
            payload=payload,
            timestamp=str(event["timestamp"]),
            id=str(event["id"]),
        )
        return candidate.fingerprint == expected

    @classmethod
    def verify_chain(cls, events: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> bool:
        previous = ""
        expected_sequence = 1
        for event in events:
            if not cls.verify_persisted_event(event):
                return False
            payload = dict(event.get("payload") or {})
            sequence = payload.get("audit_sequence")
            event_fingerprint = payload.get("audit_fingerprint")
            previous_fingerprint = payload.get("audit_prev_fingerprint")
            chain_fingerprint = payload.get("audit_chain_fingerprint")
            if not isinstance(sequence, int) or sequence != expected_sequence:
                return False
            if not isinstance(event_fingerprint, str) or not event_fingerprint:
                return False
            if previous_fingerprint != previous:
                return False
            if not isinstance(chain_fingerprint, str) or not chain_fingerprint:
                return False
            if cls._chain_fingerprint(sequence, event_fingerprint, previous) != chain_fingerprint:
                return False
            previous = event_fingerprint
            expected_sequence += 1
        return True

    @staticmethod
    def _chain_fingerprint(sequence: int, fingerprint: str, previous_fingerprint: str) -> str:
        return AuditEvent.chain_fingerprint(sequence, fingerprint, previous_fingerprint)
