from dataclasses import replace

import pytest

from singular.autopilot import ActionRequest
from singular.durable import DurableStore
from singular.execution import DurableExecutionEngine
from singular.mission_runtime import DurableMissionRuntime


def _setup(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    runtime = DurableMissionRuntime(store)
    mission = runtime.create_mission("envoyer une candidature", "email envoyé")
    action = ActionRequest(
        name="send_application",
        description="Envoyer la candidature",
        impact=5,
        risk=4,
        reversibility=6,
        sensitive=True,
        capability="send_email",
    )
    routed = runtime.route(action, mission.mission_id)
    assert routed.governor.approval_id
    return store, runtime, mission, action, routed.governor.approval_id


def test_approval_stores_native_immutable_fingerprints(tmp_path):
    store, runtime, mission, action, approval_id = _setup(tmp_path)
    with store._connect() as conn:
        row = conn.execute(
            "SELECT action_fingerprint,capability_fingerprint,contract_fingerprint FROM approvals WHERE approval_id=?",
            (approval_id,),
        ).fetchone()
    assert row is not None
    assert all(row[name] for name in ("action_fingerprint", "capability_fingerprint", "contract_fingerprint"))
    runtime.approve(approval_id)


def test_tampered_native_approval_is_refused_before_handler(tmp_path):
    store, runtime, mission, action, approval_id = _setup(tmp_path)
    runtime.approve(approval_id)
    with store._connect() as conn:
        conn.execute("UPDATE approvals SET action_fingerprint='TAMPERED' WHERE approval_id=?", (approval_id,))
    calls = []
    engine = DurableExecutionEngine(runtime)
    with pytest.raises(PermissionError, match="identité|autorité"):
        engine.execute(action, mission.mission_id, lambda a: calls.append(a))
    assert calls == []


def test_changed_contract_invalidates_existing_approval(tmp_path):
    store, runtime, mission, action, approval_id = _setup(tmp_path)
    runtime.approve(approval_id)
    changed = replace(mission, objective="envoyer une candidature URGENTE")
    store.save_mission(changed)
    calls = []
    engine = DurableExecutionEngine(runtime)
    with pytest.raises(PermissionError, match="identité|autorité"):
        engine.execute(action, mission.mission_id, lambda a: calls.append(a))
    assert calls == []


def test_missing_native_fingerprint_fails_closed_on_approval(tmp_path):
    store, runtime, mission, action, approval_id = _setup(tmp_path)
    with store._connect() as conn:
        conn.execute("UPDATE approvals SET capability_fingerprint=NULL WHERE approval_id=?", (approval_id,))
    with pytest.raises(ValueError, match="empreintes natives"):
        runtime.approve(approval_id)
