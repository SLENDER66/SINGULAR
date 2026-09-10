"""Un test ne recopie pas un message de SINGULAR sans ses accents.

Quatre fois dans la même journée, une correction du français d'un message a
fait tomber un test qui l'attendait au caractère près : « refuse », « ecris tes
tarifs », « jetons envoyes », « un cout n'est pas un gain », « pour 75 %, ecris
0.75 ». Aucun comportement n'avait changé.

C'est le pire type de test. Il ne prouve rien de plus qu'une comparaison
tolérante, et il **punit la correction des messages** -- donc il apprend à ne
plus les corriger. À la quatrième, la règle du dépôt dit d'arrêter de corriger
et de rendre l'erreur impossible.

La règle se découvre plutôt qu'elle ne s'énumère : un littéral de test qui se
retrouve, accents ôtés, dans une phrase affichée par le programme, mais qui ne
s'y retrouve pas tel qu'il est écrit, est une recopie fautive. Deux sorties
honnêtes : recopier les accents, ou passer par `sans_accents()` de
`tests/support.py` -- auquel cas la comparaison est faite sur la forme sans
accents des deux côtés, et ce test ne voit rien à redire.

Ce que ce fichier ne prétend pas faire : juger le français. Il ne connaît aucun
dictionnaire. Il compare le dépôt à lui-même, ce qui suffit -- l'erreur qu'on
veut rendre impossible est toujours une divergence entre deux endroits du
dépôt, jamais une faute d'orthographe dans l'absolu.
"""
from __future__ import annotations

import ast
import functools
import pathlib
import unicodedata

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
TESTS = RACINE / "tests"

#: Les modules dont les chaînes finissent sous ses yeux. Même liste d'esprit
#: que `SPEAKS_TO_THE_CONSOLE` dans `test_windows_console.py`, élargie à ce que
#: l'app affiche.
AFFICHENT = ("singular/__main__.py", "singular/saisie.py", "singular/sage/server.py",
             "singular/sage/notice.py", "singular/parle.py", "singular/analyse.py",
             "singular/offres.py", "singular/journal.py",
             "proto/suivi_candidatures.py")


def _sans_accents(texte: str) -> str:
    decompose = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in decompose if not unicodedata.combining(c))


def _docstrings(arbre: ast.Module) -> set[int]:
    """Les docstrings, qui expliquent le code et ne s'affichent jamais.

    Sans cette exclusion le corpus contenait des paragraphes entiers de prose
    interne, et n'importe quel bout de phrase d'un test finissait par y
    ressembler : le garde-fou criait au loup sur cinq fichiers.
    """
    portees = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    trouves = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, portees) and getattr(noeud, "body", None):
            premier = noeud.body[0]
            if (isinstance(premier, ast.Expr) and isinstance(premier.value, ast.Constant)
                    and isinstance(premier.value.value, str)):
                trouves.add(id(premier.value))
    return trouves


def _phrases_affichees(*, accentuees_seulement: bool = True) -> list[str]:
    """Toute chaîne d'au moins trois mots que le programme montre.

    Deux usages, et la distinction compte : la détection ne s'intéresse qu'aux
    phrases **accentuées**, puisqu'une phrase sans accent ne peut pas être mal
    recopiée ; mais reconnaître une citation exacte demande de les voir toutes.
    Sans ça, un test qui cite fidèlement une phrase encore sans accents se
    faisait accuser parce qu'une **autre** phrase, ailleurs, portait les mêmes
    mots correctement écrits.
    """
    phrases = []
    for nom in AFFICHENT:
        arbre = ast.parse((RACINE / nom).read_text(encoding="utf-8"))
        docs = _docstrings(arbre)
        for noeud in ast.walk(arbre):
            if not (isinstance(noeud, ast.Constant) and isinstance(noeud.value, str)):
                continue
            texte = noeud.value
            if id(noeud) in docs or "\n\n" in texte:
                continue
            if texte.count(" ") < 2:
                continue
            if accentuees_seulement and _sans_accents(texte) == texte.lower():
                continue
            phrases.append(texte)
    return phrases


def _sous_sans_accents(arbre: ast.Module) -> set[int]:
    """Les litteraux des instructions qui passent par `sans_accents`.

    Comparer sans accents des deux cotes est la sortie que ce fichier propose :
    les signaler serait refuser sa propre solution.

    L'exemption vise l'**instruction** entiere, pas une forme d'appel. Elle a
    d'abord vise `sans_accents("...")`, puis il a fallu ajouter
    `"..." in sans_accents(x)`, puis `sans_accents(x).partition("...")`, puis
    une boucle sur un tuple compare plus bas. Chaque forme oubliee accusait a
    tort un test deja correct, et il en restait toujours une. Une instruction
    qui nomme `sans_accents` compare sans accents : c'est ce qui compte, et ca
    ne se decline pas.
    """
    exemptes = set()
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.stmt):
            continue
        mentionne = any(isinstance(interne, ast.Name) and interne.id.endswith("sans_accents")
                        for interne in ast.walk(noeud))
        if not mentionne:
            continue
        for interne in ast.walk(noeud):
            if isinstance(interne, ast.Constant):
                exemptes.add(id(interne))
    return exemptes


@functools.lru_cache(maxsize=1)
def _toutes_les_phrases() -> tuple[str, ...]:
    return tuple(_phrases_affichees(accentuees_seulement=False))


def _recopies_fautives(source: str, phrases: list[str]) -> list[str]:
    fautes = []
    arbre = ast.parse(source)
    exemptes = _sous_sans_accents(arbre) | _docstrings(arbre)
    for noeud in ast.walk(arbre):
        if not (isinstance(noeud, ast.Constant) and isinstance(noeud.value, str)):
            continue
        if id(noeud) in exemptes:
            continue
        attendu = noeud.value.strip()
        if attendu.count(" ") < 2 or _sans_accents(attendu) != attendu.lower():
            continue  # trop court, ou deja ecrit avec ses accents
        nu = _sans_accents(attendu)
        # Un litteral qui se retrouve **tel quel** quelque part est une recopie
        # exacte, pas une recopie fautive -- meme si un autre message, ailleurs,
        # ecrit les memes mots avec leurs accents. Chercher la faute avant
        # d'avoir cherche la correspondance exacte accusait `test_proto_suivi.py`
        # de mal recopier `proto/suivi_candidatures.py`, qu'il citait juste.
        if any(attendu.lower() in phrase.lower() for phrase in _toutes_les_phrases()):
            continue
        for phrase in phrases:
            if nu in _sans_accents(phrase):
                fautes.append(f"ligne {noeud.lineno} : « {attendu} » -- le programme"
                              f" ecrit « {phrase.strip()[:70]} »")
                break
    return fautes


def test_le_corpus_de_phrases_n_est_pas_vide() -> None:
    """Sans phrases a comparer, le garde-fou passerait en ne cherchant rien."""
    phrases = _phrases_affichees()
    assert len(phrases) > 50, len(phrases)


@pytest.mark.parametrize(
    "fichier", sorted(p.name for p in TESTS.glob("test_*.py")),
)
def test_aucun_test_ne_recopie_un_message_sans_ses_accents(fichier: str) -> None:
    fautes = _recopies_fautives((TESTS / fichier).read_text(encoding="utf-8"),
                                _phrases_affichees())
    assert not fautes, (
        f"{fichier} attend un message de SINGULAR au caractere pres :\n  "
        + "\n  ".join(fautes)
        + "\nRecopie les accents, ou compare via `sans_accents()` de tests/support.py."
    )
