from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

from .audit import AuditTrail
from .autopilot import ApprovalRequest, ApprovalStatus, Autonomy, DelegationContract
from .durable import DurableStore, MissionStatus
from .v32_governed_core import GovernedAction, GovernedMission, GovernorDecision


@dataclass(frozen=True)
class MissionState:
    mission_id: str
    status: MissionStatus
    pending_approvals: int


class DurableMissionRuntime:
    """Durable orchestration seam: restart-safe state, approvals and audit."""

    def __init__(self, store: DurableStore | None = None) -> None:
        self.store = store or DurableStore()
        self.audit = AuditTrail()
        self.governed = GovernedMission()

    def create_mission(self, objective: str, expected_result: str, **kwargs: Any) -> DelegationContract:
        contract = DelegationContract(
            mission_id="MIS-" + uuid4().hex[:8],
            objective=objective,
            expected_result=expected_result,
            **kwargs,
        )
        self.store.save_mission(contract)
        self.audit.record("mission_created", "COMMANDER", MissionStatus.CREATED.value, {"mission_id": contract.mission_id})
        self._persist_new_audit_events()
        return contract

    def route(self, action, mission_id: str | None = None) -> GovernedAction:
        contract = self.store.load_mission(mission_id) if mission_id else None
        if mission_id is not None and contract is None:
            reasons = ("Mission inconnue : exécution refusée par défaut.",)
            self.audit.record("runtime_block", "GOVERNOR", MissionStatus.BLOCKED.value, {"action_id": action.id, "mission_id": mission_id})
            self._persist_new_audit_events()
            return GovernedAction(action, "BLACK", GovernorDecision(action.id, Autonomy.BLOCK, reasons), False, reasons)
        if contract is None and action.contract_id is not None:
            reasons = ("Action liée à un contrat mais aucun contrat n'a été fourni.",)
            self.audit.record("runtime_block", "GOVERNOR", MissionStatus.BLOCKED.value, {"action_id": action.id, "reason": reasons[0]})
            self._persist_new_audit_events()
            return GovernedAction(action, "BLACK", GovernorDecision(action.id, Autonomy.BLOCK, reasons), False, reasons)
        if contract is not None:
            if action.contract_id is not None and action.contract_id != contract.mission_id:
                reasons = ("L'action ne correspond pas au contrat de mission fourni.",)
                self.audit.record("runtime_block", "GOVERNOR", MissionStatus.BLOCKED.value, {"action_id": action.id, "mission_id": contract.mission_id, "contract_id": action.contract_id})
                self._persist_new_audit_events()
                self.store.set_mission_status(contract.mission_id, MissionStatus.BLOCKED)
                return GovernedAction(action, "BLACK", GovernorDecision(action.id, Autonomy.BLOCK, reasons), False, reasons)
            if action.contract_id is None:
                action = replace(action, contract_id=contract.mission_id)
        result = self.governed.route(action, contract)
        if result.governor.approval_id:
            approval = ApprovalRequest(action.id, "; ".join(result.governor.reasons), id=result.governor.approval_id)
            self.store.save_approval(approval, contract.mission_id if contract else None)
        if contract is not None:
            if result.governor.mode == Autonomy.ESCALATE:
                self.store.set_mission_status(contract.mission_id, MissionStatus.WAITING_APPROVAL)
            elif result.governor.mode == Autonomy.BLOCK:
                self.store.set_mission_status(contract.mission_id, MissionStatus.BLOCKED)
            else:
                self.store.set_mission_status(contract.mission_id, MissionStatus.PLANNED)
        self._persist_new_audit_events()
        return result

    def approve(self, approval_id: str) -> None:
        mission_id = self.store.get_approval_mission(approval_id)
        self.store.update_approval(approval_id, ApprovalStatus.APPROVED)
        if mission_id:
            self.store.set_mission_status(mission_id, MissionStatus.PLANNED)
        self.audit.record("approval", "HUMAN", "APPROVED", {"approval_id": approval_id, "mission_id": mission_id})
        self._persist_new_audit_events()

    def reject(self, approval_id: str) -> None:
        mission_id = self.store.get_approval_mission(approval_id)
        self.store.update_approval(approval_id, ApprovalStatus.REJECTED)
        if mission_id:
            self.store.set_mission_status(mission_id, MissionStatus.BLOCKED)
        self.audit.record("approval", "HUMAN", "REJECTED", {"approval_id": approval_id, "mission_id": mission_id})
        self._persist_new_audit_events()

    def state(self, mission_id: str) -> MissionState:
        contract = self.store.load_mission(mission_id)
        if contract is None:
            raise KeyError(mission_id)
        return MissionState(mission_id, self.store.get_mission_status(mission_id), len(self.store.pending_approvals()))

    def _persist_new_audit_events(self) -> None:
        for event in self.audit.events():
            self.store.record_audit(event)
