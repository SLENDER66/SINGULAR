"""JARVIS runtime: translate a human request into SINGULAR-governed work.

JARVIS is the interface/runtime of SINGULAR, not a second authority model.
Claude proposes; deterministic trajectory logic prioritizes; SINGULAR governs.
Execution remains behind SINGULAR's validated execution boundary.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite
from typing import Any

from ..autopilot import ActionRequest
from ..mission_runtime import DurableMissionRuntime
from .llm import LLMProvider, LLMResponse
from .trajectory import TrajectoryCandidate, TrajectoryPriority, prioritize


_SYSTEM = """Tu es JARVIS, l'interface de raisonnement de SINGULAR.
SINGULAR est l'autorité. Tu proposes, tu ne décides pas et tu n'exécutes rien.

Ta boucle conceptuelle est : OBSERVE -> UNDERSTAND -> DIAGNOSE -> PRIORITIZE
-> PLAN -> GOVERN -> EXECUTE -> VERIFY -> AUDIT -> LEARN -> REPLAN.
La priorisation doit viser la trajectoire globale, pas seulement l'action locale.
Cherche le principal facteur limitant et favorise les interventions qui ont un
fort effet de levier sur plusieurs dépendances. Respecte les contraintes de
capacité. Quand la causalité est incertaine, propose d'abord un test réversible
et peu coûteux plutôt que d'adopter une hypothèse comme un fait.
Favorise, à risque comparable, l'apprentissage, la récurrence, l'ownership,
la réversibilité et l'optionalité. Ne transforme jamais une hypothèse en fait.
Ces principes décrivent des candidats ; le code déterministe et SINGULAR
restent responsables de la priorité, de la gouvernance et de l'exécution.

N'invente aucun fait externe : si une information manque, indique-la dans
context_needed. Les valeurs numériques sont des estimations proposées, pas des
autorisations.

Schéma exact :
{
  "objective": "...",
  "expected_result": "...",
  "context_needed": ["..."],
  "actions": [
    {
      "name": "...",
      "description": "...",
      "impact": 0,
      "risk": 0,
      "reversibility": 0,
      "leverage": 5,
      "dependency": 5,
      "uncertainty": 5,
      "cost": 5,
      "learning": 5,
      "ownership": 0,
      "recurrence": 0,
      "requires_human": false,
      "sensitive": false,
      "capability": null
    }
  ]
}

