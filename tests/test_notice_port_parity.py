"""Le port Swift et le moteur Python doivent produire les mêmes observations.

Les vecteurs de `notice_vectors.json` sont le contrat entre les deux. Ils sont
générés depuis Python : ajouter une observation côté Python les change, et le
Swift qui ne la produit pas échouera — mais sur un Mac, chez quelqu'un
d'autre, un jour indéterminé. `tests/test_notice_vector_schema.py` couvre déjà
la forme du JSON ; rien ne couvrait la liste des observations elle-même.

Ce test ne compile pas le Swift, il le lit — même limite et même raison que le
test de schéma. Ce qu'il interdit n'est pas l'écart : c'est l'écart **non
déclaré**. Le port est en retard, c'est un fait assumé et écrit ci-dessous ;
ce qui ne doit pas arriver, c'est qu'une prochaine observation s'y ajoute sans
que personne le sache.
"""
from __future__ import annotations

import pathlib
import re

RACINE = pathlib.Path(__file__).resolve().parent.parent
PYTHON = RACINE / "singular/sage/notice.py"
SWIFT = RACINE / "ios/SingularSage/Core/Notice.swift"

#: Ce que le port ne sait pas encore produire, et pourquoi c'est accepté.
#:
#: Aucun compilateur Swift n'est installable dans l'environnement qui écrit ce
#: dépôt : la passerelle refuse swift.org et les binaires GitHub, c'est
#: vérifié. Écrire ici du Swift qu'on ne peut ni compiler ni exécuter
#: ajouterait du code invérifiable à un port qui n'a jamais été compilé, pour
#: une application qui ne tourne sur aucune machine disponible. L'application
#: web, elle, tourne et sert ces deux observations aujourd'hui.
#:
#: Retirer un nom d'ici sans l'implémenter côté Swift fait échouer ce test.
ABSENTES_DU_PORT = {
    "irreversibleItem",   # engagement irréversible sans verdict
    "unpricedItem",       # heures engagées sans gain attendu
}


def _observations_python() -> set[str]:
    """Les fonctions réellement branchées dans `build_notice`, pas toutes celles définies."""
    source = PYTHON.read_text(encoding="utf-8")
    bloc = re.search(r"candidates = \((.*?)\n    \)", source, flags=re.DOTALL)
    assert bloc, "le bloc « candidates » de build_notice n'a plus la même forme"
    noms = set(re.findall(r"_(\w+?)_item\(", bloc.group(1)))
    assert noms, "aucune observation lue : l'analyse a changé de forme"
    return {nom.split("_")[0] + "".join(m.title() for m in nom.split("_")[1:]) + "Item"
            for nom in noms}


def _observations_swift() -> set[str]:
    source = SWIFT.read_text(encoding="utf-8")
    noms = set(re.findall(r"static func (\w+Item)\(", source))
    assert noms, "aucune observation lue dans le Swift : l'analyse a changé de forme"
    return noms


def test_le_port_ne_prend_pas_de_retard_sans_qu_on_le_dise() -> None:
    manquantes = _observations_python() - _observations_swift()

    assert manquantes == ABSENTES_DU_PORT, (
        "l'écart entre le moteur Python et le port Swift a changé.\n"
        f"  absentes du Swift : {sorted(manquantes)}\n"
        f"  déclarées comme telles : {sorted(ABSENTES_DU_PORT)}\n"
        "Implémente-les côté Swift, ou déclare-les dans ABSENTES_DU_PORT en "
        "disant pourquoi. Les vecteurs committés attendent déjà ces observations : "
        "un port en retard échoue sur un Mac, loin d'ici."
    )


def test_le_port_ne_produit_rien_que_python_ignore() -> None:
    """L'inverse compte aussi : une observation qui n'existerait que côté Swift.

    Elle ne serait couverte par aucun vecteur, donc par rien du tout.
    """
    assert not _observations_swift() - _observations_python()
