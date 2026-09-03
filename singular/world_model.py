from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EpistemicType(str, Enum):
    FACT = "FACT"
    HYPOTHESIS = "HYPOTHESIS"
    ESTIMATE = "ESTIMATE"
    OBJECTIVE = "OBJECTIVE"
    ASPIRATION = "ASPIRATION"
    UNKNOWN = "UNKNOWN"


class TemporalState(str, Enum):
    PAST = "PAST"
    CURRENT = "CURRENT"
    PLANNED = "PLANNED"
    FUTURE = "FUTURE"
    EXPIRED = "EXPIRED"


class OpportunityClass(str, Enum):
    NORMAL = "NORMAL"
    OUTLIER = "OUTLIER"


@dataclass(frozen=True)
class WorldFact:
    key: str
    value: Any
    epistemic: EpistemicType
    temporal: TemporalState = TemporalState.CURRENT
    confidence: float = 1.0
    source: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("World fact key cannot be empty")
        if not 0 <= self.confidence <= 1:
            raise ValueError("World fact confidence must be between 0 and 1")
        if self.epistemic == EpistemicType.FACT and not self.source:
            raise ValueError("FACT requires a source")


@dataclass(frozen=True)
class WorldOpportunity:
    name: str
    potential: float
    probability: float
    cost: float
    time: float
    risk: float
    reversibility: float
    window: str | None = None
    synergies: tuple[str, ...] = ()
    classification: OpportunityClass = OpportunityClass.NORMAL
    epistemic: EpistemicType = EpistemicType.HYPOTHESIS
    confidence: float = 0.5
    source: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        for name, value in (("potential", self.potential), ("probability", self.probability), ("reversibility", self.reversibility)):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.cost < 0 or self.time < 0 or self.risk < 0:
            raise ValueError("cost, time and risk cannot be negative")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if self.epistemic == EpistemicType.FACT and not self.source:
            raise ValueError("FACT opportunities require a source")

    @property
    def leverage_score(self) -> float:
        upside = self.potential * self.probability
        friction = 1 + self.cost + self.time + self.risk
        return round(upside * (1 + self.reversibility) / friction, 4)


@dataclass
class WorldModel:
    """Single shared, epistemically typed representation of Thomas's situation."""

    facts: dict[str, WorldFact] = field(default_factory=dict)
    objectives: dict[str, WorldFact] = field(default_factory=dict)
    resources: dict[str, WorldFact] = field(default_factory=dict)
    constraints: dict[str, WorldFact] = field(default_factory=dict)
    projects: dict[str, WorldFact] = field(default_factory=dict)
    risks: dict[str, WorldFact] = field(default_factory=dict)
    opportunities: dict[str, WorldOpportunity] = field(default_factory=dict)
    decisions: dict[str, WorldFact] = field(default_factory=dict)
    results: dict[str, WorldFact] = field(default_factory=dict)

    def upsert(self, category: str, item: WorldFact) -> None:
        collection = getattr(self, category, None)
        if not isinstance(collection, dict):
            raise ValueError(f"Unknown world-model category: {category}")
        collection[item.key] = item

    def add_opportunity(self, opportunity: WorldOpportunity) -> None:
        self.opportunities[opportunity.name] = opportunity

    def get(self, category: str, key: str) -> WorldFact | WorldOpportunity | None:
        collection = getattr(self, category, None)
        if not isinstance(collection, dict):
            raise ValueError(f"Unknown world-model category: {category}")
        return collection.get(key)

    def unknowns(self) -> list[WorldFact]:
        collections = (self.facts, self.objectives, self.resources, self.constraints, self.projects, self.risks, self.decisions, self.results)
        return [item for collection in collections for item in collection.values() if item.epistemic == EpistemicType.UNKNOWN]

    def outlier_opportunities(self) -> list[WorldOpportunity]:
        return sorted(
            (item for item in self.opportunities.values() if item.classification == OpportunityClass.OUTLIER),
            key=lambda item: item.leverage_score,
            reverse=True,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "facts": len(self.facts),
            "objectives": len(self.objectives),
            "resources": len(self.resources),
            "constraints": len(self.constraints),
            "projects": len(self.projects),
            "risks": len(self.risks),
            "opportunities": len(self.opportunities),
            "decisions": len(self.decisions),
            "results": len(self.results),
            "unknowns": len(self.unknowns()),
            "outlier_opportunities": len(self.outlier_opportunities()),
        }
