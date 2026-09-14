"""L'instrument qui dit « ce refus n'a aucun temoin » n'en avait aucun lui-meme.

`tools/gardes_sans_test.py` decide quels refus de la frontiere sont prouves.
Tout ce qu'il annonce est cru, donc ses fautes ne se voient pas : il s'est
trompe deux fois le meme jour, dans le sens rassurant les deux fois.

* Sa sous-suite nommait un fichier de tests renomme entre-temps : pytest
  refusait de collecter, et **chaque refus paraissait prouve**.
* Il sabotait le depot lui-meme, donc un garde neutralise se retrouvait dans
  `git status` au moment de committer -- rattrape par un hook de sortie -- et un
  processus tue avant son `finally` laissait ce garde en place.

Troisieme fois qu'une faute de l'instrument me coute un tour : on arrete de
corriger, on ecrit ce qui echoue a la place du prochain lecteur.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

from tools.gardes_sans_test import (
    CIBLES_FRONTIERE,
    CIBLES_MATINS,
    GROUPES,
    RendLaConditionFausse,
    RendLeRefusVrai,
    RendUneMoitieFausse,
    _la_sous_suite_passe,
    moities_d_un_fichier,
    moities_rendues_d_un_fichier,
    refus_booleens_d_un_fichier,
    refus_d_un_fichier,
    _un_groupe,
    copie_a_mesurer,
    fichiers_a_copier,
)

RACINE = pathlib.Path(__file__).resolve().parent.parent


def _dans_un_depot_git() -> bool:
    acheve = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True,
                            text=True, cwd=RACINE, check=False)
    return acheve.returncode == 0


#: Trois tests d'ici mesurent le depot lui-meme, donc ils appellent `git`. Ils
#: doivent sauter la ou il n'y en a pas -- **dans la copie jetable que l'outil
#: fabrique**, qui n'est pas un depot. Sans ce saut, ces trois tests echouaient
#: dans la copie, donc la suite entiere y echouait, donc l'outil ne pouvait plus
#: confirmer aucun survivant : une passe de soixante-douze mutants annoncee sans
#: rien signaler. La faute la plus couteuse de la journee, et elle etait dans
#: l'instrument, encore.
hors_depot = pytest.mark.skipif(not _dans_un_depot_git(),
                                reason="mesure le depot lui-meme ; ici il n'y en a pas")


# --- la copie -----------------------------------------------------------------

@hors_depot
def test_saboter_dans_la_copie_ne_touche_pas_le_depot():
    """Le defaut qu'un hook de sortie a rattrape : un garde sabote pret a etre commite."""
    cible = "singular/execution.py"
    avant = (RACINE / cible).read_bytes()
    with copie_a_mesurer() as copie:
        assert (copie / cible).read_bytes() == avant
        (copie / cible).write_text("raise SystemExit('sabote')\n", encoding="utf-8")
        assert (copie / cible).read_bytes() != avant
        assert (RACINE / cible).read_bytes() == avant
    assert (RACINE / cible).read_bytes() == avant


@hors_depot
def test_la_copie_est_ce_que_python_importe():
    """Mesure, pas deduction : le paquet est installe en editable.

    Un finder de `site-packages` pointe vers l'arbre d'origine, et il est
    consulte avant `sys.path`. Si c'etait lui qui gagnait, l'outil muterait la
    copie, importerait l'original, et declarerait tous les refus prouves. C'est
    `python -m pytest` qui tranche : son repertoire courant passe devant.
    """
    with copie_a_mesurer() as copie:
        acheve = subprocess.run(
            [sys.executable, "-c", "import singular.journal as m; print(m.__file__)"],
            capture_output=True, text=True, cwd=copie, check=True,
        )
        assert acheve.stdout.strip().startswith(str(copie))


@hors_depot
def test_la_copie_porte_ce_qui_n_est_pas_encore_commite():
    """Un audit lance avant de committer doit mesurer les temoins qu'on vient d'ecrire."""
    temoin = RACINE / ".gardes_temoin_non_suivi"
    temoin.write_text("non suivi\n", encoding="utf-8")
    try:
        assert temoin.name in fichiers_a_copier()
        with copie_a_mesurer() as copie:
            assert (copie / temoin.name).read_text(encoding="utf-8") == "non suivi\n"
    finally:
        temoin.unlink()


# --- ce que l'outil nomme -----------------------------------------------------

def test_chaque_fichier_nomme_par_l_outil_existe():
    """La faute qui rendait tout vert : un fichier de tests renomme."""
    for cible in CIBLES_FRONTIERE + CIBLES_MATINS:
        assert (RACINE / cible).is_file(), f"cible disparue : {cible}"
    for nom, (_, sous_suite) in GROUPES.items():
        for fichier in sous_suite:
            assert (RACINE / fichier).is_file(), f"{nom} : sous-suite disparue : {fichier}"


