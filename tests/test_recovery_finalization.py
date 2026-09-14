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


def test_recovery_cannot_confirm_when_the_mission_is_no_longer_running(tmp_path: Path):
    """La mission doit etre RUNNING ici aussi, et rien ne l'essayait.

    Le pendant exact de `test_une_recuperation_exige_une_mission_encore_en_cours`
    dans l'autre methode de recuperation. Le cas est reel : la gouvernance annule
    la mission -- ou l'abandonne -- pendant qu'une execution attend sa preuve. La
    confirmer alors ecrirait une execution COMPLETED sous une mission annulee, un
    couple que le verificateur d'integrite considere impossible.

    La moitie voisine (`mission is None`) reste une assurance : une cle etrangere
    lie l'execution a sa mission.
    """
    store, request = _state(tmp_path)
    _persist_effect(store, request, result={"remote_id": "r1"})
    store.set_mission_status("MIS-RECOVERY-FINAL", MissionStatus.CANCELLED)

    with pytest.raises(ValueError, match="mission doit être RUNNING"):
        store.confirm_execution_recovery_from_effect("exec-final", request.provider_idempotency_key)
    assert store.get_execution("exec-final")["status"] == "RECOVERY_REQUIRED"


class _ResoutPendantNotreLecture:
    """Un second ouvrier resout la recuperation avant notre ecriture.

    Meme fenetre que dans `resolve_execution_recovery`, meme raison : `sqlite3`
    n'ouvre une transaction qu'au premier ecrit, donc les quatre lectures de cette
    methode -- execution, mission, preuve, puis la mise a jour -- ne tiennent rien.
    L'intrus ecrit sur sa **propre** connexion et valide : c'est une vraie course.

    Il frappe apres la lecture de la preuve, la derniere avant l'ecriture. Plus
    tot, il deplacerait aussi la mission et c'est le controle de mission qui
    refuserait, un refus plus haut dans la meme methode.
    """

    def __init__(self, conn, chemin, execution_key: str) -> None:
        self._conn = conn
        self._chemin = chemin
        self._execution = execution_key
        self._deja = False

    def execute(self, sql, params=()):
        curseur = self._conn.execute(sql, params)
        if not self._deja and sql.lstrip().startswith("SELECT provider_idempotency_key"):
            self._deja = True
            DurableStore(self._chemin).resolve_execution_recovery(
                self._execution, "FAIL", reason="tranche par l'autre ouvrier")
        return curseur


def test_recovery_confirmation_refuses_a_recovery_another_worker_just_closed(tmp_path: Path):
    """La transition qui transforme l'ambigu en succes ne se double pas.

    C'est la plus grave des deux courses de recuperation : celle-ci ecrit
    COMPLETED. Si elle passait apres qu'un autre ouvrier a conclu FAIL, la meme
    execution porterait deux verdicts opposes et la mission passerait a COMPLETED
    apres avoir ete declaree echouee.

    Contre-verification : le garde retire, ce test rougit quand meme, mais sur
    « Etat courant inattendu », leve une ligne plus bas par la transition de
    mission. Celui-ci refuse **avant** de toucher la mission et nomme la
    concurrence ; l'autre nomme un etat, ce qui envoie chercher ailleurs.
    """
    import contextlib

    store, request = _state(tmp_path)
    _persist_effect(store, request, result={"remote_id": "r1"})
    chemin = store.path

    vraie = store._connect

    @contextlib.contextmanager
    def connexion_espionnee():
        with vraie() as conn:
            yield _ResoutPendantNotreLecture(conn, chemin, "exec-final")

    store._connect = connexion_espionnee
    try:
        with pytest.raises(RuntimeError, match="concurrence d'état"):
            store.confirm_execution_recovery_from_effect("exec-final", request.provider_idempotency_key)
    finally:
        store._connect = vraie

    execution = DurableStore(chemin).get_execution("exec-final")
    assert execution["status"] == "FAILED"
    assert execution["error"] == "tranche par l'autre ouvrier"
    assert DurableStore(chemin).get_mission_status("MIS-RECOVERY-FINAL") is MissionStatus.FAILED
