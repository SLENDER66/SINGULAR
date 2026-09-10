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


# --- la branche que les documents envoient chercher ---------------------------

def test_the_clone_command_names_the_branch_the_mandate_declares():
    """Un clonage qui nomme une branche périmée rend l'ancienne version, en silence.

    `A_FAIRE.md` donne la commande à taper dans a-Shell pour installer SINGULAR
    sur le téléphone, sans PC. Elle nomme une branche. Le mandat en nomme une
    aussi, et c'est celle-là qui porte le travail — c'est ce que le hook de
    démarrage vérifie à chaque séance.

    Les deux se sont séparées : la commande de clonage est restée sur la
    branche d'une séance précédente pendant que le travail avançait ailleurs.
    Ça ne casse rien, et c'est le problème. On obtient une app qui démarre,
    qui a l'air normale, et à laquelle manquent les corrections qu'on croit
    avoir. On ne s'en aperçoit qu'en cherchant pourquoi le bouton promis n'est
    pas là — un jour où l'on n'a que son téléphone, donc le jour où c'est le
    plus cher.

    Ce test ne vérifie pas que la branche est à jour : ça demande le serveur, et
    c'est le travail de `tools/check_repo_state.py`, que le hook lance au
    démarrage. Il vérifie que les deux documents ne peuvent pas se contredire,
    ce qui se lit sans réseau et tient dès qu'un seul des deux est corrigé.
    """
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from check_repo_state import declared_work_branch
    finally:
        sys.path.pop(0)

    declaree = declared_work_branch(_read("CLAUDE.md"))
    assert declaree, "CLAUDE.md ne nomme plus de branche de travail"

    a_faire = _read("A_FAIRE.md")

    # Deux documents portent la commande de clonage, et un seul était vérifié.
    # `USAGE.md` faisait cloner une troisième branche tout en promettant, la
    # phrase juste au-dessus, que c'était celle du mandat.
    clones = {nom: re.findall(r"lg2 clone -b (\S+)", _read(nom))
              for nom in ("A_FAIRE.md", "USAGE.md")}
    assert clones["A_FAIRE.md"], "la commande de clonage a disparu d'A_FAIRE.md ou changé de forme"

    for nom, branches in clones.items():
        for branche in branches:
            assert branche == declaree, (
                f"{nom} fait cloner « {branche} » alors que le mandat déclare "
                f"« {declaree} » comme branche de travail.\n"
                "Le téléphone installerait une version qui n'a pas le travail en cours."
            )

    # Le PC a la même faille, par un autre chemin : `git pull` met à jour la
    # branche où l'on est, pas celle qui porte le travail. Un clone resté sur
    # la branche d'une séance précédente ne bouge donc pas, sans rien dire.
    sortie = re.search(r"git checkout (\S+)", a_faire)
    assert sortie, "la commande qui place le PC sur la bonne branche a disparu d'A_FAIRE.md"
    assert sortie.group(1) == declaree, (
        f"A_FAIRE.md fait basculer le PC sur « {sortie.group(1)} » alors que le "
        f"mandat déclare « {declaree} ».\n"
        "Le PC resterait sur l'ancienne version, et `git pull` ne le dirait pas."
    )


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


# --- les commandes du PC sont celles de sa console ---------------------------

#: Ce que la console de Thomas rejette, et ce qu'il faut écrire à la place.
#:
#: Il est sur Windows, en PowerShell — c'est écrit dans `CLAUDE.md`, et
#: `A_FAIRE.md` est déjà rédigé ainsi. `USAGE.md` ne l'était pas : son mode
#: d'emploi ouvrait sur `cd ~/SINGULAR && ...`, que la version de PowerShell
#: installée par défaut sur Windows refuse avant d'exécuter quoi que ce soit, et
#: sa section « le mettre devant tes yeux » — celle dont tout le propos est qu'un
#: journal qu'on doit penser à ouvrir finit par ne plus s'ouvrir — donnait un
#: `alias` à mettre dans `~/.bashrc`.
REJETE_PAR_POWERSHELL = {
    "&&": "deux lignes séparées",
    "||": "deux lignes séparées",
    "export ": "$env:NOM = \"...\"",
    "2>/dev/null": "2>$null",
    "alias ": "function nom { ... @args }",
    "source ": ". le-fichier",
    "~/.bashrc": "$PROFILE",
    "~/.zshrc": "$PROFILE",
}

