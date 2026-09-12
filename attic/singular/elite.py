from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class EliteScore:
    """Measurable standard for continuous specialist improvement."""

    expertise: float
    evidence: float
    outcome: float
    calibration: float
    learning: float

    @property
    def total(self) -> float:
        values = (self.expertise, self.evidence, self.outcome, self.calibration, self.learning)
        if any(not 0 <= value <= 1 for value in values):
            raise ValueError("Elite scores must be between 0 and 1.")
        return round(sum(values) / len(values), 3)

    @property
    def weakest(self) -> str:
        values: dict[str, float] = {
            "expertise": self.expertise,
            "evidence": self.evidence,
            "outcome": self.outcome,
            "calibration": self.calibration,
            "learning": self.learning,
        }
        return min(values, key=lambda key: values[key])


@dataclass(frozen=True)
class EliteReview:
    agent: str
    score: float
    priority: str
    directive: str
    wealth_relevance: str


class ConflictType(str, Enum):
    FACTUAL = "FACTUAL"
    FORECAST = "FORECAST"
    STRATEGIC = "STRATEGIC"
    RISK = "RISK"
    AUTHORIZATION = "AUTHORIZATION"
    OBJECTIVE = "OBJECTIVE"
    UNSOLVED = "UNSOLVED"


@dataclass(frozen=True)
class ConflictResolution:
    conflict_type: ConflictType
    resolver: str
    action: str
    execution_allowed: bool


class EliteEngine:
    """Continuously raise agent quality without creating agent power struggles."""

    _DIRECTIVES = {
        "expertise": "Deepen domain expertise and stay inside the specialty.",
        "evidence": "Raise source quality and verify critical claims.",
        "outcome": "Optimize for measurable real-world results.",
        "calibration": "Compare forecasts with outcomes and correct confidence.",
        "learning": "Turn failures and wins into explicit reusable lessons.",
    }

    @classmethod
    def review(cls, agent: str, score: EliteScore) -> EliteReview:
        weakest = score.weakest
        return EliteReview(agent, score.total, weakest, cls._DIRECTIVES[weakest], cls.wealth_relevance(weakest))

    @staticmethod
    def wealth_relevance(priority: str) -> str:
        mapping = {
            "expertise": "Increase scarce capabilities that can compound into stronger income and opportunities.",
            "evidence": "Improve decisions by reducing costly errors and avoiding weak opportunities.",
            "outcome": "Prefer measurable gains in stability, earning power, opportunities or patrimony.",
            "calibration": "Improve capital and career decisions by matching confidence to reality.",
            "learning": "Compound successful patterns and eliminate repeated costly mistakes.",
        }
        try:
            return mapping[priority]
        except KeyError as exc:
            raise ValueError(f"Unknown elite priority: {priority}") from exc

    @staticmethod
    def challenge(agent: str, review: EliteReview) -> dict[str, str]:
        return {
            "challenger": "RED_TEAM",
            "target": agent,
            "question": f"What evidence would prove {agent} is not yet elite?",
            "priority": review.priority,
            "directive": review.directive,
            "wealth_test": review.wealth_relevance,
        }

    @staticmethod
    def resolve_conflict(conflict_type: ConflictType) -> ConflictResolution:
        routes = {
            ConflictType.FACTUAL: ("INTELLIGENCE", "Verify the disputed claim against the strongest available evidence.", False),
            ConflictType.FORECAST: ("STRATEGY", "Compare assumptions, scenarios and calibration against prior outcomes.", False),
            ConflictType.STRATEGIC: ("COMMANDER", "Compare options against the objective hierarchy and explicit criteria.", False),
            ConflictType.RISK: ("RED_TEAM", "Stress-test downside, failure modes and irreversible consequences.", False),
            ConflictType.AUTHORIZATION: ("GOVERNOR", "Evaluate policy, capability, risk tier and human-approval requirements.", False),
            ConflictType.OBJECTIVE: ("COMMANDER", "Return to the approved objective hierarchy and resolve the priority conflict.", False),
            ConflictType.UNSOLVED: ("HUMAN", "Escalate when material disagreement remains unresolved or evidence is insufficient.", False),
        }
        resolver, action, execution_allowed = routes[conflict_type]
        return ConflictResolution(conflict_type, resolver, action, execution_allowed)
