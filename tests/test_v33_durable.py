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


# Quatre refus voisins restent sans temoin et le resteront : « Idempotency record
# could not be persisted », « Execution record could not be persisted » et les deux
# `final is None` des chemins de recuperation -- quand la ligne qu'on vient d'ecrire
# ne se relit pas. L'insertion et la lecture sont dans
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


class _ResoutPendantNotreLecture:
    """Un second ouvrier resout la recuperation avant notre ecriture.

    Il n'espionne pas pour tricher : il reproduit la seule fenetre que ce code
    laisse ouverte. `resolve_execution_recovery` lit le statut de l'execution, lit
    celui de la mission, decide, puis ecrit. Le module `sqlite3` n'ouvre une
    transaction qu'au premier ecrit -- une lecture n'en ouvre aucune --, donc
    jusqu'a la mise a jour la ligne n'est tenue par rien. Cet intrus ecrit **sur sa
    propre connexion** et valide : c'est une vraie course, pas une simulation qui
    partagerait notre transaction.

    Il frappe apres la lecture de la mission, et c'est mesure : plus tot, il fait
    aussi passer la mission a FAILED, et c'est le controle de mission qui refuse --
    un refus plus haut dans la meme methode, donc le compare-and-swap n'est jamais
    atteint. La derniere fenetre est celle-la.
    """

    def __init__(self, conn, chemin, execution_key: str) -> None:
        self._conn = conn
        self._chemin = chemin
        self._execution = execution_key
        self._deja = False

    def execute(self, sql, params=()):
        curseur = self._conn.execute(sql, params)
        if not self._deja and sql.lstrip().startswith("SELECT status FROM mission_states"):
            self._deja = True
            DurableStore(self._chemin).resolve_execution_recovery(
                self._execution, "FAIL", reason="tranche par l'autre ouvrier")
        return curseur


def test_une_recuperation_resolue_par_un_autre_ne_se_rejoue_pas(tmp_path: Path):
    """Le compare-and-swap de la resolution, que rien n'essayait.

    Deux ouvriers peuvent constater la meme execution en RECOVERY_REQUIRED : c'est
    le cas normal apres un redemarrage, et c'est exactement ce que la machine de
    recuperation est censee survivre. Le second doit refuser, pas ecrire un second
    verdict sur une execution deja resolue -- et surtout pas faire passer la mission
    a CANCELLED alors que l'autre vient de la declarer FAILED.

    Le refus est atteignable, contrairement aux relectures du meme fichier : la
    lecture du statut n'ouvre aucune transaction, donc la ligne change vraiment
    entre la lecture et l'ecriture. C'est le `WHERE status='RECOVERY_REQUIRED'` de
    la mise a jour qui le rattrape, et `rowcount != 1` qui le dit.

    La contre-verification, parce qu'un test qui ne prouve que sa propre mise en
    scene ne vaut rien : le garde retire, ce test rougit quand meme -- mais sur
    « Etat courant inattendu : FAILED », leve une ligne plus bas par la transition
    de mission. Aujourd'hui les deux refusent, parce qu'aucune transition ne sort
    une execution de RECOVERY_REQUIRED sans deplacer sa mission. Ce garde-ci est
    celui qui refuse **avant** de toucher la mission, et qui nomme ce qui s'est
    reellement passe ; l'autre nomme un etat, ce qui envoie chercher au mauvais
    endroit. Le jour ou une transition les separerait, il serait le seul.
    """
    import contextlib

    from singular.autopilot import DelegationContract

    chemin = tmp_path / "singular.db"
    store = DurableStore(chemin)
    store.save_mission(DelegationContract("MIS-COURSE", "objectif", "résultat",
                                          autonomy=Autonomy.EXECUTE_REVERSIBLE))
    store.set_mission_status("MIS-COURSE", MissionStatus.PLANNED)
    store.begin_execution_and_start_mission("cle-course", "MIS-COURSE", "ACT-COURSE")
    store.mark_execution_recovery_required("cle-course")

    vraie = store._connect

    @contextlib.contextmanager
    def connexion_espionnee():
        with vraie() as conn:
            yield _ResoutPendantNotreLecture(conn, chemin, "cle-course")

    store._connect = connexion_espionnee
    try:
        with pytest.raises(RuntimeError, match="n'a pas été persistée"):
            store.resolve_execution_recovery("cle-course", "CANCEL", reason="notre verdict")
    finally:
        store._connect = vraie

    # Le verdict de l'autre tient, le notre n'existe nulle part, et la mission
    # porte l'etat que l'autre a ecrit -- pas CANCELLED.
    execution = DurableStore(chemin).get_execution("cle-course")
    assert execution["status"] == "FAILED"
    assert execution["error"] == "tranche par l'autre ouvrier"
    assert DurableStore(chemin).get_mission_status("MIS-COURSE") is MissionStatus.FAILED


