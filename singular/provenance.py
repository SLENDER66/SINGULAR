from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any


@dataclass(frozen=True)
class ProvenanceRecord:
    """Tamper-evident provenance for one observed or derived artifact."""

    record_id: str
    source: str
    recorded_at: str
    epistemic_type: str
    confidence: float
    transformation: str = ""
    decision_id: str | None = None
    payload_digest: str = ""
    previous_digest: str = ""

    def __post_init__(self) -> None:
        if not self.record_id.strip():
            raise ValueError("record_id is required")
        if not self.source.strip():
            raise ValueError("source is required")
        if not self.recorded_at.strip():
            raise ValueError("recorded_at is required")
        if not self.epistemic_type.strip():
            raise ValueError("epistemic_type is required")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not self.payload_digest:
            raise ValueError("payload_digest is required")

    @classmethod
    def from_payload(
        cls,
        *,
        record_id: str,
        source: str,
        recorded_at: str,
        epistemic_type: str,
        confidence: float,
        payload: Any,
        transformation: str = "",
        decision_id: str | None = None,
        previous_digest: str = "",
    ) -> "ProvenanceRecord":
        payload_digest = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        return cls(
            record_id=record_id,
            source=source,
            recorded_at=recorded_at,
            epistemic_type=epistemic_type,
            confidence=confidence,
            transformation=transformation,
            decision_id=decision_id,
            payload_digest=payload_digest,
            previous_digest=previous_digest,
        )

    def digest(self) -> str:
        payload = {
            "record_id": self.record_id,
            "source": self.source,
            "recorded_at": self.recorded_at,
            "epistemic_type": self.epistemic_type,
            "confidence": self.confidence,
            "transformation": self.transformation,
            "decision_id": self.decision_id,
            "payload_digest": self.payload_digest,
            "previous_digest": self.previous_digest,
        }
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()


class ProvenanceChain:
    """Append-only, deterministic provenance chain with explicit verification."""

    def __init__(self) -> None:
        self._records: list[ProvenanceRecord] = []

    def append(self, record: ProvenanceRecord) -> str:
        if self._records and record.previous_digest != self._records[-1].digest():
            raise ValueError("record does not link to the current provenance head")
        if any(existing.record_id == record.record_id for existing in self._records):
            raise ValueError("record_id already exists")
        self._records.append(record)
        return record.digest()

    def records(self) -> tuple[ProvenanceRecord, ...]:
        return tuple(self._records)

    def head_digest(self) -> str | None:
        return self._records[-1].digest() if self._records else None

    def verify(self) -> bool:
        previous = ""
        seen: set[str] = set()
        for record in self._records:
            if record.record_id in seen or record.previous_digest != previous:
                return False
            seen.add(record.record_id)
            previous = record.digest()
        return True
