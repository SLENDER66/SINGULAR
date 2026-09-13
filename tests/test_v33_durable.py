from pathlib import Path

import pytest

from singular.autopilot import ActionRequest, ApprovalStatus, Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.mission_runtime import DurableMissionRuntime


def test_mission_survives_runtime_restart(tmp_path: Path):
    db = tmp_path / "singular.db"
    first = DurableMissionRuntime(DurableStore(db))
    contract = first.create_mission("emploi et revenus", "plan concret", autonomy=Autonomy.PREPARE)

    second = DurableMissionRuntime(DurableStore(db))
    assert second.store.load_mission(contract.mission_id).objective == "emploi et revenus"
    assert second.state(contract.mission_id).status == MissionStatus.CREATED


def test_pending_approval_survives_runtime_restart_and_can_be_resolved(tmp_path: Path):
    db = tmp_path / "singular.db"
    first = DurableMissionRuntime(DurableStore(db))
    contract = first.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    first.route(ActionRequest("send_application", "send", 5, 6, 6), contract.mission_id)
    approval = first.store.pending_approvals(contract.mission_id)[0]

    second = DurableMissionRuntime(DurableStore(db))
    assert second.state(contract.mission_id).status == MissionStatus.WAITING_APPROVAL
    recovered = second.store.pending_approvals(contract.mission_id)
    assert len(recovered) == 1
    assert recovered[0].id == approval.id
    assert recovered[0].status == ApprovalStatus.PENDING

    second.approve(approval.id)
    assert second.store.pending_approvals(contract.mission_id) == ()
    assert second.state(contract.mission_id).status == MissionStatus.PLANNED


