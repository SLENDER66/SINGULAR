from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
from .models import Action, Opportunity, Decision

@dataclass(frozen=True)
class DecisionAssessment:
    score: float
    confidence: float
    halt: bool
    reasons: list[str]

class SingularEngine:
    @staticmethod
    def action_score(a: Action) -> float:
        upside = (a.impact * 2.0 + a.urgency * 0.9 + a.leverage * 2.0 + a.optionality * 0.9 + a.reversibility * 0.35)
        friction = 1 + a.effort * 0.55 + a.risk * 0.45
        return upside / friction

    @classmethod
    def rank_actions(cls, actions: list[Action]) -> list[tuple[Action, float]]:
        return sorted(((a, cls.action_score(a)) for a in actions), key=lambda x: x[1], reverse=True)

    @staticmethod
    def opportunity_score(o: Opportunity) -> float:
        upside = o.impact * o.probability * (1 + o.leverage/10) * (1 + o.optionality/10) * (0.7 + o.reversibility/10)
        cost = 1 + o.cost + o.risk * 0.7
        return upside / cost

    @staticmethod
    def bottleneck(signals: dict[str, float]) -> str:
        return min(signals, key=signals.get) if signals else 'UNKNOWN'

    @staticmethod
    def decision_assessment(decision: Decision, consequence: float = 5.0, reversibility: float = 5.0) -> DecisionAssessment:
        reasons: list[str] = []
        unknown_penalty = min(0.6, 0.15 * len(decision.unknowns))
        base = max(0.0, decision.confidence - unknown_penalty)
        irreversible = reversibility <= 3
        high_consequence = consequence >= 8
        halt = high_consequence and irreversible and (len(decision.unknowns) > 0 or decision.confidence < 0.7)
        if decision.unknowns: reasons.append('Inconnues critiques présentes.')
        if irreversible: reasons.append('Action peu réversible.')
        if high_consequence: reasons.append('Conséquence potentiellement élevée.')
        if halt: reasons.append('HALT : validation humaine / information supplémentaire requise.')
        return DecisionAssessment(score=base, confidence=base, halt=halt, reasons=reasons)

    @staticmethod
    def red_team(decision: Decision) -> list[str]:
        return [
            'Quelle hypothèse critique pourrait être fausse ?',
            'Quelle information, si elle changeait, inverserait la recommandation ?',
            'Quel est le scénario défavorable plausible ?',
            'Existe-t-il une version plus petite, réversible ou testable de cette décision ?',
            'Quel est le coût d’opportunité de cette décision ?',
        ]

    @staticmethod
    def robust_choice(options: list[tuple[str, float, float]]) -> str | None:
        # (name, expected_value, downside). Prefer high expected value with controlled downside.
        if not options: return None
        return max(options, key=lambda x: x[1] - 0.8 * abs(x[2]))[0]
