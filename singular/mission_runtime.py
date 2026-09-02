from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .audit import AuditTrail
from .autopilot import ApprovalStatus, DelegationContract, MissionManager
from .durable import DurableStore
from .v32_governed_core import GovernedMission, GovernedAction


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
        result = self.governed.route(action, contract)
        if result.governor.approval_id:
            from .autopilot import ApprovalRequest
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
