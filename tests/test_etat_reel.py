"""Un registre de realite qui se trompe est pire qu'aucun registre.

`tools/etat_reel.py` repond a la question que la directive pose en permanence --
« ou sommes-nous, et qu'est-ce qui fonctionne vraiment » -- et il y repond en
derivant tout de l'arbre, jamais en lisant un niveau ecrit a la main. Ce fichier
garde les deux facons dont il pourrait mentir :

1. **en se trompant sur ce qu'il declare** : un module renomme, une commande qui
   n'existe plus, et le registre decrit un depot imaginaire en restant vert ;
2. **en etant complaisant** : une echelle dont tout le monde atteint le sommet ne
   mesure rien, et un barreau qui se donne sans preuve est precisement le
   « faux progres » que la directive interdit.

Le second est le plus dangereux, parce qu'il ne casse rien. Les tests d'echelle
ci-dessous verifient donc chaque barreau sur des cas fabriques, ou l'on sait ce
que la reponse doit etre.
"""
from __future__ import annotations

import pathlib

import pytest

from tools.etat_reel import (
    CAPACITES,
    ECHELLE,
    Capacite,
    cibles_de_l_instrument,
    niveau,
    rapport,
)

RACINE = pathlib.Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("capacite", CAPACITES, ids=lambda c: c.nom)
def test_chaque_module_declare_existe(capacite: Capacite) -> None:
    """Un chemin mort rendrait la capacite ABSENTE sans que personne le sache.

    C'est le defaut qu'`A_FAIRE.md` raconte pour la documentation : le texte dit
    une chose, le disque une autre, et on ne l'apprend qu'en perdant une seance.
    """
    manquants = [nom for nom in capacite.modules if not (RACINE / nom).exists()]
    assert not manquants, f"« {capacite.nom} » nomme des fichiers absents : {manquants}"


@pytest.mark.parametrize("capacite", CAPACITES, ids=lambda c: c.nom)
def test_chaque_commande_declaree_existe_vraiment(capacite: Capacite) -> None:
    """Les commandes sont lues dans le vrai analyseur, pas recopiees.

    Une sous-commande renommee ferait dire au registre qu'une capacite est
    atteignable par un chemin qui n'existe plus.
    """
    from singular.__main__ import build_parser

    actions = build_parser()._subparsers._group_actions  # noqa: SLF001 - argparse n'expose rien d'autre
    reelles = set(actions[0].choices) if actions else set()
    inconnues = [nom for nom in capacite.commandes if nom not in reelles]
    assert not inconnues, f"« {capacite.nom} » nomme des commandes inexistantes : {inconnues}"


def test_le_registre_ne_promet_jamais_la_production() -> None:
    """Le mot interdit, et la raison imprimee a chaque execution.

    La directive demande INCONNU plutot que « probablement bon ». Un registre qui
    accorderait PRODUCTION-READY depuis une lecture statique de l'arbre serait
    exactement l'illusion d'avancement qu'elle interdit.
    """
    assert "PRODUCTION-READY" not in ECHELLE
    assert "PRODUCTION-READY : INCONNU" in "\n".join(rapport())

    # Lu dans la derivation et non dans le texte : le pied de page contient le mot
    # exprès, et une premiere version de ce test s'y trompait -- elle lisait la
    # ligne qui annonce INCONNU comme un barreau accorde.
    accordes = {niveau(capacite, cibles_de_l_instrument())[0] for capacite in CAPACITES}
    assert accordes <= set(ECHELLE), f"un barreau hors echelle a ete accorde : {accordes}"


# --- l'echelle, barreau par barreau, sur des cas ou la reponse est connue -------


def test_une_capacite_sans_fichier_est_absente(tmp_path) -> None:
    fantome = Capacite("fantôme", ("singular/ce_module_n_existe_pas.py",))
    atteint, preuves = niveau(fantome, frozenset())
    assert atteint == "ABSENTE"
    assert any("absents" in preuve for preuve in preuves)


def test_le_code_range_dans_attic_n_est_pas_une_capacite() -> None:
    """La reponse honnete pour les sections 10 et 11 de la doctrine.

    `attic/` n'est pas installe par `packages.find` : ce code existe, il ne fait
    pas partie du systeme. Le nommer HORS SYSTEME plutot qu'IMPLEMENTEE est la
    difference entre un inventaire et une vitrine.
    """
    archive = Capacite("archive", ("attic/singular/wealth_engine.py",))
    atteint, preuves = niveau(archive, frozenset())
    assert atteint == "HORS SYSTÈME"
    assert any("attic/" in preuve for preuve in preuves)


def test_un_module_que_rien_n_atteint_reste_concu() -> None:
    """Du code que personne n'importe et qu'aucune commande ne touche.

    `history_world_model.py` est ce cas dans ce depot, et c'est verifie ici plutot
    qu'affirme : seule la table paresseuse du paquet le nomme, aucun module ne
    l'importe, aucune commande n'y mene.
    """
    dormant = Capacite("modèle historique", ("singular/history_world_model.py",))
    atteint, _preuves = niveau(dormant, frozenset())
    assert atteint == "CONÇUE"


def test_un_module_atteignable_sans_test_ne_depasse_pas_implementee() -> None:
    """Le barreau TESTEE se gagne par un test qui nomme le module, pas autrement.

    Le cas est reel et il est unique dans ce depot : `singular/sage/icon.py` est
    importe par le serveur du Sage et aucun test ne l'importe. C'est verifie par le
    balayage plutot que choisi, pour que ce test cesse de mesurer le jour ou
    quelqu'un lui ecrit un test -- et il faudra alors en trouver un autre, ou
    constater que le depot n'a plus de module orphelin.
    """
    orphelin = Capacite("icône du Sage", ("singular/sage/icon.py",))
    atteint, preuves = niveau(orphelin, cibles_de_l_instrument())
    assert atteint == "IMPLÉMENTÉE", (
        f"{atteint} : soit un test nomme desormais ce module, soit la derivation "
        "s'est relachee")
    assert any("importé par" in preuve for preuve in preuves)


def test_le_dernier_barreau_exige_l_instrument_et_pas_un_mot() -> None:
    """INSTRUMENTEE ne se donne que si l'outil de mutation cible vraiment le module.

    Le sommet est lu dans `gardes_sans_test.GROUPES`, donc retirer un module de
    ses cibles fait redescendre la capacite. C'est ce qui empeche le barreau de
    devenir un adjectif.
    """
    journal = Capacite("journal", ("singular/journal.py",), ("add",))
    assert niveau(journal, cibles_de_l_instrument())[0] == "INSTRUMENTÉE"
    assert niveau(journal, frozenset())[0] == "TESTÉE"


def test_l_echelle_discrimine_encore() -> None:
    """Un barreau que tout atteint ne mesure rien -- et ce test le dira.

    La docstring de l'outil l'annonce : si `INSTRUMENTÉE` finit par decrire tout le
    depot, ce n'est pas que le depot est bon, c'est que l'echelle a cesse de
    discriminer. Ce test echoue alors, et demande d'ajouter un barreau plutot que
    de se feliciter.
    """
    mesures = cibles_de_l_instrument()
    atteints = {niveau(capacite, mesures)[0] for capacite in CAPACITES}
    assert len(atteints) >= 3, (
        "toutes les capacites tombent dans moins de trois barreaux : l'echelle ne "
        f"discrimine plus (atteints : {sorted(atteints)})")
