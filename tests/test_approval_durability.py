import pytest

from singular.autopilot import ApprovalRequest, ApprovalStatus, DelegationContract
from singular.durable import DurableStore


def _store(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(
        DelegationContract(
            mission_id="MIS-APPROVAL",
            objective="test",
            expected_result="done",
        )
    )
    return store


def test_approval_identity_cannot_be_replaced(tmp_path):
    store = _store(tmp_path)
    approval = ApprovalRequest("ACT-1", "human review")
    store.save_approval(approval, "MIS-APPROVAL")

    with pytest.raises(ValueError, match="identité.*immuable"):
        store.save_approval(ApprovalRequest("ACT-2", "different", id=approval.id), "MIS-APPROVAL")

    persisted = store.get_approval(approval.id)
    assert persisted.action_id == "ACT-1"
    assert persisted.reason == "human review"


def test_terminal_approval_cannot_be_rewritten(tmp_path):
    store = _store(tmp_path)
    approval = ApprovalRequest("ACT-1", "human review")
    store.save_approval(approval, "MIS-APPROVAL")
    store.update_approval(approval.id, ApprovalStatus.APPROVED)

    with pytest.raises(ValueError, match="Transition d'approbation interdite"):
        store.update_approval(approval.id, ApprovalStatus.REJECTED)

    assert store.get_approval(approval.id).status is ApprovalStatus.APPROVED


def test_concurrent_terminal_decision_is_fail_closed(tmp_path):
    store = _store(tmp_path)
    approval = ApprovalRequest("ACT-1", "human review")
    store.save_approval(approval, "MIS-APPROVAL")

    first = store.update_approval(approval.id, ApprovalStatus.REJECTED)
    second = store.update_approval(approval.id, ApprovalStatus.REJECTED)

    assert first.status is ApprovalStatus.REJECTED
    assert second.status is ApprovalStatus.REJECTED


# --- ce qu'un verdict humain interdit ensuite -----------------------------------
#
# `DurableMissionRuntime.approve` refuse de reouvrir une approbation rejetee, et
# refuse d'approuver pour une mission qui n'attend plus. Aucun des deux refus
# n'avait de temoin -- nommes par la passe de mutation sur le socle.
#
# Le premier est le pendant de la revue REFUSEE du registre d'ameliorations : un
# humain a dit non, et rien ne doit pouvoir revenir dessus par une autre porte.
# Le second garde la coherence : approuver une mission qui a deja repris, echoue ou
# ete bloquee ecrirait une autorisation pour un etat qui n'existe plus.

def _runtime_en_attente(tmp_path):
    """Un runtime reel, une approbation en attente, la mission a WAITING_APPROVAL."""
    from singular.autopilot import ActionRequest, Autonomy
    from singular.durable import MissionStatus
    from singular.mission_runtime import DurableMissionRuntime

    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract(mission_id="MIS-VERDICT", objective="objectif",
                                          expected_result="résultat",
                                          autonomy=Autonomy.EXECUTE_AUTHORIZED))
    runtime = DurableMissionRuntime(store)
    # Une action qui demande un jugement humain : la gouvernance l'escalade, ce qui
    # cree l'approbation et met la mission en attente -- on ne fabrique donc pas
    # l'etat a la main. `sensitive=True` ne marcherait pas : la politique la classe
    # BLACK et le gouverneur la **bloque** au lieu de l'escalader, ce qui ne cree
    # aucune approbation. Le rang ORANGE est celui qui escalade.
    action = ActionRequest("envoyer", "Envoyer le dossier", 5, 5, 6, requires_human=True,
                           contract_id="MIS-VERDICT")
    gouverne = runtime.route(action, "MIS-VERDICT")
    approval_id = gouverne.governor.approval_id
    assert approval_id, "la gouvernance devait escalader"
    assert store.get_mission_status("MIS-VERDICT") is MissionStatus.WAITING_APPROVAL
    return runtime, store, approval_id


def test_une_approbation_rejetee_ne_se_reouvre_pas(tmp_path):
    runtime, store, approval_id = _runtime_en_attente(tmp_path)
    runtime.reject(approval_id)
    assert store.get_approval(approval_id).status is ApprovalStatus.REJECTED

    with pytest.raises(ValueError, match="rejetée ne peut pas être réouverte"):
        runtime.approve(approval_id)
    assert store.get_approval(approval_id).status is ApprovalStatus.REJECTED


