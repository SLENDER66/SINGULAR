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

from tools.gardes_sans_test import (
    CIBLES_FRONTIERE,
    CIBLES_MATINS,
    GROUPES,
    RendLaConditionFausse,
    RendLeRefusVrai,
    RendUneMoitieFausse,
    _la_sous_suite_passe,
    copie_a_mesurer,
    fichiers_a_copier,
)

RACINE = pathlib.Path(__file__).resolve().parent.parent


# --- la copie -----------------------------------------------------------------

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


# --- les trois formes de sabotage ---------------------------------------------

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