#: Le seul shell POSIX de sa vie : a-Shell, sur l'iPhone. Les blocs qui lui
#: sont destinés portent cette étiquette, et eux seuls.
ETIQUETTE_IPHONE = "sh"


def _blocs(nom: str) -> list[tuple[str, str, int]]:
    texte = _read(nom)
    return [(m.group(1), m.group(2), texte[:m.start()].count("\n") + 1)
            for m in re.finditer(r"```(\w*)\n(.*?)```", texte, re.DOTALL)]


@pytest.mark.parametrize("nom", ["USAGE.md", "A_FAIRE.md", "README.md"])
def test_les_commandes_du_pc_tiennent_dans_sa_console(nom: str) -> None:
    fautes = []
    for etiquette, bloc, ligne in _blocs(nom):
        if etiquette == ETIQUETTE_IPHONE:
            continue
        for rejete, remplacement in REJETE_PAR_POWERSHELL.items():
            if rejete in bloc:
                fautes.append(f"{nom}:{ligne} contient {rejete!r} — écris {remplacement}")
    assert not fautes, (
        "ces commandes ne tournent pas dans sa console :\n  " + "\n  ".join(fautes)
        + f"\nUn bloc destiné à a-Shell sur l'iPhone porte l'étiquette ```{ETIQUETTE_IPHONE}."
    )


def test_le_scan_verrait_une_commande_d_une_autre_machine() -> None:
    """Le témoin : sans lui, un lecteur qui ne trouve aucun bloc passerait au vert."""
    assert len(_blocs("USAGE.md")) > 5
    assert any(etiquette == ETIQUETTE_IPHONE for etiquette, _, _ in _blocs("USAGE.md")), (
        "plus aucun bloc iPhone : l'exemption ne protège plus rien, "
        "et le test ne prouve plus qu'il sait distinguer les deux machines")


# --- aucun document ne pointe une branche que le mandat ne declare pas --------

#: Un nom de branche du dépôt, tel qu'il s'écrit.
NOM_DE_BRANCHE = re.compile(r"\bclaude/[a-z0-9][a-z0-9-]*\b")

#: Les documents où une branche peut apparaître, y compris hors du dépôt Python.
DOCUMENTS = ["A_FAIRE.md", "USAGE.md", "README.md", "CLAUDE.md",
             "PROMPT_NOUVELLE_CONVERSATION.md", "proto/README.md"]


def _branche_declaree() -> tuple[str, set[str]]:
    """La branche de travail, et toutes celles que le mandat nomme.

    Le mandat est la seule source hors ligne : interroger `origin` ferait
    dependre la suite de tests du reseau, et un test qui ne peut pas s'executer
    ne garde rien.
    """
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from check_repo_state import declared_work_branch
    finally:
        sys.path.pop(0)
    contenu = _read("CLAUDE.md")
    return declared_work_branch(contenu), set(NOM_DE_BRANCHE.findall(contenu))


@pytest.mark.parametrize("nom", DOCUMENTS)
def test_une_commande_ne_nomme_que_les_branches_du_mandat(nom: str) -> None:
    """Une branche citée dans une commande est une branche qu'il va utiliser.

    `proto/README.md` faisait télécharger le suivi de candidatures depuis
    `claude/remote-control-feedback-ndpzle` — une branche dont la suppression
    est justement demandée, et dont l'URL brute rendra 404 le jour où il la
    supprime. La prose peut parler d'une branche morte, et A_FAIRE.md le fait
    exprès ; une commande, non : elle sera exécutée.
    """
    travail, nommees = _branche_declaree()
    texte = _read(nom)
    fautes = []
    for bloc in re.finditer(r"```\w*\n(.*?)```", texte, re.DOTALL):
        ligne = texte[:bloc.start()].count("\n") + 1
        for branche in NOM_DE_BRANCHE.findall(bloc.group(1)):
            if branche not in nommees:
                fautes.append(f"{nom}:{ligne} exécute une commande sur « {branche} »")
    assert not fautes, (
        "\n  ".join(fautes)
        + f"\nLe mandat ne nomme que {sorted(nommees)}, dont « {travail} » en travail.")


