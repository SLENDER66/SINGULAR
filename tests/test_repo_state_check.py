"""Le verdict sur l'état du dépôt distant doit être jugeable sans serveur.

`tools/check_repo_state.py` est né d'une panne vécue : la branche par défaut
du dépôt était restée trente-neuf commits en arrière, si bien qu'une session
démarrait sans `singular/sage/`, sans `ios/`, et sur un `CLAUDE.md` d'avant la
section 0. Pendant ce temps `A_FAIRE.md` affirmait que c'était réglé.

L'outil interroge un serveur ; ces tests non. Toute la décision — ce qui compte
comme un désaccord, ce qui mérite une sortie non nulle — vit dans `describe()`,
qui ne touche ni au réseau ni au disque. C'est cette fonction qui est mise en
défaut ici, y compris dans le cas qui compte le plus : celui où l'on ne sait
pas. Un outil de vérification qui répond « tout va bien » quand il n'a rien pu
vérifier est pire que pas d'outil du tout, parce qu'on le croit.
"""
from __future__ import annotations

import pathlib

import pytest

from tools.check_repo_state import declared_work_branch, describe

ROOT = pathlib.Path(__file__).resolve().parent.parent

WORK = "claude/travail"
DEFAULT = "claude/defaut"


def _describe(**overrides):
    """Le cas nominal, que chaque test déforme sur un seul point."""
    argument = {
        "work_branch": WORK,
        "default_branch": WORK,
        "branches": {WORK: "a" * 40},
        "ahead": None,
        "fast_forward": None,
    }
    argument.update(overrides)
    lines, status = describe(**argument)
    return "\n".join(lines), status


# --- le cas où tout va bien --------------------------------------------------

def test_the_default_branch_being_the_working_one_is_the_only_silence():
    text, status = _describe()
    assert status == 0
    assert "Accord" in text


# --- le cas qui a coûté une séance ------------------------------------------

def test_a_default_branch_left_behind_is_reported_and_fails():
    text, status = _describe(
        default_branch=DEFAULT,
        branches={WORK: "a" * 40, DEFAULT: "b" * 40},
        ahead=39,
        fast_forward=True,
    )
    assert status == 1, "un désaccord qui sort 0 ne serait jamais remarqué"
    assert "DESACCORD" in text
    assert "39 commits" in text
    assert WORK in text, "il faut nommer la branche sur laquelle basculer"
    assert "Aucun commit ne serait perdu" in text


def test_the_count_is_never_invented_when_it_could_not_be_computed():
    """Sans les objets en local, on ne sait pas de combien : il faut le dire."""
    text, status = _describe(
        default_branch=DEFAULT,
        branches={WORK: "a" * 40, DEFAULT: "b" * 40},
        ahead=None,
        fast_forward=None,
    )
    assert status == 1
    assert "inconnu" in text
    assert "Aucun commit ne serait perdu" not in text, (
        "rassurer sur une bascule qu'on n'a pas pu vérifier est le pire des deux"
    )


def test_a_default_branch_carrying_its_own_commits_warns_instead_of_reassuring():
    text, status = _describe(
        default_branch=DEFAULT,
        branches={WORK: "a" * 40, DEFAULT: "b" * 40},
        ahead=39,
        fast_forward=False,
    )
    assert status == 1
    assert "Attention" in text and "perdrait la trace" in text
    assert "Aucun commit ne serait perdu" not in text


# --- les états où le mandat lui-même est en cause ---------------------------

def test_a_working_branch_absent_from_the_remote_fails_loudly():
    """Le mandat enverrait la session suivante sur une branche inexistante."""
    text, status = _describe(
        default_branch=DEFAULT,
        branches={DEFAULT: "b" * 40},
    )
    assert status == 1
    assert "ABSENTE" in text


def test_a_mandate_that_names_no_branch_is_not_treated_as_agreement():
    text, status = _describe(work_branch=None)
    assert status == 1
    assert "rien à comparer" in text


@pytest.mark.parametrize("case", [
    {"work_branch": None},
    {"default_branch": DEFAULT, "branches": {DEFAULT: "b" * 40}},
    {"default_branch": DEFAULT, "branches": {WORK: "a" * 40, DEFAULT: "b" * 40}},
])
def test_nothing_but_a_verified_agreement_ever_returns_zero(case: dict):
    """La contre-vérification : chercher un état douteux qui passerait pour bon."""
    _, status = _describe(**case)
    assert status == 1


# --- ce que l'outil lit dans le mandat --------------------------------------

def test_the_working_branch_is_read_from_the_real_mandate():
    """Si `CLAUDE.md` change de forme, l'outil doit cesser de comprendre."""
    branch = declared_work_branch((ROOT / "CLAUDE.md").read_text(encoding="utf-8"))
    assert branch, "CLAUDE.md ne nomme plus sa branche de travail de façon lisible"
    assert "/" in branch and " " not in branch


def test_a_mandate_without_the_heading_yields_nothing_rather_than_a_guess():
    assert declared_work_branch("un mandat qui ne parle plus de branches") is None


def test_the_other_branches_are_listed_without_being_judged():
    """Les nommer suffit : supprimer une branche est une décision du propriétaire."""
    text, _ = _describe(
        branches={WORK: "a" * 40, "feat/morte": "c" * 40, "main": "d" * 40},
    )
    assert "feat/morte" in text
    assert "main" not in text.split("autres branches")[-1], (
        "main n'est pas un encombrement à trancher"
    )
