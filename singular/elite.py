from __future__ import annotations

from dataclasses import dataclass


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
        values = {
            "expertise": self.expertise,
            "evidence": self.evidence,
            "outcome": self.outcome,
            "calibration": self.calibration,
            "learning": self.learning,
        }
        return min(values, key=values.get)


@dataclass(frozen=True)
class EliteReview:
    agent: str
    score: float
    priority: str
    directive: str
    wealth_relevance: str


class EliteEngine:
    """Continuously raise agent quality and convert quality into real-world leverage.

    "Elite" is never a status. It is a measured trajectory. The system optimizes
    for Thomas's durable position: stability first, then earning power, capability,
    opportunities, patrimony and freedom. Wealth is an outcome to improve toward,
    never a guaranteed promise or a reason to bypass risk controls.
    """

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
        return EliteReview(
            agent=agent,
            score=score.total,
            priority=weakest,
            directive=cls._DIRECTIVES[weakest],
            wealth_relevance=cls.wealth_relevance(weakest),
        )

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
        """Create a cross-agent challenge without granting execution authority."""
        return {
            "challenger": "RED_TEAM",
            "target": agent,
            "question": f"What evidence would prove {agent} is not yet elite?",
            "priority": review.priority,
            "directive": review.directive,
            "wealth_test": review.wealth_relevance,
        }
