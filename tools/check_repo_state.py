"""Compare l'état réel du dépôt distant à ce que le mandat déclare.

Ce script existe parce que la panne s'est produite pour de bon, et sur la
séance qui l'a écrit. Le conteneur d'une session part de la branche par défaut
du dépôt. Celle-ci était restée trente-neuf commits en arrière : la séance a
donc démarré sans `singular/sage/`, sans `ios/`, et sur un `CLAUDE.md`
d'avant la section 0 — la section écrite précisément pour ne plus jamais
avoir à être réécrite. Sans comparaison des branches, elle serait partie
travailler sur la branche morte que l'ancien mandat nommait encore.

`A_FAIRE.md` affirmait pendant ce temps que « la bonne branche est la branche
par défaut ». L'affirmation était fausse, et aucun test ne pouvait le dire :
elle porte sur l'état d'un serveur, pas sur le contenu du dépôt.

D'où ce script plutôt qu'une phrase de plus dans un fichier. Il ne corrige
rien — basculer une branche par défaut est une décision du propriétaire, pas
d'une session. Il rend l'écart visible en une commande, et refuse de dire que
tout va bien lorsqu'il n'a pas pu vérifier.

    python tools/check_repo_state.py

Sortie 0 : le dépôt distant correspond au mandat.
Sortie 1 : il en diffère, ou n'a pas pu être joint.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Les branches qu'on ne compte pas comme un encombrement à trancher.
KEPT_BY_DESIGN = frozenset({"main"})


# --- ce que le mandat déclare ------------------------------------------------

def declared_work_branch(mandate: str) -> str | None:
    """La branche de travail nommée par `CLAUDE.md`, si elle y est encore."""
    found = re.search(r"Branche de travail\s*:\s*\n+\s*(\S+)", mandate)
    return found.group(1) if found else None


# --- ce que le serveur répond ------------------------------------------------

def _git(*args: str) -> str:
    """Appelle git et rend sa sortie, ou lève si l'appel n'aboutit pas."""
    done = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or f"git {' '.join(args)} a échoué")
    return done.stdout


def remote_state() -> dict[str, object]:
    """Interroge origin : branche par défaut, SHA, et toutes les branches."""
    head = _git("ls-remote", "--symref", "origin", "HEAD")
    symref = re.search(r"ref: refs/heads/(\S+)\s+HEAD", head)
    if not symref:
        raise RuntimeError("origin n'annonce pas de branche par défaut")

    branches = {}
    for line in _git("ls-remote", "--heads", "origin").splitlines():
        sha, _, ref = line.partition("\t")
        if ref.startswith("refs/heads/"):
            branches[ref.removeprefix("refs/heads/")] = sha.strip()

    return {"default": symref.group(1), "branches": branches}


def _ahead_count(behind: str, ahead: str) -> int | None:
    """Combien de commits séparent les deux, si les objets sont ici."""
    try:
        return int(_git("rev-list", "--count", f"{behind}..{ahead}").strip())
    except (RuntimeError, ValueError):
        return None


def _is_ancestor(older: str, newer: str) -> bool | None:
    """Vrai si passer de l'un à l'autre ne perdrait aucun commit."""
    try:
        done = subprocess.run(
            ["git", "merge-base", "--is-ancestor", older, newer],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
    except OSError:
        return None
    if done.returncode in (0, 1):
        return done.returncode == 0
    return None


# --- ce qu'on en dit ---------------------------------------------------------

def describe(
    *,
    work_branch: str | None,
    default_branch: str,
    branches: dict[str, str],
    ahead: int | None,
    fast_forward: bool | None,
    mandate_trustworthy: bool | None = True,
) -> tuple[list[str], int]:
    """Rend les lignes à afficher et le code de sortie. Aucun accès réseau.

    Séparé de tout le reste pour être testable : c'est ici que se décide ce
    qui compte comme un désaccord, et cette décision doit pouvoir être mise
    en défaut sans dépendre d'un serveur.

    `mandate_trustworthy` vaut faux lorsque le `CLAUDE.md` lu ne vient pas de
    la branche de travail. Ce cas n'est pas théorique : c'est précisément
    l'état que l'outil sert à diagnostiquer. Un clone resté sur une branche
    par défaut en retard porte l'ancien mandat, qui nomme l'ancienne branche
    de travail -- et l'outil conseillerait alors de basculer la branche par
    défaut sur une branche morte. Le mandat suspect passe donc avant tout le
    reste, et suffit à lui seul pour ne pas conclure.
    """
    lines: list[str] = []

    if mandate_trustworthy is not True:
        lines.append(
            "MANDAT SUSPECT : ce clone n'a pas la branche de travail dans son "
            "historique."
        )
        lines.append(
            "Le CLAUDE.md lu ici peut donc etre perime, et la branche qu'il nomme "
            "avec lui."
        )
        lines.append(
            "Faire `git fetch origin` et se placer sur la branche de travail "
            "avant de suivre ce qui suit."
        )
        lines.append("")

    if work_branch is None:
        lines.append("CLAUDE.md ne nomme plus de branche de travail : rien à comparer.")
        return lines, 1

    default_sha = branches.get(default_branch, "?")[:7]
    work_sha = branches.get(work_branch, "?")[:7]
    lines.append(f"branche par defaut : {default_branch}  {default_sha}")
    lines.append(f"branche de travail : {work_branch}  {work_sha}")
    lines.append("")

    if mandate_trustworthy is not True:
        # On s'arrete aux faits. Le conseil de bascule est calcule a partir du
        # mandat, donc il vaut ce que vaut le mandat : sur un clone reste en
        # arriere, il nommerait la branche morte que l'ancien mandat citait
        # encore, avec un ecart chiffre qui a toutes les apparences du serieux.
        # Un avertissement au-dessus ne suffit pas -- il se lit de travers, et
        # le clic, lui, est definitif.
        lines.append("Verdict non rendu tant que le mandat lu n'est pas celui du travail.")
        return lines, 1

    status = 0

    if work_branch not in branches:
        lines.append(
            f"ABSENTE : origin n'a pas {work_branch}. Le mandat envoie la session "
            "suivante sur une branche qui n'existe pas."
        )
        status = 1
    elif branches[work_branch] == branches.get(default_branch):
        # Le nom ne decide pas : deux branches distinctes posees sur le meme
        # commit servent le meme code, et une session qui part de l'une lit ce
        # que l'autre dit. C'est exactement l'etat ou mene le rattrapage, et
        # comparer les noms l'aurait declare en desaccord avec lui-meme.
        same = "" if work_branch == default_branch else " -- meme commit, sous deux noms"
        lines.append(f"Accord : la branche par defaut porte le travail{same}.")
    else:
        ecart = f"de {ahead} commits" if ahead is not None else "d'un nombre inconnu de commits"
        lines.append(f"DESACCORD : la branche par defaut est en retard {ecart}.")
        lines.append(
            "Toute nouvelle session part donc de la branche par defaut, et lit un "
            "CLAUDE.md qui n'est pas celui-ci."
        )
        if fast_forward:
            lines.append("Aucun commit ne serait perdu : la branche par defaut est un ancetre.")
        elif fast_forward is False:
            lines.append(
                "Attention : la branche par defaut porte des commits absents du travail. "
                "Basculer sans les lire en perdrait la trace."
            )
        lines.append(
            "A faire : avancer la branche par defaut jusqu'au travail, ou bien "
            f"sur GitHub, Settings > General > Default branch, basculer sur "
            f"{work_branch}."
        )
        status = 1

    others = sorted(set(branches) - {work_branch, default_branch} - KEPT_BY_DESIGN)
    if others:
        lines.append("")
        lines.append(f"{len(others)} autres branches sur origin, a garder ou a supprimer :")
        lines.extend(f"  {name}" for name in others)

    return lines, status


def main() -> int:
    mandate = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    work_branch = declared_work_branch(mandate)

    try:
        state = remote_state()
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        # Fail-closed : ne pas pouvoir verifier n'est pas la meme chose que
        # verifier que tout va bien, et c'est la confusion que le mandat
        # interdit explicitement.
        print(f"origin n'a pas pu etre interroge : {error}")
        print("Etat du depot distant : inconnu. Ne pas conclure qu'il est a jour.")
        return 1

    branches: dict[str, str] = state["branches"]  # type: ignore[assignment]
    default_branch: str = state["default"]  # type: ignore[assignment]

    ahead = fast_forward = None
    if work_branch and work_branch in branches and work_branch != default_branch:
        ahead = _ahead_count(branches[default_branch], branches[work_branch])
        fast_forward = _is_ancestor(branches[default_branch], branches[work_branch])

    # Le CLAUDE.md lu vient-il d'un clone qui connait la branche de travail ?
    # Indeterminable vaut suspect : c'est le sens de fail-closed ici.
    trustworthy: bool | None = None
    if work_branch and work_branch in branches:
        trustworthy = _is_ancestor(branches[work_branch], "HEAD")

    lines, status = describe(
        work_branch=work_branch,
        default_branch=default_branch,
        branches=branches,
        ahead=ahead,
        fast_forward=fast_forward,
        mandate_trustworthy=trustworthy,
    )
    for line in lines:
        print(line)
    return status


if __name__ == "__main__":
    sys.exit(main())
