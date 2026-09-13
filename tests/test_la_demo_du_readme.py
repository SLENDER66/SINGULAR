"""La demonstration que le README montre doit etre celle que le programme donne.

`examples/governed_http_effect.py` est la seule preuve de bout en bout qu'un
lecteur voit : socket reelle, SQLite reelle, aucun mock. Le README recopie sa
sortie ligne par ligne -- et rien ne les comparait. Une signature qui change dans
la frontiere, et le bloc du README devient une fiction que personne ne verra
vieillir, sur la page qui sert a juger si ce depot vaut qu'on le lise.

Ce test en fait la seule copie : l'attente n'est pas ecrite ici, elle est lue
dans le README. Les deux ne peuvent plus diverger, dans aucun sens -- corriger
le programme sans corriger la page echoue, et l'inverse aussi.

Il est aussi la seule verification qui traverse un **processus** entier. Le defaut
du jour se cachait exactement la : une methode greffee sur le store survivait dans
la classe pour tous les tests du meme processus, et manquait a un programme qui
demarre. Un sous-processus ne peut pas heriter de cet accident.

Les empreintes sont masquees : elles changent a chaque execution, et une page qui
promettrait la meme qu'hier serait fausse pour de bon.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
DEMO = RACINE / "examples" / "governed_http_effect.py"

#: Une empreinte tronquee -- `9e201407fc5f228c…` -- ou entiere.
EMPREINTE = re.compile(r"\b[0-9a-f]{8,}…?")


def _masque(ligne: str) -> str:
    return EMPREINTE.sub("<empreinte>", ligne.rstrip())


def _bloc_du_readme() -> list[str]:
    """Le bloc de sortie que le README affiche, celui qui commence par la decision."""
    lignes = (RACINE / "README.md").read_text(encoding="utf-8").split("\n")
    blocs: list[list[str]] = []
    courant: list[str] | None = None
    for ligne in lignes:
        if ligne.startswith("```"):
            if courant is None:
                courant = []
            else:
                blocs.append(courant)
                courant = None
            continue
        if courant is not None:
            courant.append(ligne)
    candidats = [bloc for bloc in blocs
                 if any(ligne.startswith("decision      DEC-DEMO") for ligne in bloc)]
    assert len(candidats) == 1, "le README doit montrer la sortie de la demo une fois, et une seule"
    return [ligne for ligne in candidats[0] if ligne.strip()]


def _sortie_de_la_demo() -> list[str]:
    acheve = subprocess.run(
        [sys.executable, str(DEMO)], capture_output=True, text=True, cwd=RACINE,
        timeout=120, check=False,
    )
    assert acheve.returncode == 0, f"la demo du README echoue :\n{acheve.stdout}\n{acheve.stderr}"
    return [ligne for ligne in acheve.stdout.split("\n") if ligne.strip()]


@pytest.fixture(scope="module")
def sortie() -> list[str]:
    return _sortie_de_la_demo()


def test_la_demo_dit_exactement_ce_que_le_readme_montre(sortie: list[str]):
    attendu = [_masque(ligne) for ligne in _bloc_du_readme()]
    obtenu = [_masque(ligne) for ligne in sortie]
    assert obtenu == attendu, (
        "la sortie de la demo et le bloc du README ont divergé.\n"
        f"README : {attendu}\ndemo   : {obtenu}"
    )


def test_l_effet_n_a_touche_le_reseau_qu_une_fois(sortie: list[str]):
    """Le compte d'appels est le fait ; le reste du bloc est la phrase autour de lui.

    Verifie a part, parce que c'est la seule ligne du bloc dont la valeur prouve
    quelque chose : un rejeu ou un paiement substitue qui repartirait vers le
    serveur ferait passer ce compte a deux, et le test ci-dessus le verrait -- mais
    il rougirait pour « les phrases ont diverge », ce qui ferait chercher au mauvais
    endroit.
    """
    assert any("server calls: 1" in ligne for ligne in sortie)
    assert sum("server calls still 1" in ligne for ligne in sortie) == 2, (
        "le rejeu et la substitution doivent tous deux laisser le compte a 1"
    )


def test_la_substitution_de_charge_est_refusee_par_la_frontiere(sortie: list[str]):
    refus = [ligne for ligne in sortie if ligne.startswith("refused")]
    assert len(refus) == 1 and "payload does not match the validated decision" in refus[0], refus