@pytest.mark.parametrize("statut", ["SUCCESS", "RUNNING", "RECOVERY_REQUIRED", "completed", ""])
def test_un_resultat_d_execution_n_a_que_deux_mots(tmp_path: Path, statut):
    """`finish_execution_and_mission` est « the only way an execution reaches a
    terminal state », et son vocabulaire n'etait pas garde.

    Les deux mots comptent parce que la transition de mission juste en dessous ne
    connait qu'eux : ecrire « SUCCESS » ou « RECOVERY_REQUIRED » par cette porte
    laisserait une execution dans un etat que la machine ne sait pas lire, et une
    mission qui ne suit pas. « completed » en minuscules est le cas realiste.
    """
    from singular.autopilot import DelegationContract

    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract("MIS-MOTS", "objectif", "résultat",
                                          autonomy=Autonomy.EXECUTE_REVERSIBLE))
    store.set_mission_status("MIS-MOTS", MissionStatus.PLANNED)
    store.begin_execution_and_start_mission("cle-mots", "MIS-MOTS", "ACT-MOTS")

    with pytest.raises(ValueError, match="COMPLETED ou FAILED"):
        store.finish_execution_and_mission("cle-mots", statut)
    assert store.get_execution("cle-mots")["status"] == "RUNNING"
    assert store.get_mission_status("MIS-MOTS") is MissionStatus.RUNNING


@pytest.mark.parametrize("etat", ["RUNNING", "COMPLETED", "FAILED"])
def test_seule_une_execution_en_recuperation_se_confirme_par_preuve(tmp_path: Path, etat):
    """La porte de `confirm_execution_recovery_from_effect`, et rien ne l'essayait.

    C'est la seule transition qui transforme « je ne sais pas si l'effet est
    parti » en succes durable. Elle n'a de sens que depuis RECOVERY_REQUIRED : sur
    une execution qui tourne encore, elle volerait le bail d'un autre ; sur une
    execution deja terminee, elle reecrirait un verdict rendu. Les trois autres
    refus de la meme methode -- preuve absente, preuve d'une autre execution,
    preuve pas COMPLETED -- ont deja leurs temoins ; celui-la, non.
    """
    from singular.autopilot import DelegationContract

    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract("MIS-PREUVE2", "objectif", "résultat",
                                          autonomy=Autonomy.EXECUTE_REVERSIBLE))
    store.set_mission_status("MIS-PREUVE2", MissionStatus.PLANNED)
    store.begin_execution_and_start_mission("cle-preuve2", "MIS-PREUVE2", "ACT-PREUVE2")
    if etat != "RUNNING":
        store.finish_execution_and_mission("cle-preuve2", etat, result={"ok": True})

    with pytest.raises(ValueError, match="Seule une exécution RECOVERY_REQUIRED"):
        store.confirm_execution_recovery_from_effect("cle-preuve2", "cle-fournisseur")
    assert store.get_execution("cle-preuve2")["status"] == etat


# --- ce que le socle durable refuse quand l'identifiant n'existe pas -----------
#
# Quinze des dix-huit survivants de `durable.py` a la passe du 15 septembre 2026
# sont la meme forme : `if row is None: raise KeyError(...)`. Ils etaient
# invisibles a l'outil de mutation tant que sa liste de refus ne portait pas
# `KeyError`, et aucun n'avait de temoin.
#
# L'invariant qu'ils portent ensemble vaut mieux qu'un test chacun : **une
# methode du magasin qui prend un identifiant refuse quand il est inconnu**. Elle
# ne rend jamais un resultat plausible, ni `None` qu'un appelant lirait comme
# « rien a faire ». C'est le fail-closed de la couche qui tient les missions, les
# approbations et les executions.

