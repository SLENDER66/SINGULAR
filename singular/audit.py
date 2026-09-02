from __future__ import annotations

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


class AuditTrail:
    """Append-only in-memory audit trail for the prototype."""
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(self, event_type: str, actor: str, outcome: str, payload: dict[str, Any] | None = None) -> AuditEvent:
        event = AuditEvent(event_type, actor, outcome, dict(payload or {}))
        self._events.append(event)
        return event

    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def export(self) -> list[dict[str, Any]]:
        return [asdict(event) for event in self._events]
