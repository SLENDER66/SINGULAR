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

    **`limites` et `prochaine` sont déclarées, pas dérivées, et c'est voulu.** La
    directive cumulative exige LIMITATIONS et NEXT STEP pour chaque capacité. Ni
    l'un ni l'autre ne se lit dans un arbre syntaxique : ce sont des jugements. Ils
    sont donc écrits à la main -- et `tests/test_etat_reel.py` refuse une capacité
    qui n'en porte pas, ou qui les remplit d'un mot vide comme « aucune ». Une
    limite déclarée ne peut pas flatter : elle dit ce qui manque. C'est l'inverse
    d'un niveau déclaré, qui flatterait toujours, et c'est pourquoi le barreau reste
    dérivé.

    La même raison écarte les statuts PARTIAL et SIMULATED de la directive comme
    *niveaux* : « partiellement implémentée » est un jugement, et un jugement qui
    fixe le barreau serait exactement la promotion sans preuve que la section 4
    interdit. Ce qui est partiel se dit dans `limites`, où c'est vérifiable en
    lisant, et le barreau reste ce que l'arbre démontre.
    """

    nom: str
    modules: tuple[str, ...]
    limites: str
    prochaine: str
    commandes: tuple[str, ...] = ()
    jetons: bool = False
    note: str = ""
    #: Rempli par la dérivation, jamais déclaré à la main.
    preuves: list[str] = field(default_factory=list, compare=False)


CAPACITES = (
    Capacite("journal des décisions et chaîne d'intégrité", ("singular/journal.py",),
             limites="une seule base, un seul utilisateur, aucune synchronisation "
                     "entre deux machines : la reprise `import` réunit deux journaux "
                     "à la main, elle ne les tient pas à jour",
             prochaine="rien. C'est la partie qui sert tous les matins et qui n'a "
                       "pas de manque connu ; y toucher serait du travail pour du "
                       "travail",
             commandes=("add", "resolve", "abandon", "list", "due", "export", "import"),
             note="un seul module : la chaîne est ce qui rend une entrée non "
                  "réécrivable, pas une couche séparée"),
    Capacite("Notice", ("singular/sage/notice.py",),
             limites="déterministe et sans jeton, donc elle ne dit que ce que ses "
                     "règles savent formuler ; elle ne lit pas le monde, seulement "
                     "le journal",
             prochaine="rien de nommé. Les règles se corrigent quand une phrase se "
                       "révèle fausse, pas par anticipation",
             commandes=("status", "review", "sage")),
    Capacite("serveur du Sage", ("singular/sage/server.py",),
             limites="local, un utilisateur, pas de chiffrement en transit, pas "
                     "d'authentification autre que la clé d'accès du fichier",
             prochaine="rien tant qu'il tourne sur sa machine et son téléphone. "
                       "L'exposer hors du réseau local demanderait d'abord une "
                       "authentification réelle",
             commandes=("sage",)),
    Capacite("frontière d'exécution",
             ("singular/validated_trajectory_decision.py", "singular/validated_pipeline.py",
              "singular/validated_execution.py", "singular/execution.py",
              "singular/decision_attestation.py", "singular/execution_capability.py"),
             limites="l'approbation humaine n'est pas un canal d'autorisation : une "
                     "action escaladée est refusée à la porte, pas mise en attente. "
                     "La chaîne est parcourue de bout en bout contre un vrai serveur "
                     "local, jamais contre un tiers réel : aucune contrepartie n'a "
                     "jamais reçu quoi que ce soit",
             prochaine="une contrepartie qui n'est pas 127.0.0.1. Le fournisseur "
                       "existe et il est réel ; ce qui manque est quelqu'un en face, "
                       "et ça demande une autorisation, pas du code"),
    Capacite("socle durable", ("singular/durable.py", "singular/mission_runtime.py"),
             limites="SQLite sur une machine : pas de réplication, pas de "
                     "sauvegarde automatique, et une base perdue est perdue",
             prochaine="une sauvegarde que la machine fait seule. C'est la seule "
                       "dette de ce module qui puisse coûter des mois de journal"),
    Capacite("effets externes",
             ("singular/effects.py", "singular/reconciled_execution.py"),
             limites="`HttpEffectProvider` est réel et sort vraiment du processus, "
                     "mais contre un serveur de test local ; le cas ambigu -- ni "
                     "fait ni pas fait -- est donc joué, pas subi",
             prochaine="la même que la frontière : une contrepartie réelle. Le code "
                       "du fournisseur n'a rien qui manque de connu"),
    Capacite("apprentissage",
             ("singular/improvement_registry.py", "singular/outcome_ledger.py",
              "singular/learning_review_queue.py"),
             limites="rien ne s'active seul, et c'est un invariant de sécurité, pas "
                     "un manque. Mais aucune amélioration n'a jamais été promue en "
                     "usage réel : la boucle est gardée, pas parcourue",
             prochaine="la parcourir une fois de bout en bout sur une vraie "
                       "prédiction du journal, verdict compris"),
    Capacite("conversation", ("singular/parle.py",),
             limites="dépense des jetons, plafond de soixante réponses par jour "
                     "depuis le téléphone et aucun plafond au clavier -- seulement "
                     "un compteur",
             prochaine="un plafond dur au clavier, si le compteur ne suffit plus",
             commandes=("parle",), jetons=True),
    Capacite("analyse en langage naturel", ("singular/analyse.py",),
             limites="dépense des jetons, aucun plafond, et commente un rapport "
                     "déjà calculé : elle ne décide rien",
             prochaine="aucun plafond, comme la recherche d'offres : le compteur "
                       "suffit tant qu'une analyse par jour reste la règle, et c'est "
                       "à revoir dès que l'usage change",
             commandes=("analyse",), jetons=True),
    Capacite("recherche d'offres", ("singular/offres.py",),
             limites="la plus chère par appel -- recherche web, quatre mille jetons "
                     "-- et aucun plafond",
             prochaine="un plafond, ou la couper si elle ne rend rien d'utile",
             commandes=("offres",), jetons=True),
    Capacite("capital et patrimoine",
             ("attic/singular/patrimony_engine.py", "attic/singular/wealth_engine.py",
              "attic/singular/capital_allocation.py", "attic/singular/generational.py"),
             limites="aucune source de données, aucun chemin d'exécution, aucune "
                     "décision qui lise leur sortie : des fonctions de score sur des "
                     "dataclasses écrites à la main",
             prochaine="une seule source de données réelle -- un relevé, un revenu, "
                       "une dépense -- avant toute autre ligne de code ici. Tant "
                       "qu'elle n'existe pas, ces modules restent une archive",
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


#: Ce qui fait qu'un test ne se contente pas de doubles : il ouvre un vrai port.
#: `EffectProvider` de test rend un `ProviderResult` sans rien quitter ; un serveur
#: lie sur 127.0.0.1 oblige la requete a traverser la pile reseau, a pouvoir
#: expirer, et a laisser l'effet dans l'etat ambigu pour lequel tout le protocole
#: de recuperation existe.
SORTIE_DU_PROCESSUS = ("ThreadingHTTPServer", "HTTPServer(", "socketserver")


def _tests_qui_sortent_du_processus(module: str) -> list[str]:
    """Les tests qui nomment ce module **et** ouvrent un vrai serveur.

    Derive, pas declare -- et c'est exactement ce qui a corrige une limite que
    j'avais ecrite a la main : je notais qu'aucun effet reel n'avait traverse la
    frontiere, alors qu'un test la parcourt de bout en bout contre un socket.
    """
    trouves = []
    for chemin in _tests_qui_nomment(module):
        texte = (RACINE / chemin).read_text(encoding="utf-8")
        if any(motif in texte for motif in SORTIE_DU_PROCESSUS):
            trouves.append(chemin)
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

    sorties = sorted({fichier for nom in presents
                      for fichier in _tests_qui_sortent_du_processus(nom)})
    if sorties:
        preuves.append("parcouru contre un vrai serveur par " + ", ".join(sorties))

    mutes = [nom for nom in presents if nom in mesures]
    if not mutes:
        return "TESTÉE", preuves
    preuves.append("muté par gardes_sans_test : " + ", ".join(mutes))
    return "INSTRUMENTÉE", preuves


def _enveloppe(etiquette: str, texte: str, largeur: int = 76) -> list[str]:
    """Une phrase repliee sous son etiquette, pour que le rapport reste lisible."""
    import textwrap

    marge = " " * 14
    lignes = textwrap.wrap(texte, largeur - len(marge) - len(etiquette) - 4)
    if not lignes:
        return []
    premiere = f"{marge}{etiquette} : {lignes[0]}"
    suite = [f"{marge}{' ' * (len(etiquette) + 3)}{ligne}" for ligne in lignes[1:]]
    return [premiere, *suite]


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
        lignes += _enveloppe("limites", capacite.limites)
        lignes += _enveloppe("prochaine", capacite.prochaine)
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
