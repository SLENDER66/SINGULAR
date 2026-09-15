"""Les six refus du canal d'approbation qui survivaient a leur sabotage.

`python3 tools/gardes_sans_test.py approbation`, le 15 septembre 2026 : **six
refus sur sept survivaient**. On pouvait les saboter un par un sans qu'un seul
test tombe. Ce n'etait pas une decouverte fortuite -- le registre de realite
avait d'abord sorti la capacite au barreau TESTEE et pas INSTRUMENTEE, parce que
personne n'avait jamais pointe un mutant sur ces deux modules.

Ce que ces refus gardent est precisement l'anti-substitution : qu'une approbation
donnee pour *cette* action, *cette* mission, *cette* empreinte ne puisse pas
servir a en autoriser une autre. Un garde present mais non prouve a exactement la
valeur d'un garde absent le jour ou quelqu'un le casse en le refactorisant.

Et c'est la raison pour laquelle ils sont ecrits maintenant plutot qu'apres. La
section 44 de la specification demande que le pipeline valide accepte un jour une
decision approuvee par ce canal. Le triage de l'instrument le dit : relier les
deux rendrait atteignables quatre refus aujourd'hui inatteignables. On n'ouvre
pas un chemin vers des gardes qu'on n'a pas prouves -- les temoins d'abord, le
chemin ensuite.

Chaque test ci-dessous correspond a une ligne « SURVIT » du rapport.
"""
from __future__ import annotations

import pytest

from singular.approval_binding import ApprovalBindingStore
from singular.approval_integrity import ApprovalIntegrityStore
from singular.autopilot import ActionRequest
from singular.durable import DurableStore
from singular.mission_runtime import DurableMissionRuntime


def _canal(tmp_path):
    """Une approbation reelle, telle que `route()` la produit, et son contrat.

    Le contrat se relit sur la mission plutot que sur l'action : c'est lui que
    `validate` compare, et `ActionRequest` n'en porte que l'identifiant.
    """
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
    assert routed.governor.approval_id, "cette action devait passer par une approbation"
    contrat = store.load_mission(mission.mission_id)
    return store, runtime, mission, routed.action, routed.governor.approval_id, contrat


# --- approval_binding.py:49 -- les trois moitiés du refus de rebond ----------
#
# La condition refuse qu'une approbation deja liee soit reliee a autre chose. Ses
# trois moitiés se sabotaient separement sans qu'un test tombe : chacune a
# desormais le sien, parce qu'une seule d'entre elles suffit a laisser passer une
# substitution.

def _liaison(tmp_path) -> ApprovalBindingStore:
    store = ApprovalBindingStore(tmp_path / "liaisons.db")
    store.bind("APP-1", "ACT-1", "MIS-1", "empreinte-1")
    return store


def test_une_approbation_ne_se_rebondit_pas_vers_une_autre_action(tmp_path) -> None:
    """La substitution la plus simple : approuver A, executer B."""
    store = _liaison(tmp_path)
    with pytest.raises(ValueError):
        store.bind("APP-1", "ACT-2", "MIS-1", "empreinte-1")
    assert store.get("APP-1")["action_id"] == "ACT-1", "la liaison a bougé"


def test_une_approbation_ne_se_rebondit_pas_vers_une_autre_mission(tmp_path) -> None:
    """Même action, autre mission : l'approbation vaut pour un contexte, pas pour un nom."""
    store = _liaison(tmp_path)
    with pytest.raises(ValueError):
        store.bind("APP-1", "ACT-1", "MIS-2", "empreinte-1")
    assert store.get("APP-1")["mission_id"] == "MIS-1"


def test_une_approbation_ne_se_rebondit_pas_vers_une_autre_empreinte(tmp_path) -> None:
    """Mêmes identifiants, contenu different : c'est la mutation apres approbation."""
    store = _liaison(tmp_path)
    with pytest.raises(ValueError):
        store.bind("APP-1", "ACT-1", "MIS-1", "empreinte-2")
    assert store.get("APP-1")["action_fingerprint"] == "empreinte-1"


def test_relier_deux_fois_la_meme_chose_reste_accepte(tmp_path) -> None:
    """Le cas positif, sans lequel les trois refus ci-dessus pourraient tout refuser.

    Un garde qui refuse aussi ce qu'il devrait accepter passerait les trois tests
    precedents en cassant la reprise apres redemarrage.
    """
    store = _liaison(tmp_path)
    store.bind("APP-1", "ACT-1", "MIS-1", "empreinte-1")
    assert store.get("APP-1")["action_id"] == "ACT-1"


# --- approval_integrity.py:73 -- l'identité native est immuable --------------

def test_l_identite_native_d_une_approbation_ne_se_remplace_pas(tmp_path) -> None:
    """Réécrire les empreintes natives blanchirait une substitution.

    `validate()` compare ce qui est stocke a ce qui est recalcule. Si le stocke
    peut etre reecrit, la comparaison ne prouve plus rien : il suffirait d'y
    ecrire l'empreinte de l'action substituee.
    """
    store, runtime, mission, action, approval_id, contrat = _canal(tmp_path)
    integrite = ApprovalIntegrityStore(store.path)

    autre = ActionRequest(
        name="send_application",
        description="Envoyer une TOUTE AUTRE candidature",
        impact=5,
        risk=4,
        reversibility=6,
        sensitive=True,
        capability="send_email",
    )
    with pytest.raises(ValueError):
        integrite.bind(approval_id, autre, mission.mission_id, None)

    # Et ce qui etait ecrit n'a pas bouge : le refus protege, il ne se contente
    # pas de lever.
    integrite.validate(approval_id, action, mission.mission_id, contrat)


def test_rebinder_la_meme_identite_reste_accepte(tmp_path) -> None:
    """Le cas positif du refus ci-dessus : la reprise apres redemarrage rebinde."""
    store, runtime, mission, action, approval_id, contrat = _canal(tmp_path)
    integrite = ApprovalIntegrityStore(store.path)
    integrite.bind(approval_id, action, mission.mission_id, contrat)
    integrite.validate(approval_id, action, mission.mission_id, contrat)


# --- approval_integrity.py:92 -- une empreinte manquante refuse --------------

def test_une_approbation_sans_empreinte_native_est_refusee(tmp_path) -> None:
    """Le cas le plus dangereux : l'absence de preuve lue comme une preuve.

    Une approbation ecrite avant que ces colonnes existent porte des `NULL`.
    Comparer `NULL` a `NULL` rendrait « identique » -- et une approbation d'un
    autre temps autoriserait n'importe quelle action d'aujourd'hui. Le refus
    distingue « rien ne correspond » de « rien n'est ecrit ».
    """
    store, runtime, mission, action, approval_id, contrat = _canal(tmp_path)
    integrite = ApprovalIntegrityStore(store.path)

    with store._connect() as conn:
        conn.execute(
            "UPDATE approvals SET action_fingerprint=NULL, capability_fingerprint=NULL,"
            " contract_fingerprint=NULL WHERE approval_id=?", (approval_id,))

    with pytest.raises(PermissionError):
        integrite.validate(approval_id, action, mission.mission_id, contrat)