def test_missions_have_unique_ids(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    first = runtime.create_mission("same objective", "same result")
    second = runtime.create_mission("same objective", "same result")
    assert first.mission_id != second.mission_id


def test_sensitive_action_creates_no_execution_and_is_blocked(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("finance", "préparer", autonomy=Autonomy.EXECUTE_AUTHORIZED)
    result = runtime.route(ActionRequest("transfer_money", "transfer", 9, 9, 1), contract.mission_id)
    assert not result.allowed
    assert result.governor.mode == Autonomy.BLOCK
    assert runtime.store.pending_approvals() == ()
    assert runtime.state(contract.mission_id).status == MissionStatus.BLOCKED


def test_idempotency_key_is_deterministic(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    key1 = store.idempotency_key("mission", "action", "v1")
    key2 = store.idempotency_key("mission", "action", "v1")
    assert key1 == key2
    assert len(key1) == 64


# --- une cle d'execution ne sert qu'a une mission et une action -----------------
#
# `_validate_execution_identity` refuse une ligne dont la mission ou l'action ne
# sont pas celles qu'on annonce. Le refus n'avait aucun temoin -- nomme par la
# passe de mutation sur le socle.
#
# Le chemin est direct : la cle est un **argument** de
# `begin_execution_and_start_mission`. Elle derive normalement de la mission et de
# l'action, mais rien n'oblige l'appelant a la calculer ainsi -- et c'est ce garde
# qui rattrape le cas ou deux travaux differents se retrouveraient sous la meme
# cle : le second lirait le resultat du premier comme si c'etait le sien.

def test_une_cle_d_execution_ne_se_reutilise_pas_pour_une_autre_mission(tmp_path: Path):
    import pytest

    from singular.autopilot import DelegationContract
    from singular.durable import MissionStatus

    store = DurableStore(tmp_path / "singular.db")
    for mission in ("MIS-UN", "MIS-DEUX"):
        store.save_mission(DelegationContract(mission, "objectif", "résultat",
                                              autonomy=Autonomy.EXECUTE_REVERSIBLE))
        store.set_mission_status(mission, MissionStatus.PLANNED)

    store.begin_execution_and_start_mission("meme-cle", "MIS-UN", "ACT-UN")

    with pytest.raises(ValueError, match="réutilisée pour une autre mission ou action"):
        store.begin_execution_and_start_mission("meme-cle", "MIS-DEUX", "ACT-UN")
    with pytest.raises(ValueError, match="réutilisée pour une autre mission ou action"):
        store.begin_execution_and_start_mission("meme-cle", "MIS-UN", "ACT-DEUX")


# Deux refus voisins restent sans temoin et le resteront : « Idempotency record
# could not be persisted » et « Execution record could not be persisted », quand la
# ligne qu'on vient d'inserer ne se relit pas. L'insertion et la lecture sont dans
# la meme transaction, donc seule une panne de la base les declenche -- et une base
# qui perd une ligne inseree ne se simule pas sans simuler la base elle-meme, ce
# qui ne prouverait rien de ce code. Assurances, pas trous.


# --- un bail nul n'est pas un bail ---------------------------------------------
#
# Les deux entrees qui posent un bail le refusent nul ou negatif, et aucune des
# deux n'avait de temoin ici. Le moteur d'execution a le meme refus a la
# construction, teste ce matin ; le socle, lui, l'avait sans preuve.
#
# La consequence est celle qui a justifie le test du moteur : un bail nul rend
# chaque execution immediatement perimee, donc la tentative suivante la lit comme
# une execution eventee -- une recuperation a demander a un fournisseur, c'est-a-dire
# une ambiguite inventee sur un effet qui n'a jamais commence.

@pytest.mark.parametrize("bail", [0, -1, -300])
def test_un_bail_non_positif_est_refuse_a_la_revendication(tmp_path: Path, bail):
    from singular.autopilot import DelegationContract
    from singular.durable import MissionStatus

    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract("MIS-BAIL", "objectif", "résultat",
                                          autonomy=Autonomy.EXECUTE_REVERSIBLE))
    store.set_mission_status("MIS-BAIL", MissionStatus.PLANNED)

    with pytest.raises(ValueError, match="lease doit être positive"):
        store.begin_execution_and_start_mission("cle-bail", "MIS-BAIL", "ACT-BAIL",
                                                lease_seconds=bail)
    assert store.get_execution("cle-bail") is None, "rien ne doit avoir ete revendique"


@pytest.mark.parametrize("bail", [0, -1])
def test_un_battement_de_coeur_ne_raccourcit_pas_le_bail_a_zero(tmp_path: Path, bail):
    """Prolonger un bail avec une duree nulle serait le rendre, pas le tenir."""
    from singular.autopilot import DelegationContract
    from singular.durable import MissionStatus

    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract("MIS-BATT", "objectif", "résultat",
                                          autonomy=Autonomy.EXECUTE_REVERSIBLE))
    store.set_mission_status("MIS-BATT", MissionStatus.PLANNED)
    store.begin_execution_and_start_mission("cle-batt", "MIS-BATT", "ACT-BATT")
    avant = store.get_execution("cle-batt")["lease_until"]

    with pytest.raises(ValueError, match="lease doit être positive"):
        store.heartbeat_execution("cle-batt", lease_seconds=bail)
    assert store.get_execution("cle-batt")["lease_until"] == avant


def test_un_battement_de_coeur_sur_une_execution_finie_est_refuse(tmp_path: Path):
    """Le bail ne se prolonge que sur ce qui tourne encore.

    Le cas reel : un ouvrier prolonge son bail alors que son execution a ete
    finie entre-temps -- par une recuperation, ou par lui-meme au tour precedent.
    Sans ce refus, la prolongation ne toucherait aucune ligne et l'ouvrier
    continuerait de se croire titulaire du bail : deux acteurs pensant tenir la
    meme execution, ce que le bail existe precisement pour empecher.

    Une cle inconnue tombe sur le meme refus, et c'est la meme phrase qui
    convient : « inexistante ou non active ».
    """
    from singular.autopilot import DelegationContract
    from singular.durable import MissionStatus

    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract("MIS-COEUR", "objectif", "résultat",
                                          autonomy=Autonomy.EXECUTE_REVERSIBLE))
    store.set_mission_status("MIS-COEUR", MissionStatus.PLANNED)
    store.begin_execution_and_start_mission("cle-coeur", "MIS-COEUR", "ACT-COEUR")
    store.finish_execution_and_mission("cle-coeur", "COMPLETED", result={"ok": True})

    with pytest.raises(RuntimeError, match="inexistante ou non active"):
        store.heartbeat_execution("cle-coeur")
    with pytest.raises(RuntimeError, match="inexistante ou non active"):
        store.heartbeat_execution("cle-qui-n-a-jamais-existe")


