"""Ce que le système sait faire, et ce qui le prouve.

« Le système peut faire X » et « le système sait faire X » ne sont pas la même
phrase, et toute la directive Genesis tient dans cet écart. Une capacité qui a
marché une fois a marché une fois. Ce module refuse de lui accorder autre chose
tant que les preuves ne sont pas là, et il les compte plutôt que de les croire.

**L'échelle de preuve, et la règle qui la rend honnête.**

E0 inscrite, jamais vérifiée · E1 vérifiée une fois · E2 vérifiée sur deux
instances distinctes · E3 sur trois, sans aucun échec · E4 en plus sur une
instance abîmée, celle qui a demandé de récupérer · E5 en plus dans deux
domaines distincts.

La règle qui compte est la dernière : **un seul échec enregistré plafonne à E2.**
« Observée » et « répétée » sont des faits, qu'un échec ultérieur ne défait pas.
« Vérifiée », « robuste » et « prouvée sur un domaine » sont des affirmations de
fiabilité, et un échec les réfute. Sans ce plafond, une capacité accumulerait des
succès jusqu'à E5 en ratant une fois sur trois, ce qui serait exactement la
métrique optimisée contre la réalité que la directive interdit.

**L'artefact, pas le nom.**

Une capacité est liée à l'empreinte de son code, calculée par
`artifact_fingerprint` -- celle-là même que la frontière d'exécution du dépôt
utilise pour refuser qu'un jeton de capacité désigne un autre objet après un
redémarrage. Réinscrire un nom avec un autre artefact est permis, mais **remet
les preuves à zéro** : elles avaient été gagnées par l'ancien code. C'est le seul
mécanisme qui empêche « candidat X, évalué, approuvé » d'activer autre chose que
X.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from ..execution_capability import artifact_fingerprint

#: Les niveaux, du moins prouvé au plus prouvé. L'ordre est celui de la liste.
NIVEAUX = ("E0", "E1", "E2", "E3", "E4", "E5")

#: Ce que chaque niveau veut dire, en une ligne, pour que le rapport le dise
#: plutôt que de laisser lire un code.
SENS = {
    "E0": "inscrite, jamais vérifiée",
    "E1": "vérifiée une fois",
    "E2": "vérifiée sur deux instances distinctes",
    "E3": "vérifiée sur trois instances, sans aucun échec",
    "E4": "en plus, vérifiée sur une instance abîmée",
    "E5": "en plus, vérifiée dans deux domaines distincts",
}

#: Au-delà de ce niveau, un échec enregistré retire le droit d'en parler.
PLAFOND_APRES_ECHEC = "E2"


@dataclass(frozen=True)
class Preuve:
    """Une exécution vérifiée, et sur quoi.

    `instance` est ce qui distingue deux emplois : deux appels sur la même
    instance ne font pas une répétition, ils font un rejeu. `abimee` marque
    l'instance qui a demandé de récupérer -- c'est elle qui sépare « ça marche »
    de « ça tient ».
    """

    instance: str
    domaine: str
    abimee: bool = False
    reussi: bool = True


@dataclass(frozen=True)
class Capacite:
    """Ce que le système sait faire, avec de quoi le contredire.

    `procedure` est le code. `empreinte` est son identité, calculée et pas
    déclarée. Les preuves sont un journal, pas un compteur : on peut relire
    lesquelles ont échoué.
    """

    nom: str
    but: str
    procedure: Callable[..., Any]
    empreinte: str
    #: La mission d'où elle sort. Sans ça, « d'où vient cette capacité ? » n'a
    #: pas de réponse, et la directive en fait une question de premier ordre.
    provenance: str = ""
    version: int = 1
    preuves: tuple[Preuve, ...] = ()
    #: Le nombre de fois qu'elle a été **remise** à un appelant, pas le nombre de
    #: fois qu'elle a servi. Le solveur essaie les lecteurs inscrits jusqu'à ce
    #: qu'un réponde, donc ce compteur grandit avec la taille du registre et pas
    #: avec l'utilité de la capacité. Il s'appelait `reutilisations` et le
    #: rapport affichait « employée 2× » pour une capacité qui n'avait rien
    #: répondu : un chiffre juste qui se lisait faux.
    remises: int = 0

    @property
    def reutilisations(self) -> int:
        """Les fois où elle a servi **et tenu**, d'après les preuves enregistrées.

        Dérivé, jamais incrémenté : un compteur qu'on incrémente à la main finit
        par compter autre chose que ce que son nom dit, et c'est exactement ce
        qui est arrivé à `remises`.
        """
        return sum(1 for preuve in self.preuves if preuve.reussi)

    @property
    def echecs(self) -> int:
        return sum(1 for preuve in self.preuves if not preuve.reussi)

    @property
    def instances_reussies(self) -> frozenset[str]:
        return frozenset(preuve.instance for preuve in self.preuves if preuve.reussi)

    @property
    def domaines_reussis(self) -> frozenset[str]:
        return frozenset(preuve.domaine for preuve in self.preuves if preuve.reussi)

    @property
    def abimee_tenue(self) -> bool:
        return any(preuve.reussi and preuve.abimee for preuve in self.preuves)

    @property
    def niveau(self) -> str:
        """Le niveau de preuve, recalculé depuis les preuves à chaque lecture.

        Recalculé, jamais stocké : un niveau écrit dans un champ est un niveau
        qu'on peut poser sans l'avoir gagné, et c'est précisément la falsification
        que la directive demande de rendre impossible.
        """
        distinctes = len(self.instances_reussies)
        if distinctes == 0:
            atteint = "E0"
        elif distinctes == 1:
            atteint = "E1"
        elif distinctes == 2:
            atteint = "E2"
        else:
            atteint = "E3"
            if self.abimee_tenue:
                atteint = "E4"
                if len(self.domaines_reussis) >= 2:
                    atteint = "E5"
        if self.echecs and NIVEAUX.index(atteint) > NIVEAUX.index(PLAFOND_APRES_ECHEC):
            return PLAFOND_APRES_ECHEC
        return atteint

    @property
    def sens(self) -> str:
        return SENS[self.niveau]


class SubstitutionRefusee(RuntimeError):
    """Le code inscrit sous ce nom n'est pas celui qu'on vient de présenter."""


class Registre:
    """Les capacités du système, et ce qu'elles ont réellement prouvé.

    En mémoire, exprès et pour l'instant : le banc différentiel a besoin de
    comparer un registre vide à un registre rempli, dans le même processus,
    plusieurs fois. Rien ici ne persiste, donc rien ici ne survit à un
    redémarrage -- c'est une limite, elle est écrite, et le jour où Genesis
    devra la franchir c'est `DurableCapabilityStore` qui portera la persistance,
    pas une deuxième table inventée à côté.
    """

    def __init__(self) -> None:
        self._capacites: dict[str, Capacite] = {}

    def __contains__(self, nom: str) -> bool:
        return nom in self._capacites

    def __len__(self) -> int:
        return len(self._capacites)

    def noms(self) -> tuple[str, ...]:
        return tuple(sorted(self._capacites))

    def chercher(self, nom: str) -> Capacite | None:
        """Ce que GAMMA fait avant de construire : regarder si ça existe déjà."""
        return self._capacites.get(nom)

    def inscrire(self, nom: str, but: str, procedure: Callable[..., Any], *,
                 provenance: str = "") -> Capacite:
        """Inscrit une capacité, ou la remplace en remettant ses preuves à zéro.

        Le même nom et le même artefact : rien ne bouge, on rend l'inscrite.
        Le même nom et un autre artefact : c'est une nouvelle version, et elle
        repart à E0. Les preuves appartenaient au code qui les avait gagnées.
        """
        empreinte = artifact_fingerprint(procedure)
        existante = self._capacites.get(nom)
        if existante is not None and existante.empreinte == empreinte:
            return existante
        version = 1 if existante is None else existante.version + 1
        capacite = Capacite(nom=nom, but=but, procedure=procedure, empreinte=empreinte,
                            provenance=provenance, version=version)
        self._capacites[nom] = capacite
        return capacite

    def employer(self, nom: str, procedure_attendue: Callable[..., Any] | None = None) -> Capacite:
        """Rend la capacité et compte l'emploi, après avoir vérifié son identité.

        `procedure_attendue` est le contrôle anti-substitution du côté de
        l'appelant : quelqu'un qui a gardé une référence au code qu'il croyait
        autorisé peut exiger que ce soit encore celui-là. Sans ce paramètre, on
        rend simplement l'inscrite -- l'empreinte reste calculée sur l'objet
        réellement stocké, jamais sur une déclaration.
        """
        capacite = self._capacites.get(nom)
        if capacite is None:
            raise KeyError(nom)
        if capacite.empreinte != artifact_fingerprint(capacite.procedure):
            raise SubstitutionRefusee(
                f"« {nom} » ne porte plus l'artefact sous lequel elle a été inscrite")
        if procedure_attendue is not None:
            if artifact_fingerprint(procedure_attendue) != capacite.empreinte:
                raise SubstitutionRefusee(
                    f"« {nom} » désigne un autre artefact que celui attendu")
        capacite = replace(capacite, remises=capacite.remises + 1)
        self._capacites[nom] = capacite
        return capacite

    def prouver(self, nom: str, preuve: Preuve) -> Capacite:
        """Enregistre ce qu'un emploi a donné, réussite comme échec.

        Les échecs s'enregistrent aussi, et c'est tout l'intérêt : un registre
        qui ne garde que les succès produit un niveau de preuve qui monte tout
        seul.
        """
        capacite = self._capacites[nom]
        capacite = replace(capacite, preuves=capacite.preuves + (preuve,))
        self._capacites[nom] = capacite
        return capacite

    def rapport(self) -> tuple[dict[str, Any], ...]:
        """De quoi lire l'état du registre sans avoir à le parcourir soi-même."""
        return tuple({
            "nom": capacite.nom,
            "but": capacite.but,
            "niveau": capacite.niveau,
            "sens": capacite.sens,
            "version": capacite.version,
            "empreinte": capacite.empreinte,
            "provenance": capacite.provenance,
            "remises": capacite.remises,
            "reutilisations": capacite.reutilisations,
            "instances_reussies": len(capacite.instances_reussies),
            "domaines_reussis": len(capacite.domaines_reussis),
            "echecs": capacite.echecs,
        } for capacite in (self._capacites[nom] for nom in self.noms()))


__all__ = ["NIVEAUX", "PLAFOND_APRES_ECHEC", "SENS", "Capacite", "Preuve", "Registre",
           "SubstitutionRefusee"]
