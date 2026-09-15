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


def _fabriquee(nom: str, modules: tuple[str, ...], **reste) -> Capacite:
    """Une capacite de test, dont seuls les fichiers comptent.

    Les champs declares -- limites, prochaine etape -- sont exiges du vrai registre
    par les tests du bas de ce fichier. Ici ils ne servent a rien : ce qu'on mesure
    est la derivation du barreau, qui ne les regarde pas. Les remplir de texte reel
    ferait croire le contraire.
    """
    return Capacite(nom, modules, limites="sans objet : capacite fabriquee pour un test",
                    prochaine="sans objet : capacite fabriquee pour un test", **reste)


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
    fantome = _fabriquee("fantôme", ("singular/ce_module_n_existe_pas.py",))
    atteint, preuves = niveau(fantome, frozenset())
    assert atteint == "ABSENTE"
    assert any("absents" in preuve for preuve in preuves)


def test_le_code_range_dans_attic_n_est_pas_une_capacite() -> None:
    """La reponse honnete pour les sections 10 et 11 de la doctrine.

    `attic/` n'est pas installe par `packages.find` : ce code existe, il ne fait
    pas partie du systeme. Le nommer HORS SYSTEME plutot qu'IMPLEMENTEE est la
    difference entre un inventaire et une vitrine.
    """
    archive = _fabriquee("archive", ("attic/singular/wealth_engine.py",))
    atteint, preuves = niveau(archive, frozenset())
    assert atteint == "HORS SYSTÈME"
    assert any("attic/" in preuve for preuve in preuves)


def test_un_module_que_rien_n_atteint_reste_concu() -> None:
    """Du code que personne n'importe et qu'aucune commande ne touche.

    `history_world_model.py` est ce cas dans ce depot, et c'est verifie ici plutot
    qu'affirme : seule la table paresseuse du paquet le nomme, aucun module ne
    l'importe, aucune commande n'y mene.
    """
    dormant = _fabriquee("modèle historique", ("singular/history_world_model.py",))
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
    orphelin = _fabriquee("icône du Sage", ("singular/sage/icon.py",))
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
    journal = _fabriquee("journal", ("singular/journal.py",), commandes=("add",))
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


# --- les deux champs declares, et pourquoi ils ne peuvent pas flatter ------------
#
# La directive cumulative exige LIMITATIONS et NEXT STEP pour chaque capacite. Ni
# l'un ni l'autre ne se derive d'un arbre syntaxique : ce sont des jugements. Ils
# sont donc ecrits a la main -- et c'est tenable pour une raison precise : une
# limite declaree ne peut pas flatter, elle dit ce qui manque. Un niveau declare,
# lui, flatterait toujours ; c'est pourquoi le barreau reste derive.
#
# Ce qui peut arriver a un champ declare, en revanche, c'est de se vider : « aucune
# limite connue », « RAS », une chaine blanche. Ces tests le refusent.

#: Ce qu'on ecrit quand on n'a rien a dire, et qui vaut moins que rien : le lecteur
#: croit qu'une limite a ete cherchee.
MOTS_VIDES = ("aucune", "rien à signaler", "ras", "n/a", "aucun", "tbd", "à définir")


@pytest.mark.parametrize("capacite", CAPACITES, ids=lambda c: c.nom)
def test_chaque_capacite_declare_ses_limites(capacite: Capacite) -> None:
    limites = capacite.limites.strip()
    assert limites, f"« {capacite.nom} » ne declare aucune limite"
    assert len(limites) > 30, (
        f"« {capacite.nom} » : une limite d'un mot n'est pas une limite ({limites!r})")
    assert limites.lower() not in MOTS_VIDES, (
        f"« {capacite.nom} » remplit ses limites d'un mot vide : le lecteur croirait "
        "qu'une limite a ete cherchee")


@pytest.mark.parametrize("capacite", CAPACITES, ids=lambda c: c.nom)
def test_chaque_capacite_declare_sa_prochaine_etape(capacite: Capacite) -> None:
    """« Rien » est une reponse valable ici, mais elle doit etre argumentee.

    La difference avec les limites : une capacite peut legitimement n'avoir aucune
    prochaine etape -- le journal sert tous les matins et n'a pas de manque connu.
    Ce qui est refuse est le « rien » nu, sans la raison. `CLAUDE.md` §0 interdit le
    travail dont le seul effet est qu'il y ait du travail ; dire pourquoi on ne
    touche a rien est precisement l'application de cette regle, et ca se lit.
    """
    prochaine = capacite.prochaine.strip()
    assert prochaine, f"« {capacite.nom} » ne declare aucune prochaine etape"
    assert len(prochaine) > 20, (
        f"« {capacite.nom} » : « {prochaine} » ne dit pas assez pour etre suivi")
    assert prochaine.lower() not in MOTS_VIDES


def test_le_rapport_imprime_les_deux_champs() -> None:
    """Declares mais pas imprimes, ils ne serviraient a personne."""
    texte = "\n".join(rapport())
    assert texte.count("limites :") == len(CAPACITES)
    assert texte.count("prochaine :") == len(CAPACITES)


def test_le_niveau_reste_derive_et_ne_peut_pas_etre_declare() -> None:
    """Aucun champ de `Capacite` ne nomme un barreau : la promotion est impossible.

    C'est l'invariant qui fait tenir tout le registre. La directive interdit de
    faire progresser une capacite sans preuve ; la seule facon de le garantir est
    qu'il n'existe aucun endroit ou ecrire un niveau.
    """
    champs = set(Capacite.__dataclass_fields__)
    assert not champs & {"niveau", "statut", "status", "barreau"}, (
        f"un champ permet de declarer un niveau : {champs}")
    for capacite in CAPACITES:
        declare = f"{capacite.limites} {capacite.prochaine} {capacite.note}".upper()
        intrus = [barreau for barreau in ECHELLE if barreau in declare]
        assert not intrus, (
            f"« {capacite.nom} » ecrit un barreau dans un champ declare : {intrus}")
