"""Le port Swift et le moteur Python doivent produire les mêmes observations.

Les vecteurs de `notice_vectors.json` sont le contrat entre les deux. Ils sont
générés depuis Python : ajouter une observation côté Python les change, et le
Swift qui ne la produit pas échouera — mais sur un Mac, chez quelqu'un
d'autre, un jour indéterminé. `tests/test_notice_vector_schema.py` couvre déjà
la forme du JSON ; rien ne couvrait la liste des observations elle-même.

Ce test ne compile pas le Swift, il le lit — même limite et même raison que le
test de schéma. Ce qu'il interdit n'est pas l'écart : c'est l'écart **non
déclaré**. Le port est en retard, c'est un fait assumé, déclaré dans
`ABSENTES_DU_PORT` ; ce qui ne doit pas arriver, c'est qu'une prochaine
observation s'y ajoute sans que personne le sache.

Ce fichier a longtemps porté, dans son propre message d'erreur, l'aveu que les
vecteurs committés exigeaient déjà les deux observations manquantes : l'écart
était déclaré ici et contredit là-bas, et la suite Swift échouait pour de bon
sur un Mac. C'est le générateur qui refuse maintenant d'écrire un tel vecteur.
"""
from __future__ import annotations

import pathlib
import re

from tools.generate_notice_vectors import ABSENTES_DU_PORT

RACINE = pathlib.Path(__file__).resolve().parent.parent
PYTHON = RACINE / "singular/sage/notice.py"
SWIFT = RACINE / "ios/SingularSage/Core/Notice.swift"

def _en_swift(nom_python: str) -> str:
    """`_unresolved_hours_item` devient `unresolvedHoursItem`."""
    morceaux = nom_python.lstrip("_").split("_")
    return morceaux[0] + "".join(morceau.title() for morceau in morceaux[1:])


#: Une ligne du dictionnaire de `_candidates` : sa clé, puis la fonction appelée.
LIGNE = re.compile(r'"(\w+)":\s*(\w+)\(')


def _lignes_des_candidats() -> list[tuple[str, str]]:
    source = PYTHON.read_text(encoding="utf-8")
    depart = source.find("def _candidates(")
    assert depart >= 0, "`_candidates` a disparu de notice.py"
    bloc = re.search(r"return \{\n(.*?)\n    \}", source[depart:], flags=re.DOTALL)
    assert bloc, "le dictionnaire de `_candidates` n'a plus la même forme"
    lignes = LIGNE.findall(bloc.group(1))
    assert lignes, "aucune observation lue : l'analyse a changé de forme"
    return lignes


def test_chaque_cle_nomme_la_fonction_qu_elle_appelle() -> None:
    """La clé est le nom de la fonction. Deux écritures, donc un test.

    C'est le prix du nommage : sans lui, personne ne sait quelle fonction a
    écrit une phrase. Une clé qui ment ferait croire au générateur de vecteurs
    qu'une observation absente du port n'a pas été produite.
    """
    for cle, appelee in _lignes_des_candidats():
        assert cle == appelee, f"la clé {cle!r} appelle {appelee!r}"


def _observations_python() -> set[str]:
    """Les fonctions réellement branchées dans la Notice, pas toutes celles définies."""
    # Le tiret bas de tête est facultatif : `foundation_item` est publique
    # depuis que `python -m singular review` l'appelle au lieu de réécrire
    # la règle. Une observation publique reste une observation.
    return {_en_swift(cle) for cle, _ in _lignes_des_candidats()}


def _observations_swift() -> set[str]:
    source = SWIFT.read_text(encoding="utf-8")
    noms = set(re.findall(r"static func (\w+Item)\(", source))
    assert noms, "aucune observation lue dans le Swift : l'analyse a changé de forme"
    return noms


def test_le_port_ne_prend_pas_de_retard_sans_qu_on_le_dise() -> None:
    manquantes = _observations_python() - _observations_swift()

    declarees = {_en_swift(nom) for nom in ABSENTES_DU_PORT}

    assert manquantes == declarees, (
        "l'écart entre le moteur Python et le port Swift a changé.\n"
        f"  absentes du Swift : {sorted(manquantes)}\n"
        f"  déclarées comme telles : {sorted(declarees)}\n"
        "Implémente-les côté Swift, ou déclare-les dans ABSENTES_DU_PORT "
        "(`tools/generate_notice_vectors.py`) en disant pourquoi. Le générateur "
        "refusera d'écrire un vecteur qui les déclenche : sans ça, le port "
        "échoue sur un Mac, loin d'ici."
    )


def test_le_port_ne_produit_rien_que_python_ignore() -> None:
    """L'inverse compte aussi : une observation qui n'existerait que côté Swift.

    Elle ne serait couverte par aucun vecteur, donc par rien du tout.
    """
    assert not _observations_swift() - _observations_python()