Tous les scores sont entre 0 et 10. Une action sensible ou nécessitant un
jugement humain doit être marquée comme telle. Le champ capability est une
proposition non autoritative et sera ignoré par le runtime pour empêcher le
modèle de sélectionner une permission. Ne mets jamais de code exécutable, de
clé, de secret ou de commande shell dans capability.
"""


@dataclass(frozen=True)
class ProposedAction:
    name: str
    description: str
    impact: float
    risk: float
    reversibility: float
    leverage: float = 5.0
    dependency: float = 5.0
    uncertainty: float = 5.0
    cost: float = 5.0
    learning: float = 5.0
    ownership: float = 0.0
    recurrence: float = 0.0
    requires_human: bool = False
    sensitive: bool = False
    capability: str | None = None

    def trajectory_candidate(self) -> TrajectoryCandidate:
        return TrajectoryCandidate(
            name=self.name,
            impact=self.impact,
            risk=self.risk,
            reversibility=self.reversibility,
            leverage=self.leverage,
            dependency=self.dependency,
            uncertainty=self.uncertainty,
            cost=self.cost,
            learning=self.learning,
            ownership=self.ownership,
            recurrence=self.recurrence,
        )


@dataclass(frozen=True)
class MissionProposal:
    objective: str
    expected_result: str
    context_needed: tuple[str, ...]
    actions: tuple[ProposedAction, ...]
    llm: LLMResponse

    @property
    def priorities(self) -> tuple[TrajectoryPriority, ...]:
        """Return deterministic priorities in proposal order."""
        return tuple(prioritize(action.trajectory_candidate()) for action in self.actions)


class JarvisParseError(ValueError):
    """The model response is not a valid, bounded mission proposal."""


class JarvisRuntime:
    """User-facing orchestration seam above SINGULAR's durable core."""

    DEFAULT_MAX_TOKENS = 1200
    DEFAULT_MAX_ACTIONS = 8
    DEFAULT_MAX_REQUEST_CHARS = 12000
    DEFAULT_MAX_CONTEXT_CHARS = 20000

    def __init__(
        self,
        provider: LLMProvider,
        mission_runtime: DurableMissionRuntime | None = None,
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_actions: int = DEFAULT_MAX_ACTIONS,
        max_request_chars: int = DEFAULT_MAX_REQUEST_CHARS,
        max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    ) -> None:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if max_actions < 1:
            raise ValueError("max_actions must be positive")
        if max_request_chars < 1 or max_context_chars < 1:
            raise ValueError("input limits must be positive")
        self.provider = provider
        self.missions = mission_runtime or DurableMissionRuntime()
        self.max_tokens = max_tokens
        self.max_actions = max_actions
        self.max_request_chars = max_request_chars
        self.max_context_chars = max_context_chars

    def propose(self, request: str, *, context: str = "") -> MissionProposal:
        if not request.strip():
            raise ValueError("request must not be blank")
        request = request.strip()
        context = context.strip()
        if len(request) > self.max_request_chars:
            raise ValueError("request exceeds configured size limit")
        if len(context) > self.max_context_chars:
            raise ValueError("context exceeds configured size limit")
        response = self.provider.complete(
            system=_SYSTEM,
            user=f"REQUEST:\n{request}\n\nCONTEXT:\n{context}",
            max_tokens=self.max_tokens,
        )
        data = self._decode(response.text)
        return MissionProposal(
            objective=self._text(data, "objective"),
            expected_result=self._text(data, "expected_result"),
            context_needed=self._strings(data, "context_needed"),
            actions=self._actions(data, max_actions=self.max_actions),
            llm=response,
        )

    def route(self, proposal: MissionProposal):
        """Persist the mission and route actions in deterministic priority order.

        Trajectory priority changes ordering only. Every action still crosses
        DurableMissionRuntime, which owns governance, approvals, audit and
        replay protection. In particular, the LLM-provided ``capability`` field
        is never copied into ActionRequest: permissions must come from trusted
        SINGULAR composition, never from model output.
        """
        contract = self.missions.create_mission(
            proposal.objective,
            proposal.expected_result,
        )
        ranked = sorted(
            enumerate(proposal.actions),
            key=lambda item: (-prioritize(item[1].trajectory_candidate()).score, item[0]),
        )
        decisions = tuple(
            self.missions.route(
                ActionRequest(
                    name=action.name,
                    description=action.description,
                    impact=action.impact,
                    risk=action.risk,
                    reversibility=action.reversibility,
                    requires_human=action.requires_human,
                    sensitive=action.sensitive,
                    contract_id=contract.mission_id,
                    capability=None,
                ),
                contract.mission_id,
            )
            for _, action in ranked
        )
        return contract, decisions

    @staticmethod
    def _decode(text: str) -> dict[str, Any]:
        raw = text.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            if len(lines) < 3 or not lines[-1].strip().startswith("```"):
                raise JarvisParseError("Incomplete JSON code fence")
            raw = "\n".join(lines[1:-1]).strip()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            raise JarvisParseError("LLM response is not valid JSON") from None
        if not isinstance(value, dict):
            raise JarvisParseError("Mission proposal must be a JSON object")
        return value

    @staticmethod
    def _text(data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise JarvisParseError(f"{key} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _strings(data: dict[str, Any], key: str) -> tuple[str, ...]:
        value = data.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
            raise JarvisParseError(f"{key} must be a list of non-empty strings")
        return tuple(item.strip() for item in value)

    @classmethod
    def _actions(cls, data: dict[str, Any], *, max_actions: int = DEFAULT_MAX_ACTIONS) -> tuple[ProposedAction, ...]:
        value = data.get("actions")
        if not isinstance(value, list):
            raise JarvisParseError("actions must be a list")
        if not value:
            raise JarvisParseError("at least one proposed action is required")
        if len(value) > max_actions:
            raise JarvisParseError("actions exceed configured proposal limit")
        actions: list[ProposedAction] = []
        for item in value:
            if not isinstance(item, dict):
                raise JarvisParseError("each action must be an object")
            numbers: dict[str, float] = {}
            for key in (
                "impact", "risk", "reversibility", "leverage", "dependency",
                "uncertainty", "cost", "learning", "ownership", "recurrence",
            ):
                number = item.get(key, ProposedAction.__dataclass_fields__[key].default)
                if isinstance(number, bool) or not isinstance(number, (int, float)) or not isfinite(number) or not 0 <= number <= 10:
                    raise JarvisParseError(f"action {key} must be finite and between 0 and 10")
                numbers[key] = float(number)
            capability = item.get("capability")
            if capability is not None and (not isinstance(capability, str) or not capability.strip()):
                raise JarvisParseError("capability must be null or a non-empty string")
            actions.append(
                ProposedAction(
                    name=cls._text(item, "name"),
                    description=cls._text(item, "description"),
                    **numbers,
                    requires_human=cls._bool(item, "requires_human"),
                    sensitive=cls._bool(item, "sensitive"),
                    capability=capability.strip() if isinstance(capability, str) else None,
                )
            )
        return tuple(actions)

    @staticmethod
    def _bool(data: dict[str, Any], key: str) -> bool:
        value = data.get(key)
        if not isinstance(value, bool):
            raise JarvisParseError(f"{key} must be boolean")
        return value


__all__ = ["JarvisParseError", "JarvisRuntime", "MissionProposal", "ProposedAction"]
