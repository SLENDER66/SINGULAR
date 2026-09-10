"""Une seule porte ecrit dans le journal, et c'est `journal.py`.

Tout ce depot repose sur une phrase de l'en-tete de `singular/journal.py` :
« A journal you can edit afterwards teaches you nothing. » Elle tient parce que
`add()`, `resolve()` et `abandon()` sont les seuls chemins d'ecriture, qu'ils
serialisent la lecture de la tete de chaine, et qu'ils signent chaque entree
derriere la precedente.

Rien ne l'obligeait. Une session pressee -- un nouvel ecran, une migration, un
import de donnees -- pouvait ouvrir la base et ecrire une ligne a la main. La
ligne serait acceptee, la chaine serait rompue, et `verify()` rendrait faux
pour toujours puisqu'une entree ne se reecrit pas. Le journal ne se repare pas :
il se recommence.

Ce fichier n'attend pas la premiere fois. Il refuse une ecriture SQL sur la
table du journal ailleurs que dans `journal.py`, et nomme le fichier fautif.

Le pendant de `tests/test_saisie_au_clavier.py`, qui garde l'autre versant :
personne n'appelle `journal.add()` sans traverser `singular.saisie`.
"""
from __future__ import annotations

import ast
import pathlib
import re

RACINE = pathlib.Path(__file__).resolve().parent.parent

#: Le domicile unique de l'ecriture.
DOMICILE = RACINE / "singular" / "journal.py"

#: Ou l'on cherche : tout le code qui tourne chez lui.
SOURCES = [chemin
           for dossier in ("singular", "tools", "proto")
           for chemin in sorted((RACINE / dossier).rglob("*.py"))]

#: Une ecriture SQL sur la table du journal.
ECRITURE = re.compile(r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|DROP\s+TABLE|ALTER\s+TABLE)\b"
                      r"[\s\S]{0,80}?\bjournal_entries\b", re.IGNORECASE)

#: La seule exception, et pourquoi elle est admise.
#:
#: Le generateur de vecteurs simule une chaine rompue pour que le port Swift
#: puisse verifier qu'il la detecte. Il ecrit donc sous le journal, exprès, et
#: sa propre docstring explique qu'il n'existe aucun autre chemin : rien dans
#: l'API ne reecrit une entree, et c'est bien la le sujet.
TOLEREES = {
    "tools/generate_notice_vectors.py":
        "simule une chaine rompue pour le vecteur « chaine_rompue »",
}


def _ecritures(chemin: pathlib.Path) -> list[tuple[int, str]]:
    """Les litteraux de ce fichier qui ecrivent dans la table du journal.

    On lit les chaines de l'arbre syntaxique et pas le fichier brut : un
    commentaire qui cite du SQL n'ecrit rien, et un test qui crie au loup finit
    desactive.
    """
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    trouves = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str) \
                and ECRITURE.search(noeud.value):
            trouves.append((noeud.lineno, " ".join(noeud.value.split())[:70]))
    return trouves


def test_seul_le_journal_ecrit_dans_le_journal() -> None:
    fautes = []
    for chemin in SOURCES:
        relatif = chemin.relative_to(RACINE).as_posix()
        if chemin == DOMICILE or relatif in TOLEREES:
            continue
        fautes += [f"{relatif}:{ligne} — {sql}" for ligne, sql in _ecritures(chemin)]

    assert not fautes, (
        "ces fichiers ecrivent dans la table du journal sans passer par "
        "`journal.py` :\n  " + "\n  ".join(fautes)
        + "\n  La chaine d'integrite se construit dans `add()`, `resolve()` et "
        "`abandon()`. Une ligne ecrite a cote la rompt pour toujours : le "
        "journal ne se repare pas, il se recommence."
    )


def test_l_exception_declaree_existe_vraiment() -> None:
    """Une tolerance qui ne protege plus rien doit disparaitre de la liste."""
    for relatif, raison in TOLEREES.items():
        chemin = RACINE / relatif
        assert chemin.exists(), f"{relatif} n'existe plus : retire-le de TOLEREES"
        assert _ecritures(chemin), (
            f"{relatif} n'ecrit plus dans le journal ({raison}) : retire-le de "
            "TOLEREES, sinon la porte reste ouverte pour rien")


def test_le_scan_verrait_une_ecriture_clandestine(tmp_path) -> None:
    """Le temoin : un analyseur qui ne trouve rien passerait au vert."""
    coupable = tmp_path / "coupable.py"
    coupable.write_text(
        'import sqlite3\n'
        'def triche(conn):\n'
        '    conn.execute("INSERT INTO journal_entries(entry_id) VALUES(?)", ("DEC-0",))\n',
        encoding="utf-8")
    assert _ecritures(coupable)

    innocent = tmp_path / "innocent.py"
    innocent.write_text(
        '"""On parle de journal_entries sans y toucher, et on lit la table."""\n'
        'def lire(conn):\n'
        '    return conn.execute("SELECT * FROM journal_entries").fetchall()\n',
        encoding="utf-8")
    assert not _ecritures(innocent), "lire n'est pas ecrire"


def test_le_domicile_ecrit_bien_lui() -> None:
    """Et le temoin du temoin : sans ecriture nulle part, tout ceci est creux."""
    assert len(_ecritures(DOMICILE)) >= 3, "add, resolve et abandon ecrivent"
    assert len(SOURCES) > 20
