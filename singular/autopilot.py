from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from uuid import uuid4


class Autonomy(str, Enum):
    OBSERVE = "OBSERVE"
    ANALYZE = "ANALYZE"
    PREPARE = "PREPARE"
    EXECUTE_REVERSIBLE = "EXECUTE_REVERSIBLE"
    EXECUTE_AUTHORIZED = "EXECUTE_AUTHORIZED"
    ESCALATE = "ESCALATE"
    BLOCK = "BLOCK"


class ActionClass(str, Enum):
    AUTOMATABLE = "AUTOMATABLE"
    AI_DELEGABLE = "AI_DELEGABLE"
    AI_PREPARABLE = "AI_PREPARABLE"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class DelegationContract:
    mission_id: str
    objective: str
    expected_result: str
    autonomy: Autonomy = Autonomy.PREPARE
    budget_limit: Optional[float] = None
    deadline: Optional[str] = None
    forbidden_actions: tuple[str, ...] = ()
    escalation_conditions: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()


@dataclass
class ActionRequest:
    name: str
    description: str
    impact: float
    risk: float
    reversibility: float
    requires_human: bool = False
    sensitive: bool = False
    contract_id: Optional[str] = None
    id: str = field(default_factory=lambda: "ACT-" + uuid4().hex[:8])
    capability: str | None = None


@dataclass
class ApprovalRequest:
    action_id: str
    reason: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    id: str = field(default_factory=lambda: "APR-" + uuid4().hex[:8])


@dataclass(frozen=True)
class GovernorDecision:
    action_id: str
    mode: Autonomy
    reasons: tuple[str, ...]
    approval_id: Optional[str] = None


class HumanTaskFilter:
    """Minimize human workload while preserving human-only judgment."""

    @staticmethod
    def classify(action: ActionRequest) -> ActionClass:
        if action.requires_human or action.sensitive:
            return ActionClass.HUMAN_REQUIRED
        if action.risk <= 2 and action.reversibility >= 7:
            return ActionClass.AUTOMATABLE
        if action.risk <= 4 and action.reversibility >= 5:
            return ActionClass.AI_DELEGABLE
        return ActionClass.AI_PREPARABLE


class Governor:
    """Fail-closed authorization layer for actions.

    A contract grants only the authority explicitly attached to that mission.
    Contract identity is therefore part of the authorization decision, not a
    caller-supplied hint that can be silently ignored.
    """

    @staticmethod
    def evaluate(action: ActionRequest, contract: Optional[DelegationContract]) -> GovernorDecision:
        reasons: list[str] = []
        if contract is not None and action.contract_id not in (None, contract.mission_id):
            return GovernorDecision(
                action.id,
                Autonomy.BLOCK,
                ("L'action référence un contrat différent du contrat de mission.",),
            )
        if contract and action.name in contract.forbidden_actions:
            return GovernorDecision(
                action.id,
                Autonomy.BLOCK,
                ("Action explicitement interdite par le contrat.",),
            )
        if action.requires_human or action.sensitive:
            reasons.append("Jugement humain requis ou opération sensible.")
            return GovernorDecision(action.id, Autonomy.ESCALATE, tuple(reasons), "APR-" + uuid4().hex[:8])
        if action.risk >= 8 or action.reversibility <= 2:
            reasons.append("Risque élevé ou faible réversibilité.")
            return GovernorDecision(action.id, Autonomy.ESCALATE, tuple(reasons), "APR-" + uuid4().hex[:8])
        if contract is None:
            reasons.append("Aucun contrat d'autorisation explicite.")
            return GovernorDecision(action.id, Autonomy.PREPARE, tuple(reasons))
        if contract.autonomy in (Autonomy.EXECUTE_REVERSIBLE, Autonomy.EXECUTE_AUTHORIZED):
            return GovernorDecision(action.id, contract.autonomy, ("Action couverte par le contrat d'autonomie.",))
        return GovernorDecision(action.id, Autonomy.PREPARE, ("Contrat autorise la préparation mais pas l'exécution.",))


class ExecutionBus:
    def __init__(self):
        self.approvals: dict[str, ApprovalRequest] = {}
        self.completed: list[str] = []

    def submit(self, action: ActionRequest, contract: Optional[DelegationContract] = None) -> GovernorDecision:
        decision = Governor.evaluate(action, contract)
        if decision.mode == Autonomy.ESCALATE:
            approval = ApprovalRequest(
                action.id,
                "; ".join(decision.reasons),
                id=decision.approval_id or "APR-" + uuid4().hex[:8],
            )
            self.approvals[approval.id] = approval
        return decision

    def approve(self, approval_id: str) -> None:
        approval = self.approvals.get(approval_id)
        if approval is None:
            raise KeyError(f"Unknown approval: {approval_id}")
        approval.status = ApprovalStatus.APPROVED

    def reject(self, approval_id: str) -> None:
        approval = self.approvals.get(approval_id)
        if approval is None:
            raise KeyError(f"Unknown approval: {approval_id}")
        approval.status = ApprovalStatus.REJECTED

    def pending(self) -> list[ApprovalRequest]:
        return [a for a in self.approvals.values() if a.status == ApprovalStatus.PENDING]


class MissionManager:
    def __init__(self):
        self.contracts: dict[str, DelegationContract] = {}
        self.bus = ExecutionBus()

    def create_contract(self, objective: str, expected_result: str, **kwargs) -> DelegationContract:
        mission_id = "MIS-" + uuid4().hex[:8]
        contract = DelegationContract(mission_id, objective, expected_result, **kwargs)
        self.contracts[mission_id] = contract
        return contract

    def route(self, action: ActionRequest, mission_id: Optional[str] = None) -> GovernorDecision:
        if mission_id is None:
            return self.bus.submit(action, None)
        contract = self.contracts.get(mission_id)
        if contract is None:
            return GovernorDecision(
                action.id,
                Autonomy.BLOCK,
                ("Mission inconnue: aucune autorisation ne peut être déduite.",),
            )
        return self.bus.submit(action, contract)
