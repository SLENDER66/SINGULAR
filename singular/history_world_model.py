"""Evidence-bounded historical memory and probabilistic future reasoning.

History is stored as evidence and mechanisms, not as moral labels. Future
scenarios remain explicitly hypothetical and can inform preparation, but never
authorize execution.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from enum import Enum
from hashlib import sha256
from math import isfinite
from typing import Any


class EpistemicLevel(str, Enum):
    ESTABLISHED_FACT = "ESTABLISHED_FACT"
    PROBABLE_FACT = "PROBABLE_FACT"
    INTERPRETATION = "INTERPRETATION"
    CONTESTED = "CONTESTED"
    HYPOTHESIS = "HYPOTHESIS"
    SCENARIO = "SCENARIO"
    SPECULATION = "SPECULATION"


class HistoricalMode(str, Enum):
    CONSTRUCTION = "CONSTRUCTION"
    DESTRUCTION = "DESTRUCTION"
    RESILIENCE = "RESILIENCE"
    AMBIVALENCE = "AMBIVALENCE"


class FutureDisposition(str, Enum):
    PREPARE = "PREPARE"
    WATCH = "WATCH"
    IGNORE = "IGNORE"


@dataclass(frozen=True)
class HistoricalEvidence:
    id: str
    statement: str
    source: str
    level: EpistemicLevel
    reliability: float
    mode: HistoricalMode
    mechanisms: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.statement.strip() or not self.source.strip():
            raise ValueError("historical evidence id, statement and source are required")
        if not isfinite(self.reliability) or not 0.0 <= self.reliability <= 1.0:
            raise ValueError("historical evidence reliability must be between 0 and 1")
        if not self.mechanisms:
            raise ValueError("historical evidence must name at least one mechanism")


@dataclass(frozen=True)
class HistoricalPattern:
    id: str
    mechanism: str
    evidence_ids: tuple[str, ...]
    support: float
    recurrence: float
    counterevidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.mechanism.strip() or not self.evidence_ids:
            raise ValueError("historical pattern requires an id, mechanism and evidence")
        for name, value in (("support", self.support), ("recurrence", self.recurrence)):
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"historical pattern {name} must be between 0 and 1")


@dataclass(frozen=True)
class FutureScenario:
    id: str
    horizon_years: float
    statement: str
    probability: float
    evidence_ids: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    disposition: FutureDisposition = FutureDisposition.WATCH

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.statement.strip():
            raise ValueError("future scenario id and statement are required")
        for name, value in (("horizon_years", self.horizon_years), ("probability", self.probability)):
            if not isfinite(value):
                raise ValueError(f"future scenario {name} must be finite")
        if self.horizon_years <= 0 or not 0.0 <= self.probability <= 1.0:
            raise ValueError("future scenario horizon must be positive and probability between 0 and 1")
        if not self.assumptions:
            raise ValueError("future scenario assumptions must be explicit")


@dataclass(frozen=True)
class WorldStateSnapshot:
    as_of: str
    canonical_facts: tuple[HistoricalEvidence, ...]
    patterns: tuple[HistoricalPattern, ...]
    scenarios: tuple[FutureScenario, ...]
    fingerprint: str

    @classmethod
    def build(cls, as_of: str, canonical_facts: tuple[HistoricalEvidence, ...],
              patterns: tuple[HistoricalPattern, ...], scenarios: tuple[FutureScenario, ...]) -> "WorldStateSnapshot":
        if not as_of.strip():
            raise ValueError("as_of is required")
        for fact in canonical_facts:
            if fact.level not in {EpistemicLevel.ESTABLISHED_FACT, EpistemicLevel.PROBABLE_FACT}:
                raise ValueError("only established/probable evidence can enter canonical facts")
        payload = {
            "as_of": as_of,
            "canonical_facts": canonical_facts,
            "patterns": patterns,
            "scenarios": scenarios,
        }
        return cls(as_of, canonical_facts, patterns, scenarios, _fingerprint(payload))

    def verify(self) -> bool:
        try:
            return self.fingerprint == _fingerprint({
                "as_of": self.as_of,
                "canonical_facts": self.canonical_facts,
                "patterns": self.patterns,
                "scenarios": self.scenarios,
            })
        except (TypeError, ValueError):
            return False


@dataclass(frozen=True)
class TemporalContext:
    historical_patterns: tuple[HistoricalPattern, ...]
    active_scenarios: tuple[FutureScenario, ...]
    canonical_world: WorldStateSnapshot

    def __post_init__(self) -> None:
        if not self.canonical_world.verify():
            raise ValueError("canonical world snapshot fingerprint is invalid")
        scenario_ids = {scenario.id for scenario in self.canonical_world.scenarios}
        if any(scenario.id not in scenario_ids for scenario in self.active_scenarios):
            raise ValueError("active scenario must belong to the canonical world snapshot")


@dataclass(frozen=True)
class TemporalAssessment:
    confidence: float
    uncertainty: float
    preparation_recommended: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        for name, value in (("confidence", self.confidence), ("uncertainty", self.uncertainty)):
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"temporal assessment {name} must be between 0 and 1")


class HistoricalReasoner:
    @staticmethod
    def derive_patterns(evidence: tuple[HistoricalEvidence, ...]) -> tuple[HistoricalPattern, ...]:
        grouped: dict[str, list[HistoricalEvidence]] = {}
        for item in evidence:
            if item.level in {EpistemicLevel.ESTABLISHED_FACT, EpistemicLevel.PROBABLE_FACT, EpistemicLevel.CONTESTED}:
                for mechanism in item.mechanisms:
                    grouped.setdefault(mechanism, []).append(item)
        patterns: list[HistoricalPattern] = []
        for mechanism, items in sorted(grouped.items()):
            if not items:
                continue
            support = sum(item.reliability for item in items) / len(items)
            recurrence = min(1.0, len(items) / 5.0)
            counterevidence = tuple(item.id for item in items if item.level is EpistemicLevel.CONTESTED)
            patterns.append(HistoricalPattern(
                id=f"PAT-{sha256(mechanism.encode()).hexdigest()[:10]}",
                mechanism=mechanism,
                evidence_ids=tuple(item.id for item in items),
                support=round(support, 4),
                recurrence=round(recurrence, 4),
                counterevidence=counterevidence,
            ))
        return tuple(patterns)


class FutureReasoner:
    @staticmethod
    def assess(scenario: FutureScenario, evidence: tuple[HistoricalEvidence, ...]) -> TemporalAssessment:
        supporting = {item.id: item.reliability for item in evidence}
        support = [supporting[eid] for eid in scenario.evidence_ids if eid in supporting]
        evidence_confidence = sum(support) / len(support) if support else 0.25
        horizon_penalty = min(0.7, scenario.horizon_years / 100.0)
        confidence = max(0.0, min(1.0, scenario.probability * evidence_confidence * (1.0 - horizon_penalty)))
        uncertainty = 1.0 - confidence
        reasons = [f"SCENARIO_PROBABILITY:{scenario.probability:.3f}"]
        if not support:
            reasons.append("NO_DIRECT_EVIDENCE")
        if scenario.horizon_years > 10:
            reasons.append("LONG_HORIZON")
        return TemporalAssessment(round(confidence, 4), round(uncertainty, 4), scenario.disposition is FutureDisposition.PREPARE, tuple(reasons))

    @staticmethod
    def authorize_from_future(*, scenario: FutureScenario) -> bool:
        """Future scenarios can never authorize an action."""
        return False


def build_temporal_context(
    *, as_of: str, evidence: tuple[HistoricalEvidence, ...], scenarios: tuple[FutureScenario, ...]
) -> TemporalContext:
    patterns = HistoricalReasoner.derive_patterns(evidence)
    canonical = tuple(
        item for item in evidence
        if item.level in {EpistemicLevel.ESTABLISHED_FACT, EpistemicLevel.PROBABLE_FACT}
    )
    snapshot = WorldStateSnapshot.build(as_of, canonical, patterns, scenarios)
    return TemporalContext(patterns, scenarios, snapshot)


def _fingerprint(payload: Any) -> str:
    canonical = json.dumps(_normalize(payload), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _normalize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: _normalize(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("temporal model does not fingerprint non-finite values")
    return value


__all__ = [
    "EpistemicLevel", "HistoricalMode", "FutureDisposition", "HistoricalEvidence",
    "HistoricalPattern", "FutureScenario", "WorldStateSnapshot", "TemporalContext",
    "TemporalAssessment", "HistoricalReasoner", "FutureReasoner", "build_temporal_context",
]
