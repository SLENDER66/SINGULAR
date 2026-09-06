"""Les commandes doivent survivre à une console Windows.

Ce projet vise explicitement un PC Windows où rien n'est installé — c'est
écrit dans l'en-tête du serveur. Or la console de Windows n'écrit pas en
UTF-8 : elle écrit dans la page de code du système, cp850 en France. Python
lève `UnicodeEncodeError` sur ce qu'elle ne sait pas représenter, et la
commande s'arrête au moment d'afficher son résultat.

La panne était réelle et bien placée : la ligne qui explique comment ajouter
le Sage à l'écran d'accueil de l'iPhone contenait une flèche. Elle est la
seule chose à lire de toute la sortie, et c'est elle qui cassait.

Deux protections, et ce fichier tient les deux :

* les messages écrits ici restent dans ce que cp850 accepte, pour être lus et
  pas remplacés par des points d'interrogation ;
* la sortie tolère l'irreprésentable, parce que le journal contient les mots
  de l'utilisateur — un emoji dans un titre ne doit pas coûter la commande.
"""
from __future__ import annotations

import ast
import io
import pathlib

import pytest

from singular.__main__ import _survive_narrow_consoles

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Les modules qui parlent à la console. Le reste du dépôt n'écrit rien.
SPEAKS_TO_THE_CONSOLE = ["singular/__main__.py", "singular/sage/server.py"]

#: La page de code d'une console française. cp1252 est plus permissive.
CONSOLE = "cp850"


def _literals(path: pathlib.Path):
    """Les chaînes du code, docstrings exclues : elles ne sont pas affichées."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docstrings:
            yield node.lineno, node.value


@pytest.mark.parametrize("relative", SPEAKS_TO_THE_CONSOLE)
def test_every_message_fits_a_windows_console(relative: str) -> None:
    path = ROOT / relative
    seen = 0
    offenders = []
    for line, text in _literals(path):
        seen += 1
        try:
            text.encode(CONSOLE)
        except UnicodeEncodeError as error:
            offenders.append(f"{relative}:{line} contient {text[error.start:error.end]!r}")
    assert seen, f"aucune chaîne lue dans {relative} — l'analyse a changé de forme"
    assert not offenders, (
        "ces messages ne peuvent pas s'afficher sur une console Windows française :\n  "
        + "\n  ".join(offenders))


def test_the_output_survives_a_character_the_console_cannot_write() -> None:
    """La protection qui couvre ce qu'aucun test de source ne peut couvrir.

    Un titre de décision vient de l'utilisateur. S'il y met un emoji, la
    commande qui l'affiche doit rendre un caractère de remplacement, pas
    échouer après avoir écrit dans le journal.
    """
    narrow = io.TextIOWrapper(io.BytesIO(), encoding=CONSOLE)
    with pytest.raises(UnicodeEncodeError):
        narrow.write("Postuler chez 🦊")
        narrow.flush()

    tolerant = io.TextIOWrapper(io.BytesIO(), encoding=CONSOLE)
    tolerant.reconfigure(errors="replace")
    tolerant.write("Postuler chez 🦊")
    tolerant.flush()  # ne doit pas lever


def test_the_guard_is_installed_and_does_not_explode(capsys) -> None:
    """Et il ne doit rien casser quand la sortie n'est pas reconfigurable."""
    _survive_narrow_consoles()
    print("accentué : décision, résolue, échéance")
    assert "décision" in capsys.readouterr().out
