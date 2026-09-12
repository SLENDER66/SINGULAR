from dataclasses import replace

import pytest

from singular.approval_binding import ApprovalBindingStore
from singular.approval_integrity import ApprovalIntegrityStore
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
    # route() binds the approval to the action it governed, which carries the
    # contract id it filled in -- not to the action as first written.
    return store, runtime, mission, routed.action, routed.governor.approval_id


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


def test_tampered_native_approval_is_refused(tmp_path):
    """Assert the control where it lives and is reachable.

    This used to drive DurableExecutionEngine.execute, the raw API, which now
    refuses every call before any approval logic runs -- so the test passed on
    the wrong exception and proved nothing about approval integrity.
    """
    store, runtime, mission, action, approval_id = _setup(tmp_path)
    runtime.approve(approval_id)
    with store._connect() as conn:
        conn.execute("UPDATE approvals SET action_fingerprint='TAMPERED' WHERE approval_id=?", (approval_id,))

    contract = store.load_mission(mission.mission_id)
    with pytest.raises(PermissionError):
        ApprovalIntegrityStore(store.path).validate(approval_id, action, mission.mission_id, contract)


def test_changed_contract_invalidates_existing_approval(tmp_path):
    """The contract cannot be mutated under an approval, and would not validate.

    Two controls, one after the other: DurableStore refuses to overwrite a
    mission with a different payload at all, and even handed the altered
    contract directly, approval integrity refuses it.
    """
    store, runtime, mission, action, approval_id = _setup(tmp_path)
    runtime.approve(approval_id)
    changed = replace(mission, objective="envoyer une candidature URGENTE")

    with pytest.raises(ValueError):
        store.save_mission(changed)

    with pytest.raises(PermissionError):
        ApprovalIntegrityStore(store.path).validate(approval_id, action, mission.mission_id, changed)


def test_changed_action_breaks_its_durable_approval_binding(tmp_path):
    """The second half of the same guard: the binding fingerprint must not match."""
    store, runtime, mission, action, approval_id = _setup(tmp_path)
    runtime.approve(approval_id)
    bound = ApprovalBindingStore(store.path).fingerprint(approval_id)
    assert bound == runtime._action_fingerprint(action, mission.mission_id)

    tampered = replace(action, impact=9)
    assert runtime._action_fingerprint(tampered, mission.mission_id) != bound


def test_raw_execution_api_refuses_before_any_approval_check(tmp_path):
    """Why the two tests above no longer go through the engine."""
    store, runtime, mission, action, approval_id = _setup(tmp_path)
    runtime.approve(approval_id)
    calls = []
    engine = DurableExecutionEngine(runtime)
    with pytest.raises(PermissionError, match="ValidatedTrajectoryDecision"):
        engine.execute(action, mission.mission_id, lambda a: calls.append(a))
    assert calls == []


def test_missing_native_fingerprint_fails_closed_on_approval(tmp_path):
    store, runtime, mission, action, approval_id = _setup(tmp_path)
    with store._connect() as conn:
        conn.execute("UPDATE approvals SET capability_fingerprint=NULL WHERE approval_id=?", (approval_id,))
    with pytest.raises(ValueError, match="empreintes natives"):
        runtime.approve(approval_id)