def test_une_sous_suite_qui_ne_collecte_pas_est_un_echec():
    """Le controle d'entree de l'outil repose sur ca, et c'est ce qui avait manque."""
    assert _la_sous_suite_passe(("tests/test_ce_fichier_n_existe_pas.py",)) is False


# --- les quatre formes de sabotage ---------------------------------------------

SOURCE = """
def refuse(a, b):
    if a or b:
        raise PermissionError("non")
    if a and b:
        raise PermissionError("non non")
    return False

def accepte() -> bool:
    if False:
        return False
    return False

def verdict(a, b, c) -> bool:
    return a or b or c
"""


def _mute(transformateur):
    arbre = transformateur.visit(ast.parse(SOURCE))
    assert transformateur.touche, "le transformateur n'a rien touche"
    ast.fix_missing_locations(arbre)
    return ast.unparse(arbre)


def test_la_condition_entiere_devient_fausse():
    assert "if False:\n        raise PermissionError('non')" in _mute(RendLaConditionFausse(3))


def test_un_refus_qui_rend_faux_devient_un_accord():
    """La forme que la premiere version ignorait : un predicat qui cesse de refuser."""
    mute = _mute(RendLeRefusVrai(12))
    assert "return True" in mute
    assert mute.count("return False") == 2  # celui de `refuse` et le dernier, intacts


def test_une_moitie_prend_l_element_neutre_de_son_operateur():
    """`False` dans un `or`, `True` dans un `and` : l'autre moitie continue de garder."""
    assert "if False or b:" in _mute(RendUneMoitieFausse((3, 0)))
    assert "if a or False:" in _mute(RendUneMoitieFausse((3, 1)))
    assert "if True and b:" in _mute(RendUneMoitieFausse((5, 0)))
    assert "if a and True:" in _mute(RendUneMoitieFausse((5, 1)))


def test_une_moitie_rendue_prend_aussi_l_element_neutre():
    """La quatrieme forme : un predicat qui **rend** un booleen compose.

    Les trois premieres ne voient que ce qui refuse -- un `raise`, un `return
    False`. Celle-ci voit ce qui decide, et c'est la seule qui trouve quoi que ce
    soit dans `global_control.py`, ou `requires_human` reunit cinq raisons d'exiger
    un humain par des `or`.
    """
    assert "return False or b or c" in _mute(RendUneMoitieFausse((15, 0)))
    assert "return a or False or c" in _mute(RendUneMoitieFausse((15, 1)))
    assert "return a or b or False" in _mute(RendUneMoitieFausse((15, 2)))


def test_la_quatrieme_forme_ne_ramasse_que_les_predicats_declares():
    """Le meme critere que la forme 2 : `-> bool` declare un predicat.

    Sans lui, tout `return a or b` du depot deviendrait un mutant -- y compris ceux
    qui rendent autre chose qu'un booleen, ou muter ne dirait plus la meme chose.
    """
    trouves = moities_rendues_d_un_fichier(ast.parse(SOURCE))
    assert [clef for clef, _ in trouves] == [(15, 0), (15, 1), (15, 2)]
    assert all("verdict" in quoi for _, quoi in trouves)

    sans_annotation = ast.parse("def v(a, b):\n    return a or b\n")
    assert moities_rendues_d_un_fichier(sans_annotation) == []


def test_la_porte_globale_est_desormais_visible():
    """Le defaut qui a motive la quatrieme forme, verifie sur le vrai fichier.

    `global_control.py` ne leve aucun refus : les trois premieres formes n'y
    trouvaient rien, donc l'instrument disait « rien a signaler » sur le module qui
    decide si une action peut etre preparee et si un humain est requis.
    """
    source = (RACINE / "singular" / "global_control.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    assert refus_d_un_fichier(arbre) == []
    assert refus_booleens_d_un_fichier(arbre) == []
    assert moities_d_un_fichier(arbre) == []

    rendus = moities_rendues_d_un_fichier(arbre)
    predicats = {quoi.rsplit("(", 1)[1].rstrip(")") for _, quoi in rendus}
    assert predicats == {"can_prepare", "requires_human"}


def test_une_suite_entiere_deja_rouge_arrete_l_outil(monkeypatch: pytest.MonkeyPatch):
    """Le controle d'entree qui manquait, et qui a coute une passe entiere.

    Si la suite entiere echoue sans mutant, chaque survivant du sous-ensemble est
    annonce comme un faux positif : l'outil ne mesure plus rien et dit que tout
    va bien. Il doit refuser de mesurer, et le dire.
    """
    import tools.gardes_sans_test as outil

    monkeypatch.setattr(outil, "_JUGES_VERIFIES", set())
    monkeypatch.setattr(outil, "_la_sous_suite_passe", lambda *args, **kwargs: True)
    monkeypatch.setattr(outil, "_la_suite_entiere_passe", lambda *args, **kwargs: False)

    assert _un_groupe("frontiere") == -1
