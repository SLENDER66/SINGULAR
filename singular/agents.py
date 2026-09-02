from __future__ import annotations
from dataclasses import dataclass
from .engine import SingularEngine
from .models import Action, Decision, WorldModel

@dataclass
class Commander:
    name: str = 'COMMANDER'

    def triage(self, actions: list[Action]) -> dict:
        ranked = SingularEngine.rank_actions(actions)
        return {
            'mission': 'Maximiser le progrès réel sous contraintes.',
            'best_next_action': ranked[0][0].model_dump() if ranked else None,
            'ranked': [{'action': a.model_dump(), 'score': round(s, 3)} for a, s in ranked],
        }

    def decide(self, decision: Decision, consequence: float = 5, reversibility: float = 5) -> dict:
        assessment = SingularEngine.decision_assessment(decision, consequence, reversibility)
        decision.red_team = SingularEngine.red_team(decision)
        decision.validation_required = assessment.halt or consequence >= 8 or reversibility <= 2
        decision.status = 'PROPOSED'
        return {'decision': decision, 'assessment': assessment}

class RedTeam:
    name = 'ADVERSARY_CORE'
    def challenge(self, decision: Decision) -> list[str]:
        return SingularEngine.red_team(decision)

class LearningEngine:
    name = 'LEARNING_ENGINE'
    def learn(self, decision: Decision) -> dict:
        if decision.actual_result is None:
            return {'status': 'WAITING', 'reason': 'Résultat réel absent.'}
        lesson = decision.lesson or 'Comparer systématiquement prévision et résultat avant de modifier une règle.'
        return {'status': 'LEARNED', 'lesson': lesson, 'decision_id': decision.id}

class SystemArchitect:
    name = 'SYSTEM_ARCHITECT'
    def propose_change(self, evidence: str, problem: str, modification: str, success_metric: str) -> dict:
        return {
            'problem': problem,
            'evidence': evidence,
            'proposed_modification': modification,
            'success_metric': success_metric,
            'approval_required': True,
        }
