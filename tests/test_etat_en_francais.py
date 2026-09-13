"""Les quatre états d'une décision se disent en français, et d'une seule façon.

Deux défauts trouvés en se servant de la commande, pas en lisant le code.

**`--status` ne parlait qu'anglais.** `python3 -m singular list --status ouverte`
répondait « invalid choice: 'ouverte' (choose from 'open', 'happened',
'did_not_happen', 'abandoned') » : un refus en anglais, proposant quatre mots
qu'il n'a jamais lus ailleurs -- ce sont les valeurs de la base, pas son
vocabulaire. Dans le même outil, `--tier revenus` et `--reversibility
reversible` fonctionnent.

**« Journal vide » était faux.** Un journal de trois décisions toutes tranchées,
avec `--status ouverte`, affichait exactement l'écran d'un journal neuf -- le
chemin du fichier pour seule information. Or `A_FAIRE.md` lui dit justement qu'un
journal neuf et un journal absent donnent le même écran, et que c'est ce qu'il
faut savoir distinguer.

**Et le même état portait trois noms.** `list` affichait « échoué », `resolve`
« PAS ARRIVÉ », `abandon` « abandonné », tous les trois dans le même fichier. Un
mot par état, dans `Status.label`, et les trois écrans le lisent. « échoué »
n'était pas seulement un troisième mot : c'était un jugement, et une prédiction
qui ne s'est pas réalisée n'est pas un échec.
"""
from __future__ import annotations

import ast
import pathlib
from datetime import UTC, datetime

import pytest

from singular.__main__ import main
from singular.journal import DecisionJournal, Status, Tier

RACINE = pathlib.Path(__file__).resolve().parent.parent
NOW = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def _journal(tmp_path, tranchees: int = 0, ouvertes: int = 0) -> DecisionJournal:
    journal = DecisionJournal(tmp_path / "journal.db")
    for index in range(tranchees):
        entree = journal.add(title=f"Tranchee {index}", action="a", predicted="b", probability=0.6,
                             tier=Tier.REVENUS, cost_hours=2, horizon_days=7, now=NOW)
        journal.resolve(entree.entry_id, happened=False, now=NOW)
    for index in range(ouvertes):
        journal.add(title=f"Ouverte {index}", action="a", predicted="b", probability=0.6,
                    tier=Tier.CAPACITES, cost_hours=3, horizon_days=7, now=NOW)
    return journal


def _list(tmp_path, capsys, *arguments) -> tuple[int, str]:
    capsys.readouterr()
    code = main(["--db", str(tmp_path / "journal.db"), "list", *arguments])
    return code, capsys.readouterr().out


# --- ce qu'il tape ------------------------------------------------------------

@pytest.mark.parametrize("mot", ["pas arrivée", "pas arrivee", "pas-arrivee", "PAS_ARRIVEE",
                                 "did_not_happen", "DID_NOT_HAPPEN"])
def test_le_filtre_comprend_l_etat_en_francais_et_la_valeur_de_la_base(tmp_path, capsys, mot):
    """Accents, casse et séparateurs sont indifférents des deux côtés.

    Les valeurs anglaises restent acceptées parce qu'elles sont ce que la base
    contient : la normalisation ne doit pas les casser en voulant parler
    français. Elle les a cassées une fois -- les soulignés devenaient des espaces
    d'un côté de la comparaison seulement.
    """
    _journal(tmp_path, tranchees=1)

    code, sortie = _list(tmp_path, capsys, "--status", mot)

    assert code == 0, sortie
    assert Status.DID_NOT_HAPPEN.label in sortie
    assert "Tranchee 0" in sortie


def test_un_etat_inconnu_est_refuse_dans_sa_langue_avec_les_quatre_mots(tmp_path, capsys):
    _journal(tmp_path, ouvertes=1)

    code, sortie = _list(tmp_path, capsys, "--status", "peut-etre")

    assert code == 2
    for statut in Status:
        assert statut.label in sortie, "le refus doit proposer les quatre états"
    assert "invalid choice" not in sortie, "argparse refuserait en anglais"


# --- ce qu'il lit -------------------------------------------------------------

