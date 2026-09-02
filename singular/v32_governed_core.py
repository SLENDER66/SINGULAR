from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Callable

from .autopilot import ActionRequest, Autonomy, DelegationContract, ExecutionBus, GovernorDecision
from .audit import AuditTrail
from .security import ActionPolicy


class Specialist(str, Enum):
    STRATEGY = "STRATEGY"
    INTELLIGENCE = "INTELLIGENCE"
    FINANCE = "FINANCE"
    CAREER = "CAREER"
    BUSINESS = "BUSINESS"
    CAPABILITY = "CAPABILITY"
    LIFE = "LIFE"


@dataclass(frozen=True)
class SpecialistResult:
    specialist: Specialist
    findings: tuple[str, ...]
    confidence: float
    recommended_next_step: str | None = None


@dataclass(frozen=True)
class WorkforcePlan:
    mission_id: str
    specialists: tuple[Specialist, ...]
    rationale: str


@dataclass(frozen=True)
class GovernedAction:
    action: ActionRequest
    policy_tier: str
    governor: GovernorDecision
    can_prepare: bool
    can_execute: bool
    requires_human: bool
    reasons: tuple[str, ...]

    @property
    def allowed(self) -> bool:
        return self.can_prepare


class WorkforceRouter:
    KEYWORDS: dict[Specialist, tuple[str, ...]] = {
        Specialist.FINANCE: ("finance", "revenu", "budget", "dette", "argent", "invest"),
        Specialist.CAREER: ("emploi", "carrière", "cv", "recrut", "travail", "poste"),
        Specialist.BUSINESS: ("business", "entreprise", "client", "vente", "marché"),
        Specialist.CAPABILITY: ("compétence", "formation", "anglais", "apprendre"),
        Specialist.LIFE: ("vie", "logement", "famille", "mobilité", "santé"),
        Specialist.INTELLIGENCE: ("recherche", "actualité", "marché", "donnée", "preuve"),
        Specialist.STRATEGY: ("stratégie", "objectif", "priorité", "décision", "plan"),
    }

    def plan(self, mission_id: str, objective: str) -> WorkforcePlan:
        text = objective.lower()
        selected = [s for s, words in self.KEYWORDS.items() if any(w in text for w in words)]
        if not selected:
            selected = [Specialist.STRATEGY, Specialist.INTELLIGENCE]
        if Specialist.STRATEGY not in selected:
            selected.insert(0, Specialist.STRATEGY)
        return WorkforcePlan(mission_id, tuple(dict.fromkeys(selected)), "Routage par impact sémantique et priorité stratégique.")


class GovernedExecutor:
    def __init__(self, bus: ExecutionBus | None = None, audit: AuditTrail | None = None) -> None:
        self.bus = bus or ExecutionBus()
        self.audit = audit or AuditTrail()

    def route(self, action: ActionRequest, contract: DelegationContract | None = None) -> GovernedAction:
        policy = ActionPolicy.evaluate(action)
        if not policy.can_prepare:
            result = GovernedAction(action, policy.tier.value, GovernorDecision(action.id, Autonomy.BLOCK, policy.reasons), False, False, policy.requires_human, policy.reasons)
            self.audit.record("governance_block", "GOVERNOR", "BLOCKED", {"action_id": action.id, "reasons": list(policy.reasons)})
            return result
        governed_action = replace(action, requires_human=True) if policy.requires_human else action
        decision = self.bus.submit(governed_action, contract)
        governor_can_execute = decision.mode in {Autonomy.EXECUTE_REVERSIBLE, Autonomy.EXECUTE_AUTHORIZED, Autonomy.ESCALATE}
        can_execute = policy.can_execute and governor_can_execute
        if decision.mode == Autonomy.ESCALATE:
            can_execute = policy.can_execute
        result = GovernedAction(action, policy.tier.value, decision, True, can_execute, policy.requires_human or decision.mode == Autonomy.ESCALATE, decision.reasons)
        self.audit.record("governance_route", "GOVERNOR", decision.mode.value, {"action_id": action.id, "policy_tier": policy.tier.value, "can_execute": can_execute})
        return result


@dataclass(frozen=True)
class RedTeamFinding:
    severity: str
    statement: str
    blocking: bool = False


class RedTeamGate:
    def inspect(self, action: ActionRequest, contract: DelegationContract | None) -> tuple[RedTeamFinding, ...]:
        findings: list[RedTeamFinding] = []
        if contract is None and action.risk >= 5:
            findings.append(RedTeamFinding("HIGH", "Action à risque sans contrat explicite.", True))
        if action.risk >= 8:
            findings.append(RedTeamFinding("CRITICAL", "Risque élevé : validation humaine obligatoire.", True))
        elif action.risk >= 5:
            findings.append(RedTeamFinding("HIGH", "Risque modéré/élevé : validation humaine recommandée.", False))
        if action.reversibility <= 2:
            findings.append(RedTeamFinding("CRITICAL", "Action faiblement réversible.", True))
        # Sensitivity is an authorization signal, not an automatic hard block.
        # ActionPolicy/capabilities can require human approval while preserving
        # the approval lifecycle needed to authorize the action explicitly.
        if action.sensitive:
            findings.append(RedTeamFinding("HIGH", "Action sensible : contrôle d'autorité renforcé.", False))
        if contract and action.name in contract.forbidden_actions:
            findings.append(RedTeamFinding("CRITICAL", "Action interdite par le contrat.", True))
        return tuple(findings)


class GovernedMission:
    def __init__(self) -> None:
        self.router = WorkforceRouter()
        self.executor = GovernedExecutor()
        self.red_team = RedTeamGate()

    def plan(self, contract: DelegationContract) -> WorkforcePlan:
        return self.router.plan(contract.mission_id, contract.objective)

    def route(self, action: ActionRequest, contract: DelegationContract | None = None) -> GovernedAction:
        findings = self.red_team.inspect(action, contract)
        if any(f.blocking for f in findings):
            reasons = tuple(f.statement for f in findings if f.blocking)
            self.executor.audit.record("red_team_block", "ADVERSARY_CORE", "BLOCKED", {"action_id": action.id, "reasons": list(reasons)})
            return GovernedAction(action, "RED", GovernorDecision(action.id, Autonomy.BLOCK, reasons), False, False, True, reasons)
        return self.executor.route(action, contract)
