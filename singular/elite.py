from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EliteScore:
    """Small, measurable standard for continuous specialist improvement."""

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


class EliteEngine:
    """One rule: every agent must improve from evidence, not from ego."""

    @staticmethod
    def review(agent: str, score: EliteScore) -> EliteReview:
        directives = {
            "expertise": "Deepen domain expertise and stay inside the specialty.",
            "evidence": "Raise source quality and verify critical claims.",
            "outcome": "Optimize for measurable real-world results.",
            "calibration": "Compare forecasts with outcomes and correct confidence.",
            "learning": "Turn failures and wins into explicit reusable lessons.",
        }
        return EliteReview(agent, score.total, score.weakest, directives[score.weakest])
