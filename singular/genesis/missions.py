"""ALPHA, BETA, GAMMA : exécuter, échouer, devenir capable.

Les trois missions de la directive, sur les fichiers réels de ce dépôt.

**ALPHA — comprendre.** Deux sources, deux formats, une synthèse, un
vérificateur qui recalcule. Elle démontre l'exécution structurée : le solveur ne
sait pas d'avance quel lecteur va marcher, il essaie, et sa trajectoire garde
chaque essai raté.

**BETA — échouer.** La même forme, mais une source est tronquée et une autre
absente. Le solveur doit s'en apercevoir, le diagnostiquer, se rabattre sur ce
qui reste, et vérifier quand même. Ce qui est mesuré n'est pas qu'il réussisse :
c'est qu'un échec apparaisse dans sa trajectoire, suivi d'une récupération.

**GAMMA — devenir capable.** Un format que rien ici ne sait lire. Le solveur
détecte le manque, cherche dans le registre, ne trouve pas, construit un
lecteur, l'essaie sur un échantillon mis de côté, et ne l'inscrit que s'il tient.
Puis une mission de contrôle, sur une **autre** instance du même format, mesure
ce que cette capacité a changé.

Le solveur est déterministe. Il n'appelle aucun modèle, ne touche pas au réseau,
n'écrit nulle part. C'est un choix, pas une limite temporaire : une expérience
qui ne peut tourner qu'avec une clé d'API et cinq dollars de crédit est une
expérience qui ne tournera pas, et le CI ne pourrait jamais la rejouer.
L'intelligence est un paramètre du solveur, pas une dépendance du banc.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .capability import Preuve, Registre
from .lecteurs import TOUS, FormatRefuse
from .mission import Etape, Mission, Trajectoire

#: Le nom sous lequel un lecteur appris s'inscrit. Un seul endroit, parce que
#: le solveur le cherche et GAMMA l'inscrit : deux orthographes et la capacité
#: serait inscrite sans jamais être retrouvée.
LECTEUR_APPRIS = "lecteur:cle_valeur"


# --- ce que GAMMA doit apprendre à lire ---------------------------------------

def construire_lecteur(separateur: str) -> Callable[[str], dict[str, list[str]]]:
    """Fabrique un lecteur `cle<sep>valeur` pour le séparateur observé.

    C'est la capacité, et elle est construite, pas choisie dans une liste. Le
    séparateur est capturé par la fermeture, donc deux lecteurs construits sur
    deux séparateurs différents sont deux artefacts différents --
    `artifact_fingerprint` regarde les captures de fermeture, et c'est ce qui
    empêche d'inscrire l'un en croyant avoir prouvé l'autre.
    """
    def lire(texte: str) -> dict[str, list[str]]:
        trouve: dict[str, list[str]] = {}
        for ligne in texte.splitlines():
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or separateur not in ligne:
                continue
            cle, _, valeur = ligne.partition(separateur)
            trouve.setdefault(cle.strip(), []).append(valeur.strip())
        if not trouve:
            raise FormatRefuse(f"aucune ligne « cle{separateur}valeur »")
        return trouve
    return lire


def construire_lecteur_memorisant(texte_appris: str,
                                  reponse: dict[str, list[str]]
                                  ) -> Callable[[str], dict[str, list[str]]]:
    """Une capacité qui a retenu la réponse au lieu d'apprendre à la trouver.

    Elle existe pour être réfutée. La directive dit que la victoire n'est pas
    « la deuxième mission a réussi » mais « elle a bénéficié de l'expérience de
    la première » ; sans un cas qui réussit la première et rate la seconde, le
    banc ne prouverait que sa propre complaisance.
    """
    def lire(texte: str) -> dict[str, list[str]]:
        if texte != texte_appris:
            raise FormatRefuse("je n'ai vu que l'autre texte")
        return dict(reponse)
    return lire


# --- le solveur ---------------------------------------------------------------

def _lire_avec_capacite(texte: str, trajectoire: Trajectoire,
                        registre: Registre) -> dict[str, list[str]] | None:
    """Le chemin court : une capacité inscrite, employée en un pas."""
    if LECTEUR_APPRIS not in registre:
        return None
    capacite = registre.employer(LECTEUR_APPRIS)
    trajectoire.note(Etape.CAPACITE, LECTEUR_APPRIS, detail=capacite.niveau)
    try:
        return capacite.procedure(texte)
    except FormatRefuse as refus:
        trajectoire.note(Etape.ECHEC, LECTEUR_APPRIS, detail=str(refus))
        return None


def _lire_en_tatonnant(texte: str, trajectoire: Trajectoire) -> dict[str, list[str]] | None:
    """Le chemin long : essayer les lecteurs connus jusqu'à ce qu'un tienne."""
    for nom, lecteur in TOUS:
        try:
            lu = lecteur(texte)
        except FormatRefuse as refus:
            trajectoire.note(Etape.ECHEC, nom, detail=str(refus))
            continue
        trajectoire.note(Etape.LECTURE, nom)
        return lu
    return None


def lire_source(texte: str, trajectoire: Trajectoire,
                registre: Registre) -> dict[str, list[str]] | None:
    """Lire un texte, par le chemin le plus court dont on dispose."""
    lu = _lire_avec_capacite(texte, trajectoire, registre)
    if lu is not None:
        return lu
    avant = trajectoire.combien(Etape.ECHEC)
    lu = _lire_en_tatonnant(texte, trajectoire)
    if lu is not None and trajectoire.combien(Etape.ECHEC) > avant:
        trajectoire.note(Etape.RECUPERATION, "un autre lecteur a tenu", cout=0.0)
    return lu


def resoudre(mission: Mission, trajectoire: Trajectoire, registre: Registre) -> Any:
    """Extrait ce que la mission demande, en notant tout ce qui se passe.

    `parametres["demande"]` est une suite de `(source, champ)`. Une source
    absente ou illisible ne fait pas tomber la mission : elle est notée et on
    continue, parce que ce que BETA mesure est exactement la suite qu'on donne à
    un manque.
    """
    demande = mission.parametres.get("demande", ())
    reponse: dict[str, list[str]] = {}
    for source, champ in demande:
        texte = mission.sources.get(source)
        if texte is None:
            trajectoire.note(Etape.ECHEC, source, detail="source absente")
            trajectoire.note(Etape.RECUPERATION, f"on se passe de {source}", cout=0.0)
            continue
        lu = lire_source(texte, trajectoire, registre)
        if lu is None:
            trajectoire.note(Etape.ECHEC, source, detail="aucun lecteur ne tient")
            continue
        if champ not in lu:
            trajectoire.note(Etape.ECHEC, f"{source}.{champ}", detail="champ absent")
            continue
        reponse[f"{source}.{champ}"] = lu[champ]
    return reponse


# --- GAMMA : détecter le manque, construire, éprouver, inscrire ----------------

SEPARATEURS_ESSAYES = (": ", "=", "\t")


def acquerir_lecteur(echantillon: str, controle: tuple[str, str], trajectoire: Trajectoire,
                     registre: Registre, *, provenance: str) -> bool:
    """Le cycle de la directive, en entier et dans l'ordre, sans rien sauter.

    DÉTECTER LE MANQUE → CHERCHER DANS LE REGISTRE → RÉUTILISER SI POSSIBLE →
    SINON CONSTRUIRE → BAC À SABLE → TESTER → VÉRIFIER → INSCRIRE.

    `controle` est une paire `(clé, valeur)` mise de côté : c'est le test du bac
    à sable. Un lecteur construit qui ne la retrouve pas n'est **pas** inscrit,
    et c'est le seul moyen d'éviter qu'une capacité entre au registre sur la
    foi de celui qui l'a écrite.
    """
    if registre.chercher(LECTEUR_APPRIS) is not None:
        trajectoire.note(Etape.CAPACITE, LECTEUR_APPRIS, cout=0.0, detail="déjà inscrite")
        return True

    trajectoire.note(Etape.ECHEC, "lecture", detail="aucun lecteur connu pour ce format")
    cle, attendue = controle
    for separateur in SEPARATEURS_ESSAYES:
        candidat = construire_lecteur(separateur)
        trajectoire.note(Etape.CONSTRUCTION, f"lecteur({separateur!r})")
        try:
            lu = candidat(echantillon)
        except FormatRefuse:
            trajectoire.note(Etape.ECHEC, f"bac à sable {separateur!r}", detail="rien lu")
            continue
        if lu.get(cle) != [attendue]:
            trajectoire.note(Etape.ECHEC, f"bac à sable {separateur!r}",
                             detail="le contrôle ne ressort pas")
            continue
        registre.inscrire(LECTEUR_APPRIS, "lire un format clé/valeur", candidat,
                          provenance=provenance)
        trajectoire.note(Etape.RECUPERATION, "capacité construite et inscrite", cout=0.0)
        return True
    return False


# --- les sources réelles ------------------------------------------------------

def sources_du_depot(racine: str | Path) -> dict[str, str]:
    """Les vrais fichiers, lus une fois, avant que la mission ne commence.

    Une mission qui irait au disque pendant son exécution ne serait pas
    rejouable, et le banc a besoin de rejouer exactement la même chose deux fois.
    """
    racine = Path(racine)
    return {
        "changelog": (racine / "CHANGELOG.md").read_text(encoding="utf-8"),
        "pyproject": (racine / "pyproject.toml").read_text(encoding="utf-8"),
        "ci": (racine / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
    }


def _version_publiee(sources: dict[str, str]) -> str | None:
    accord = re.search(r'^version\s*=\s*"([^"]+)"', sources.get("pyproject", ""),
                       flags=re.MULTILINE)
    return accord.group(1) if accord else None


def _versions_du_changelog(sources: dict[str, str]) -> list[str]:
    return re.findall(r"^## (\d+\.\d+\.\d+)", sources.get("changelog", ""),
                      flags=re.MULTILINE)


def alpha(sources: dict[str, str]) -> Mission:
    """Deux sources, deux formats, et une réponse que le juge recalcule seul."""
    def verifier(reponse: Any, sources: dict[str, str]) -> bool:
        if not isinstance(reponse, dict):
            return False
        return (reponse.get("changelog.version") == _versions_du_changelog(sources)
                and reponse.get("pyproject.version") == [_version_publiee(sources)])

    return Mission(
        nom="ALPHA",
        objectif="Quelles versions le changelog déclare-t-il, et laquelle pyproject publie-t-il ?",
        sources=sources,
        verifier=verifier,
        attendu="les versions du changelog, et celle de pyproject",
        parametres={"demande": (("changelog", "version"), ("pyproject", "version"))},
    )


def beta(sources: dict[str, str]) -> Mission:
    """La même question, avec une source tronquée et une absente.

    Le vérificateur ne demande pas l'impossible : la version publiée est
    introuvable, donc la réponse juste est celle qui **n'invente pas** ce
    qu'elle n'a pas pu lire. Un solveur qui comblerait le trou par une
    déduction échouerait ici, et c'est voulu.
    """
    abimees = dict(sources)
    abimees["pyproject"] = sources["pyproject"][: len(sources["pyproject"]) // 3].replace('"', "")
    abimees.pop("notice", None)

    def verifier(reponse: Any, sources: dict[str, str]) -> bool:
        if not isinstance(reponse, dict):
            return False
        return (reponse.get("changelog.version") == _versions_du_changelog(sources)
                and "pyproject.version" not in reponse
                and "notice.version" not in reponse)

    return Mission(
        nom="BETA",
        objectif="La même question, avec une source tronquée et une source absente.",
        sources=abimees,
        verifier=verifier,
        attendu="les versions du changelog, et rien d'inventé pour le reste",
        parametres={"demande": (("changelog", "version"), ("pyproject", "version"),
                                ("notice", "version"))},
    )


#: Le format que personne ici ne sait lire. Deux instances distinctes, parce que
#: mesurer une amélioration sur l'instance qui a servi à apprendre mesurerait
#: une mémoire.
GAMMA_APPRENTISSAGE = """# relevé du matin
machine: mac
journal: présent
verdicts: 42
"""

GAMMA_CONTROLE = """# relevé du soir
machine: téléphone
journal: absent
verdicts: 7
"""

#: La même chose, abîmée pour de vrai : des lignes qui ne sont pas des paires,
#: un commentaire, du blanc. Une capacité qui tient là-dessus a montré autre
#: chose qu'une capacité qui tient sur un texte propre, et c'est précisément ce
#: que le barreau E4 sépare.
GAMMA_ABIMEE = """
    ### relevé arraché

