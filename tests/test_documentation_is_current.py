"""La documentation qui affirme des faits doit être vérifiée comme du code.

Ce fichier existe parce que la même panne s'est produite quatre fois en une
journée : `CLAUDE.md` annonçait une branche abandonnée et une PR fermée, le
README public annonçait 572 tests alors qu'il y en avait 708, `USAGE.md`
ignorait une commande entière, et le prompt de reprise comptait faux les commits
qu'il venait lui-même de décrire.

Aucune de ces erreurs n'a fait échouer quoi que ce soit. C'est précisément le
problème : une documentation fausse ne casse rien, elle envoie simplement la
personne suivante au mauvais endroit, et on ne l'apprend qu'en perdant une
séance. Corriger le chiffre une cinquième fois ne changerait rien ; le rendre
vérifiable, si.

Ce qui est testé ici est ce qui peut l'être sans devenir absurde : l'existence
de ce qui est cité, la correspondance entre ce que le CLI offre et ce que le
mode d'emploi décrit, et la cohérence entre la version publiée et le changelog.
Le ton, l'exactitude d'une explication ou la pertinence d'un exemple ne sont pas
testables — ils restent à la charge du lecteur.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from singular.__main__ import build_parser

ROOT = Path(__file__).resolve().parent.parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


# --- ce que le README dit contenir ------------------------------------------

def test_every_path_in_the_readme_layout_exists():
    """Un chemin cité qui n'existe plus est le premier signe d'un README figé."""
    layout = re.search(r"## Layout\n+```\n(.*?)```", _read("README.md"), re.DOTALL)
    assert layout, "le bloc « Layout » a disparu du README"

    cited = [line.split()[0] for line in layout.group(1).splitlines() if line.strip()]
    assert len(cited) >= 8, "le bloc « Layout » ne cite presque plus rien"

    missing = [path for path in cited if not (ROOT / path).exists()]
    assert not missing, f"le README cite des chemins qui n'existent pas : {missing}"


# --- ce que le mode d'emploi décrit -----------------------------------------

def _documented_commands(text: str) -> set[str]:
    """Une commande est documentée si son nom apparaît comme du code.

    Deux formes comptent : la ligne complète `python -m singular <cmd>`, et le
    premier mot d'un fragment entre accents graves — `abandon DEC-xxx "raison"`
    documente bien `abandon`, et exiger le nom seul rejetait toute commande
    montrée avec ses arguments.
    """
    invoked = set(re.findall(r"python -m singular (\w+)", text))
    inline = {span.split()[0] for span in re.findall(r"`([^`\n]+)`", text) if span.split()}
    return invoked | inline


def test_every_cli_command_is_documented():
    """Ajouter une commande sans l'écrire quelque part, c'est ne pas l'ajouter."""
    parser = build_parser()
    actions = [action for action in parser._actions if hasattr(action, "choices") and action.choices]
    commands = {name for action in actions for name in action.choices}
    assert commands, "aucune sous-commande trouvée : le parseur a changé de forme"

    documented = _documented_commands(_read("USAGE.md"))
    undocumented = sorted(commands - documented)
    assert not undocumented, f"commandes absentes de USAGE.md : {undocumented}"


def test_usage_does_not_promise_commands_that_do_not_exist():
    """L'autre sens : un mode d'emploi qui décrit une commande retirée."""
    parser = build_parser()
    commands = {
        name
        for action in parser._actions
        if hasattr(action, "choices") and action.choices
        for name in action.choices
    }
    promised = set(re.findall(r"python -m singular (\w+)", _read("USAGE.md")))
    phantom = sorted(promised - commands)
    assert not phantom, f"USAGE.md décrit des commandes inexistantes : {phantom}"


# --- la version publiée ------------------------------------------------------

def test_the_published_version_has_a_changelog_entry():
    version = tomllib.loads(_read("pyproject.toml"))["project"]["version"]
    headings = re.findall(r"^## ([0-9]+\.[0-9]+\.[0-9]+)", _read("CHANGELOG.md"), re.MULTILINE)
    assert headings, "le changelog n'a plus d'entrée versionnée"
    assert headings[0] == version, (
        f"pyproject publie {version} et le changelog ouvre sur {headings[0]} : "
        "l'un des deux n'a pas été mis à jour"
    )


# --- ce qui a déjà menti une fois -------------------------------------------

DEAD_REFERENCES = {
    "feat/validated-execution-boundary": "branche abandonnée",
    "Dépôt GitHub privé": "le dépôt est public",
    "PR #4": "fermée et intégrée",
}


@pytest.mark.parametrize("reference,why", sorted(DEAD_REFERENCES.items()))
def test_documents_that_guide_a_session_do_not_cite_dead_things(reference: str, why: str):
    """Les trois affirmations qui ont réellement coûté du temps, épinglées.

    `CLAUDE.md` est chargé d'office au début de chaque session : une information
    périmée y a l'autorité des instructions du projet et envoie travailler sur
    une branche morte avant toute vérification. Le prompt de reprise a le même
    rôle. Les autres documents peuvent citer ces noms comme de l'histoire ;
    ces deux-là, non.
    """
    for name in ("CLAUDE.md", "PROMPT_NOUVELLE_CONVERSATION.md"):
        text = _read(name)
        if reference in text:
            surrounding = [line for line in text.splitlines() if reference in line]
            assert all("mort" in line or "fermée" in line or "n'y retourne pas" in line
                       for line in surrounding), (
                f"{name} cite « {reference} » ({why}) sans dire que c'est périmé : {surrounding}"
            )
