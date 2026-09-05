"""Routing a governance verdict must leave a durable trace.

DurableMissionRuntime.route() only audited its own pre-checks (unknown mission,
contract mismatch) and governance drift. The verdict itself -- the thing that
lets an action cross the execution boundary, or refuses it -- was recorded by
GovernedExecutor into an in-memory AuditTrail that is never persisted and dies
with the process. So after a restart nothing could answer "why was this action
allowed to execute?", and a red-team BLOCK left no durable evidence at all.
"""
import json
from pathlib import Path

import pytest

from singular.autopilot import ActionRequest, Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.mission_runtime import DurableMissionRuntime


def _runtime(tmp_path: Path) -> DurableMissionRuntime:
    return DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))


def _events(runtime: DurableMissionRuntime, event_type: str) -> list[dict]:
    return [event for event in runtime.store.audit_events() if event["event_type"] == event_type]


def test_normal_route_persists_the_governance_verdict(tmp_path: Path):
    runtime = _runtime(tmp_path)
    contract = runtime.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)

    governed = runtime.route(action, contract.mission_id)

    recorded = _events(runtime, "governance_route")
    assert len(recorded) == 1
    payload = recorded[0]["payload"]
    assert recorded[0]["actor"] == "GOVERNOR"
    assert recorded[0]["outcome"] == governed.governor.mode.value
    assert payload["action_id"] == action.id
    assert payload["mission_id"] == contract.mission_id
    assert payload["approval_id"] == governed.governor.approval_id
    assert payload["policy_tier"] == governed.policy_tier
    assert payload["can_prepare"] == governed.can_prepare
    assert payload["can_execute"] == governed.can_execute
    assert payload["requires_human"] == governed.requires_human
    assert payload["reasons"] == list(governed.reasons)
    assert runtime.store.verify_audit_integrity() is True


def test_verdict_is_bound_to_the_action_identity_it_was_issued_for(tmp_path: Path):
    """A verdict without the action fingerprint proves nothing about what was allowed."""
    runtime = _runtime(tmp_path)
    contract = runtime.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)

    governed = runtime.route(action, contract.mission_id)

    payload = _events(runtime, "governance_route")[0]["payload"]
    expected = runtime.approval_integrity.action_fingerprint(governed.action, contract.mission_id)
    assert payload["action_fingerprint"] == expected
    assert payload["idempotency_key"] == runtime.store.idempotency_key("route", contract.mission_id, action.id)


def test_blocked_verdict_is_durably_audited(tmp_path: Path):
    """A refusal is evidence too: BLOCK used to be persisted nowhere."""
    runtime = _runtime(tmp_path)
    contract = runtime.create_mission("finance", "safe plan", autonomy=Autonomy.EXECUTE_AUTHORIZED)

    blocked = runtime.route(ActionRequest("high_risk", "danger", 8, 8, 6), contract.mission_id)

    assert blocked.governor.mode == Autonomy.BLOCK
    recorded = _events(runtime, "governance_route")
    assert [event["outcome"] for event in recorded] == [Autonomy.BLOCK.value]
    assert recorded[0]["payload"]["can_execute"] is False
    assert recorded[0]["payload"]["reasons"] == list(blocked.reasons)
    assert runtime.state(contract.mission_id).status == MissionStatus.BLOCKED


def test_replayed_verdict_is_audited_as_a_replay_after_restart(tmp_path: Path):
    """The decision an execution actually replays must be traceable, not only its first issuance."""
    first = _runtime(tmp_path)
    contract = first.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)
    issued = first.route(action, contract.mission_id)

    restarted = _runtime(tmp_path)
    replayed = restarted.route(action, contract.mission_id)

    assert replayed == issued
    assert len(_events(restarted, "governance_route")) == 1
    replays = _events(restarted, "governance_route_replayed")
    assert len(replays) == 1
    assert replays[0]["outcome"] == issued.governor.mode.value
    assert replays[0]["payload"]["action_fingerprint"] == _events(restarted, "governance_route")[0]["payload"]["action_fingerprint"]
    assert replays[0]["payload"]["can_execute"] == issued.can_execute
    assert restarted.store.verify_audit_integrity() is True


def test_provenance_survives_a_crash_between_decision_and_audit(tmp_path: Path):
    """A verdict persisted without its audit event is re-audited on first replay."""
    crashed = _runtime(tmp_path)
    contract = crashed.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)
    crashed._audit_governance = lambda *args, **kwargs: None  # crash after put_idempotent
    crashed.route(action, contract.mission_id)
    assert _events(crashed, "governance_route") == []

    restarted = _runtime(tmp_path)
    replayed = restarted.route(action, contract.mission_id)

    replays = _events(restarted, "governance_route_replayed")
    assert len(replays) == 1
    assert replays[0]["payload"]["action_fingerprint"] == restarted.approval_integrity.action_fingerprint(replayed.action, contract.mission_id)
    assert restarted.store.verify_audit_integrity() is True


def test_audited_verdicts_keep_one_unbroken_chain_across_missions(tmp_path: Path):
    runtime = _runtime(tmp_path)
    for index in range(3):
        contract = runtime.create_mission(f"career {index}", "prepared", autonomy=Autonomy.PREPARE)
        runtime.route(ActionRequest("send_application", f"send {index}", 5, 6, 6), contract.mission_id)

    persisted = runtime.store.audit_events()
    assert [event["payload"]["audit_sequence"] for event in persisted] == list(range(1, len(persisted) + 1))
    assert len(_events(runtime, "governance_route")) == 3
    assert runtime.store.verify_audit_integrity() is True


def test_governance_drift_still_fails_closed_without_recording_a_verdict(tmp_path: Path):
    """A refused replay must not leave an audit event claiming the decision was served."""
    runtime = _runtime(tmp_path)
    contract = runtime.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)
    runtime.route(action, contract.mission_id)
    key = runtime.store.idempotency_key("route", contract.mission_id, action.id)
    drifted = dict(runtime.store.get_idempotent(key))
    drifted["can_execute"] = not drifted["can_execute"]
    with runtime.store._connect() as conn:
        conn.execute("UPDATE idempotency SET result=? WHERE key=?", (json.dumps(drifted, sort_keys=True), key))

    with pytest.raises(PermissionError, match="politique de gouvernance"):
        runtime.route(action, contract.mission_id)

    assert _events(runtime, "governance_route_replayed") == []
    assert len(_events(runtime, "governance_drift")) == 1
