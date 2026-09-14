import pytest

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
    store, _, _ = _setup(tmp_path)
    complet = {"provider": "provider", "operation": "send", "payload_fingerprint": "fp"}
    for champ in complet:
        for vide in ("", "   "):
            arguments = dict(complet)
            arguments[champ] = vide
            with pytest.raises(ValueError, match="provider, operation and payload_fingerprint are required"):
                ReconciledExecutionFinalizer(store).finalize("EXEC-1", **arguments)


def _preuve_completee(store, request, **colonnes):
    """Un effet en preuve, ecrit par le coordinateur puis amene a COMPLETED.

    On passe par `prepare` plutot que par un INSERT a la main : la ligne porte
    alors la cle que le code derive vraiment, et non celle que le test croit.
    `colonnes` permet d'abimer une colonne precise -- c'est la substitution qu'on
    veut jouer, pas une base inventee.
    """
    ExternalEffectCoordinator(store).prepare(request)
    with store._connect() as conn:
        conn.execute(
            "UPDATE external_effects SET status='COMPLETED',result=? WHERE provider_idempotency_key=?",
            ('{"ok":true}', request.provider_idempotency_key),
        )
        for nom, valeur in colonnes.items():
            conn.execute(
                f"UPDATE external_effects SET {nom}=? WHERE provider_idempotency_key=?",
                (valeur, request.provider_idempotency_key),
            )


def _finalise(store, request, **remplacements):
    arguments = {"provider": request.provider, "operation": request.operation,
                 "payload_fingerprint": request.payload_fingerprint,
                 "action_fingerprint": request.action_fingerprint}
    arguments.update(remplacements)
    return ReconciledExecutionFinalizer(store).finalize("EXEC-1", **arguments)


def test_le_trajet_nominal_de_la_finalisation_passe(tmp_path):
    """Sans ca, les refus suivants passeraient en ne gardant rien."""
    store, request, _ = _setup(tmp_path)
    _preuve_completee(store, request)

    assert _finalise(store, request).result == {"ok": True}
    assert store.get_execution("EXEC-1")["status"] == "COMPLETED"


@pytest.mark.parametrize("etat", ["RUNNING", "COMPLETED", "FAILED"])
def test_seule_une_execution_en_quarantaine_se_finalise(tmp_path, etat):
    """Finaliser ailleurs, c'est ecrire un verdict sur une execution qui a le sien.

    Sur une execution qui tourne encore, ce serait voler son bail ; sur une
    execution deja terminee, reecrire un resultat rendu. La quarantaine est le seul
    etat ou « je ne sais pas si l'effet est parti » est vrai.
    """
    store, request, _ = _setup(tmp_path, execution_status=etat)
    _preuve_completee(store, request)

    with pytest.raises(ValueError, match="Seule une exécution RECOVERY_REQUIRED"):
        _finalise(store, request)
    assert store.get_execution("EXEC-1")["status"] == etat


def test_le_finaliseur_refuse_une_preuve_liee_a_une_autre_action(tmp_path):
    """La substitution d'action, jumelle de celle du payload deja gardee.

    L'empreinte d'action n'entre pas dans la cle de preuve : la meme execution, le
    meme fournisseur et la meme operation retrouvent donc la ligne meme si l'action
    a change. C'est ce garde-la qui refuse -- sinon un effet parti pour une action
    fermerait l'execution d'une autre.
    """
    store, request, _ = _setup(tmp_path)
    _preuve_completee(store, request)

    with pytest.raises(ValueError, match="ne correspond pas à l'action"):
        _finalise(store, request, action_fingerprint="une-autre-empreinte")
    assert store.get_execution("EXEC-1")["status"] == "RECOVERY_REQUIRED"


@pytest.mark.parametrize("etat", ["INTENT", "UNKNOWN", "FAILED"])
def test_une_preuve_non_terminale_ne_finalise_rien(tmp_path, etat):
    """« Peut-etre parti » ne devient pas « parti » parce qu'on le finalise."""
    store, request, _ = _setup(tmp_path)
    _preuve_completee(store, request, status=etat)

    with pytest.raises(ValueError, match="preuve externe non terminale"):
        _finalise(store, request)
    assert store.get_execution("EXEC-1")["status"] == "RECOVERY_REQUIRED"


def test_la_finalisation_exige_une_mission_encore_en_cours(tmp_path):
    """Le troisieme exemplaire du meme invariant, apres les deux de `durable.py`.

    La gouvernance peut annuler la mission pendant qu'une execution attend sa
    preuve. Finaliser alors ecrirait une execution COMPLETED sous une mission
    annulee : un couple que le verificateur d'integrite considere impossible.
    """
    store, request, _ = _setup(tmp_path)
    _preuve_completee(store, request)
    store.set_mission_status("MIS-1", MissionStatus.CANCELLED)

    with pytest.raises(ValueError, match="mission doit être RUNNING"):
        _finalise(store, request)
    assert store.get_execution("EXEC-1")["status"] == "RECOVERY_REQUIRED"


# Le `rowcount != 1` qui suit la mise a jour est une assurance ici, et il ne l'est
# pas dans `durable.py` : la difference est une ligne de SQL. `finalize` ouvre son
# bloc par `BEGIN IMMEDIATE`, donc la transaction d'ecriture est prise **avant** la
# premiere lecture et aucun autre ecrivain ne peut s'interposer.
# `resolve_execution_recovery` et `confirm_execution_recovery_from_effect` ne le
# font pas : `sqlite3` n'ouvre alors une transaction qu'au premier ecrit, la fenetre
# entre lecture et ecriture est reelle, et leurs compare-and-swap ont chacun leur
# temoin de course -- deux ouvriers sur la meme recuperation. Trois methodes qui
# font le meme trajet, deux disciplines ; c'est ecrit ici pour que la prochaine
# passe ne conclue pas de l'une a l'autre.
#
# Faut-il aligner les deux autres sur `BEGIN IMMEDIATE` ? Non, et c'est une decision
# prise, pas un oubli. Les deux formes sont sures : l'une refuse le second ouvrier,
# l'autre le fait attendre puis lui donne un refus plus precis. Mais les
# compare-and-swap de `durable.py` sont **prouves** -- deux temoins de course les
# atteignent -- alors que sous `BEGIN IMMEDIATE` ils deviendraient inatteignables,
# donc des assurances de plus. Un garde prouve vaut mieux qu'un garde plus elegant
# que rien n'essaie, et c'est la regle que toute cette passe applique.
#
# Les trois refus qui comparent le fournisseur, l'operation et la cle d'execution de
# la preuve sont des assurances, pas des trous : la cle sous laquelle la preuve est
# cherchee **est** derivee de ces trois valeurs, donc une ligne trouvee les porte
# forcement. Les atteindre demanderait d'abimer la base a la main pour tester un
# chemin que le code ne produit pas. L'empreinte de charge et celle de l'action, au
# contraire, n'entrent pas dans la cle : ce sont les deux seules substitutions
# reellement possibles, et elles ont chacune leur temoin ci-dessus.