def test_une_approbation_ne_vaut_plus_pour_une_mission_qui_n_attend_plus(tmp_path):
    """Le cas atteignable : la mission est bloquee pendant que l'approbation dort.

    La moitie `mission_id is not None` du meme garde, elle, reste une assurance, et
    c'est mesure contre la suite entiere : une approbation sans mission ne peut pas
    exister avec ses empreintes natives, parce que ce sont le routage et son contrat
    qui les ecrivent. Le garde protege donc une forme que le runtime ne produit pas.
    """
    from singular.durable import MissionStatus

    runtime, store, approval_id = _runtime_en_attente(tmp_path)
    store.set_mission_status("MIS-VERDICT", MissionStatus.BLOCKED)

    with pytest.raises(ValueError, match="plus valide pour l'état actuel"):
        runtime.approve(approval_id)
    assert store.get_approval(approval_id).status is ApprovalStatus.PENDING


def test_un_refus_ne_vaut_plus_pour_une_mission_qui_a_repris(tmp_path):
    """Le jumeau du garde precedent, dans `reject`, et rien ne l'essayait.

    Refuser est le geste prudent, donc on pourrait croire qu'il n'a pas besoin
    d'etre garde. Il en a besoin, et pour une raison qui se mesure : `reject` ecrit
    le verdict **puis** met la mission a BLOCKED. Si la mission a repris entre-temps,
    RUNNING -> BLOCKED est une transition interdite -- le store la refuse -- et la
    base garde alors une approbation REFUSEE sous une mission qui continue de
    tourner. Une autorisation humaine rejetee qui ne bloque rien est pire que pas
    d'autorisation du tout : elle dit qu'un humain a tranche, et rien ne suit.

    Le garde refuse avant d'ecrire quoi que ce soit, donc l'approbation reste
    PENDING et la mission son etat. Verifie en sabotant : le garde retire, le test
    rougit sur « Transition de mission interdite », l'approbation deja passee a
    REFUSEE.

    La moitie `mission_id is not None` reste ici la meme assurance que dans
    `approve`, pour la meme raison : une approbation sans mission ne peut pas
    exister avec ses empreintes natives.
    """
    from singular.durable import MissionStatus

    runtime, store, approval_id = _runtime_en_attente(tmp_path)
    store.set_mission_status("MIS-VERDICT", MissionStatus.PLANNED)
    store.set_mission_status("MIS-VERDICT", MissionStatus.RUNNING)

    with pytest.raises(ValueError, match="plus valide pour l'état actuel"):
        runtime.reject(approval_id)
    assert store.get_approval(approval_id).status is ApprovalStatus.PENDING
    assert store.get_mission_status("MIS-VERDICT") is MissionStatus.RUNNING


@pytest.mark.parametrize("sabotage", ["effacee", "changee"])
def test_une_liaison_d_approbation_incoherente_refuse_la_validation(tmp_path, sabotage):
    """Les deux magasins de liaison doivent dire la meme chose, et rien ne l'essayait.

    Une approbation porte son empreinte d'action a deux endroits : le magasin
    natif, qui la calcule, et la table de liaison historique. Le runtime exige
    qu'ils concordent avant de valider -- c'est la garantie que l'approbation
    couvre bien l'action qu'on croit, et pas une autre glissee entre-temps.

    Les deux moities sont jouees : la liaison effacee, et la liaison changee. La
    premiere est le cas d'une base a moitie ecrite ; la seconde est la substitution
    elle-meme.
    """
    runtime, store, approval_id = _runtime_en_attente(tmp_path)

    with runtime.approval_bindings._connect() as conn:
        if sabotage == "effacee":
            conn.execute("DELETE FROM approval_bindings WHERE approval_id=?", (approval_id,))
        else:
            conn.execute("UPDATE approval_bindings SET action_fingerprint=? WHERE approval_id=?",
                         ("0" * 64, approval_id))

    with pytest.raises(ValueError, match="liaison d'identité de l'approbation est incohérente"):
        runtime.approve(approval_id)
    assert store.get_approval(approval_id).status is ApprovalStatus.PENDING