machine: mac
ceci n'est pas une paire
   
journal
verdicts: 3
"""


def gamma(texte: str, *, nom: str = "GAMMA", attendu: str = "mac") -> Mission:
    """Une mission qui demande un format qu'aucun lecteur inscrit ne tient."""
    def verifier(reponse: Any, _sources: dict[str, str]) -> bool:
        return isinstance(reponse, dict) and reponse.get("releve.machine") == [attendu]

    return Mission(
        nom=nom,
        objectif="Quelle machine ce relevé déclare-t-il ?",
        sources={"releve": texte},
        verifier=verifier,
        attendu="la valeur de « machine »",
        parametres={"demande": (("releve", "machine"),)},
    )


def delta(sources: dict[str, str]) -> Mission:
    """Le deuxième domaine, et c'est un vrai fichier du dépôt.

    Le lecteur a été appris sur un relevé écrit à la main. On lui demande ici de
    répondre sur `.github/workflows/ci.yml`, qui n'a rien à voir : c'est la
    configuration qui fait tourner le CI. Sans cette mission, « généralisation »
    resterait un mot, et E5 une case qu'on coche.

    Ce qu'elle ne prétend pas : le lecteur ne comprend pas YAML. Il lit les
    paires `clé: valeur` qu'il trouve, à plat -- l'imbrication est perdue et une
    entrée de liste garde son tiret. C'est assez pour dire comment ce workflow
    s'appelle ; ce n'est pas un analyseur YAML, et l'écrire ici évite qu'un
    lecteur pressé le croie.
    """
    def verifier(reponse: Any, _sources: dict[str, str]) -> bool:
        return isinstance(reponse, dict) and reponse.get("ci.name") == ["CI"]

    return Mission(
        nom="DELTA",
        objectif="Comment s'appelle le workflow qui fait tourner le CI ?",
        sources={"ci": sources["ci"]},
        verifier=verifier,
        attendu="le nom déclaré par le workflow",
        parametres={"demande": (("ci", "name"),)},
    )


