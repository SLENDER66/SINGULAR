from __future__ import annotations

from datetime import UTC, datetime

from .autopilot import ApprovalRequest, ApprovalStatus
from .durable import DurableStore


def save_approval(self: DurableStore, approval: ApprovalRequest, mission_id: str | None = None) -> None:
    """Persist an approval identity once; never replace an existing authorization row."""
    now = datetime.now(UTC).isoformat()
    with self._connect() as conn:
        row = conn.execute(
            "SELECT action_id,mission_id,reason,status,created_at FROM approvals WHERE approval_id=?",
            (approval.id,),
        ).fetchone()
        if row is not None:
            expected = (approval.action_id, mission_id, approval.reason, approval.status.value)
            actual = (row["action_id"], row["mission_id"], row["reason"], row["status"])
            if actual != expected:
                raise ValueError("L'identité d'une approbation existante est immuable.")
            return
        conn.execute(
            "INSERT INTO approvals(approval_id,action_id,mission_id,reason,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (approval.id, approval.action_id, mission_id, approval.reason, approval.status.value, now, now),
        )


def update_approval(self: DurableStore, approval_id: str, status: ApprovalStatus) -> ApprovalRequest:
    """Allow only one human authorization decision; terminal approvals cannot be rewritten."""
    status = ApprovalStatus(status)
    now = datetime.now(UTC).isoformat()
    with self._connect() as conn:
        row = conn.execute(
            "SELECT approval_id,action_id,reason,status FROM approvals WHERE approval_id=?",
            (approval_id,),
        ).fetchone()
        if row is None:
            raise KeyError(approval_id)
        current = ApprovalStatus(row["status"])
        if current == status:
            return ApprovalRequest(row["action_id"], row["reason"], current, row["approval_id"])
        if current is not ApprovalStatus.PENDING:
            raise ValueError(f"Transition d'approbation interdite : {current.value} -> {status.value}")
        cur = conn.execute(
            "UPDATE approvals SET status=?,updated_at=? WHERE approval_id=? AND status=?",
            (status.value, now, approval_id, ApprovalStatus.PENDING.value),
        )
        if cur.rowcount != 1:
            raise RuntimeError("La transition d'approbation a échoué à cause d'une concurrence d'état.")
        return ApprovalRequest(row["action_id"], row["reason"], status, row["approval_id"])


if getattr(DurableStore.save_approval, "__module__", "") != __name__:
    DurableStore.save_approval = save_approval
if getattr(DurableStore.update_approval, "__module__", "") != __name__:
    DurableStore.update_approval = update_approval
