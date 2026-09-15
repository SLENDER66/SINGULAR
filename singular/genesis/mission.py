"""Une mission, sa trajectoire, et le juge qui dit si elle a réussi.

Le pari de la directive Genesis est qu'une expérience vérifiée peut devenir une
capacité réutilisable, et qu'une capacité réutilisable peut rendre une mission
suivante objectivement meilleure. Ce module tient le plus petit des trois
morceaux : de quoi exécuter une mission et savoir, sans croire personne, si elle
a réussi.

**Trois règles de forme, et elles ne sont pas décoratives.**

Le juge est séparé du solveur. Un solveur qui déclare « j'ai réussi » ne prouve
rien ; `Mission.verifier` recalcule la réponse par un autre chemin, à partir de
la source, et compare. C'est la seule raison pour laquelle un chiffre
d'amélioration voudra dire quelque chose plus loin.

La trajectoire est écrite pendant, pas après. Un compte rendu rédigé à la fin
est un compte rendu qui arrange : chaque pas est enregistré au moment où il
arrive, y compris ceux qui échouent, et le coût s'additionne tout seul.

Rien ici ne touche au monde. Une mission lit ; elle n'écrit pas, n'exécute pas,
n'appelle personne. `tests/test_genesis_isolation.py` le refuse plutôt que de le
promettre -- la frontière d'exécution du dépôt a son propre chemin, et Genesis
ne doit jamais en devenir une porte dérobée.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Etape(str, Enum):
    """Ce qu'un pas de trajectoire est, pour qu'on puisse les compter séparément."""

    LECTURE = "LECTURE"
    #: Un pas qui a échoué et que le solveur a vu échouer.
    ECHEC = "ECHEC"
    #: Ce qu'il a fait de cet échec. Sans ce genre-là, « il a récupéré » ne se
    #: mesure pas : on ne verrait qu'un échec suivi d'une réussite.
    RECUPERATION = "RECUPERATION"
    #: Une capacité du registre a **répondu**. Posé quand elle rend ce qu'on lui
    #: demandait, pas quand on la lui demande : le solveur essaie les capacités
    #: inscrites jusqu'à ce qu'une réponde, et compter les essais attribuerait à
    #: l'expérience ce que le tâtonnement a obtenu.
    CAPACITE = "CAPACITE"
    #: Le solveur a construit ce qui lui manquait.
    CONSTRUCTION = "CONSTRUCTION"
    #: Il s'est arrêté et a demandé un humain. Le compteur le plus important de
    #: la directive : une autonomie qui monte en appelant plus souvent à l'aide
    #: n'est pas une autonomie qui monte.
    HUMAIN = "HUMAIN"


@dataclass(frozen=True)
class Pas:
    """Un pas, ce qu'il a coûté, et ce qu'il a donné."""

    genre: Etape
    quoi: str
    cout: float = 1.0
    detail: str = ""

    def __post_init__(self) -> None:
        if self.cout < 0 or self.cout != self.cout or self.cout in (float("inf"), float("-inf")):
            raise ValueError("le coût d'un pas est un nombre fini positif")


@dataclass
class Trajectoire:
    """Ce qui s'est passé, dans l'ordre, pendant qu'une mission s'exécutait.

    Mutable exprès : elle s'écrit pendant la mission. Ce qui la lit ensuite --
    le banc, le rapport -- ne la modifie pas, et `figer()` en rend une copie que
    plus personne ne peut changer.
    """

    mission: str
    pas: list[Pas] = field(default_factory=list)

    def note(self, genre: Etape, quoi: str, *, cout: float = 1.0, detail: str = "") -> None:
        self.pas.append(Pas(genre, quoi, cout, detail))

    @property
    def cout(self) -> float:
        return round(sum(pas.cout for pas in self.pas), 4)

    def combien(self, genre: Etape) -> int:
        return sum(1 for pas in self.pas if pas.genre is genre)

    @property
    def capacites_reutilisees(self) -> tuple[str, ...]:
        return tuple(pas.quoi for pas in self.pas if pas.genre is Etape.CAPACITE)

    def figer(self) -> tuple[Pas, ...]:
        return tuple(self.pas)


@dataclass(frozen=True)
class Resultat:
    """Ce qu'une mission a rendu, et ce que le juge en a dit.

    `verifie` ne vient jamais du solveur. Il vient de `Mission.verifier`, qui
    recalcule depuis la source. Un solveur peut se tromper en croyant réussir ;
    c'est précisément le cas que ce champ existe pour attraper.
    """

    mission: str
    reponse: Any
    verifie: bool
    trajectoire: tuple[Pas, ...]
    cout: float
    erreurs: int
    recuperations: int
    interventions_humaines: int
    capacites_reutilisees: tuple[str, ...]
    pourquoi: str = ""


@dataclass(frozen=True)
class Mission:
    """Un objectif, ses sources, et de quoi juger la réponse sans croire le solveur.

    `sources` est un dictionnaire de noms vers des textes. Pas de chemins : une
    mission qui lit le disque au moment où elle s'exécute n'est pas reproductible
    et ne peut pas être rejouée à l'identique dans un banc différentiel. Ce qui
    vient du disque y est mis par l'appelant, une fois, avant.

    `verifier` reçoit la réponse du solveur et les sources, et rend `True` ou
    `False`. Il n'a pas accès à la trajectoire : un juge qui voit comment on a
    répondu finit par juger la manière.
    """

    nom: str
    objectif: str
    sources: dict[str, str]
    verifier: Callable[[Any, dict[str, str]], bool]
    #: Ce que la mission attend comme famille de réponse, pour le rapport.
    attendu: str = ""
    #: Ce que le solveur a besoin de savoir et que l'objectif dit en français.
    #: Générique exprès : ce fichier ne doit rien connaître du domaine, sinon
    #: chaque nouveau domaine demanderait de le rouvrir.
    parametres: dict[str, Any] = field(default_factory=dict)

    def juger(self, reponse: Any) -> bool:
        """Le verdict, et un juge qui lève est un juge qui refuse.

        Une exception dans le vérificateur ne doit jamais devenir une réussite :
        un solveur qui rendrait un objet inattendu ferait planter le juge, et
        `except` large ici est ce qui empêche ce plantage de valoir un succès.

        **C'est donc ici qu'est la discipline de type, et nulle part ailleurs.**
        Les vérificateurs des missions commençaient tous par un
        `isinstance(reponse, dict)`. `tools/gardes_sans_test.py` les a nommés :
        aucune entrée ne peut distinguer ces gardes de leur absence, puisqu'un
        `.get` sur autre chose qu'un dictionnaire lève et que cette ligne-ci
        rattrape. Ils promettaient un contrôle que celui-ci faisait déjà, et
        seraient revenus dans chaque rapport d'audit. Un vérificateur peut donc
        supposer ce qu'il veut : ce qui ne tient pas est un refus.
        """
        try:
            return bool(self.verifier(reponse, dict(self.sources)))
        except Exception:
            return False


def executer(mission: Mission, solveur: Callable[[Mission, Trajectoire], Any]) -> Resultat:
    """Lance un solveur sur une mission et rend ce qui s'est réellement passé.

    Un solveur qui lève n'est pas un solveur qui réussit : l'exception devient un
    échec enregistré, pas une exception qui remonte. Le banc doit pouvoir
    comparer une mission ratée à une mission réussie sans que la première
    l'interrompe.
    """
    trajectoire = Trajectoire(mission.nom)
    pourquoi = ""
    try:
        reponse = solveur(mission, trajectoire)
    except Exception as erreur:  # noqa: BLE001 -- un solveur qui plante est un solveur qui rate
        trajectoire.note(Etape.ECHEC, "solveur", detail=type(erreur).__name__)
        reponse = None
        pourquoi = f"le solveur a levé {type(erreur).__name__}"

    verifie = mission.juger(reponse)
    if not verifie and not pourquoi:
        pourquoi = "la réponse ne passe pas le vérificateur"
    return Resultat(
        mission=mission.nom,
        reponse=reponse,
        verifie=verifie,
        trajectoire=trajectoire.figer(),
        cout=trajectoire.cout,
        erreurs=trajectoire.combien(Etape.ECHEC),
        recuperations=trajectoire.combien(Etape.RECUPERATION),
        interventions_humaines=trajectoire.combien(Etape.HUMAIN),
        capacites_reutilisees=trajectoire.capacites_reutilisees,
        pourquoi=pourquoi,
    )


__all__ = ["Etape", "Mission", "Pas", "Resultat", "Trajectoire", "executer"]