#: Chaque methode publique qui prend un identifiant, et l'appel qui la nourrit
#: d'un identifiant que rien n'a jamais ecrit.
LECTURES_PAR_IDENTIFIANT = {
    "get_mission_status": lambda s: s.get_mission_status("MIS-inconnue"),
    "get_approval": lambda s: s.get_approval("APP-inconnue"),
    "get_approval_mission": lambda s: s.get_approval_mission("APP-inconnue"),
    "update_approval": lambda s: s.update_approval("APP-inconnue", ApprovalStatus.APPROVED),
    "begin_execution_and_start_mission": lambda s: s.begin_execution_and_start_mission(
        "cle", "MIS-inconnue", "ACT-1"),
    "heartbeat_execution": lambda s: s.heartbeat_execution("cle-inconnue"),
    "mark_execution_recovery_required": lambda s: s.mark_execution_recovery_required("cle-inconnue"),
    "resolve_execution_recovery": lambda s: s.resolve_execution_recovery("cle-inconnue", "FAIL"),
    "confirm_execution_recovery_from_effect": lambda s: s.confirm_execution_recovery_from_effect(
        "cle-inconnue", "cle-fournisseur"),
    "finish_execution_and_mission": lambda s: s.finish_execution_and_mission(
        "cle-inconnue", "COMPLETED"),
}


@pytest.mark.parametrize("methode", sorted(LECTURES_PAR_IDENTIFIANT))
def test_un_identifiant_inconnu_est_refuse_et_rien_n_est_ecrit(tmp_path: Path, methode):
    """Refuser, jamais rendre un resultat plausible.

    `heartbeat_execution` leve un `RuntimeError` la ou les autres levent un
    `KeyError` -- les deux refusent, et la difference est assumee : elle dit
    « inexistante **ou non active** », ce qui n'est pas la meme question.
    """
    store = DurableStore(tmp_path / "singular.db")

    with pytest.raises((KeyError, RuntimeError)):
        LECTURES_PAR_IDENTIFIANT[methode](store)

    with store._connect() as conn:
        for table in ("missions", "approvals", "executions"):
            compte = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            assert compte == 0, f"{methode} a ecrit dans {table} pour un identifiant inconnu"


def test_aucune_lecture_par_identifiant_n_echappe_a_ce_test():
    """Une methode ajoutee demain sans son cas fait rougir la suite.

    La liste ci-dessus est ecrite a la main ; celle-ci est lue dans le code. Le
    critere est « la methode leve un `KeyError` sur son propre parametre », ce qui
    est exactement la forme des quinze survivants.
    """
    import ast

    racine = Path(__file__).resolve().parent.parent
    arbre = ast.parse((racine / "singular/durable.py").read_text(encoding="utf-8"))

    levent = set()
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.FunctionDef) or noeud.name.startswith("_"):
            continue
        parametres = {a.arg for a in noeud.args.args}
        for interne in ast.walk(noeud):
            if (isinstance(interne, ast.Raise) and isinstance(interne.exc, ast.Call)
                    and getattr(interne.exc.func, "id", "") == "KeyError"
                    and interne.exc.args
                    and getattr(interne.exc.args[0], "id", "") in parametres):
                levent.add(noeud.name)

    assert levent, "plus aucun `raise KeyError(<parametre>)` : ce test ne prouve plus rien"
    oubliees = sorted(levent - set(LECTURES_PAR_IDENTIFIANT))
    assert not oubliees, (
        f"ces methodes refusent un identifiant inconnu sans etre essayees : {oubliees}")


def test_une_execution_dont_la_mission_a_disparu_est_refusee(tmp_path: Path):
    """La seconde lecture de `confirm_execution_recovery_from_effect`.

    L'execution existe, elle est bien RECOVERY_REQUIRED, et sa mission n'est plus
    la. Sans ce refus, une execution serait confirmee COMPLETED par preuve
    externe **au nom d'une mission qui n'existe pas** -- et la transition de
    mission qui suit travaillerait dans le vide.

    L'etat est monte en retirant la ligne de mission, comme les tests de
    falsification du journal montent les leurs : c'est le modele de menace de ce
    depot, une base qu'on a editee a cote du code.
    """
    from singular.autopilot import DelegationContract

    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract("MIS-ORPHELINE", "objectif", "résultat",
                                          autonomy=Autonomy.EXECUTE_REVERSIBLE))
    store.set_mission_status("MIS-ORPHELINE", MissionStatus.PLANNED)
    store.begin_execution_and_start_mission("cle-orpheline", "MIS-ORPHELINE", "ACT-1")
    store.mark_execution_recovery_required("cle-orpheline")

    with store._connect() as conn:
        conn.execute("DELETE FROM mission_states WHERE mission_id=?", ("MIS-ORPHELINE",))

    with pytest.raises(KeyError):
        store.confirm_execution_recovery_from_effect("cle-orpheline", "cle-fournisseur")

    assert store.get_execution("cle-orpheline")["status"] == "RECOVERY_REQUIRED", (
        "l'execution reste en attente plutôt que de passer COMPLETED sans mission")
