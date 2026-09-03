"""Executable architecture invariants for SINGULAR.

These invariants describe properties that must remain true as the system grows.
They are intentionally small and dependency-light so higher-level tests can
use them without importing concrete execution providers.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class InvariantSeverity(str, Enum):
    BLOCKING = "BLOCKING"
    WARNING = "WARNING"


@dataclass(frozen=True)
class ArchitectureInvariant:
    id: str
    statement: str
    severity: InvariantSeverity = InvariantSeverity.BLOCKING

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.statement.strip():
            raise ValueError("Invariant id and statement are required")


@dataclass(frozen=True)
class InvariantViolation:
    invariant_id: str
    detail: str


class ArchitectureInvariantRegistry:
    """Canonical registry for non-negotiable architectural properties."""

    def __init__(self, invariants: Iterable[ArchitectureInvariant] = ()) -> None:
        values = tuple(invariants)
        ids = [item.id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError("Invariant ids must be unique")
        self._invariants = {item.id: item for item in values}

    def register(self, invariant: ArchitectureInvariant) -> None:
        if invariant.id in self._invariants:
            raise ValueError(f"Invariant already registered: {invariant.id}")
        self._invariants[invariant.id] = invariant

    def get(self, invariant_id: str) -> ArchitectureInvariant:
        return self._invariants[invariant_id]

    def all(self) -> tuple[ArchitectureInvariant, ...]:
        return tuple(self._invariants[key] for key in sorted(self._invariants))

    def blocking(self) -> tuple[ArchitectureInvariant, ...]:
        return tuple(item for item in self.all() if item.severity is InvariantSeverity.BLOCKING)


DEFAULT_INVARIANTS = ArchitectureInvariantRegistry(
    (
        ArchitectureInvariant("AUTH-001", "No side effect occurs without a validated decision and valid durable attestation."),
        ArchitectureInvariant("AUTH-002", "The executed action, contract, capability, provider and payload are bound to the validated decision."),
        ArchitectureInvariant("AUTH-003", "An approval identity is immutable after creation and a terminal approval cannot be rewritten."),
        ArchitectureInvariant("EXEC-001", "Execution is idempotent for a given execution identity."),
        ArchitectureInvariant("EXEC-002", "A restart cannot manufacture a successful execution result absent durable evidence."),
        ArchitectureInvariant("EXEC-003", "A RECOVERY_REQUIRED execution cannot be replayed, confirmed, or finalized through the normal execution path."),
        ArchitectureInvariant("EXEC-004", "External-effect reconciliation is the only path that may convert an ambiguous external effect into a proven terminal outcome."),
        ArchitectureInvariant("EXEC-005", "Execution state and mission state must reach terminal consistency through one authoritative durable transition."),
        ArchitectureInvariant("EXEC-006", "Concurrent workers cannot both acquire the same execution or external-effect lease."),
        ArchitectureInvariant("LEARN-001", "Outcome learning consumes only verified durable execution observations."),
        ArchitectureInvariant("LEARN-002", "Learning may propose changes but cannot silently mutate execution authority."),
        ArchitectureInvariant("EPI-001", "Hypothetical or contested future evidence cannot directly authorize execution."),
        ArchitectureInvariant("AUDIT-001", "Security-relevant decisions and execution results remain tamper-evident and verifiable."),
        ArchitectureInvariant("FAIL-001", "Ambiguity, integrity failure or missing authorization fails closed rather than guessing."),
    )
)


__all__ = [
    "ArchitectureInvariant",
    "InvariantSeverity",
    "InvariantViolation",
    "ArchitectureInvariantRegistry",
    "DEFAULT_INVARIANTS",
]
