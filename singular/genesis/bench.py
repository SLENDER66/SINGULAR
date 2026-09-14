"""Le banc qui compare AZAZEL à AZAZEL, et le test de naissance.

L'hypothèse de la directive n'est pas « la deuxième mission a réussi ». C'est
« la deuxième mission a objectivement bénéficié de l'expérience de la première ».
Ce module est ce qui permet de la contredire.

**Ce qu'il mesure.** La même mission, deux fois : une fois sans rien, une fois
avec ce que l'expérience a laissé. Réussite, coût, erreurs, récupérations,
appels à un humain, capacités réemployées. Les écarts sont rendus tels quels,
et le verdict ne se lit pas sur un seul d'entre eux.

**Trois refus, et ils sont la raison d'être du fichier.**

1. Une amélioration ne se déclare pas si la version expérimentée n'a pas passé
   le vérificateur. Un coût plus bas sur une réponse fausse est un coût plus bas
   sur une réponse fausse.
2. Une amélioration ne se déclare pas si un axe a empiré. Moins d'étapes en
   appelant deux fois plus souvent un humain n'est pas une autonomie qui monte,
   et c'est exactement ce que la directive appelle optimiser la métrique contre
   la réalité.
3. **Une amélioration mesurée sur l'instance qui a servi à apprendre n'est pas
   une amélioration, c'est une mémorisation.** Le banc exige de savoir sur quoi
   la capacité a été prouvée, et refuse le mot « naissance » si la mission de
   contrôle retombe sur une de ces instances.

Si rien ne s'améliore, le verdict est `AUCUNE` et ce n'est pas un bug du banc.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .capability import Registre
from .mission import Mission, Resultat, Trajectoire, executer

#: Un solveur : il reçoit la mission, sa trajectoire à remplir, et le registre.
Solveur = Callable[[Mission, Trajectoire, Registre], Any]

#: Les trois verdicts. Nommés plutôt qu'écrits en toutes lettres à chaque
#: comparaison : une faute de frappe dans un littéral rendrait un verdict que
#: personne ne teste, et le banc dirait n'importe quoi sans échouer.
AMELIORATION = "AMELIORATION"
REFUTE = "REFUTE"
AUCUNE = "AUCUNE"

#: Les axes où empirer interdit de parler d'amélioration. La réussite et l'appel
#: à un humain d'abord : ce sont les deux que la directive place au-dessus des
#: autres, et un gain de coût ne les rachète pas.
AXES_QUI_NE_DOIVENT_PAS_EMPIRER = ("verifie", "interventions_humaines", "erreurs")


@dataclass(frozen=True)
class Ecart:
    """Un axe, ses deux valeurs, et le sens dans lequel il a bougé."""

    axe: str
    avant: float
    apres: float

    @property
    def delta(self) -> float:
        return round(self.apres - self.avant, 4)


@dataclass(frozen=True)
class Comparaison:
    """Ce que l'expérience a changé, axe par axe, et ce qu'on a le droit d'en dire."""

    mission: str
    base: Resultat
    experimente: Resultat
    ecarts: tuple[Ecart, ...]
    verdict: str
    pourquoi: str
    instance: str = ""

    @property
    def capacites_reutilisees(self) -> tuple[str, ...]:
        return self.experimente.capacites_reutilisees


def _axes(resultat: Resultat) -> dict[str, float]:
    return {
        "verifie": 1.0 if resultat.verifie else 0.0,
        "cout": resultat.cout,
        "erreurs": float(resultat.erreurs),
        "recuperations": float(resultat.recuperations),
        "interventions_humaines": float(resultat.interventions_humaines),
    }


#: Les axes qu'on veut voir monter. Tous les autres, on veut les voir descendre.
MONTE = frozenset({"verifie"})