def test_entrer_en_recuperation_deux_fois_ne_leve_pas(tmp_path: Path):
    """L'idempotence de l'entree en recuperation, et ce qu'elle garde.

    Le refus qui suit l'ecriture ne parle que du cas impossible : aucune ligne
    touchee **alors que** la ligne dit encore RUNNING. La seconde moitie de cette
    condition est ce qui rend le second appel legal -- sans elle, rappeler la
    methode sur une execution deja en recuperation leverait, et la reprise apres
    un redemarrage deviendrait un echec au lieu d'un no-op.

    Le cas est reel : deux ouvriers, ou un ouvrier qui reessaie apres un
    redemarrage, peuvent tous deux constater le bail perime.
    """
    from singular.autopilot import DelegationContract
    from singular.durable import MissionStatus

    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract("MIS-RECUP", "objectif", "résultat",
                                          autonomy=Autonomy.EXECUTE_REVERSIBLE))
    store.set_mission_status("MIS-RECUP", MissionStatus.PLANNED)
    store.begin_execution_and_start_mission("cle-recup", "MIS-RECUP", "ACT-RECUP")

    premier = store.mark_execution_recovery_required("cle-recup")
    second = store.mark_execution_recovery_required("cle-recup")

    assert premier["status"] == "RECOVERY_REQUIRED"
    assert second["status"] == "RECOVERY_REQUIRED"
    assert second["finished_at"] == premier["finished_at"], "le second appel ne rejoue rien"


# Le refus « Execution state could not enter recovery » garde le cas impossible :
# aucune ligne touchee alors que la ligne dit encore RUNNING. Pour l'atteindre il
# faudrait remettre une execution terminee sur RUNNING entre l'ecriture et la
# lecture -- un etat que l'API ne sait pas produire. Le simuler demanderait de
# forcer la base dans une forme qu'elle n'a jamais, ce qui ne prouverait rien de ce
# code. Assurance, pas trou.


# --- une recuperation ne se conclut pas en succes -------------------------------
#
# `resolve_execution_recovery` n'accepte que FAIL et CANCEL, et ce refus n'avait
# aucun temoin. C'est l'invariant que le mandat nomme « recovery ambiguity » : une
# execution dont personne ne sait si l'effet est parti ne devient un succes que par
# la preuve du fournisseur -- `confirm_execution_recovery_from_effect` --, jamais
# par la decision de l'appelant.
#
# Sans ce refus, un appelant presse resout en « SUCCESS » et le systeme compte un
# virement qui n'a peut-etre jamais eu lieu.

@pytest.mark.parametrize("verdict", ["SUCCESS", "COMPLETED", "OK", "fail", "cancel", ""])
def test_une_recuperation_ne_se_resout_pas_en_succes(tmp_path: Path, verdict):
    from singular.autopilot import DelegationContract

    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract("MIS-PREUVE", "objectif", "résultat",
                                          autonomy=Autonomy.EXECUTE_REVERSIBLE))
    store.set_mission_status("MIS-PREUVE", MissionStatus.PLANNED)
    store.begin_execution_and_start_mission("cle-preuve", "MIS-PREUVE", "ACT-PREUVE")
    store.mark_execution_recovery_required("cle-preuve")

    with pytest.raises(ValueError, match="sans preuve externe"):
        store.resolve_execution_recovery("cle-preuve", verdict)
    assert store.get_execution("cle-preuve")["status"] == "RECOVERY_REQUIRED"


def test_une_recuperation_exige_une_mission_encore_en_cours(tmp_path: Path):
    """La mission doit etre RUNNING pendant une recuperation, et rien ne l'essayait.

    Le cas atteignable : la mission est annulee -- gouvernance, abandon -- pendant
    qu'une execution attend sa resolution. Resoudre alors ecrirait un etat
    d'execution sous une mission qui n'est plus en cours, donc un couple que le
    verificateur d'integrite considere impossible.

    La moitie voisine (`mission is None`) reste une assurance : une cle etrangere
    lie l'execution a sa mission, donc la ligne existe forcement.
    """
    from singular.autopilot import DelegationContract

    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract("MIS-ANNUL", "objectif", "résultat",
                                          autonomy=Autonomy.EXECUTE_REVERSIBLE))
    store.set_mission_status("MIS-ANNUL", MissionStatus.PLANNED)
    store.begin_execution_and_start_mission("cle-annul", "MIS-ANNUL", "ACT-ANNUL")
    store.mark_execution_recovery_required("cle-annul")
    store.set_mission_status("MIS-ANNUL", MissionStatus.CANCELLED)

    with pytest.raises(ValueError, match="mission doit être RUNNING"):
        store.resolve_execution_recovery("cle-annul", "FAIL", reason="abandonnée")
    assert store.get_execution("cle-annul")["status"] == "RECOVERY_REQUIRED"
