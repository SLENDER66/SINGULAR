from pathlib import Path

import pytest

from singular.durable import DurableStore
from singular.effects import (
    EffectRequest,
    EffectStatus,
    ExternalEffectCoordinator,
    ProviderResult,
)
from tests.support import claimed_execution_store


class FakeProvider:
    def __init__(self):
        self.execute_calls = 0
        self.reconcile_calls = 0

    def execute(self, request, idempotency_key):
        self.execute_calls += 1
        return ProviderResult("COMPLETED", {"ok": True})

    def reconcile(self, request, idempotency_key):
        self.reconcile_calls += 1
        return ProviderResult("COMPLETED", {"reconciled": True})


def make_request(store: DurableStore) -> tuple[ExternalEffectCoordinator, EffectRequest]:
    coordinator = ExternalEffectCoordinator(store)
    request = EffectRequest("execution-1", "fake", "send", {"to": "a"}, "action-fp")
    return coordinator, request


def test_concurrent_transition_can_only_finalize_once(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    coordinator, request = make_request(store)
    coordinator.prepare(request)
    assert coordinator._claim(request.provider_idempotency_key) is True
    coordinator._transition(request.provider_idempotency_key, EffectStatus.COMPLETED.value, result={"ok": True})

    with pytest.raises(RuntimeError, match="Transition d'effet perdue|concurrence d'état"):
        coordinator._transition(request.provider_idempotency_key, EffectStatus.UNKNOWN.value, error="late worker")

    assert coordinator.get(request)["status"] == EffectStatus.COMPLETED.value


def test_recovery_race_cannot_recover_completed_effect(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    coordinator, request = make_request(store)
    coordinator.prepare(request)
    assert coordinator._claim(request.provider_idempotency_key) is True
    coordinator._transition(request.provider_idempotency_key, EffectStatus.COMPLETED.value, result={"ok": True})

    with pytest.raises(ValueError, match="Récupération d'effet impossible"):
        coordinator.recover_in_flight(request, reason="worker supposé abandonné")

    assert coordinator.get(request)["status"] == EffectStatus.COMPLETED.value


def test_unknown_reconciliation_is_idempotent_after_completion(tmp_path: Path):
    store = claimed_execution_store(tmp_path / "s.db", execution_key="execution-1")
    coordinator, request = make_request(store)
    coordinator.prepare(request)
    assert coordinator._claim(request.provider_idempotency_key) is True
    coordinator._transition(request.provider_idempotency_key, EffectStatus.UNKNOWN.value, error="ambiguous")
    # Reconciliation is reserved to quarantined executions.
    store.mark_execution_recovery_required("execution-1")

    provider = FakeProvider()
    first = coordinator.reconcile(request, provider)
    second = coordinator.reconcile(request, provider)

    assert first.status == EffectStatus.COMPLETED.value
    assert second.status == EffectStatus.COMPLETED.value
    assert provider.reconcile_calls == 1


# --- la transition de mission, quand un autre ecrivain passe devant -------------
#
# `_transition_mission_status` lit l'etat, verifie la transition, puis ecrit
# **sous condition** de l'etat lu. Si un autre ecrivain a change l'etat entre les
# deux, l'ecriture ne touche aucune ligne et le refus dit « concurrence d'etat ».
#
# Ce refus n'avait aucun temoin -- nomme par la passe de mutation sur le socle
# durable. C'est le compare-and-swap de la machine d'etats : sans lui, la
# transition se croirait faite alors qu'elle n'a rien ecrit, et deux ouvriers
# pourraient penser tous les deux detenir la mission.

class _ConcurrenceApresLaLecture:
    """Un autre ecrivain glisse une transition entre la lecture et l'ecriture.

    Le vrai cas est deux processus sur la meme base ; ici un seul suffit a le
    reproduire fidelement, parce que la fenetre est entre deux requetes de la
    meme fonction et que l'ecriture est conditionnee par ce qui a ete lu.
    """

    def __init__(self, conn, mission_id: str, vers) -> None:
        self._conn = conn
        self._mission = mission_id
        self._vers = vers
        self._deja = False

    def execute(self, sql, params=()):
        curseur = self._conn.execute(sql, params)
        if not self._deja and sql.startswith("SELECT status FROM mission_states"):
            self._deja = True
            self._conn.execute(
                "UPDATE mission_states SET status=? WHERE mission_id=?",
                (self._vers.value, self._mission),
            )
        return curseur


def test_une_transition_de_mission_doublee_par_un_autre_refuse(tmp_path: Path):
    from singular.autopilot import Autonomy, DelegationContract
    from singular.durable import MissionStatus

    store = DurableStore(tmp_path / "singular.db")
    contrat = DelegationContract("MIS-RACE", "objectif", "résultat",
                                 autonomy=Autonomy.EXECUTE_REVERSIBLE)
    store.save_mission(contrat)
    store.set_mission_status("MIS-RACE", MissionStatus.PLANNED)

    with store._connect() as conn:
        espion = _ConcurrenceApresLaLecture(conn, "MIS-RACE", MissionStatus.BLOCKED)
        with pytest.raises(RuntimeError, match="concurrence d'état"):
            DurableStore._transition_mission_status(
                espion, "MIS-RACE", MissionStatus.RUNNING,
                expected_current=MissionStatus.PLANNED,
            )

    # L'etat reste celui que l'autre ecrivain a pose : on ne l'ecrase pas.
    assert store.get_mission_status("MIS-RACE") is MissionStatus.BLOCKED
