from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .audit import AuditTrail
from .autopilot import ApprovalRequest, ApprovalStatus, Autonomy, DelegationContract, MissionManager
from .durable import DurableStore
from .v32_governed_core import GovernedAction, GovernedMission, GovernorDecision


@dataclass(frozen=True)
class MissionState:
    mission_id: str
    status: str
    pending_approvals: int


class DurableMissionRuntime:
    """Durable orchestration seam: restart-safe state, approvals and audit."""

    def __init__(self, store: DurableStore | None = None) -> None:
        self.store = store or DurableStore()
        self.audit = AuditTrail()
        self.manager = MissionManager()
        self.governed = GovernedMission()

    def create_mission(self, objective: str, expected_result: str, **kwargs: Any) -> DelegationContract:
        contract = self.manager.create_contract(objective, expected_result, **kwargs)
        self.store.save_mission(contract)
        self.audit.record("mission_created", "COMMANDER", "CREATED", {"mission_id": contract.mission_id})
        self._persist_new_audit_events()
        return contract

    def route(self, action, mission_id: str | None = None) -> GovernedAction:
        contract = self.store.load_mission(mission_id) if mission_id else None
        if mission_id is not None and contract is None:
            reasons = ("Mission inconnue : exécution refusée par défaut.",)
            self.audit.record("runtime_block", "GOVERNOR", "BLOCKED", {"action_id": action.id, "mission_id": mission_id})
            self._persist_new_audit_events()
            return GovernedAction(action, "BLACK", GovernorDecision(action.id, Autonomy.BLOCK, reasons), False, reasons)
        if contract is None and action.contract_id is not None:
            reasons = ("Action liée à un contrat mais aucun contrat n'a été fourni.",)
            self.audit.record("runtime_block", "GOVERNOR", "BLOCKED", {"action_id": action.id, "reason": reasons[0]})
            self._persist_new_audit_events()
            return GovernedAction(action, "BLACK", GovernorDecision(action.id, Autonomy.BLOCK, reasons), False, reasons)
        if contract is not None:
            if action.contract_id is not None and action.contract_id != contract.mission_id:
                reasons = ("L'action ne correspond pas au contrat de mission fourni.",)
                self.audit.record("runtime_block", "GOVERNOR", "BLOCKED", {"action_id": action.id, "mission_id": contract.mission_id, "contract_id": action.contract_id})
                self._persist_new_audit_events()
                return GovernedAction(action, "BLACK", GovernorDecision(action.id, Autonomy.BLOCK, reasons), False, reasons)
            if action.contract_id is None:
                from dataclasses import replace
                action = replace(action, contract_id=contract.mission_id)
        result = self.governed.route(action, contract)
        if result.governor.approval_id:
            approval = ApprovalRequest(action.id, "; ".join(result.governor.reasons), id=result.governor.approval_id)
            self.store.save_approval(approval)
        self._persist_new_audit_events()
        return result

    def approve(self, approval_id: str) -> None:
        self.store.update_approval(approval_id, ApprovalStatus.APPROVED)
        self.audit.record("approval", "HUMAN", "APPROVED", {"approval_id": approval_id})
        self._persist_new_audit_events()

    def reject(self, approval_id: str) -> None:
        self.store.update_approval(approval_id, ApprovalStatus.REJECTED)
        self.audit.record("approval", "HUMAN", "REJECTED", {"approval_id": approval_id})
        self._persist_new_audit_events()

    def state(self, mission_id: str) -> MissionState:
        contract = self.store.load_mission(mission_id)
        if contract is None:
            raise KeyError(mission_id)
        pending = self.store.pending_approvals()
        return MissionState(mission_id, "ACTIVE", len(pending))

    def _persist_new_audit_events(self) -> None:
        for event in self.audit.events():
            self.store.record_audit(event)
