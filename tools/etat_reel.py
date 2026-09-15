"""Où en est AZAZEL, dérivé du dépôt et non écrit à la main.

La directive de réalité demande un « Reality Ledger » : l'état vérifiable de
chaque capacité, et l'interdiction de la faire progresser artificiellement. Écrit
en prose dans un fichier, ce registre serait le pire objet possible de ce dépôt --
une page qui affirme des niveaux que rien ne vérifie, et qui vieillit à chaque
commit. Trois fois déjà un chiffre écrit à la main a menti ici ; `CLAUDE.md` §24
dit qu'au troisième passage on rend l'erreur impossible.

Ce registre est donc une **commande**, sur le modèle de `check_repo_state.py` :

    python3 tools/etat_reel.py

Il ne corrige rien et ne décide rien. Il lit l'arbre dans lequel il tourne, donc
il est juste sur n'importe quelle branche et après n'importe quelle fusion.

**L'échelle, et ce que chaque barreau exige comme preuve.**

* « ABSENTE » -- aucun fichier. Une capacité qui n'existe pas n'existe pas.
* « HORS SYSTÈME » -- le code existe, mais sous `attic/`, que `packages.find`
  n'installe pas. C'est la réponse honnête pour ce qui a été écrit puis mis de
  côté : ce n'est pas une capacité du système, c'est une archive.
* « CONÇUE » -- le module est dans `singular/`, mais rien ne l'importe et aucune
  commande n'y mène. Du code que personne n'atteint.
* « IMPLÉMENTÉE » -- atteignable, mais aucun test ne le nomme.
* « TESTÉE » -- atteignable et nommé par au moins un test.
* « INSTRUMENTÉE » -- en plus, l'instrument de mutation le compte parmi ses
  cibles : ses refus peuvent être sabotés un par un pour savoir lesquels un test
  attrape vraiment. Le barreau dit qu'un instrument est pointé dessus, **pas**
  que son verdict est bon -- et il a été nommé ainsi exprès. Le barreau
  au-dessus, « chaque refus a son témoin », demande dix minutes de mutation :
  cette commande ne peut pas le remplir, donc elle ne le prétend pas.

**Ce que cette commande ne dira jamais.** « PRODUCTION-READY ». Rien ici ne mesure
un usage réel, une charge, une panne subie en production. La directive exige
« UNKNOWN » plutôt que « probablement bon » : le pied de page le dit à chaque
exécution, au lieu de laisser le dernier barreau ressembler à une fin.

`MESURÉE` ne veut pas dire « sans défaut » non plus. Il veut dire qu'un
instrument a été pointé dessus et que son verdict est écrit à côté du code. La
liste des refus qui n'ont toujours pas de témoin est ce que
`tools/gardes_sans_test.py` imprime -- en dix minutes, donc pas ici.
"""
from __future__ import annotations

import ast
import pathlib
import sys
from dataclasses import dataclass, field

RACINE = pathlib.Path(__file__).resolve().parent.parent

#: Les barreaux, du moins prouvé au plus prouvé.
ECHELLE = ("ABSENTE", "HORS SYSTÈME", "CONÇUE", "IMPLÉMENTÉE", "TESTÉE",
           "INSTRUMENTÉE")


@dataclass(frozen=True)
class Capacite:
    """Une capacité, ses fichiers, et comment un humain l'atteint.

    `commandes` nomme les sous-commandes de `python3 -m singular` qui y mènent ;
    la liste est confrontée au vrai analyseur d'arguments par
    `tests/test_etat_reel.py`, pour qu'une commande renommée fasse rougir un test
    au lieu de rendre ce registre faux en silence.

    `jetons` dit si la capacité dépense de l'argent. C'est une donnée de la
    doctrine autant que de la technique : la section 11 parle de patrimoine, et
    savoir ce qui coûte est la première ligne de ce sujet.
    """

    nom: str
    modules: tuple[str, ...]
    commandes: tuple[str, ...] = ()
    jetons: bool = False
    note: str = ""
    #: Rempli par la dérivation, jamais déclaré à la main.
    preuves: list[str] = field(default_factory=list, compare=False)


