"""JARVIS runtime: translate a human request into SINGULAR-governed work.

This first runtime slice intentionally stops at governance. Claude can propose
missions and actions, but it cannot execute them. DurableMissionRuntime owns the
mission and Governor decision; later slices will attach the validated execution
pipeline and tools without creating a second authority model.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite
from typing import Any

from ..autopilot import ActionRequest
from ..mission_runtime import DurableMissionRuntime
from .llm import LLMProvider, LLMResponse


_SYSTEM = """Tu es JARVIS, l'interface de raisonnement de SINGULAR.
SINGULAR est l'autorité. Tu proposes, tu ne décides pas et tu n'exécutes rien.
Transforme la demande humaine en proposition JSON strictement structurée.
N'invente aucun fait externe : si une information manque, indique-la comme
unknown dans le champ context_needed.

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
      "requires_human": false,
      "sensitive": false,
      "capability": null
    }
  ]
}
Les scores impact/risk/reversibility sont des propositions et doivent rester
entre 0 et 10. Une action sensible ou nécessitant un jugement humain doit être
marquée comme telle. Ne mets jamais de code exécutable, de clé, de secret ou
de commande shell dans capability.
"""


@dataclass(frozen=True)
class ProposedAction:
    name: str
    description: str
    impact: float
    risk: float
    reversibility: float
    requires_human: bool = False
    sensitive: bool = False
    capability: str | None = None


@dataclass(frozen=True)
class MissionProposal:
    objective: str
    expected_result: str
    context_needed: tuple[str, ...]
    actions: tuple[ProposedAction, ...]
    llm: LLMResponse


class JarvisParseError(ValueError):
    """The model response is not a valid, bounded mission proposal."""


class JarvisRuntime:
    """User-facing orchestration seam above SINGULAR's durable core."""

    def __init__(self, provider: LLMProvider, mission_runtime: DurableMissionRuntime | None = None, *, max_tokens: int = 1200) -> None:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        self.provider = provider
        self.missions = mission_runtime or DurableMissionRuntime()
        self.max_tokens = max_tokens

    def propose(self, request: str, *, context: str = "") -> MissionProposal:
        if not request.strip():
            raise ValueError("request must not be blank")
        response = self.provider.complete(
            system=_SYSTEM,
            user=f"REQUEST:\n{request.strip()}\n\nCONTEXT:\n{context.strip()}",
            max_tokens=self.max_tokens,
        )
        data = self._decode(response.text)
        return MissionProposal(
            objective=self._text(data, "objective"),
            expected_result=self._text(data, "expected_result"),
            context_needed=self._strings(data, "context_needed"),
            actions=self._actions(data),
            llm=response,
        )

    def route(self, proposal: MissionProposal):
        """Persist the proposal and route every action through SINGULAR.

        This method deliberately returns governance results only. There is no
        direct handler call here, so the provider cannot smuggle execution past
        the durable execution boundary.
        """
        contract = self.missions.create_mission(
            proposal.objective,
            proposal.expected_result,
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
                    capability=action.capability,
                ),
                contract.mission_id,
            )
            for action in proposal.actions
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
        except json.JSONDecodeError as exc:
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
    def _actions(cls, data: dict[str, Any]) -> tuple[ProposedAction, ...]:
        value = data.get("actions")
        if not isinstance(value, list):
            raise JarvisParseError("actions must be a list")
        if not value:
            raise JarvisParseError("at least one proposed action is required")
        actions: list[ProposedAction] = []
        for item in value:
            if not isinstance(item, dict):
                raise JarvisParseError("each action must be an object")
            numbers: dict[str, float] = {}
            for key in ("impact", "risk", "reversibility"):
                number = item.get(key)
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