@pytest.mark.parametrize("nom", DOCUMENTS)
def test_aucun_document_ne_declare_une_autre_branche_de_travail(nom: str) -> None:
    """Le pire cas : un mandat qui envoie la prochaine session au mauvais endroit.

    `PROMPT_NOUVELLE_CONVERSATION.md` est le bloc qu'il colle dans une nouvelle
    conversation. Il déclarait une branche de travail que `CLAUDE.md` ne déclare
    pas — c'est-à-dire exactement la panne qu'`A_FAIRE.md` raconte avoir déjà
    coûté une séance entière.
    """
    travail, _nommees = _branche_declaree()
    for declaration in re.finditer(r"[Bb]ranche de travail[^\n]*?`([^`]+)`", _read(nom)):
        assert declaration.group(1) == travail, (
            f"{nom} déclare « {declaration.group(1)} » comme branche de travail, "
            f"le mandat déclare « {travail} ».")


def test_le_scan_lit_bien_des_branches() -> None:
    """Le témoin : sans branche trouvée nulle part, les deux tests ci-dessus sont creux."""
    travail, nommees = _branche_declaree()
    assert travail and len(nommees) >= 2, "le mandat doit nommer la branche de travail et la branche par defaut"
    trouvees = {branche for nom in DOCUMENTS for branche in NOM_DE_BRANCHE.findall(_read(nom))}
    assert travail in trouvees


# --- tout clone nomme sa branche, dans tout le depot --------------------------

#: Une commande de clonage, quel que soit l'outil : `git` sur le Mac et le PC,
#: `lg2` dans a-Shell sur l'iPhone.
CLONE = re.compile(r"\b(?:git|lg2)\s+clone\b([^\n`]*)")


def _est_une_commande(suite: str) -> bool:
    """Une commande a executer, et non une phrase qui parle du clonage.

    Les deux documents expliquent la regle en toutes lettres -- « un `lg2 clone`
    sans elle prend la branche par defaut ». Un test qui compte ces phrases
    comme des fautes crie au loup, et un test qui crie au loup finit desactive.
    Une commande porte l'adresse du depot, ou son `-b`.
    """
    return "github.com" in suite or "-b " in suite

#: Tous les documents, et pas une liste tenue a la main.
#:
#: La liste etait la faute. `A_FAIRE.md` et `USAGE.md` etaient gardes ; les deux
#: commandes du chemin Mac -- `ios/README.md` et l'etape 2 d'`A_FAIRE.md` --
#: clonaient sans `-b` et personne ne les regardait. Un depot se parcourt.
def _tous_les_documents() -> list[pathlib.Path]:
    return [chemin for chemin in sorted(ROOT.rglob("*.md"))
            if ".git" not in chemin.parts and "node_modules" not in chemin.parts]


def test_tout_clone_nomme_la_branche_de_travail() -> None:
    """Cloner sans `-b` prend la branche par defaut, qui n'est pas la bonne.

    Elle est deja restee trente-neuf commits en arriere, et une seance entiere
    est partie d'un depot sans le Sage et sans `ios/`. Le chemin Mac, celui qui
    compile l'application native, clonait ainsi -- et compiler une version d'il
    y a un mois ferait chercher des pannes deja corrigees.

    `CHANGELOG.md` est exclu : il raconte l'histoire, dont d'anciennes branches,
    et corriger le passe serait le reecrire.
    """
    travail, _ = _branche_declaree()
    fautes = []
    for chemin in _tous_les_documents():
        relatif = chemin.relative_to(ROOT).as_posix()
        if relatif == "CHANGELOG.md":
            continue
        texte = chemin.read_text(encoding="utf-8")
        for trouve in CLONE.finditer(texte):
            ligne = texte[:trouve.start()].count("\n") + 1
            if not _est_une_commande(trouve.group(1)):
                continue
            if f"-b {travail}" not in trouve.group(1):
                fautes.append(f"{relatif}:{ligne} clone sans nommer « {travail} »")

    assert not fautes, (
        "\n  ".join(fautes)
        + f"\n  Ecris `clone -b {travail} ...` : sans `-b`, c'est la branche par "
        "defaut qui arrive, et elle n'est pas toujours celle qui porte le travail."
    )


def test_le_scan_voit_bien_les_clones() -> None:
    """Le temoin : sans clone trouve nulle part, le test ci-dessus est creux."""
    trouves = [chemin.relative_to(ROOT).as_posix() for chemin in _tous_les_documents()
               if CLONE.search(chemin.read_text(encoding="utf-8"))]
    assert len(trouves) >= 3, f"trop peu de clones lus : {trouves}"
    assert "ios/README.md" in trouves, "le chemin Mac doit etre couvert"
