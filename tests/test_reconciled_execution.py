from singular.autopilot import DelegationContract
from singular.durable import DurableStore, MissionStatus
from singular.effects import EffectRequest, EffectStatus, ExternalEffectCoordinator, ProviderResult
from singular.reconciled_execution import ReconciledExecutionFinalizer


class Provider:
    def execute(self, request, idempotency_key):
        return ProviderResult(EffectStatus.UNKNOWN.value, error="network ambiguity")

    def reconcile(self, request, idempotency_key):
        return ProviderResult(EffectStatus.COMPLETED.value, {"remote_id": "confirmed"})


def _setup(tmp_path, *, execution_status="RECOVERY_REQUIRED"):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract("MIS-1", "recover", "done"))
    with store._connect() as conn:
        conn.execute("UPDATE mission_states SET status='RUNNING' WHERE mission_id='MIS-1'")
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at) VALUES(?,?,?,?,datetime('now'))",
            ("EXEC-1", "MIS-1", "ACT-1", execution_status),
        )
    request = EffectRequest("EXEC-1", "provider", "send", {"id": "x"}, "action-fp")
    coordinator = ExternalEffectCoordinator(store)
    return store, request, coordinator


def test_reconciliation_proves_effect_then_finalizer_closes_execution(tmp_path):
    # The execution has to be RUNNING for the effect to be attempted at all: a
    # quarantined execution refuses any new external effect, which is the point
    # of the quarantine. This test started from RECOVERY_REQUIRED and then asked
    # the coordinator to send, so it never got past that guard.
    store, request, coordinator = _setup(tmp_path, execution_status="RUNNING")
    outcome = coordinator.execute(request, Provider())
    assert outcome.status == EffectStatus.UNKNOWN.value

    # An ambiguous provider outcome is what puts the execution in quarantine;
    # DurableExecutionEngine does this when it sees UNKNOWN.
    store.mark_execution_recovery_required("EXEC-1")
    outcome = coordinator.reconcile(request, Provider())
    assert outcome.status == EffectStatus.COMPLETED.value
    assert store.get_execution("EXEC-1")["status"] == "RECOVERY_REQUIRED"

    final = ReconciledExecutionFinalizer(store).finalize(
        "EXEC-1",
        provider=request.provider,
        operation=request.operation,
        payload_fingerprint=request.payload_fingerprint,
        action_fingerprint=request.action_fingerprint,
    )
    assert final.result == {"remote_id": "confirmed"}
    assert store.get_execution("EXEC-1")["status"] == "COMPLETED"
    assert store.get_mission_status("MIS-1") is MissionStatus.COMPLETED


def test_finalizer_rejects_operator_asserted_success_without_completed_effect(tmp_path):
    store, request, _ = _setup(tmp_path)
    try:
        ReconciledExecutionFinalizer(store).finalize(
            "EXEC-1",
            provider=request.provider,
            operation=request.operation,
            payload_fingerprint=request.payload_fingerprint,
            action_fingerprint=request.action_fingerprint,
        )
    except ValueError as exc:
        assert "preuve durable" in str(exc)
    else:
        raise AssertionError("Unauthenticated recovery finalization was accepted")
    assert store.get_execution("EXEC-1")["status"] == "RECOVERY_REQUIRED"


def test_finalizer_rejects_payload_substitution(tmp_path):
    store, request, coordinator = _setup(tmp_path)
    coordinator.prepare(request)
    with store._connect() as conn:
        conn.execute(
            "UPDATE external_effects SET status='COMPLETED',result=? WHERE provider_idempotency_key=?",
            ('{"ok":true}', request.provider_idempotency_key),
        )
    try:
        ReconciledExecutionFinalizer(store).finalize(
            "EXEC-1",
            provider=request.provider,
            operation=request.operation,
            payload_fingerprint="forged-payload-fingerprint",
            action_fingerprint=request.action_fingerprint,
        )
    except ValueError as exc:
        assert "payload" in str(exc)
    else:
        raise AssertionError("Payload substitution was accepted")


def test_la_cle_de_preuve_est_celle_sous_laquelle_l_effet_a_ete_ecrit():
    """La finalisation cherche la preuve la ou l'effet l'a ecrite, par construction.

    Les deux derivations etaient deux copies de la meme ligne, dans deux modules.
    Une copie qui change ne se plaint pas : la finalisation ne trouverait plus jamais
    de preuve et refuserait chaque reconciliation avec « aucune preuve durable ne
    correspond », ce qui envoie chercher du cote de la base plutot que du calcul.

    Il n'y a plus qu'un domicile ; ce test dit que c'est bien lui que les deux
    chemins interrogent, et qu'il separe vraiment deux triplets voisins.
    """
    from singular.effects import EffectRequest, cle_d_idempotence

    requete = EffectRequest(execution_key="exec-1", provider="banque", operation="virement",
                            payload={"montant": 42}, action_fingerprint="fp")
    assert requete.provider_idempotency_key == cle_d_idempotence("exec-1", "banque", "virement")

    # Le separateur `\x1f` ne peut pas apparaitre dans les champs, donc un
    # decoupage different ne peut pas produire la meme cle.
    assert cle_d_idempotence("exec", "1banque", "virement") != cle_d_idempotence("exec1", "banque", "virement")


# --- la porte d'entree du finaliseur --------------------------------------------
#
# `finalize` est la transition qui transforme un effet externe ambigu en succes
# durable, sur preuve. Ses deux refus d'entree n'avaient aucun temoin : la
# reconciliation etait toujours appelee avec des arguments bien formes.
#
# Ils ne sont pas decoratifs. La cle de preuve est derivee de ces trois champs --
# `cle_d_idempotence(execution_key, provider, operation)` -- donc un champ vide
# n'echoue pas bruyamment : il derive une **autre** cle, qui ne trouve rien, et le
# refus qu'on lirait serait « aucune preuve durable ne correspond ». On irait
# chercher du cote de la base au lieu de l'appel.


def test_le_finaliseur_refuse_une_execution_sans_cle(tmp_path):
    import pytest

    store, _, _ = _setup(tmp_path)
    for vide in ("", "   "):
        with pytest.raises(ValueError, match="execution_key cannot be blank"):
            ReconciledExecutionFinalizer(store).finalize(
                vide, provider="provider", operation="send", payload_fingerprint="fp")


def test_le_finaliseur_exige_les_trois_champs_de_la_preuve(tmp_path):
    """Les trois moities du meme garde, jouees separement.

    Fournisseur, operation et empreinte de charge : ce sont les trois choses qui
    disent *quel* effet est parti dans le monde. Il en manque une, et la preuve
    qu'on rapprocherait n'est plus celle qui a ete autorisee.
    """
    import pytest

    store, _, _ = _setup(tmp_path)
    complet = {"provider": "provider", "operation": "send", "payload_fingerprint": "fp"}
    for champ in complet:
        for vide in ("", "   "):
            arguments = dict(complet)
            arguments[champ] = vide
            with pytest.raises(ValueError, match="provider, operation and payload_fingerprint are required"):
                ReconciledExecutionFinalizer(store).finalize("EXEC-1", **arguments)
