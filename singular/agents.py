from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .engine import SingularEngine
from .models import Action, Decision, Status


@dataclass
class Commander:
    """SINGULAR's simple decision core: one objective, one priority, one next move."""

    name: str = "COMMANDER"

    def triage(self, actions: list[Action]) -> dict:
        ranked = SingularEngine.rank_actions(actions)
        return {
            "mission": "Maximiser le progrès réel sous contraintes.",
            "best_next_action": ranked[0][0].model_dump() if ranked else None,
            "ranked": [{"action": a.model_dump(), "score": round(s, 3)} for a, s in ranked],
        }

    def command(
        self,
        objective: str,
        actions: list[Action],
        *,
        blockers: list[str] | None = None,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a compact operating brief without executing anything.

        The Commander deliberately does only four things: focus the objective,
        select the highest-leverage next action, expose blockers, and define the
        decision gate. Execution remains governed elsewhere.
        """
        blockers = list(blockers or [])
        state = dict(state or {})
        ranked = SingularEngine.rank_actions(actions)
        best = ranked[0][0] if ranked else None

        if blockers:
            next_move = "Lever le blocage principal avant d'ajouter du travail."
            mode = "BLOCKED"
        elif best is None:
            next_move = "Obtenir les informations minimales nécessaires pour choisir une action."
            mode = "CLARIFY"
        else:
            next_move = best.description
            mode = "ACT"

        risk = float(getattr(best, "risk", 0.0)) if best is not None else 0.0
        human_gate = risk >= 8.0 or (best is not None and getattr(best, "reversibility", 5.0) <= 2.0)

        return {
            "objective": objective,
            "mode": mode,
            "priority": best.model_dump() if best is not None else None,
            "next_move": next_move,
            "blockers": blockers,
            "human_gate": human_gate,
            "state": state,
            "principle": "Faire moins, mais faire ce qui change réellement la situation.",
        }

    def decide(self, decision: Decision, consequence: float = 5, reversibility: float = 5) -> dict:
        assessment = SingularEngine.decision_assessment(decision, consequence, reversibility)
        decision.red_team = SingularEngine.red_team(decision)
        decision.validation_required = assessment.halt or consequence >= 8 or reversibility <= 2
        decision.status = Status.PROPOSED
        return {"decision": decision, "assessment": assessment}


class RedTeam:
    name = "ADVERSARY_CORE"

    def challenge(self, decision: Decision) -> list[str]:
        return SingularEngine.red_team(decision)


class LearningEngine:
    name = "LEARNING_ENGINE"

    def learn(self, decision: Decision) -> dict:
        if decision.actual_result is None:
            return {"status": "WAITING", "reason": "Résultat réel absent."}
        lesson = decision.lesson or "Comparer systématiquement prévision et résultat avant de modifier une règle."
        return {"status": "LEARNED", "lesson": lesson, "decision_id": decision.id}


class SystemArchitect:
    name = "SYSTEM_ARCHITECT"

    def propose_change(self, evidence: str, problem: str, modification: str, success_metric: str) -> dict:
        return {
            "problem": problem,
            "evidence": evidence,
            "proposed_modification": modification,
            "success_metric": success_metric,
            "approval_required": True,
        }
