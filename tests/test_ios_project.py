"""Le projet Xcode doit rester ouvrable et complet.

Personne ici n'a Xcode : ce projet est écrit à la main et poussé sans avoir
jamais été ouvert. La panne qu'on veut exclure n'est pas subtile — c'est
« the project is damaged and cannot be opened », qui bloque la personne qui
compile avant même la première erreur Swift, et sans rien lui apprendre.

Le vrai risque n'est pas le fichier d'aujourd'hui, qui a été vérifié : c'est
celui de demain. Ajouter un fichier Swift sans le déclarer dans le projet le
laisserait hors de la compilation, et le symptôme serait « type inconnu » dans
un fichier qui, lui, est correct. Ce test attache cette vérification à la
suite, pour qu'elle tourne sans qu'on y pense.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

CHECKER = pathlib.Path(__file__).resolve().parent.parent / "tools/check_xcode_project.py"


def test_the_xcode_project_opens_and_is_complete() -> None:
    result = subprocess.run([sys.executable, str(CHECKER)], capture_output=True, text=True)
    assert result.returncode == 0, (
        "le projet Xcode ne tient plus :\n" + result.stdout + result.stderr)


def test_the_checker_refuses_a_damaged_project(tmp_path: pathlib.Path) -> None:
    """Un vérificateur qui ne dit jamais non ne prouve rien.

    On lui donne un projet dont il ne reste que l'en-tête : il doit refuser.
    Sans ce cas, une régression qui ferait passer le vérificateur en mode
    « tout va bien quoi qu'il arrive » ne se verrait nulle part.
    """
    source = CHECKER.read_text()
    damaged = tmp_path / "SingularSage.xcodeproj"
    damaged.mkdir(parents=True)
    (damaged / "project.pbxproj").write_text("// !$*UTF8*$!\n{ objectVersion = 56")

    copy = tmp_path / "check.py"
    copy.write_text(source.replace(
        'PROJECT = pathlib.Path(__file__).resolve().parent.parent / "ios/SingularSage.xcodeproj/project.pbxproj"',
        f'PROJECT = pathlib.Path({str(damaged / "project.pbxproj")!r})'))

    result = subprocess.run([sys.executable, str(copy)], capture_output=True, text=True)
    assert result.returncode == 1, "un projet tronqué doit être refusé"
    assert "damaged" in result.stdout
