"""« La suite passe en ordre aleatoire » etait mesure a la main, jamais exige.

Le README l'affirme : « It passes in isolation and in randomised order ». C'etait
vrai parce que je passais des graines a la main dans cette session -- et faux
partout ailleurs : `pytest-randomly` n'etait pas dans les dependances `dev`, donc
le CI ne l'installait pas, donc `pytest -q` y tournait dans l'ordre du disque.
Une affirmation tenue par ma memoire n'est pas tenue.

Le defaut de cette famille trouve le 13 septembre 2026 -- un jeton de capacite
partage qu'un test revoquait pour les suivants -- ne se voit que dans un certain
ordre. Aucune etape du CI ne l'aurait vu.

Ce fichier epingle les deux moities de la reparation : la dependance qui rend le
hasard possible, et l'etape qui l'exige. Et au passage la configuration en
double que pytest annoncait ignorer a chaque demarrage.
"""
from __future__ import annotations

import importlib.metadata
import pathlib
import tomllib

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
CI = (RACINE / ".github/workflows/ci.yml").read_text(encoding="utf-8")
PYPROJECT = (RACINE / "pyproject.toml").read_text(encoding="utf-8")
DEV = tomllib.loads(PYPROJECT)["project"]["optional-dependencies"]["dev"]


def test_le_hasard_est_installe_par_les_dependances_de_developpement():
    """Sans le greffon, `pytest -q` est deterministe et l'etape aleatoire ment en vert.

    La dependance est lue dans la liste `dev`, pas cherchee dans le texte du
    fichier : ecrite comme une sous-chaine, cette assertion etait satisfaite par
    le commentaire qui explique la dependance juste au-dessus d'elle. Un temoin
    qu'une prose contente ne prouve rien -- verifie en la retirant.
    """
    assert any(exigence.startswith("pytest-randomly") for exigence in DEV), DEV
    assert importlib.metadata.version("pytest-randomly")


def test_le_ci_lance_la_suite_dans_les_deux_ordres():
    assert "run: pytest -q -p no:randomly" in CI, "l'ordre reproductible a disparu"
    assert "run: pytest -q\n" in CI, "l'ordre aleatoire a disparu"


def test_aucun_des_deux_ordres_n_est_informatif():
    """Une etape `continue-on-error` ne prouve rien : elle raconte."""
    etapes = CI.split("      - name: ")
    for etape in etapes:
        if "pytest -q" in etape:
            assert "continue-on-error" not in etape, f"etape non bloquante : {etape[:40]}"


def test_la_configuration_de_pytest_n_a_qu_une_maison(request: pytest.FixtureRequest):
    """pytest le disait a chaque demarrage : « ignoring pytest config in pyproject.toml »."""
    assert "[tool.pytest.ini_options]" not in PYPROJECT
    assert (RACINE / "pytest.ini").is_file()
    assert pathlib.Path(str(request.config.inipath)).name == "pytest.ini"
