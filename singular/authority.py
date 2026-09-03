from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AgentPower(str, Enum):
    EVIDENCE = "evidence"
    ANALYSIS = "analysis"
    STRATEGY = "strategy"
    CHALLENGE = "challenge"
    RECOMMEND = "recommend"
    AUTHORIZE = "authorize"
    EXECUTE = "execute"
    SYSTEM_CHANGE = "system_change"
    HUMAN_FINAL = "human_final"


class ConflictType(str, Enum):
    FACTUAL = "factual"
    FORECAST = "forecast"
    STRATEGIC = "strategic"
    RISK = "risk"
    AUTHORIZATION = "authorization"
    OBJECTIVE = "objective"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class AuthorityProfile:
    agent: str
    powers: frozenset[AgentPower]


@dataclass(frozen=True)
class ConflictResolution:
    conflict: ConflictType
    authority: str
    action: str
    execution_allowed: bool = False


PROFILES = {
    "INTELLIGENCE": AuthorityProfile("INTELLIGENCE", frozenset({AgentPower.EVIDENCE})),
    "STRATEGY": AuthorityProfile("STRATEGY", frozenset({AgentPower.ANALYSIS, AgentPower.STRATEGY})),
    "SPECIALIST": AuthorityProfile("SPECIALIST", frozenset({AgentPower.ANALYSIS})),
    "RED_TEAM": AuthorityProfile("RED_TEAM", frozenset({AgentPower.CHALLENGE})),
    "COMMANDER": AuthorityProfile("COMMANDER", frozenset({AgentPower.RECOMMEND})),
    "GOVERNOR": AuthorityProfile("GOVERNOR", frozenset({AgentPower.AUTHORIZE})),
    "EXECUTION": AuthorityProfile("EXECUTION", frozenset({AgentPower.EXECUTE})),
    "SYSTEM_ARCHITECT": AuthorityProfile("SYSTEM_ARCHITECT", frozenset({AgentPower.SYSTEM_CHANGE})),
    "HUMAN": AuthorityProfile("HUMAN", frozenset({AgentPower.HUMAN_FINAL, AgentPower.AUTHORIZE, AgentPower.EXECUTE, AgentPower.SYSTEM_CHANGE})),
}


class AuthorityProtocol:
    """Deterministic separation of advice, authorization and execution.

    No agent can elevate its own authority, alter another agent's mission to win
    a dispute, or convert a recommendation/challenge into execution authority.
    """

    @staticmethod
    def profile(agent: str) -> AuthorityProfile:
        try:
            return PROFILES[agent]
        except KeyError as exc:
            raise ValueError(f"Unknown authority profile: {agent}") from exc

    @classmethod
    def can(cls, agent: str, power: AgentPower) -> bool:
        return power in cls.profile(agent).powers

    @classmethod
    def require(cls, agent: str, power: AgentPower) -> None:
        if not cls.can(agent, power):
            raise PermissionError(f"{agent} cannot exercise {power.value} authority")

    @staticmethod
    def resolve(conflict: ConflictType) -> ConflictResolution:
        table = {
            ConflictType.FACTUAL: ConflictResolution(conflict, "INTELLIGENCE", "Rechercher et vérifier les preuves."),
            ConflictType.FORECAST: ConflictResolution(conflict, "STRATEGY", "Comparer les hypothèses et recalibrer les prévisions."),
            ConflictType.STRATEGIC: ConflictResolution(conflict, "STRATEGY", "Comparer explicitement les options selon les mêmes critères."),
            ConflictType.RISK: ConflictResolution(conflict, "RED_TEAM", "Évaluer le danger et déclencher un blocage si le seuil de sécurité est atteint."),
            ConflictType.AUTHORIZATION: ConflictResolution(conflict, "GOVERNOR", "Appliquer la gouvernance et demander l'humain si la règle l'exige."),
            ConflictType.OBJECTIVE: ConflictResolution(conflict, "COMMANDER", "Revenir à la hiérarchie des objectifs et à la mission source."),
            ConflictType.UNRESOLVED: ConflictResolution(conflict, "HUMAN", "Suspendre l'action et soumettre le désaccord à Thomas."),
        }
        return table[conflict]

    @staticmethod
    def invariant_rules() -> tuple[str, ...]:
        return (
            "advice_is_not_authorization",
            "recommendation_is_not_execution",
            "challenge_is_not_override",
            "system_change_is_not_self_approval",
            "no_agent_can_elevate_its_own_authority",
            "no_agent_can_modify_another_mission_to_win_a_dispute",
            "unresolved_high_consequence_conflict_requires_human_review",
        )
