"""Translate historical/future world state into bounded decision advice.

This layer is intentionally advisory: it can prioritize observation or preparation,
but it cannot create authorization, waive governance, or escalate a future
scenario into an executable action.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .collective_intelligence import KnowledgeKind, SharedSignal
from .history_world_model import FutureDisposition, FutureReasoner, TemporalAssessment, TemporalContext


@dataclass(frozen=True)
class TemporalSignal:
    scenario_id: str
    disposition: FutureDisposition
    confidence: float
    uncertainty: float
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise ValueError("scenario_id is required")
        for name, value in (("confidence", self.confidence), ("uncertainty", self.uncertainty)):
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"temporal signal {name} must be between 0 and 1")


@dataclass(frozen=True)
class TemporalAdvisory:
    signals: tuple[TemporalSignal, ...]
    preparation_scenarios: tuple[str, ...]
    watch_scenarios: tuple[str, ...]
    blocked_from_authorization: bool = True

    def __post_init__(self) -> None:
        known = {signal.scenario_id for signal in self.signals}
        if not set(self.preparation_scenarios) <= known or not set(self.watch_scenarios) <= known:
            raise ValueError("temporal advisory references an unknown scenario")
        if not self.blocked_from_authorization:
            raise ValueError("temporal advisory must remain non-authorizing")

    @property
    def uncertainty(self) -> float:
        if not self.signals:
            return 1.0
        return round(sum(signal.uncertainty for signal in self.signals) / len(self.signals), 4)

    def as_shared_signals(self, contributor: str = "temporal_advisor") -> tuple[SharedSignal, ...]:
        """Expose forecasts to collective cognition without granting authority."""
        if not contributor.strip():
            raise ValueError("contributor is required")
        return tuple(
            SharedSignal(
                contributor=contributor,
                kind=KnowledgeKind.FORECAST,
                subject=signal.scenario_id,
                claim=f"Temporal scenario {signal.scenario_id}: disposition={signal.disposition.value}",
                confidence=signal.confidence,
                evidence_refs=signal.reasons,
                critical=False,
            )
            for signal in self.signals
        )


class TemporalAdvisor:
    """Produce auditable preparation/watch advice from the temporal world model."""

    def assess(self, context: TemporalContext) -> TemporalAdvisory:
        evidence = context.canonical_world.canonical_facts
        signals: list[TemporalSignal] = []
        for scenario in context.active_scenarios:
            assessment: TemporalAssessment = FutureReasoner.assess(scenario, evidence)
            signals.append(TemporalSignal(
                scenario_id=scenario.id,
                disposition=scenario.disposition,
                confidence=assessment.confidence,
                uncertainty=assessment.uncertainty,
                reasons=assessment.reasons,
            ))
        ordered = tuple(sorted(signals, key=lambda signal: (-signal.confidence, signal.scenario_id)))
        return TemporalAdvisory(
            signals=ordered,
            preparation_scenarios=tuple(signal.scenario_id for signal in ordered if signal.disposition is FutureDisposition.PREPARE),
            watch_scenarios=tuple(signal.scenario_id for signal in ordered if signal.disposition is FutureDisposition.WATCH),
        )

    @staticmethod
    def can_authorize(_: TemporalAdvisory) -> bool:
        """Temporal advice is structurally incapable of authorizing execution."""
        return False


__all__ = ["TemporalSignal", "TemporalAdvisory", "TemporalAdvisor"]
