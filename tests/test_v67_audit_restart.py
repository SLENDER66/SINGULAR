from pathlib import Path

import pytest

from singular.audit import AuditTrail
from singular.autopilot import Autonomy
from singular.durable import DurableStore
from singular.mission_runtime import DurableMissionRuntime


def test_runtime_restores_audit_sequence_and_chain_after_restart(tmp_path: Path):
    db = tmp_path / "s.db"
    first = DurableMissionRuntime(DurableStore(db))
    mission = first.create_mission("first", "created", autonomy=Autonomy.PREPARE)
    first.audit.record("test_event", "TEST", "OK", {"mission_id": mission.mission_id})
    first._persist_new_audit_events()

    restarted = DurableMissionRuntime(DurableStore(db))
    event = restarted.audit.record("test_event", "TEST", "OK", {"mission_id": mission.mission_id})
    restarted._persist_new_audit_events()

    events = restarted.store.audit_events()
    assert AuditTrail.verify_chain(events) is True
    assert event.payload["audit_sequence"] == 3
    assert event.payload["audit_prev_fingerprint"] == events[1]["payload"]["audit_fingerprint"]


def test_runtime_fails_closed_when_persisted_audit_chain_is_tampered(tmp_path: Path):
    db = tmp_path / "s.db"
    runtime = DurableMissionRuntime(DurableStore(db))
    runtime.create_mission("first", "created", autonomy=Autonomy.PREPARE)

    with runtime.store._connect() as conn:
        conn.execute(
            "UPDATE audit_events SET payload=? WHERE event_id=(SELECT event_id FROM audit_events ORDER BY timestamp,event_id LIMIT 1)",
            ('{"mission_id":"tampered","audit_sequence":1,"audit_fingerprint":"tampered","audit_prev_fingerprint":"","audit_chain_fingerprint":"tampered"}',),
        )

    with pytest.raises(ValueError, match="intégrité de la chaîne d'audit"):
        DurableMissionRuntime(DurableStore(db))
