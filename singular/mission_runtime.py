from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any
from uuid import uuid4

from .approval_binding import ApprovalBindingStore
from .approval_integrity import ApprovalIntegrityStore
from .audit import AuditTrail
from .autopilot import ApprovalRequest, ApprovalStatus, Autonomy, DelegationContract
from .durable import MISSION_TRANSITIONS, DurableStore, MissionStatus
from .v32_governed_core import GovernedAction, GovernedMission, GovernorDecision


@dataclass(frozen=True)
class MissionState:
    mission_id: str
    status: MissionStatus
    pending_approvals: int


class DurableMissionRuntime:
    """Durable orchestration seam: restart-safe state, approvals, audit and replay safety."""

    def __init__(self, store: DurableStore | None = None) -> None:
        self.store = store or DurableStore()
        self.approval_bindings = ApprovalBindingStore(self.store.path)
        self.approval_integrity = ApprovalIntegrityStore(self.store.path)
        self.audit = AuditTrail()
        self.governed = GovernedMission()

    def create_mission(self, objective: str, expected_result: str, **kwargs: Any) -> DelegationContract:
        contract = DelegationContract(mission_id="MIS-" + uuid4().hex[:8], objective=objective, expected_result=expected_result, **kwargs)
        self.store.save_mission(contract)
        self.audit.record("mission_created", "COMMANDER", MissionStatus.CREATED.value, {"mission_id": contract.mission_id})
        self._persist_new_audit_events()
        return contract

    def route(self, action, mission_id: str | None = None) -> GovernedAction:
        contract = self.store.load_mission(mission_id) if mission_id else None
        if mission_id is not None and contract is None:
            return self._blocked(action, None, ("Mission inconnue : exécution refusée par défaut.",))
        if contract is None and action.contract_id is not None:
            return self._blocked(action, None, ("Action liée à un contrat mais aucun contrat n'a été fourni.",))
        if contract is not None:
            if action.contract_id is not None and action.contract_id != contract.mission_id:
                self._set_status(contract.mission_id, MissionStatus.BLOCKED)
                return self._blocked(action, contract.mission_id, ("L'action ne correspond pas au contrat de mission fourni.",))
            if action.contract_id is None:
                action = replace(action, contract_id=contract.mission_id)
            with self.store._connect() as conn:
                cross_mission = conn.execute(
                    "SELECT 1 FROM approval_bindings WHERE action_id=? AND (mission_id IS NULL OR mission_id<>?) LIMIT 1",
                    (action.id, contract.mission_id),
                ).fetchone()
            if cross_mission is not None:
                self._set_status(contract.mission_id, MissionStatus.BLOCKED)
                raise ValueError("L'action ne correspond pas au contrat de mission fourni.")

        idempotency_key = self.store.idempotency_key("route", contract.mission_id if contract else "", action.id)
        fingerprint = self.approval_integrity.action_fingerprint(action, contract.mission_id if contract else None)
        cached = self.store.get_idempotent(idempotency_key)
        if cached is not None:
            stored_fingerprint = self.store.get_idempotency_fingerprint(idempotency_key)
            if stored_fingerprint != fingerprint:
                raise ValueError("Identité d'action réutilisée avec un contenu différent.")
            current = self.governed.route(action, contract)
            if not self._governance_matches(current, cached):
                self.audit.record("governance_drift", "GOVERNOR", "BLOCKED", {"action_id": action.id, "mission_id": contract.mission_id if contract else None})
                self._persist_new_audit_events()
                raise PermissionError("La politique de gouvernance a changé depuis la décision persistée : exécution refusée.")
            return self._from_cached(action, cached)

        result = self.governed.route(action, contract)
        if result.governor.approval_id:
            approval = ApprovalRequest(action.id, "; ".join(result.governor.reasons), id=result.governor.approval_id)
            self.store.save_approval(approval, contract.mission_id if contract else None)
            self._bind_approval(approval.id, action, contract)
        if contract is not None:
            target = {Autonomy.ESCALATE: MissionStatus.WAITING_APPROVAL, Autonomy.BLOCK: MissionStatus.BLOCKED}.get(result.governor.mode, MissionStatus.PLANNED)
            current_status = self.store.get_mission_status(contract.mission_id)
            if current_status in {MissionStatus.CREATED, MissionStatus.WAITING_APPROVAL} or (current_status == MissionStatus.PLANNED and target != MissionStatus.PLANNED):
                self._set_status(contract.mission_id, target)
        cached_result = self.store.put_idempotent(idempotency_key, self._cache(result), fingerprint)
        self._persist_new_audit_events()
        return self._from_cached(action, cached_result)

    @staticmethod
    def _governance_matches(current: GovernedAction, cached: dict[str, Any]) -> bool:
        return (
            current.policy_tier == cached.get("policy_tier")
            and current.governor.mode.value == cached.get("mode")
            and tuple(current.reasons) == tuple(cached.get("reasons", ()))
            and current.can_prepare == bool(cached.get("can_prepare", cached.get("allowed", False)))
            and current.can_execute == bool(cached.get("can_execute", False))
            and current.requires_human == bool(cached.get("requires_human", current.governor.mode == Autonomy.ESCALATE))
        )

    def approve(self, approval_id: str) -> None:
        approval = self.store.get_approval(approval_id)
        mission_id = self.store.get_approval_mission(approval_id)
        if approval.status == ApprovalStatus.REJECTED:
            raise ValueError("Une approbation rejetée ne peut pas être réouverte.")
        if approval.status == ApprovalStatus.APPROVED:
            return
        if mission_id is not None and self.store.get_mission_status(mission_id) != MissionStatus.WAITING_APPROVAL:
            raise ValueError("Une approbation n'est plus valide pour l'état actuel de la mission.")
        native = self.approval_integrity.get(approval_id)
        if any(native[name] is None for name in native):
            raise ValueError("Approbation sans empreintes natives complètes : validation refusée.")
        legacy = self.approval_bindings.fingerprint(approval_id)
        if legacy is None or legacy != native["action_fingerprint"]:
            raise ValueError("La liaison d'identité de l'approbation est incohérente : validation refusée.")
        self.store.update_approval(approval_id, ApprovalStatus.APPROVED)
        if mission_id:
            self._set_status(mission_id, MissionStatus.PLANNED)
        self.audit.record("approval", "HUMAN", "APPROVED", {"approval_id": approval_id, "mission_id": mission_id})
        self._persist_new_audit_events()

    def reject(self, approval_id: str) -> None:
        approval = self.store.get_approval(approval_id)
        mission_id = self.store.get_approval_mission(approval_id)
        if approval.status == ApprovalStatus.REJECTED:
            return
        if approval.status == ApprovalStatus.APPROVED:
            raise ValueError("Une approbation déjà validée ne peut pas être rejetée.")
        if mission_id is not None and self.store.get_mission_status(mission_id) != MissionStatus.WAITING_APPROVAL:
            raise ValueError("Une approbation n'est plus valide pour l'état actuel de la mission.")
        self.store.update_approval(approval_id, ApprovalStatus.REJECTED)
        if mission_id:
            self._set_status(mission_id, MissionStatus.BLOCKED)
        self.audit.record("approval", "HUMAN", "REJECTED", {"approval_id": approval_id, "mission_id": mission_id})
        self._persist_new_audit_events()

    def state(self, mission_id: str) -> MissionState:
        if self.store.load_mission(mission_id) is None:
            raise KeyError(mission_id)
        return MissionState(mission_id, self.store.get_mission_status(mission_id), len(self.store.pending_approvals(mission_id)))

    def _set_status(self, mission_id: str, target: MissionStatus) -> None:
        current = self.store.get_mission_status(mission_id)
        if current == target:
            return
        if target not in MISSION_TRANSITIONS[current]:
            raise ValueError(f"Transition de mission interdite : {current.value} -> {target.value}")
        self.store.set_mission_status(mission_id, target)

    def _blocked(self, action, mission_id: str | None, reasons: tuple[str, ...]) -> GovernedAction:
        self.audit.record("runtime_block", "GOVERNOR", MissionStatus.BLOCKED.value, {"action_id": action.id, "mission_id": mission_id, "reasons": list(reasons)})
        if mission_id is not None:
            self._set_status(mission_id, MissionStatus.BLOCKED)
        result = GovernedAction(action, "BLACK", GovernorDecision(action.id, Autonomy.BLOCK, reasons), False, False, True, reasons)
        self._persist_new_audit_events()
        return result

    @staticmethod
    def _action_fingerprint(action, mission_id: str | None) -> str:
        payload = asdict(action)
        payload.pop("id", None)
        canonical = json.dumps({"mission_id": mission_id, "action": payload}, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _bind_approval(self, approval_id: str, action, contract: DelegationContract | None) -> None:
        self.approval_integrity.bind(approval_id, action, contract.mission_id if contract else None, contract)
        self.approval_bindings.bind(approval_id, action.id, contract.mission_id if contract else None, self.approval_integrity.action_fingerprint(action, contract.mission_id if contract else None))

    @classmethod
    def approval_fingerprint(cls, approval_id: str, store: DurableStore) -> str | None:
        return ApprovalBindingStore(store.path).fingerprint(approval_id)

    @staticmethod
    def _cache(result: GovernedAction) -> dict[str, Any]:
        return {"policy_tier": result.policy_tier, "mode": result.governor.mode.value, "reasons": list(result.reasons), "approval_id": result.governor.approval_id, "can_prepare": result.can_prepare, "can_execute": result.can_execute, "requires_human": result.requires_human, "allowed": result.allowed}

    @staticmethod
    def _from_cached(action, cached: dict[str, Any]) -> GovernedAction:
        decision = GovernorDecision(action.id, Autonomy(cached["mode"]), tuple(cached["reasons"]), cached.get("approval_id"))
        can_prepare = bool(cached.get("can_prepare", cached.get("allowed", False)))
        can_execute = bool(cached.get("can_execute", False))
        requires_human = bool(cached.get("requires_human", decision.mode == Autonomy.ESCALATE))
        return GovernedAction(action, cached["policy_tier"], decision, can_prepare, can_execute, requires_human, tuple(cached["reasons"]))

    def _persist_new_audit_events(self) -> None:
        for event in self.audit.events():
            self.store.record_audit(event)