def test_aucune_decision_de_cet_etat_ne_se_dit_pas_journal_vide(tmp_path, capsys):
    """Trois décisions tranchées et zéro ouverte : le journal n'est pas vide."""
    _journal(tmp_path, tranchees=3)

    code, sortie = _list(tmp_path, capsys, "--status", "ouverte")

    assert code == 0
    assert "vide" not in sortie.lower(), f"« {sortie.strip()} » est faux : le journal porte 3 décisions"
    assert Status.OPEN.label in sortie
    assert "3 décisions" in sortie


def test_un_journal_reellement_vide_le_dit_toujours(tmp_path, capsys):
    """Le contraire doit rester vrai : sans filtre et sans décision, c'est vide."""
    _journal(tmp_path)

    code, sortie = _list(tmp_path, capsys)

    assert code == 0
    assert "vide" in sortie.lower()


# --- un mot par état ----------------------------------------------------------

def test_les_trois_ecrans_disent_le_meme_mot(tmp_path, capsys):
    """`list`, `resolve` et `abandon` nommaient le même état de trois façons."""
    journal = _journal(tmp_path)
    tranchee = journal.add(title="A trancher", action="a", predicted="b", probability=0.75,
                           tier=Tier.REVENUS, cost_hours=1, horizon_days=3, now=NOW)
    abandonnee = journal.add(title="A abandonner", action="a", predicted="b", probability=0.5,
                             tier=Tier.REVENUS, cost_hours=1, horizon_days=3, now=NOW)
    base = str(tmp_path / "journal.db")

    capsys.readouterr()
    assert main(["--db", base, "resolve", tranchee.entry_id, "--no"]) == 0
    verdict = capsys.readouterr().out
    assert main(["--db", base, "abandon", abandonnee.entry_id, "plus d'actualite"]) == 0
    arret = capsys.readouterr().out
    _, listing = _list(tmp_path, capsys)

    assert Status.DID_NOT_HAPPEN.label.upper() in verdict
    assert Status.ABANDONED.label in arret
    assert Status.DID_NOT_HAPPEN.label in listing
    assert Status.ABANDONED.label in listing


def test_aucun_ecran_ne_reecrit_un_mot_d_etat_a_la_main():
    """Le mot vit dans `Status.label`. Un littéral qui le contient peut diverger.

    Le test lit l'arbre, et cherche le mot **dans** les chaînes, pas seulement
    comme chaîne entière. La première version ne comparait que des littéraux
    entiers, et le sabotage évident lui échappait : personne n'écrit `"abandonnée"`
    tout seul, on écrit `f"  {id}  abandonnée - {lesson}"`, dont la partie
    constante est `"  abandonnée - "`. Un garde qui n'attrape pas la forme sous
    laquelle la faute se commet n'interdit rien.

    Les cinq copies trouvées ainsi : les quatre mots de `list`, le verdict de
    `resolve`, le mot d'`abandon`, la ligne du bilan hebdomadaire, et l'aide de
    `--status` -- qui les recopiait tous les quatre d'un coup.
    """
    from tests.support import sans_accents

    mots = {sans_accents(statut.label) for statut in Status}
    source = RACINE / "singular" / "__main__.py"
    arbre = ast.parse(source.read_text(encoding="utf-8"))
    # Une docstring explique, elle n'affiche pas. Celle de `_statut_tape` nomme
    # les quatre mots pour dire ce qu'elle accepte, et c'est sa raison d'etre.
    docstrings = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            premier = noeud.body[0] if noeud.body else None
            if (isinstance(premier, ast.Expr) and isinstance(premier.value, ast.Constant)
                    and isinstance(premier.value.value, str)):
                docstrings.add(id(premier.value))
    fautes = []
    for noeud in ast.walk(arbre):
        if not (isinstance(noeud, ast.Constant) and isinstance(noeud.value, str)):
            continue
        if id(noeud) in docstrings:
            continue
        nu = sans_accents(noeud.value)
        trouves = sorted(mot for mot in mots if mot in nu)
        if trouves:
            fautes.append(f"{source.name}:{noeud.lineno}: {trouves} dans « {noeud.value.strip()} »")
    assert not fautes, (
        "ces littéraux recopient un mot de `Status.label`, qui est son seul "
        f"domicile : {fautes}"
    )
