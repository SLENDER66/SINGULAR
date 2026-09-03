from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class KnowledgeKind(str, Enum):
    EVIDENCE = "EVIDENCE"
    ANALYSIS = "ANALYSIS"
    FORECAST = "FORECAST"
    CHALLENGE = "CHALLENGE"
    RECOMMENDATION = "RECOMMENDATION"


@dataclass(frozen=True)
class SharedSignal:
    """A typed contribution to SINGULAR's shared cognitive state."""

    contributor: str
    kind: KnowledgeKind
    subject: str
    claim: str
    confidence: float = 0.5
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.contributor or not self.subject or not self.claim:
            raise ValueError("Shared signals require contributor, subject and claim")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("Signal confidence must be finite and in [0, 1]")
        if any(not ref for ref in self.evidence_refs):
            raise ValueError("Evidence references must be non-empty")


@dataclass(frozen=True)
class Deliberation:
    """Collective view: agreement never erases dissent or authority boundaries."""

    subject: str
    signals: tuple[SharedSignal, ...]
    consensus: str | None
    dissent: tuple[str, ...]
    unresolved: bool

    @property
    def contributors(self) -> tuple[str, ...]:
        return tuple(sorted({signal.contributor for signal in self.signals}))


class CollectiveIntelligence:
    """Unifies cognition without flattening governance.

    Agents share one evidence/analysis/challenge space, while authority remains
    separate. Consensus informs decisions; it never becomes authorization.
    """

    @staticmethod
    def deliberate(subject: str, signals: tuple[SharedSignal, ...]) -> Deliberation:
        if not subject:
            raise ValueError("Deliberation subject is required")
        relevant = tuple(signal for signal in signals if signal.subject == subject)
        if not relevant:
            return Deliberation(subject, (), None, (), True)

        claims: dict[str, list[SharedSignal]] = {}
        for signal in relevant:
            claims.setdefault(signal.claim, []).append(signal)
        ranked = sorted(
            claims.items(),
            key=lambda item: (-sum(s.confidence for s in item[1]), item[0]),
        )
        winning_claim, winning_signals = ranked[0]
        total_confidence = sum(signal.confidence for signal in relevant)
        winning_confidence = sum(signal.confidence for signal in winning_signals)
        consensus = winning_claim if winning_confidence > total_confidence / 2 else None
        dissent = tuple(sorted(claim for claim, _ in ranked[1:]))
        unresolved = consensus is None
        return Deliberation(subject, relevant, consensus, dissent, unresolved)

    @staticmethod
    def authority_boundary() -> tuple[str, ...]:
        return (
            "shared_knowledge_is_not_shared_authority",
            "consensus_is_not_authorization",
            "dissent_is_not_disobedience",
            "red_team_challenge_is_preserved",
            "human_final_authority_is_preserved",
        )
