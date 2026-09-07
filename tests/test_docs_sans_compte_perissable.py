"""Aucun document ne réécrit un nombre qu'une commande sait compter.

Trois fois la même panne : « huit étapes du CV » alors qu'il y en avait cinq,
« huit branches » alors qu'il y en avait dix, et le compte d'écart entre deux
branches avant elles. Chaque fois un lecteur — moi, ou une session future — a
cru le texte plutôt que l'outil.

`CLAUDE.md` §24 dit qu'à la troisième occurrence on cesse de corriger et on
rend l'erreur impossible. Ce fichier est cette troisième occurrence.

Il ne condamne pas tout chiffre : « laissée 39 commits en arrière » raconte un
incident daté qui ne bougera plus, et « les deux branches » est structurel.
Ce qui est interdit est précis : annoncer un nombre pour une collection qu'un
outil énumère déjà.

* les étapes du CV : la source vivante est `ETAPES_CV`, et le test compare ;
* les branches du dépôt distant : aucune source hors ligne, donc le compte est
  interdit en toutes lettres — `tools/check_repo_state.py` les liste.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCUMENTS = ["A_FAIRE.md", "CLAUDE.md", "PROMPT_NOUVELLE_CONVERSATION.md", "proto/README.md"]

MOTS = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6,
    "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12,
}
NOMBRE = r"\d+|" + "|".join(MOTS)


def _valeur(brut: str) -> int:
    return int(brut) if brut.isdigit() else MOTS[brut.lower()]


def _etapes_du_cv() -> list[str]:
    source = ROOT / "proto" / "suivi_candidatures.py"
    spec = importlib.util.spec_from_file_location("proto_etapes", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules["proto_etapes"] = module
    spec.loader.exec_module(module)
    return module.ETAPES_CV


#: Un document est replié à la main : « huit branches traînent encore\nsur
#: GitHub » met le sujet et son contexte sur deux lignes. Un test qui raisonne
#: par ligne rate exactement ce cas -- il l'a raté à sa première écriture.
#: On regarde donc autour du nombre, pas la ligne qui le porte.
FENETRE = 140


def _contexte(texte: str, debut: int, fin: int) -> str:
    return texte[max(0, debut - FENETRE):fin + FENETRE]


def _trouver(relative: str, nom: str, proche: str):
    """Chaque « <nombre> <nom> » dont le voisinage parle de `proche`."""
    texte = (ROOT / relative).read_text(encoding="utf-8")
    for trouve in re.finditer(rf"\b({NOMBRE})\s+{nom}\b", texte, flags=re.IGNORECASE):
        if not re.search(proche, _contexte(texte, trouve.start(), trouve.end()), flags=re.IGNORECASE):
            continue
        ligne = texte[:trouve.start()].count("\n") + 1
        yield f"{relative}:{ligne} annonce « {trouve.group(0)} »", _valeur(trouve.group(1))


@pytest.mark.parametrize("relative", DOCUMENTS)
def test_un_compte_d_etapes_annonce_est_le_vrai(relative: str) -> None:
    """Si un document dit combien d'étapes compte le CV, il doit avoir raison."""
    attendu = len(_etapes_du_cv())
    fautes = [ou for ou, valeur in _trouver(relative, "étapes", "CV") if valeur != attendu]

    assert not fautes, (
        f"le CV compte {attendu} etape(s) dans ETAPES_CV :\n  " + "\n  ".join(fautes)
        + "\n  écris « les étapes du CV » plutôt qu'un nombre qui vieillira."
    )


@pytest.mark.parametrize("relative", DOCUMENTS)
def test_aucun_document_ne_compte_les_branches_du_depot(relative: str) -> None:
    """Le nombre de branches sur origin ne se vérifie pas hors ligne : pas de nombre.

    « les deux branches » reste permis : la branche par défaut et la branche de
    travail sont deux par construction, pas par comptage. C'est pour ça que le
    voisinage doit parler du dépôt distant pour que le compte soit refusé.
    """
    fautes = [ou for ou, _ in _trouver(relative, "branches", r"GitHub|origin|distant")]

    assert not fautes, (
        "ce compte vieillira sans que personne le voie :\n  " + "\n  ".join(fautes)
        + "\n  dis « plusieurs branches » et laisse check_repo_state.py les lister."
    )
