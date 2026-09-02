from pathlib import Path

from singular.audit import AuditTrail
from singular.autopilot import ActionRequest, Autonomy
from singular.durable import DurableStore
from singular.mission_runtime import DurableMissionRuntime


def test_audit_events_persist_correlation_and_identity_metadata(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    contract = runtime.create_mission("observe", "auditable", autonomy=Autonomy.PREPARE)
    action = ActionRequest("safe_action", "inspect", 1, 1, 10)

    runtime.route(action, contract.mission_id)
    persisted = store.audit_events()

    assert persisted
    event = persisted[0]
    payload = event["payload"]
    assert payload["mission_id"] == contract.mission_id
    assert payload["correlation_id"] == contract.mission_id
    assert payload["related_ids"]["mission_id"] == contract.mission_id
    assert payload["audit_sequence"] == 1
    assert payload["audit_fingerprint"]
    assert AuditTrail.verify_persisted_event(event)


def test_persisted_audit_fingerprint_detects_tampering(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    contract = runtime.create_mission("observe", "auditable", autonomy=Autonomy.PREPARE)
    runtime.audit.record("decision", "TEST", "OK", {"mission_id": contract.mission_id, "action_id": "ACT-1"})
    runtime._persist_new_audit_events()

    event = dict(store.audit_events()[0])
    event["payload"] = dict(event["payload"])
    event["payload"]["action_id"] = "ACT-TAMPERED"

    assert AuditTrail.verify_persisted_event(event) is False


def test_restart_can_reconstruct_audit_correlation(tmp_path: Path):
    db = tmp_path / "s.db"
    runtime = DurableMissionRuntime(DurableStore(db))
    contract = runtime.create_mission("restart", "reconstruct", autonomy=Autonomy.PREPARE)
    action = ActionRequest("safe_action", "inspect", 1, 1, 10)
    runtime.route(action, contract.mission_id)

    restarted = DurableMissionRuntime(DurableStore(db))
    events = restarted.store.audit_events()

    assert events
    assert any(e["payload"].get("mission_id") == contract.mission_id for e in events)
    assert all(AuditTrail.verify_persisted_event(e) for e in events)