def comparer(mission: Mission, base: Resultat, experimente: Resultat, *,
             instance: str = "") -> Comparaison:
    """Le verdict, en appliquant les trois refus dans l'ordre où ils comptent."""
    avant, apres = _axes(base), _axes(experimente)
    ecarts = tuple(Ecart(axe, avant[axe], apres[axe]) for axe in avant)

    def mieux(axe: str) -> bool:
        return apres[axe] > avant[axe] if axe in MONTE else apres[axe] < avant[axe]

    def pire(axe: str) -> bool:
        return apres[axe] < avant[axe] if axe in MONTE else apres[axe] > avant[axe]

    if not experimente.verifie:
        verdict, pourquoi = REFUTE, (
            "la version expérimentée n'a pas passé le vérificateur : "
            f"{experimente.pourquoi or 'réponse fausse'}")
    elif any(pire(axe) for axe in AXES_QUI_NE_DOIVENT_PAS_EMPIRER):
        empires = ", ".join(axe for axe in AXES_QUI_NE_DOIVENT_PAS_EMPIRER if pire(axe))
        verdict, pourquoi = REFUTE, f"un axe a empiré : {empires}"
    elif any(mieux(axe) for axe in avant):
        gagnes = ", ".join(axe for axe in avant if mieux(axe))
        verdict, pourquoi = AMELIORATION, f"mieux sur : {gagnes}"
    else:
        verdict, pourquoi = AUCUNE, "rien n'a bougé dans le bon sens"

    return Comparaison(mission.nom, base, experimente, ecarts, verdict, pourquoi, instance)


def banc(mission: Mission, solveur: Solveur, registre: Registre, *,
         instance: str = "") -> Comparaison:
    """La même mission deux fois : sans rien, puis avec ce qui a été appris.

    Le même solveur des deux côtés, et c'est délibéré. Comparer deux solveurs
    différents mesurerait l'écart entre deux programmes ; on veut l'écart que
    fait le registre, donc une seule chose change entre les deux passages.
    """
    vide = Registre()
    base = executer(mission, lambda m, t: solveur(m, t, vide))
    experimente = executer(mission, lambda m, t: solveur(m, t, registre))
    return comparer(mission, base, experimente, instance=instance)


@dataclass(frozen=True)
class TestDeNaissance:
    """Mission A, ce qu'elle a laissé, mission B, et ce que ça a changé."""

    comparaison: Comparaison
    capacites: tuple[str, ...]
    niveaux: dict[str, str]
    ne: bool
    pourquoi: str


# `constater_naissance` et non `test_de_naissance` : pytest collecte tout ce qui
# s'appelle `test_*`, y compris une fonction de bibliothèque importée dans un
# fichier de tests. Elle y arrivait sans fixtures et cassait la suite.
def constater_naissance(controle: Mission, solveur: Solveur, registre: Registre, *,
                      instance: str, apprises_sur: frozenset[str] | set[str]) -> TestDeNaissance:
    """La question de la directive, posée de façon à pouvoir répondre non.

    `apprises_sur` est l'ensemble des instances sur lesquelles le registre a
    appris. Si `instance` en fait partie, il n'y a pas de naissance à constater :
    une mission qui retombe sur ce qu'elle a déjà vu mesure une mémoire, pas une
    capacité. Le banc tourne quand même -- le chiffre reste intéressant -- mais
    le mot est refusé et la raison est écrite.
    """
    comparaison = banc(controle, solveur, registre, instance=instance)
    niveaux = {ligne["nom"]: ligne["niveau"] for ligne in registre.rapport()}

    if instance in set(apprises_sur):
        return TestDeNaissance(
            comparaison, comparaison.capacites_reutilisees, niveaux, False,
            f"« {instance} » a servi à apprendre : ce qu'on mesure est une mémorisation")
    if comparaison.verdict != AMELIORATION:
        return TestDeNaissance(
            comparaison, comparaison.capacites_reutilisees, niveaux, False,
            comparaison.pourquoi)
    if not comparaison.capacites_reutilisees:
        return TestDeNaissance(
            comparaison, comparaison.capacites_reutilisees, niveaux, False,
            "la mission s'est améliorée sans employer aucune capacité : "
            "l'expérience n'y est pour rien")
    return TestDeNaissance(
        comparaison, comparaison.capacites_reutilisees, niveaux, True,
        comparaison.pourquoi)


__all__ = ["AMELIORATION", "AUCUNE", "AXES_QUI_NE_DOIVENT_PAS_EMPIRER", "REFUTE", "Comparaison", "Ecart", "Solveur",
           "TestDeNaissance", "banc", "comparer", "constater_naissance"]
