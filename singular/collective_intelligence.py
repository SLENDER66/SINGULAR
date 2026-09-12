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
    critical: bool = False

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
    collective_confidence: float = 0.0
    blocking_challenges: tuple[str, ...] = ()

    @property
    def contributors(self) -> tuple[str, ...]:
        return tuple(sorted({signal.contributor for signal in self.signals}))


class CollectiveIntelligence:
    """Unifies cognition without flattening governance.

    Agents share one evidence/analysis/challenge space, while authority remains
    separate. Deliberation is evidence-aware, calibration-aware and resistant
    to confidence inflation from duplicated or correlated contributions.
    """

    _KIND_WEIGHT = {
        KnowledgeKind.EVIDENCE: 1.00,
        KnowledgeKind.ANALYSIS: 0.90,
        KnowledgeKind.FORECAST: 0.85,
        KnowledgeKind.RECOMMENDATION: 0.80,
        KnowledgeKind.CHALLENGE: 0.00,
    }

    @staticmethod
    def _signal_weight(
        signal: SharedSignal,
        calibration: dict[str, float] | None,
    ) -> float:
        calibrated = 1.0 if calibration is None else calibration.get(signal.contributor, 1.0)
        if not isfinite(calibrated) or calibrated < 0:
            raise ValueError("Calibration weights must be finite and non-negative")
        evidence_bonus = 1.0 if signal.evidence_refs else 0.75
        return signal.confidence * CollectiveIntelligence._KIND_WEIGHT[signal.kind] * calibrated * evidence_bonus

    @staticmethod
    def deliberate(
        subject: str,
        signals: tuple[SharedSignal, ...],
        *,
        calibration: dict[str, float] | None = None,
    ) -> Deliberation:
        if not subject:
            raise ValueError("Deliberation subject is required")
        relevant = tuple(signal for signal in signals if signal.subject == subject)
        if not relevant:
            return Deliberation(subject, (), None, (), True)

        # One contributor cannot create a majority by repeating the same claim.
        # Evidence references also cap the contribution of correlated/reused evidence.
        claims: dict[str, dict[str, float]] = {}
        for signal in relevant:
            if signal.kind is KnowledgeKind.CHALLENGE:
                continue
            weight = CollectiveIntelligence._signal_weight(signal, calibration)
            contributor_claims = claims.setdefault(signal.claim, {})
            previous = contributor_claims.get(signal.contributor, 0.0)
            contributor_claims[signal.contributor] = max(previous, weight)

        scored = sorted(
            ((claim, sum(contributor_weights.values())) for claim, contributor_weights in claims.items()),
            key=lambda item: (-item[1], item[0]),
        )

        total_support = sum(score for _, score in scored)
        winning_claim: str | None = None
        winning_score = 0.0
        if scored:
            winning_claim, winning_score = scored[0]

        blocking = tuple(
            signal.claim
            for signal in relevant
            if signal.kind is KnowledgeKind.CHALLENGE and signal.critical and signal.confidence >= 0.8
        )

        # Consensus requires a real independent majority. A critical Red Team
        # challenge keeps the deliberation unresolved until explicitly reviewed.
        #
        # Weighted score alone is not a majority of minds. Two contributors
        # advancing different claims once each is a disagreement, but EVIDENCE
        # outweighs ANALYSIS, so the weighted test alone declared the heavier
        # kind the consensus. That matters beyond tidiness: an unresolved
        # deliberation is one of the conditions that make GlobalDecisionReport
        # require a human, so resolving a genuine split silently removed a
        # human-review trigger. Require a majority of the contributors who took
        # a position as well as a majority of the weight.
        backing = len(claims.get(winning_claim, {})) if winning_claim is not None else 0
        positioned = len({contributor for claim in claims.values() for contributor in claim})
        independent_majority = positioned > 0 and backing * 2 > positioned
        consensus = (
            winning_claim
            if winning_claim is not None and total_support > 0 and winning_score > total_support / 2
            and independent_majority
            and not blocking
            else None
        )
        # With no consensus nothing is agreed, so every claim is dissent.
        # Reporting only the lower-weighted ones implied the top claim had been
        # accepted when in fact the deliberation was left open.
        dissent = tuple(sorted(claim for claim, _ in (scored[1:] if consensus is not None else scored)))
        dissent += tuple(sorted({signal.claim for signal in relevant if signal.kind is KnowledgeKind.CHALLENGE}))
        unresolved = consensus is None or bool(blocking)
        collective_confidence = (winning_score / total_support) if total_support else 0.0
        return Deliberation(
            subject,
            relevant,
            consensus,
            tuple(dict.fromkeys(dissent)),
            unresolved,
            collective_confidence,
            tuple(dict.fromkeys(blocking)),
        )

    @staticmethod
    def authority_boundary() -> tuple[str, ...]:
        return (
            "shared_knowledge_is_not_shared_authority",
            "consensus_is_not_authorization",
            "dissent_is_not_disobedience",
            "red_team_challenge_is_preserved",
            "human_final_authority_is_preserved",
        )