CAPACITES = (
    Capacite("journal des décisions et chaîne d'intégrité", ("singular/journal.py",),
             ("add", "resolve", "abandon", "list", "due", "export", "import"),
             note="un seul module : la chaîne est ce qui rend une entrée non "
                  "réécrivable, pas une couche séparée"),
    Capacite("Notice", ("singular/sage/notice.py",), ("status", "review", "sage")),
    Capacite("serveur du Sage", ("singular/sage/server.py",), ("sage",)),
    Capacite("frontière d'exécution",
             ("singular/validated_trajectory_decision.py", "singular/validated_pipeline.py",
              "singular/validated_execution.py", "singular/execution.py",
              "singular/decision_attestation.py", "singular/execution_capability.py")),
    Capacite("socle durable", ("singular/durable.py", "singular/mission_runtime.py")),
    Capacite("effets externes",
             ("singular/effects.py", "singular/reconciled_execution.py")),
    Capacite("apprentissage",
             ("singular/improvement_registry.py", "singular/outcome_ledger.py",
              "singular/learning_review_queue.py")),
    Capacite("conversation", ("singular/parle.py",), ("parle",), jetons=True),
    Capacite("analyse en langage naturel", ("singular/analyse.py",), ("analyse",), jetons=True),
    Capacite("recherche d'offres", ("singular/offres.py",), ("offres",), jetons=True),
    Capacite("capital et patrimoine",
             ("attic/singular/patrimony_engine.py", "attic/singular/wealth_engine.py",
              "attic/singular/capital_allocation.py", "attic/singular/generational.py"),
             note="sections 10 et 11 de la doctrine"),
)


def _fichiers_presents(capacite: Capacite) -> tuple[list[str], list[str]]:
    """Ce qui existe, et ce qui manque. Les deux comptent."""
    presents = [nom for nom in capacite.modules if (RACINE / nom).exists()]
    manquants = [nom for nom in capacite.modules if nom not in presents]
    return presents, manquants


def _sous_attic(presents: list[str]) -> bool:
    return bool(presents) and all(nom.startswith("attic/") for nom in presents)


def _nom_importable(module: str) -> str:
    """`singular/sage/notice.py` -> `singular.sage.notice`."""
    return module.removesuffix(".py").replace("/", ".")


def _sources(dossier: str) -> list[pathlib.Path]:
    return sorted((RACINE / dossier).rglob("*.py"))


def _qui_importe(module: str) -> list[str]:
    """Les modules de `singular/` qui importent celui-ci, lui-meme exclu.

    Lu dans l'arbre syntaxique : un nom cité dans un commentaire ou une docstring
    n'est pas un import, et le compter rendrait ce registre trop généreux --
    exactement le biais que la directive interdit.
    """
    cible = _nom_importable(module)
    court = cible.rsplit(".", 1)[-1]
    lecteurs = []
    for chemin in _sources("singular"):
        relatif = chemin.relative_to(RACINE).as_posix()
        if relatif == module:
            continue
        try:
            arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.ImportFrom):
                # `from .notice import x` comme `from singular.sage.notice import x`.
                nom = noeud.module or ""
                if nom == cible or nom.endswith("." + court) or (noeud.level and nom == court):
                    lecteurs.append(relatif)
                    break
                if noeud.level and any(alias.name == court for alias in noeud.names):
                    lecteurs.append(relatif)
                    break
            elif isinstance(noeud, ast.Import):
                if any(alias.name == cible for alias in noeud.names):
                    lecteurs.append(relatif)
                    break
    return lecteurs


