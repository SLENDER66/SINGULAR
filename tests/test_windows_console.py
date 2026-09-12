"""Les commandes doivent survivre à une console étroite en encodage.

La contrainte vient d'un PC Windows, la machine principale jusqu'au
10 septembre 2026. Sa console n'écrit pas en UTF-8 : elle écrit dans la page de
code du système, cp850 en France. Python lève `UnicodeEncodeError` sur ce
qu'elle ne sait pas représenter, et la commande s'arrête au moment d'afficher
son résultat.

**Le Mac a remplacé le PC, et son Terminal est en UTF-8.** Cette règle n'est
donc plus obligatoire. Elle reste pour deux raisons, et une session future a le
droit de la retirer si elles cessent de valoir : elle ne coûte rien -- aucun de
ces messages n'a besoin d'une flèche -- et le chemin iPhone, dans a-Shell,
n'a jamais été mesuré. Une contrainte gratuite qui garde la sortie portable
vaut mieux qu'un caractère qu'on ne peut plus tester.

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
import re

import pytest

from singular.__main__ import _survive_narrow_consoles

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Les modules dont toute chaîne finit à l'écran.
#:
#: `tools/check_xcode_project.py` y a été ajouté après coup : sa sortie normale
#: tenait, mais son message d'erreur portait une croix et un tiret cadratin. Or
#: c'est le seul chemin qui compte — `A_FAIRE.md` demande d'envoyer ce message
#: quand Xcode refuse le projet, et il cassait au moment de l'écrire. Une panne
#: réservée au jour où l'on en a besoin ne se découvre jamais avant.
#:
#: `tools/generate_notice_vectors.py` n'y est pas, et ce n'est pas un oubli :
#: ses longues chaînes décrivent les vecteurs dans un JSON lu par les tests
#: Swift, en UTF-8. Les juger sur la page de code d'une console française
#: interdirait des accents que personne n'affiche.
SPEAKS_TO_THE_CONSOLE = [
    "singular/__main__.py",
    # Les refus de saisie y sont ecrits une fois, et le clavier les affiche.
    # Le fichier a suivi les messages : la liste doit suivre aussi.
    "singular/saisie.py",
    "proto/suivi_candidatures.py",
    "singular/sage/server.py",
    "tools/check_xcode_project.py",
    "tools/check_repo_state.py",
]

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


def test_aucune_source_n_affirme_qu_il_est_sur_windows() -> None:
    """Le code portait des justifications que le changement de machine a rendues fausses.

    « Ce serveur doit démarrer sur un PC Windows où rien n'est installé », « il
    est sur Windows », « son nom d'utilisateur Windows » : trois affirmations
    dans les modules, vraies jusqu'au 10 septembre 2026 et fausses depuis. Les
    documents avaient été traduits ce jour-là, pas le code.

    Une phrase fausse dans un commentaire ne casse rien et se lit avec autorité :
    la prochaine session la croit, et corrige le code pour lui correspondre.
    C'est la forme de bug que `PROMPT_NOUVELLE_CONVERSATION.md` demande de
    retenir plutôt que le bug lui-même.

    Parler de Windows reste permis -- `chmod`, `os.replace`, cp850 s'y
    comportent autrement, et c'est une raison légitime d'écrire portable. Ce qui
    est refusé est de dire que **c'est sa machine**.
    """
    fautes = []
    for relative in SPEAKS_TO_THE_CONSOLE + ["singular/sage/server.py", "singular/parle.py"]:
        chemin = ROOT / relative
        if not chemin.exists():
            continue
        texte = re.sub(r"\s*\n\s*#?\s*", " ", chemin.read_text(encoding="utf-8"))
        for affirmation in ("il est sur Windows", "sur un PC Windows où rien",
                            "son nom d'utilisateur Windows", "qui est son terminal",
                            "en `cmd` et en PowerShell",
                            # Troisieme passage de la meme erreur, et le premier
                            # ou elle ne nomme pas Windows : les documents le
                            # 10 septembre, les docstrings le meme jour, puis
                            # ces cinq-la, dont deux dans des phrases affichees
                            # -- « le detail est ecrit dans la fenetre du PC ou
                            # tourne le Sage », qu'il lisait sur son telephone
                            # pendant que le Sage tournait sur son Mac.
                            # Ancrees sur le present, pas sur « PC » : « le
                            # meme code tourne sur son Mac [...] et tournait
                            # sur son PC Windows » est vrai et doit passer. Un
                            # garde-fou qui crie au loup finit desactive.
                            "sur le PC,", "au PC,", "du PC ou tourne",
                            "tourne sur son PC", "sur son PC et"):
            if affirmation in texte:
                fautes.append(f"{relative} : « {affirmation} »")

    assert not fautes, (
        "ces sources affirment encore qu'il est sur Windows :\n  " + "\n  ".join(fautes)
        + "\n  Sa machine est un Mac depuis le 10 septembre 2026. Parler de "
        "Windows pour justifier du code portable reste permis ; dire que c'est "
        "sa machine, non.")
