from __future__ import annotations

import json
from pathlib import Path

import pytest

from singular.autopilot import DelegationContract
from singular.durable import DurableStore, MissionStatus
from singular.effects import EffectRequest


def _state(tmp_path: Path):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(
        DelegationContract(
            mission_id="MIS-RECOVERY-FINAL",
            objective="recover",
            expected_result="completed",
        )
    )
    with store._connect() as conn:
        conn.execute("UPDATE mission_states SET status='RUNNING' WHERE mission_id=?", ("MIS-RECOVERY-FINAL",))
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at) VALUES(?,?,?,?,datetime('now'))",
            ("exec-final", "MIS-RECOVERY-FINAL", "ACT-1", "RECOVERY_REQUIRED"),
        )
    request = EffectRequest(
        execution_key="exec-final",
        provider="provider-a",
        operation="send",
        payload={"to": "target"},
        action_fingerprint="action-fp",
    )
    return store, request


def _persist_effect(store: DurableStore, request: EffectRequest, *, status: str = "COMPLETED", execution_key: str | None = None, result=None):
    with store._connect() as conn:
        conn.execute(
            "INSERT INTO external_effects(provider_idempotency_key,execution_key,provider,operation,payload_fingerprint,action_fingerprint,status,result,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                request.provider_idempotency_key,
                execution_key or request.execution_key,
                request.provider,
                request.operation,
                request.payload_fingerprint,
                request.action_fingerprint,
                status,
                None if result is None else json.dumps(result, sort_keys=True),
                "now",
                "now",
            ),
        )


def test_recovery_completion_requires_matching_persisted_effect(tmp_path: Path):
    store, request = _state(tmp_path)
    _persist_effect(store, request, result={"remote_id": "r1"})

    row = store.confirm_execution_recovery_from_effect("exec-final", request.provider_idempotency_key)

    assert row["status"] == "COMPLETED"
    assert json.loads(row["result"]) == {"remote_id": "r1"}
    assert store.get_mission_status("MIS-RECOVERY-FINAL") is MissionStatus.COMPLETED


def test_recovery_cannot_confirm_without_effect(tmp_path: Path):
    store, request = _state(tmp_path)
    with pytest.raises(ValueError, match="preuve durable"):
        store.confirm_execution_recovery_from_effect("exec-final", request.provider_idempotency_key)
    assert store.get_execution("exec-final")["status"] == "RECOVERY_REQUIRED"


def test_recovery_rejects_effect_from_another_execution(tmp_path: Path):
    store, request = _state(tmp_path)
    _persist_effect(store, request, execution_key="exec-other", result={"remote_id": "wrong"})
    with pytest.raises(ValueError, match="autre exécution"):
        store.confirm_execution_recovery_from_effect("exec-final", request.provider_idempotency_key)
    assert store.get_execution("exec-final")["status"] == "RECOVERY_REQUIRED"


def test_recovery_rejects_non_completed_effect(tmp_path: Path):
    store, request = _state(tmp_path)
    _persist_effect(store, request, status="UNKNOWN")
    with pytest.raises(ValueError, match="COMPLETED"):
        store.confirm_execution_recovery_from_effect("exec-final", request.provider_idempotency_key)
    assert store.get_execution("exec-final")["status"] == "RECOVERY_REQUIRED"


def test_recovery_finalization_rolls_back_if_mission_is_not_running(tmp_path: Path):
    store, request = _state(tmp_path)
    _persist_effect(store, request, result={"remote_id": "r1"})
    store.set_mission_status("MIS-RECOVERY-FINAL", MissionStatus.CANCELLED)
    with pytest.raises(ValueError, match="RUNNING"):
        store.confirm_execution_recovery_from_effect("exec-final", request.provider_idempotency_key)
    row = store.get_execution("exec-final")
    assert row is not None
    assert row["status"] == "RECOVERY_REQUIRED"
    assert row["result"] is None