def _tests_qui_nomment(module: str) -> list[str]:
    """Les fichiers de tests qui importent ce module."""
    cible = _nom_importable(module)
    court = cible.rsplit(".", 1)[-1]
    trouves = []
    for chemin in _sources("tests"):
        texte = chemin.read_text(encoding="utf-8")
        if f"from {cible} import" in texte or f"import {cible}" in texte \
                or f"from singular import {court}" in texte:
            trouves.append(chemin.relative_to(RACINE).as_posix())
    return trouves


def cibles_de_l_instrument() -> frozenset[str]:
    """Les modules que `gardes_sans_test.py` mute, quelle que soit sa liste du jour."""
    sys.path.insert(0, str(RACINE))
    try:
        from tools import gardes_sans_test
    finally:
        sys.path.pop(0)
    mesures: set[str] = set()
    for cibles, _suite in gardes_sans_test.GROUPES.values():
        mesures.update(cibles)
    return frozenset(mesures)


def niveau(capacite: Capacite, mesures: frozenset[str]) -> tuple[str, list[str]]:
    """Le barreau atteint, et les preuves qui l'ont donné.

    Chaque barreau est une conjonction : on ne monte que si le précédent tient.
    Rien n'est déclaré, tout est lu -- c'est la seule façon qu'un registre de ce
    genre ne mente pas au bout de trois semaines.
    """
    presents, manquants = _fichiers_presents(capacite)
    preuves = []
    if manquants:
        preuves.append("absents : " + ", ".join(manquants))
    if not presents:
        return "ABSENTE", preuves
    if _sous_attic(presents):
        preuves.append("sous attic/, que packages.find n'installe pas")
        return "HORS SYSTÈME", preuves

    lecteurs = sorted({lecteur for nom in presents for lecteur in _qui_importe(nom)})
    if capacite.commandes:
        preuves.append("commandes : " + ", ".join(capacite.commandes))
    if lecteurs:
        preuves.append(f"importé par {len(lecteurs)} module(s), dont {lecteurs[0]}")
    if not capacite.commandes and not lecteurs:
        return "CONÇUE", preuves

    tests = sorted({fichier for nom in presents for fichier in _tests_qui_nomment(nom)})
    if not tests:
        return "IMPLÉMENTÉE", preuves
    preuves.append(f"nommé par {len(tests)} fichier(s) de tests, dont {tests[0]}")

    mutes = [nom for nom in presents if nom in mesures]
    if not mutes:
        return "TESTÉE", preuves
    preuves.append("muté par gardes_sans_test : " + ", ".join(mutes))
    return "INSTRUMENTÉE", preuves


def rapport() -> list[str]:
    mesures = cibles_de_l_instrument()
    lignes = ["état réel, dérivé de cet arbre — aucun niveau n'est écrit à la main", ""]
    for capacite in CAPACITES:
        atteint, preuves = niveau(capacite, mesures)
        cout = "  [dépense des jetons]" if capacite.jetons else ""
        lignes.append(f"{atteint:<13} {capacite.nom}{cout}")
        for preuve in preuves:
            lignes.append(f"              · {preuve}")
        if capacite.note:
            lignes.append(f"              · {capacite.note}")
        lignes.append("")
    lignes += [
        "PRODUCTION-READY : INCONNU pour tout ce qui précède.",
        "  Rien dans ce dépôt ne mesure un usage réel, une charge, une panne subie.",
        "  La directive exige INCONNU plutôt que « probablement bon ».",
        "",
        "INSTRUMENTÉE ne dit pas que le verdict est bon : un instrument est pointé",
        "  dessus. Le barreau au-dessus — chaque refus a son témoin — demande dix",
        "  minutes : python3 tools/gardes_sans_test.py",
    ]
    return lignes


def main(arguments: list[str] | None = None) -> int:
    if arguments:
        print(f"{pathlib.Path(__file__).name} ne prend aucun argument.", file=sys.stderr)
        return 2
    print("\n".join(rapport()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
