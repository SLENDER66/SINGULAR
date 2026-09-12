from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class GenerationalCharter:
    """Minimum continuity contract for a system intended to outlive its founder."""

    generation: int
    mission: str
    values_locked_by_human: bool = True
    governance_documented: bool = False
    knowledge_portable: bool = False
    audit_restorable: bool = False
    successor_defined: bool = False

    def __post_init__(self) -> None:
        if self.generation < 1:
            raise ValueError("generation must be positive")
        if not self.mission.strip():
            raise ValueError("mission cannot be empty")


@dataclass(frozen=True)
class GenerationalReadiness:
    generation: int
    score: float
    ready: bool
    priorities: tuple[str, ...]


class GenerationalEngine:
    """Measure whether SINGULAR can be transmitted without becoming founder-dependent."""

    @staticmethod
    def assess(
        charter: GenerationalCharter,
        *,
        capital_protection: float,
        founder_independence: float,
        institutional_resilience: float,
    ) -> GenerationalReadiness:
        values = {
            "capital_protection": capital_protection,
            "founder_independence": founder_independence,
            "institutional_resilience": institutional_resilience,
        }
        for name, value in values.items():
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and between 0 and 1")

        binary = {
            "governance_documented": charter.governance_documented,
            "knowledge_portable": charter.knowledge_portable,
            "audit_restorable": charter.audit_restorable,
            "successor_defined": charter.successor_defined,
            "values_locked_by_human": charter.values_locked_by_human,
        }
        score = (sum(values.values()) + sum(binary.values())) / 8
        priorities: list[str] = []
        if not charter.governance_documented:
            priorities.append("DOCUMENT_GOVERNANCE")
        if not charter.knowledge_portable:
            priorities.append("MAKE_KNOWLEDGE_PORTABLE")
        if not charter.audit_restorable:
            priorities.append("ENSURE_AUDIT_RESTORATION")
        if not charter.successor_defined:
            priorities.append("DEFINE_SUCCESSION")
        if not charter.values_locked_by_human:
            priorities.append("REQUIRE_HUMAN_VALUES_CONTROL")
        if capital_protection < 0.7:
            priorities.append("PROTECT_PATRIMONY")
        if founder_independence < 0.7:
            priorities.append("REMOVE_FOUNDER_SINGLE_POINT_OF_FAILURE")
        if institutional_resilience < 0.7:
            priorities.append("BUILD_INSTITUTIONAL_RESILIENCE")

        return GenerationalReadiness(
            charter.generation,
            round(score, 6),
            not priorities,
            tuple(priorities),
        )