def epsilon(sources: dict[str, str]) -> Mission:
    """Le format où la capacité ne tient pas, et il faut que ça se voie.

    `pyproject.toml` écrit `cle = "valeur"` : aucune ligne `clé: valeur`, donc le
    lecteur appris refuse. C'est un échec réel, sur un fichier réel, et il est
    joué exprès -- un registre qui n'enregistrerait que les emplois réussis
    produirait un niveau de preuve qui monte tout seul.
    """
    def verifier(reponse: Any, _sources: dict[str, str]) -> bool:
        return isinstance(reponse, dict) and reponse.get("pyproject.version") is not None

    return Mission(
        nom="EPSILON",
        objectif="Quelle version pyproject publie-t-il — lue par le lecteur appris ?",
        sources={"pyproject": sources["pyproject"]},
        verifier=verifier,
        attendu="une version, que ce lecteur-là ne sait pas atteindre",
        parametres={"demande": (("pyproject", "version"),)},
    )


def apprendre_de_gamma(registre: Registre, trajectoire: Trajectoire) -> bool:
    """Ce que GAMMA laisse derrière elle, une fois éprouvé."""
    return acquerir_lecteur(GAMMA_APPRENTISSAGE, ("journal", "présent"), trajectoire,
                            registre, provenance="GAMMA")


def prouver_emploi(registre: Registre, *, instance: str, domaine: str,
                   abimee: bool, reussi: bool) -> None:
    """Enregistre ce qu'un emploi a donné. Les échecs comptent aussi."""
    registre.prouver(LECTEUR_APPRIS,
                     Preuve(instance=instance, domaine=domaine, abimee=abimee, reussi=reussi))


__all__ = ["GAMMA_ABIMEE", "GAMMA_APPRENTISSAGE", "GAMMA_CONTROLE", "LECTEUR_APPRIS",
           "SEPARATEURS_ESSAYES", "acquerir_lecteur", "alpha", "apprendre_de_gamma", "beta",
           "construire_lecteur", "construire_lecteur_memorisant", "delta", "epsilon",
           "gamma", "lire_source", "prouver_emploi", "resoudre", "sources_du_depot"]
