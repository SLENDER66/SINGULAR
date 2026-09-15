"""A decision journal that refuses to let activity pass for results.

The constitution this repository is built to satisfy opens with one sentence:
"Maximiser le progrès réel de Thomas sous contraintes, sans confondre activité
et résultat." Nothing in the codebase enforced it. Thirteen thousand lines were
written across four versions, each predicted to move the project forward, and
none of those predictions was ever written down or checked.

This is the smallest thing that fixes that. Before doing something, you record
what you expect and how sure you are. When the horizon passes, the entry comes
back and asks what actually happened. It then tells you where your confidence is
wrong and where your hours went.

It deliberately does not use the execution boundary. That machinery governs
actions on the world and is heavy on purpose; a journal entry changes nothing
outside your own head. What it does borrow is the discipline: entries are
hash-chained, so a prediction cannot be quietly improved after the outcome is
known. A journal you can edit afterwards teaches you nothing.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from math import isfinite
from pathlib import Path
from typing import Any

from .learning import Forecast, ForecastKind, LearningEngine
from .sqlite_support import SqliteLocation

SCHEMA_VERSION = 3
DEFAULT_PATH = Path.home() / ".singular" / "journal.db"

#: Nombre de verdicts en dessous duquel une calibration ne veut rien dire.
#:
#: Le seuil vivait dans `singular/sage/notice.py`, que le moteur ne peut pas
#: importer -- la dependance va dans l'autre sens. Resultat : `summary_line`, la
#: ligne que son profil shell imprime, tenait sa propre regle, sans minimum du
#: tout, et annoncait « calibration -85% » **apres un seul verdict** pendant que
#: la Notice se taisait sur les memes donnees. C'est la cinquieme fois que ce
#: defaut se produit -- lire l'en-tete de `tests/test_une_seule_regle_par_phrase.py`
#: -- et la premiere ou il est dans le moteur lui-meme. Les deux seuils
#: d'affichage vivent donc ici, ou la seule chose qui les lit sans pouvoir
#: importer le Sage peut les lire, et le Sage les importe.
CALIBRATION_MINIMUM = 3

#: L'ecart voyant : en dessous, on ne montre un chiffre que s'il est demontre.
#:
#: La ligne de statut en avait une copie a 0.10, la Notice tranche a 0.15 : sur
#: un ecart de 12 % la ligne parlait et la Notice se taisait. Une seule valeur.
CALIBRATION_GAP = 0.15


# --- ce que vaut sa confiance ------------------------------------------------
#
# La règle vivait dans `singular/sage/notice.py`. Elle en descend pour la même
# raison que ses deux seuils l'avaient déjà fait : `summary_line`, la ligne que
# son profil shell imprime dans chaque terminal, ne peut pas importer le Sage --
# la dépendance va dans l'autre sens -- et tenait donc sa propre version de la
# règle. Elle en était à « assez de verdicts, et quinze points d'écart », c'est-
# à-dire à la version d'avant le 9 septembre : sur un écart de dix points établi
# sur deux cents verdicts, la Notice concluait et la ligne se taisait.
#
# C'est la sixième fois que ce défaut se paie, et la sixième a de quoi trancher :
# la Notice sait désormais dire « tu l'as déjà corrigé », pendant que chaque
# terminal ouvert aurait continué d'afficher l'écart d'une vie. On arrête donc de
# corriger et on rend l'erreur impossible -- la règle entière est ici, le Sage
# l'importe, et `tests/test_une_seule_regle_par_phrase.py` échoue si elle se
# remet à vivre à deux endroits.

#: Écart de calibration à partir duquel un constat non démontré vaut d'être
#: montré. Ce n'est plus la condition pour conclure : la preuve l'est.
#:
#: Un demi-point : en deçà, la phrase dirait « tu te surestimes de +0% ».
#: Plancher d'arrondi, pas plancher de jugement — la nuance est le sujet même
#: du choix ci-dessous.
CALIBRATION_ARRONDI = 0.005

#: Au-delà de quelle rareté un écart cesse de s'expliquer par le hasard.
#: Une fois sur vingt : le seuil est conventionnel, il est écrit ici plutôt que
#: sous-entendu, et la phrase affichée donne la rareté réelle pour qu'on puisse
#: en juger autrement.
CALIBRATION_HASARD = 0.05


def _distribution(probabilities: list[float]) -> list[float]:
    """La loi du nombre de réussites, exacte, quand chaque pari a sa probabilité.

    Chaque pari déplace une part `p` du poids vers « une réussite de plus ».
    Deux questions s'en servent — « son écart vient-il du hasard ? » et « son
    écart est-il devenu petit ? » — et elles la calculaient chacune de leur
    côté avant que la seconde existe.
    """
    distribution = [1.0]
    for p in probabilities:
        suivante = [0.0] * (len(distribution) + 1)
        for reussites, poids in enumerate(distribution):
            suivante[reussites] += poids * (1.0 - p)
            suivante[reussites + 1] += poids * p
        distribution = suivante
    return distribution


def chance_du_hasard(probabilities: list[float], hits: int) -> float:
    """La chance qu'un écart au moins aussi grand sorte de probabilités justes.

    C'est la question du journal, posée exactement : si chacune de ses
    prédictions valait ce qu'il a annoncé, à quelle fréquence obtiendrait-il un
    résultat aussi éloigné de ce qu'il attendait ?

    La distribution du nombre de réussites se construit en ajoutant les paris
    un par un — chaque pari déplace une part `p` du poids vers « une réussite
    de plus ». Exact, y compris quand les probabilités diffèrent entre elles :
    une moyenne aurait été une approximation, et approximer la réponse à la
    seule question pour laquelle cet outil existe serait une drôle d'économie.

    Déterministe, sans réseau, sans modèle : de l'arithmétique sur des
    flottants, dans le même ordre des deux côtés du portage.
    """
    if not probabilities:
        return 1.0
    distribution = _distribution(probabilities)
    attendu = sum(probabilities)
    ecart = abs(hits - attendu)
    return sum(poids for reussites, poids in enumerate(distribution)
               if abs(reussites - attendu) >= ecart - 1e-9)


def chance_d_un_ecart_moindre(probabilities: list[float], hits: int,
                              borne: float) -> float:
    """La chance de paraître aussi juste **en étant** biaisé d'au moins `borne`.

    `chance_du_hasard` répond à « son écart peut-il venir du hasard ? ». Elle ne
    répond pas à la question inverse, et c'est celle-là qui décide s'il faut se
    taire : « son écart est-il devenu petit ? ». Un écart non démontré n'est pas
    un écart démontré nul — sur six verdicts, presque rien n'est démontrable, et
    conclure « c'est corrigé » parce que la preuve manque serait exactement le
    défaut que ce fichier reproche déjà à l'autre bord.

    On renverse donc la charge. On suppose qu'il se surestime d'au moins
    `borne` : chacune de ses prédictions à `p` n'arriverait qu'à `p - borne`.
    Sous cette hypothèse, quelle chance de réussir au moins autant qu'il a
    réussi ? Si elle est infime, l'hypothèse tombe. Le symétrique tombe de la
    même façon pour la sous-estimation, et c'est le plus grand des deux qui est
    rendu : il faut écarter les deux pour dire que l'écart est petit.

    Limite assumée : une prédiction annoncée en dessous de `borne` ne peut pas
    porter un biais de `borne` — `0,10 - 0,15` n'est pas une probabilité. Elle
    entre alors à zéro, la valeur réalisable la plus proche, et l'hypothèse
    testée est un peu plus faible qu'annoncé sur ces paris-là.

    Déterministe, sans réseau, sans modèle, comme sa voisine.
    """
    # `borne <= 0` ne suffisait pas, et le trou penchait du mauvais côté : avec
    # `inf`, toutes les probabilités se ramenaient aux bornes et la fonction
    # rendait **zéro**, c'est-à-dire « écart démontré petit, avec certitude ».
    # Une entrée dégénérée donnait le verdict le plus permissif possible. La
    # règle du dépôt tranche dans l'autre sens : en cas d'ambiguïté, on refuse.
    # `not (0 < borne < 1)` attrape aussi `nan`, dont toutes les comparaisons
    # sont fausses.
    if not probabilities or not 0 < borne < 1:
        return 1.0
    surestime = [min(1.0, max(0.0, p - borne)) for p in probabilities]
    sousestime = [min(1.0, max(0.0, p + borne)) for p in probabilities]
    haut = sum(poids for reussites, poids in enumerate(_distribution(surestime))
               if reussites >= hits)
    bas = sum(poids for reussites, poids in enumerate(_distribution(sousestime))
              if reussites <= hits)
    return max(haut, bas)


def _periode(probabilites: list[float], resultats: list[int]) -> dict[str, Any]:
    """Ce que vaut sa confiance sur une tranche de son journal."""
    verdicts = len(resultats)
    # « Arrivé ou non », pas « combien » : un rapport d'une autre version, ou
    # fabriqué à la main, ne doit pas pouvoir gonfler le compte des réussites
    # au-dessus du nombre de verdicts et rendre une probabilité impossible.
    hits = sum(1 for resultat in resultats if resultat)
    gap = round(sum(probabilites) / verdicts - hits / verdicts, 2) or 0.0
    hasard = chance_du_hasard(probabilites, hits)
    return {
        "verdicts": verdicts,
        "gap": gap,
        "chance": hasard,
        "conclusive": hasard <= CALIBRATION_HASARD and abs(gap) >= CALIBRATION_ARRONDI,
        "equivalence": chance_d_un_ecart_moindre(probabilites, hits, CALIBRATION_GAP),
    }


def calibration_progression(report: dict[str, Any]) -> dict[str, Any] | None:
    """Son écart a une date, et le chiffre du jour ne la portait pas.

    `calibration_verdict` mesure toute la vie du journal d'un seul bloc. Un
    biais corrigé il y a deux mois y pèse donc autant qu'hier, et la Notice
    continue de dire « baisse tes probabilités d'autant » à quelqu'un qui les a
    déjà baissées. Corriger un jugement juste, c'est le dérégler : ce fichier le
    dit déjà pour le petit échantillon, et le laissait faire pour le passé.

    Le journal est coupé en deux moitiés, **dans l'ordre où les décisions ont
    été prises** — c'est l'instant du jugement, pas celui du verdict. Chaque
    moitié est mesurée seule. `corrige` n'est vrai que si la première moitié
    montre un écart que le hasard n'explique pas *et* que la seconde démontre un
    écart inférieur à `CALIBRATION_GAP`, au sens de `chance_d_un_ecart_moindre`.
    Les deux, sinon rien : une moitié récente muette est une moitié sans preuve,
    pas une preuve d'amélioration.

    Limite assumée : une décision récente dont l'horizon court encore n'a pas de
    verdict et n'entre nulle part. La moitié récente penche donc vers les
    horizons courts, et une amélioration lue ici ne vaut d'abord que pour eux.

    `None` tant qu'il n'y a pas deux moitiés dignes de ce nom.
    """
    probabilites = list(report.get("resolved_probabilities") or [])
    resultats = list(report.get("resolved_outcomes") or [])
    if len(probabilites) != len(resultats) or len(resultats) < 2 * CALIBRATION_MINIMUM:
        return None
    coupe = len(resultats) // 2
    debut = _periode(probabilites[:coupe], resultats[:coupe])
    recent = _periode(probabilites[coupe:], resultats[coupe:])
    return {
        "debut": debut,
        "recent": recent,
        # Trois conditions, et la troisieme a ete trouvee en attaquant les deux
        # premieres. « L'ecart recent est demontre inferieur a quinze points » ne
        # veut pas dire « il n'y a plus d'ecart » : sur quatre cents verdicts, un
        # ecart de dix points passe l'equivalence *et* se demontre. Le Sage
        # aurait alors tenu les deux phrases a la fois -- « ton ecart recent est
        # de +10 %, c'est prouve » et « c'est corrige, ne corrige pas » -- ce qui
        # est exactement le defaut que cette section entiere existe pour fermer.
        # Corrige veut donc dire : la moitie recente ne demontre plus rien.
        #
        # Consequence a ne pas prendre pour une panne : ce verdict se fait rare a
        # mesure que le journal grossit, parce que sur huit cents verdicts meme
        # deux points finissent par se demontrer. C'est voulu. Plus il y a de
        # donnees, plus le Sage a le droit d'etre precis, et moins il a le droit
        # de dire grossierement que tout va bien. Une session qui « reparerait »
        # ca en retirant la troisieme condition remettrait la contradiction.
        "corrige": (debut["conclusive"]
                    and recent["equivalence"] <= CALIBRATION_HASARD
                    and not recent["conclusive"]),
    }


def calibration_verdict(report: dict[str, Any]) -> dict[str, Any] | None:
    """Ce que valent ses probabilités — calculé une fois, pour tous ceux qui l'affichent.

    La phrase du rapport et la vignette dorée au-dessus disent la même chose ;
    elles le disaient chacune à leur façon. La vignette gardait « écart ≥ 15 %
    et 3 verdicts » et s'allumait donc en alerte pendant que la phrase, juste
    en dessous, expliquait qu'il était trop tôt pour conclure. Deux réponses
    contradictoires à la même question, sur le même écran.

    Ce n'est pas la première fois : `test_sage_web_client.py` garde déjà une
    vignette qui avait survécu à la correction de sa phrase. Troisième fois,
    donc la règle n'a plus qu'un domicile et les interfaces lisent son verdict
    au lieu de le refaire.
    """
    gap = report["overconfidence"]
    if gap is None or report["resolved"] < CALIBRATION_MINIMUM:
        return None
    hasard = chance_du_hasard(report["resolved_probabilities"],
                              round(report["hit_rate"] * report["resolved"]))
    return {
        "gap": gap,
        "chance": hasard,
        # « Conclusif » veut dire démontré, et rien d'autre. Il a voulu dire
        # « démontré et d'au moins quinze points », ce qui rendait muet un écart
        # de dix points établi sur deux cents verdicts.
        "conclusive": hasard <= CALIBRATION_HASARD and abs(gap) >= CALIBRATION_ARRONDI,
        # « Y a-t-il lieu d'en parler ? » est encore une question de la règle, et
        # elle vivait dans deux corps de fonction : la Notice et la ligne de
        # statut, qui n'en donnaient pas la même réponse. Démontré, on le dit
        # quel que soit l'écart ; sinon, seulement s'il saute aux yeux.
        "montrable": (hasard <= CALIBRATION_HASARD and abs(gap) >= CALIBRATION_ARRONDI)
        or abs(gap) >= CALIBRATION_GAP,
    }


class Tier(str, Enum):
    """The constitution's hierarchy, in its own order.

    Recording which rung a decision serves is the whole point: it is how you
    find out you spent a month on Patrimoine while Revenus stayed empty.
    """

    STABILITE = "STABILITE"
    REVENUS = "REVENUS"
    CAPACITES = "CAPACITES"
    OPPORTUNITES = "OPPORTUNITES"
    PATRIMOINE = "PATRIMOINE"
    LIBERTE = "LIBERTE"

    @property
    def rank(self) -> int:
        return list(Tier).index(self) + 1

    @property
    def label(self) -> str:
        """Le nom du rang tel qu'il est écrit dans la constitution.

        Les valeurs stockées sont sans accent, pour qu'une base écrite hier
        reste lisible demain quel que soit l'encodage. Ce qu'on montre à
        l'écran, lui, doit être le mot juste.
        """
        return {
            Tier.STABILITE: "Stabilité",
            Tier.REVENUS: "Revenus",
            Tier.CAPACITES: "Capacités",
            Tier.OPPORTUNITES: "Opportunités",
            Tier.PATRIMOINE: "Patrimoine",
            Tier.LIBERTE: "Liberté",
        }[self]


class Status(str, Enum):
    OPEN = "OPEN"
    HAPPENED = "HAPPENED"
    DID_NOT_HAPPEN = "DID_NOT_HAPPEN"
    ABANDONED = "ABANDONED"

    @property
    def label(self) -> str:
        """Le mot que les écrans montrent pour cet état, et il n'y en a qu'un.

        Il y en avait trois, tous dans `__main__.py` : `list` affichait
        « échoué », `resolve` « PAS ARRIVÉ », `abandon` « abandonné ». Le même
        état portait donc deux noms sur deux écrans du même outil, et le bouton
        de l'app disait encore autrement.

        « échoué » n'était pas seulement un troisième mot, c'était un jugement :
        une prédiction qui ne s'est pas réalisée n'est pas un échec, et ce dépôt
        a déjà payé le reproche prématuré une fois. Le fait se dit « pas
        arrivée », comme dans l'app et comme dans la Notice.

        Féminin, parce que ce qui est ouvert ou arrivé est une décision. Les
        valeurs stockées restent l'anglais en majuscules : une base écrite hier
        doit rester lisible demain.
        """
        return {
            Status.OPEN: "ouverte",
            Status.HAPPENED: "arrivée",
            Status.DID_NOT_HAPPEN: "pas arrivée",
            Status.ABANDONED: "abandonnée",
        }[self]


class ImportRefused(PermissionError):
    """Une reprise refusée, et laquelle des trois raisons.

    Sous-classe de `PermissionError` pour ne rien casser de ce qui l'attrape
    déjà, mais distincte : `python -m singular` traduit `PermissionError` par
    « cette décision a déjà été tranchée », qui est la bonne phrase pour
    `resolve` et une absurdité ici. Jouer la commande deux fois de suite l'a
    montré tout de suite.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        #: `source_broken`, `self_broken` ou `duplicates`.
        self.reason = reason


class Reversibility(str, Enum):
    """Peut-on revenir en arrière, et à quel prix ?

    La constitution dit : « En cas d'incertitude critique et de conséquence
    élevée : HALT. » Rien dans une décision ne permettait de l'appliquer. Le
    journal savait ce qu'une décision coûte en heures ; jamais ce que coûte de
    s'être trompé. Une dette est l'exemple le plus net : deux décisions à
    5 000 euros et 20 heures ne sont pas la même décision selon qu'on peut
    l'annuler la semaine suivante ou qu'on la rembourse pendant trois ans.

    Les valeurs stockées sont sans accent, comme celles de `Tier` : une base
    écrite aujourd'hui doit rester lisible quel que soit l'encodage.
    """

    REVERSIBLE = "REVERSIBLE"
    COUTEUSE = "COUTEUSE"
    IRREVERSIBLE = "IRREVERSIBLE"

    @property
    def label(self) -> str:
        return {
            Reversibility.REVERSIBLE: "réversible",
            Reversibility.COUTEUSE: "coûteuse à défaire",
            Reversibility.IRREVERSIBLE: "irréversible",
        }[self]


@dataclass(frozen=True)
class Entry:
    entry_id: str
    title: str
    action: str
    predicted: str
    probability: float
    tier: Tier
    cost_hours: float
    horizon_days: int
    created_at: str
    due_at: str
    status: Status
    resolved_at: str | None
    lesson: str | None
    brier_score: float | None
    previous_fingerprint: str
    fingerprint: str
    #: En euros. `None` veut dire « pas chiffré », pas « zéro » : une décision
    #: dont on n'a pas estimé le gain n'est pas une décision sans gain, et les
    #: confondre effacerait justement ce que la Notice doit reprocher.
    expected_gain_eur: float | None = None
    reversibility: Reversibility | None = None
    #: L'empreinte que cette entrée portait dans le journal d'où elle vient.
    #:
    #: `None` pour une décision écrite ici. Non nulle pour une décision reprise
    #: d'un autre journal : son contenu n'a pas bougé -- la charge signée est
    #: la même -- mais elle est resignée derrière une autre entrée, donc son
    #: empreinte change. L'ancienne reste écrite à côté, comme preuve que la
    #: reprise n'a rien réécrit.
    imported_fingerprint: str | None = None

    @property
    def is_open(self) -> bool:
        return self.status is Status.OPEN

    @property
    def due_on(self) -> date:
        """Le jour de l'échéance. Un horizon se donne en jours, il tombe un jour.

        `due_at` porte l'heure à laquelle la décision a été écrite, parce qu'il
        vaut `created_at + horizon_days`. Comparé comme un instant, un horizon
        de 14 jours pris un soir à 20 h échoit le quatorzième jour à 20 h — et
        quelqu'un qui ouvre son rapport le matin, ce que le rituel du dépôt lui
        demande de faire, ne voit rien ce jour-là. Le verdict lui est réclamé
        le lendemain, systématiquement, alors que `A_FAIRE.md` lui promet la
        carte en tête « le 20 septembre ».

        Ce n'est pas un détail d'affichage : rendre le verdict à l'échéance est
        la seule chose que cet outil demande à son auteur de faire, et il la
        demandait toujours avec un jour de retard.

        Le jour est celui d'UTC, dans lequel `created_at` est écrit. Une
        décision enregistrée entre 22 h et minuit à Paris porte donc la date
        UTC de la veille, et son échéance sera réclamée un jour plus tôt qu'il
        ne l'aurait compté. C'est la contrepartie, elle est étroite, et elle va
        dans le bon sens : demander un jour trop tôt se voit et se remet à
        demain ; demander un jour trop tard fait manquer le jour dit.
        """
        return datetime.fromisoformat(self.due_at).date()

    def is_due(self, now: datetime | None = None) -> bool:
        """Vrai dès que le jour de l'échéance a commencé."""
        moment = now or datetime.now(UTC)
        return moment.date() >= self.due_on

    def days_until_due(self, now: datetime | None = None) -> int:
        """Jours restants avant l'échéance, jamais négatif."""
        moment = now or datetime.now(UTC)
        return max(0, (self.due_on - moment.date()).days)

    def overdue_days(self, now: datetime | None = None) -> int:
        moment = now or datetime.now(UTC)
        return max(0, (moment.date() - self.due_on).days)


def _fingerprint(payload: dict, previous: str) -> str:
    material = json.dumps({"previous": previous, **payload}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _colonne(row: sqlite3.Row, nom: str, cast=None):
    """La valeur d'une colonne qui peut ne pas exister dans ce schema."""
    if nom not in row.keys() or row[nom] is None:
        return None
    return row[nom] if cast is None else cast(row[nom])


def _payload(
    *,
    entry_id: str, title: str, action: str, predicted: str, probability: float,
    tier: str, cost_hours: float, horizon_days: int, created_at: str,
    expected_gain_eur: float | None, reversibility: str | None,
) -> dict:
    """La matière que l'empreinte signe. Écrite une fois, lue par les deux côtés.

    Elle l'était deux fois -- dans `add()` et dans `verify()` -- et deux copies
    d'une même vérité finissent par diverger. Ajouter un champ à l'une aurait
    déclaré réécrit un journal auquel personne n'a touché, définitivement,
    puisque les entrées ne sont jamais réécrites.

    Les deux champs d'affaires n'entrent dans la charge que lorsqu'ils sont
    renseignés. C'est ce qui permet à une entrée écrite avant qu'ils existent
    de rester vérifiable : sa charge est exactement celle d'hier, à l'octet
    près. Et c'est aussi ce qui fait qu'une valeur glissée après coup dans la
    base change la charge, donc l'empreinte : `verify()` la voit. Un gain
    attendu qu'on pourrait réviser une fois le résultat connu n'apprendrait
    rien -- c'est la raison d'être de la chaîne.
    """
    payload = {
        "entry_id": entry_id, "title": title, "action": action, "predicted": predicted,
        "probability": probability, "tier": tier, "cost_hours": cost_hours,
        "horizon_days": horizon_days, "created_at": created_at,
    }
    if expected_gain_eur is not None:
        payload["expected_gain_eur"] = expected_gain_eur
    if reversibility is not None:
        payload["reversibility"] = reversibility
    return payload


class DecisionJournal:
    """Append-only, hash-chained record of what you expected and what happened."""

    def __init__(self, path: str | Path = DEFAULT_PATH, *,
                 lecture_seule: bool = False) -> None:
        """`lecture_seule` ouvre une base sans la toucher. Voir `import_from`.

        Ouvrir un journal le **migrait**, et c'est le defaut que ce drapeau
        corrige. Trois `ALTER TABLE` partaient sur le fichier au premier
        contact, avant le moindre controle : mesure faite sur un journal de
        trois mois ramene au schema d'alors, son empreinte md5 changeait.

        Le fichier vise est le seul exemplaire de trois mois de decisions, pose
        sur une cle USB peut-etre protegee en ecriture. Une lecture qui ecrit
        est un defaut meme quand elle n'abime rien.
        """
        self._location = SqliteLocation(path, lecture_seule=lecture_seule)
        self.path = self._location.reference
        self.lecture_seule = lecture_seule
        if lecture_seule:
            self._verifie_la_version()
        else:
            self._init_schema()

    def _verifie_la_version(self) -> None:
        """Un journal ecrit par une version future ne se lit pas de travers.

        En lecture seule on ne migre pas, donc rien ne verifie la version. Or
        les regles de la charge d'empreinte pourraient changer : lire une base
        plus recente avec les regles d'aujourd'hui declarerait sa chaine rompue.
        Dire « ton journal est casse » a quelqu'un dont le journal va bien est
        la pire reponse possible ici.

        Plus ancienne, en revanche, se lit : `_payload` n'inclut les champs
        recents que lorsqu'ils sont renseignes, exactement pour ca.
        """
        with self._connect() as conn:
            ligne = conn.execute("SELECT version FROM journal_schema").fetchone()
        version = int(ligne["version"]) if ligne else SCHEMA_VERSION
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"journal schema v{version} does not match v{SCHEMA_VERSION}")

    def _connect(self) -> AbstractContextManager[sqlite3.Connection]:
        return self._location.session()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            # Le verrou d'ecriture d'abord, et explicitement. Sans lui, le
            # controle et l'action de la migration ne sont pas dans la meme
            # section critique : `PRAGMA table_info` dit « colonne absente » a
            # deux processus a la fois, et le second `ALTER TABLE` echoue en
            # « duplicate column name ».
            #
            # Ce n'est pas theorique : le Sage tourne pendant qu'on tape `add`
            # dans une autre fenetre, et les deux migrent au premier lancement
            # apres une mise a jour. On avait cru la sequence protegee par le
            # `CREATE TABLE IF NOT EXISTS` ci-dessous -- SQLite l'optimise en
            # rien du tout quand la table existe, et ne prend alors aucun
            # verrou. C'est le test de concurrence qui l'a montre, apres avoir
            # ete pris pour instable.
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("CREATE TABLE IF NOT EXISTS journal_schema (version INTEGER NOT NULL)")
            row = conn.execute("SELECT version FROM journal_schema").fetchone()
            if row is None:
                conn.execute("INSERT INTO journal_schema(version) VALUES(?)", (SCHEMA_VERSION,))
            else:
                self._migrate(conn, int(row["version"]))
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS journal_entries (
                    entry_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    action TEXT NOT NULL,
                    predicted TEXT NOT NULL,
                    probability REAL NOT NULL,
                    tier TEXT NOT NULL,
                    cost_hours REAL NOT NULL,
                    horizon_days INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    resolved_at TEXT,
                    lesson TEXT,
                    brier_score REAL,
                    previous_fingerprint TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    expected_gain_eur REAL,
                    reversibility TEXT,
                    imported_fingerprint TEXT
                )
                """
            )

    @staticmethod
    def _migrate(conn: sqlite3.Connection, version: int) -> None:
        """Fait passer une base existante à la version courante, ou refuse.

        `CREATE TABLE IF NOT EXISTS` ne migre rien : il ne s'exécute pas quand
        la table est là, et une base d'hier serait restée sans les colonnes
        neuves pendant que le code les lit. `CLAUDE.md` §13 l'interdit
        explicitement.

        Ce qui est ajouté ici est ajouté en NULL. C'est voulu : une décision
        prise avant que le gain attendu existe n'a pas de gain attendu, et lui
        en inventer un -- zéro compris -- réécrirait l'histoire. Sa charge
        d'empreinte reste donc celle de la v1, et la chaîne tient.
        """
        if version == SCHEMA_VERSION:
            return
        if version > SCHEMA_VERSION or version < 1:
            raise RuntimeError(f"journal schema v{version} does not match v{SCHEMA_VERSION}")

        if version == 1:
            tables = {r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "journal_entries" in tables:
                colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(journal_entries)")}
                if "expected_gain_eur" not in colonnes:
                    conn.execute("ALTER TABLE journal_entries ADD COLUMN expected_gain_eur REAL")
                if "reversibility" not in colonnes:
                    conn.execute("ALTER TABLE journal_entries ADD COLUMN reversibility TEXT")
            version = 2

        if version == 2:
            tables = {r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "journal_entries" in tables:
                colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(journal_entries)")}
                if "imported_fingerprint" not in colonnes:
                    conn.execute(
                        "ALTER TABLE journal_entries ADD COLUMN imported_fingerprint TEXT")
            version = 3

        conn.execute("UPDATE journal_schema SET version=?", (version,))

    # --- writing -------------------------------------------------------------

    def add(
        self,
        *,
        title: str,
        action: str,
        predicted: str,
        probability: float,
        tier: Tier,
        cost_hours: float,
        horizon_days: int,
        expected_gain_eur: float | None = None,
        reversibility: Reversibility | None = None,
        now: datetime | None = None,
    ) -> Entry:
        """Record a decision before acting on it.

        The probability is not decoration. It is what makes the entry checkable:
        "I think this works" cannot be wrong, "70% this produces a reply within
        14 days" can.
        """
        for name, value in (("probability", probability), ("cost_hours", cost_hours)):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if not 0 < probability < 1:
            raise ValueError("probability must be strictly between 0 and 1: certainty is not a forecast")
        if cost_hours < 0:
            raise ValueError("cost_hours cannot be negative")
        if horizon_days < 1:
            raise ValueError("a decision needs a horizon of at least one day to be checkable")
        if not title.strip() or not action.strip() or not predicted.strip():
            raise ValueError("title, action and predicted outcome are all required")
        # Le gain reste facultatif -- l'exiger ferait enregistrer moins de
        # décisions, et une décision non écrite est pire qu'une décision sans
        # chiffre. Mais un chiffre donné doit être un nombre : NaN se propage
        # sans lever, et un total de gains contaminé par un NaN reste NaN sans
        # que rien ne le signale.
        if expected_gain_eur is not None:
            if not isfinite(expected_gain_eur):
                raise ValueError("expected_gain_eur must be finite")
            if expected_gain_eur < 0:
                raise ValueError("expected_gain_eur cannot be negative: a cost is not a gain")
        if reversibility is not None and not isinstance(reversibility, Reversibility):
            raise TypeError("reversibility must be a Reversibility, not a bare string")

        # Canonicalise before fingerprinting, because the row is read back
        # canonicalised. `add(cost_hours=60)` fingerprinted the integer 60 and
        # `_entry` returned 60.0, which json renders differently, so verify()
        # declared an untouched journal rewritten -- from its very first entry,
        # for ever, since entries are never rewritten. The CLI passes floats and
        # never saw it; any other caller broke the chain by writing to it.
        # Validation runs first, so a string still raises rather than being
        # quietly converted into a number.
        probability = float(probability)
        cost_hours = float(cost_hours)
        horizon_days = int(horizon_days)
        # Même raison que ci-dessus : add(expected_gain_eur=5000) signerait
        # l'entier 5000 quand la ligne relue rend 5000.0.
        if expected_gain_eur is not None:
            expected_gain_eur = float(expected_gain_eur)

        moment = now or datetime.now(UTC)
        entry_id = "DEC-" + uuid.uuid4().hex[:8]
        payload = _payload(
            entry_id=entry_id, title=title, action=action, predicted=predicted,
            probability=probability, tier=tier.value, cost_hours=cost_hours,
            horizon_days=horizon_days, created_at=moment.isoformat(),
            expected_gain_eur=expected_gain_eur,
            reversibility=None if reversibility is None else reversibility.value,
        )
        with self._connect() as conn:
            # Same reason as the outcome ledger and the audit trail: reading the
            # head and inserting behind it has to be one serialised step, or two
            # writers link to the same entry and verify() reports a journal
            # nobody touched as broken -- for good, since entries are never
            # rewritten.
            conn.execute("BEGIN IMMEDIATE")
            previous = self._head(conn)
            fingerprint = _fingerprint(payload, previous)
            due = (moment + timedelta(days=horizon_days)).isoformat()
            conn.execute(
                "INSERT INTO journal_entries(entry_id,title,action,predicted,probability,tier,cost_hours,horizon_days,"
                "created_at,due_at,status,resolved_at,lesson,brier_score,previous_fingerprint,fingerprint,"
                "expected_gain_eur,reversibility)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (entry_id, title, action, predicted, probability, tier.value, cost_hours, horizon_days,
                 moment.isoformat(), due, Status.OPEN.value, None, None, None, previous, fingerprint,
                 expected_gain_eur, None if reversibility is None else reversibility.value),
            )
        return Entry(entry_id, title, action, predicted, probability, tier, cost_hours, horizon_days,
                     moment.isoformat(), due, Status.OPEN, None, None, None, previous, fingerprint,
                     expected_gain_eur, reversibility)

    def resolve(self, entry_id: str, *, happened: bool, lesson: str = "", now: datetime | None = None) -> Entry:
        """Record what actually happened. Scores the prediction, does not rewrite it.

        La leçon est la sienne, ou rien. Elle valait, quand il n'écrivait rien,
        « Forecast DEC-138fee1a was incorrect: predicted 0.75, observed 0. » --
        une phrase de machine, en anglais, dans un outil français, écrite dans
        le champ prévu pour ce que *lui* a compris, et gravée pour de bon
        puisque ce journal ne se réécrit pas.

        Elle n'apprend rien : la probabilité, le statut et le score de Brier
        sont déjà dans l'entrée, et cette phrase ne fait que les redire. Elle
        coûte, en revanche, la seule chose qui compte ici -- on ne distinguait
        plus « il n'a rien noté » de « il a noté ceci », et c'est la règle du
        dépôt sur la provenance, celle qui lui a déjà coûté un CV faux et un
        marché écarté.
        """
        moment = now or datetime.now(UTC)
        with self._connect() as conn:
            # Le verrou avant la lecture, sinon le controle ne controle rien.
            # Deux resolutions simultanees lisaient toutes deux OPEN, passaient
            # toutes deux le refus ci-dessous, et ecrivaient toutes deux : une
            # decision tranchee deux fois, et celle qui perdait la course
            # s'entendait repondre que son verdict etait enregistre alors que
            # le journal disait l'inverse. Mesure, pas suppose -- quatre
            # processus, deux verdicts contradictoires acceptes.
            #
            # « history is not editable » est la promesse centrale de ce
            # fichier. Elle ne tenait qu'en l'absence de concurrence.
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM journal_entries WHERE entry_id=?", (entry_id,)).fetchone()
            if row is None:
                raise KeyError(entry_id)
            if row["status"] != Status.OPEN.value:
                raise PermissionError(f"{entry_id} was already resolved as {row['status']}; history is not editable")
            record = LearningEngine.evaluate_binary(
                Forecast(entry_id, ForecastKind.BINARY, probability=row["probability"], confidence=row["probability"]),
                happened,
            )
            status = Status.HAPPENED if happened else Status.DID_NOT_HAPPEN
            # `AND status=OPEN` en plus du verrou : si la course se rouvrait un
            # jour par un autre chemin, l'ecriture ne passerait pas en silence.
            ecrit = conn.execute(
                "UPDATE journal_entries SET status=?, resolved_at=?, lesson=?, brier_score=?"
                " WHERE entry_id=? AND status=?",
                (status.value, moment.isoformat(), lesson, record.brier_score,
                 entry_id, Status.OPEN.value),
            )
            if ecrit.rowcount != 1:
                raise PermissionError(f"{entry_id} a ete tranche par quelqu'un d'autre entre-temps")
            row = conn.execute("SELECT * FROM journal_entries WHERE entry_id=?", (entry_id,)).fetchone()
        return self._entry(row)

    def abandon(self, entry_id: str, *, reason: str, now: datetime | None = None) -> Entry:
        """Stopping is a result too, and an honest one. It is not a silent delete."""
        moment = now or datetime.now(UTC)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")  # meme course que resolve()
            row = conn.execute("SELECT status FROM journal_entries WHERE entry_id=?", (entry_id,)).fetchone()
            if row is None:
                raise KeyError(entry_id)
            if row["status"] != Status.OPEN.value:
                raise PermissionError(f"{entry_id} was already resolved as {row['status']}")
            ecrit = conn.execute(
                "UPDATE journal_entries SET status=?, resolved_at=?, lesson=?"
                " WHERE entry_id=? AND status=?",
                (Status.ABANDONED.value, moment.isoformat(), reason, entry_id, Status.OPEN.value),
            )
            if ecrit.rowcount != 1:
                raise PermissionError(f"{entry_id} a ete tranche par quelqu'un d'autre entre-temps")
            row = conn.execute("SELECT * FROM journal_entries WHERE entry_id=?", (entry_id,)).fetchone()
        return self._entry(row)

    def import_from(self, source: str | Path) -> tuple[Entry, ...]:
        """Reprendre les décisions d'un autre journal, à la suite de celui-ci.

        Le cas est celui du 10 septembre 2026 : la machine change, l'ancienne
        est hors de portée pour une durée inconnue, et il faut pouvoir écrire en
        attendant sans avoir à choisir plus tard laquelle des deux histoires
        garder.

        Recoller deux bases ligne à ligne ne marche pas, et c'est mesuré :
        `tests/test_deux_journaux.py` insère les lignes de l'une dans l'autre et
        `verify()` rend faux. Chaque empreinte signe la précédente, donc une
        entrée glissée au milieu rompt la chaîne de toutes les suivantes.

        Reprendre, ce n'est pas recoller. Les entrées de la source sont
        **ajoutées à la fin**, dans leur ordre d'origine, et resignées derrière
        la dernière entrée d'ici. Ce qui est signé ne change pas -- la charge
        d'empreinte porte la prédiction, pas le verdict, et elle est recalculée
        à l'identique. Ce qui change est le maillon, parce qu'une entrée ne peut
        pas suivre deux entrées différentes.

        L'empreinte d'origine est écrite à côté, dans `imported_fingerprint`.
        C'est ce qui distingue une reprise d'une réécriture : la preuve que le
        contenu repris est exactement celui qui avait été signé là-bas reste
        dans la base, et se revérifie.

        Ce qui ne survit pas, et il faut le dire : la chaîne **d'origine** ne se
        rejoue plus comme chaîne, puisque les maillons ont été remplacés. Ce qui
        reste est l'empreinte de chaque entrée reprise, plus le fait que la
        source a été vérifiée entière avant d'entrer -- c'est le refus
        `source_broken` qui le garantit. Assumé : conserver aussi le maillon
        d'origine demanderait une colonne de plus pour un geste qui arrive une
        fois dans la vie d'un journal.

        Refuse, et ne écrit rien, si :

        * la source ne se vérifie pas -- reprendre un journal falsifié y
          blanchirait la falsification ;
        * ce journal-ci ne se vérifie pas -- on n'ajoute pas derrière une chaîne
          déjà rompue ;
        * un identifiant existe des deux côtés -- ce serait la même décision
          comptée deux fois, et le journal ment alors sur ce qu'il a coûté.

        Rend les entrées reprises, telles qu'elles sont désormais écrites ici.
        """
        # En lecture seule, et c'est la moitie qui compte. Ouvrir la source
        # normalement la **migrait** : trois `ALTER TABLE` sur le seul
        # exemplaire de trois mois de decisions, avant meme le controle de
        # chaine, donc y compris quand la reprise finit par etre refusee.
        autre = DecisionJournal(source, lecture_seule=True)
        if not autre.verify():
            raise ImportRefused(
                "source_broken", f"the journal to import does not verify: {autre.path}")
        if not self.verify():
            raise ImportRefused(
                "self_broken", f"this journal does not verify: {self.path}")

        a_reprendre = autre._chain()
        if not a_reprendre:
            return ()
        deja = {entree.entry_id for entree in self.entries()}
        collisions = sorted(e.entry_id for e in a_reprendre if e.entry_id in deja)
        if collisions:
            raise ImportRefused(
                "duplicates",
                f"{len(collisions)} entries are already here: {', '.join(collisions[:3])}")

        try:
            self._reprendre(a_reprendre)
        except sqlite3.IntegrityError as course:
            # La cle primaire a tenu -- aucune entree en double, chaine intacte --
            # mais le message part en anglais sur son ecran. Le controle des
            # doublons ci-dessus se fait hors transaction : deux reprises
            # simultanees le passent toutes les deux, et celle qui perd la course
            # se voit refuser par SQLite. Mesure, en elargissant la fenetre a la
            # main : « UNIQUE constraint failed: journal_entries.entry_id ».
            if "entry_id" not in str(course):
                raise
            raise ImportRefused(
                "duplicates", "these entries were imported by someone else first"
            ) from None

        reprises = {entree.entry_id for entree in a_reprendre}
        return tuple(e for e in self._chain() if e.entry_id in reprises)

    def _reprendre(self, a_reprendre: tuple[Entry, ...]) -> None:
        """L'écriture elle-même, dans une seule transaction sérialisée."""
        with self._connect() as conn:
            # Meme raison que `add` : lire la tete et ecrire derriere doit etre
            # un seul pas serialise, sinon deux ecrivains se chainent au meme
            # endroit et la chaine casse pour de bon.
            conn.execute("BEGIN IMMEDIATE")
            previous = self._head(conn)
            for entree in a_reprendre:
                payload = _payload(
                    entry_id=entree.entry_id, title=entree.title, action=entree.action,
                    predicted=entree.predicted, probability=entree.probability,
                    tier=entree.tier.value, cost_hours=entree.cost_hours,
                    horizon_days=entree.horizon_days, created_at=entree.created_at,
                    expected_gain_eur=entree.expected_gain_eur,
                    reversibility=None if entree.reversibility is None
                    else entree.reversibility.value,
                )
                fingerprint = _fingerprint(payload, previous)
                conn.execute(
                    "INSERT INTO journal_entries(entry_id,title,action,predicted,probability,"
                    "tier,cost_hours,horizon_days,created_at,due_at,status,resolved_at,lesson,"
                    "brier_score,previous_fingerprint,fingerprint,expected_gain_eur,"
                    "reversibility,imported_fingerprint)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (entree.entry_id, entree.title, entree.action, entree.predicted,
                     entree.probability, entree.tier.value, entree.cost_hours,
                     entree.horizon_days, entree.created_at, entree.due_at,
                     entree.status.value, entree.resolved_at, entree.lesson,
                     entree.brier_score, previous, fingerprint, entree.expected_gain_eur,
                     None if entree.reversibility is None else entree.reversibility.value,
                     entree.imported_fingerprint or entree.fingerprint),
                )
                previous = fingerprint

    # --- reading -------------------------------------------------------------

    def entries(self, *, status: Status | None = None) -> tuple[Entry, ...]:
        query = "SELECT * FROM journal_entries"
        params: tuple = ()
        if status is not None:
            query += " WHERE status=?"
            params = (status.value,)
        query += " ORDER BY created_at"
        with self._connect() as conn:
            return tuple(self._entry(row) for row in conn.execute(query, params).fetchall())

    def due(self, *, now: datetime | None = None) -> tuple[Entry, ...]:
        """Open decisions whose horizon has passed, la plus en retard d'abord.

        Le jour de l'échéance compte comme échu dès son début : voir
        `Entry.due_on`, qui porte la raison et ce qu'elle a coûté.

        **L'ordre est celui du retard, et il compte.** Il suivait `entries()`,
        donc la date d'écriture, ce qui n'est pas la même chose : un horizon
        long pris il y a longtemps échoit après un horizon court pris hier.
        Trois surfaces s'appuient sur cet ordre et disaient toutes la même
        chose de travers.

        `python3 -m singular due` listait une décision en retard d'un jour
        au-dessus d'une décision en retard de trente-neuf, et terminait en lui
        donnant la commande pour trancher **la première**. La Notice était
        pire, parce qu'elle se contredisait dans une seule phrase : elle
        annonçait « la plus ancienne attend depuis 39 jours » -- un `max()` --
        puis proposait `resolve` sur `overdue[0]`, une autre décision. Et
        l'app reçoit `entry_ids` dans cet ordre.

        Trier ici plutôt qu'aux trois endroits : c'est la même règle, elle a
        un domicile. Le second critère départage les ex æquo pour que deux
        exécutions donnent le même écran.

        **Le port Swift, lui, triait déjà juste.** `Notice.swift` fait
        `sorted { $0.dueAt < $1.dueAt }` depuis toujours. Les deux moteurs
        divergeaient donc pour de bon, et les vecteurs de parité ne l'ont pas
        vu parce qu'aucun d'eux ne portait le cas : il faut un horizon long
        pris avant un horizon court pour que les deux ordres se séparent.
        """
        moment = now or datetime.now(UTC)
        echues = [e for e in self.entries(status=Status.OPEN) if e.is_due(moment)]
        # La clé est celle du port Swift, `Notice.swift` : `sorted { $0.dueAt
        # < $1.dueAt }`. Trier sur `-overdue_days` donnerait le même premier
        # mais regrouperait par jour, et deux échéances du même jour à des
        # heures différentes se rangeraient autrement des deux côtés.
        echues.sort(key=lambda e: (e.due_at, e.created_at))
        return tuple(echues)

    def _chain(self) -> tuple[Entry, ...]:
        """Entries in the order they were written, which is the order they were chained.

        Not the order they are read in. `entries()` sorts by created_at so the
        journal reads chronologically, but created_at is supplied by the caller:
        recording a decision after the fact -- add(now=yesterday) -- put an entry
        before one it was chained behind, and verify() then called an untouched
        journal rewritten. A hash chain follows insertion, nothing else.
        """
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM journal_entries ORDER BY rowid").fetchall()
        return tuple(self._entry(row) for row in rows)

    def verify(self) -> bool:
        """Has any prediction been rewritten since it was made?"""
        previous = ""
        for entry in self._chain():
            payload = _payload(
                entry_id=entry.entry_id, title=entry.title, action=entry.action,
                predicted=entry.predicted, probability=entry.probability, tier=entry.tier.value,
                cost_hours=entry.cost_hours, horizon_days=entry.horizon_days,
                created_at=entry.created_at, expected_gain_eur=entry.expected_gain_eur,
                reversibility=None if entry.reversibility is None else entry.reversibility.value,
            )
            if entry.previous_fingerprint != previous or _fingerprint(payload, previous) != entry.fingerprint:
                return False
            previous = entry.fingerprint
        return True

    def summary_line(self, *, now: datetime | None = None) -> str:
        """One line, short enough for a shell prompt.

        A journal you have to remember to open is a journal you stop opening.
        This is meant to be printed by your shell profile, so the number of
        decisions you have not faced is in front of you whether you want it or
        not.

        **Ce que cette ligne coute, mesure plutot que suppose.** Lire le verdict
        du moteur au lieu d'en tenir une copie a un prix : `chance_du_hasard`
        construit la loi exacte du nombre de reussites, ce qui est quadratique
        en nombre de verdicts. Mesure le 14 septembre 2026, arrondie a ce qui
        se reproduit d'une execution a l'autre -- deux passages sur la meme
        machine ecartent de 25 %, donc les chiffres precis mentiraient : de
        l'ordre de 10 ms a 100 verdicts, 50 ms a 500, 200 ms a 1000, 700 ms a
        2000. Le cout ne depend pas du nombre de probabilites distinctes, c'est
        verifie. Avant que cette ligne lise le verdict, elle ne payait rien.

        A un verdict par jour, les 200 ms arrivent dans trois ans et les 700 ms
        dans six. C'est donc une dette datee, pas un defaut d'aujourd'hui, et
        elle est ecrite ici plutot que corrigee maintenant : construire un cache
        ou une approximation pour un probleme qui se posera dans trois ans
        couterait de la complexite tout de suite contre rien de mesurable.

        Quand elle se posera, la correction n'est pas « remettre une regle ici »
        -- ce defaut-la s'est paye six fois. C'est soit une borne de Hoeffding
        qui tranche `conclusive` en temps lineaire quand elle suffit, en laissant
        le calcul exact pour le reste, soit un cache du verdict pose sur
        l'empreinte de tete du journal, qui change deja a chaque ecriture.
        """
        report = self.review(now=now)
        if not report["decisions"]:
            return "SINGULAR · journal vide"
        parts = []
        overdue = report["overdue"]
        parts.append(f"{overdue} à trancher" if overdue else "rien à trancher")
        if report["hours_unresolved"]:
            parts.append(f"{report['hours_unresolved']:g}h sans verdict")
        # Ce n'etait pas la regle du Sage, c'etait sa copie -- et une copie de la
        # version d'avant le 9 septembre : « assez de verdicts, et quinze points
        # d'ecart ». Sur dix points etablis sur deux cents verdicts, la Notice
        # concluait et cette ligne se taisait. Elle lit maintenant le meme
        # verdict, et le meme `corrige` : sans lui, chaque terminal ouvert aurait
        # affiche l'ecart d'une vie pendant que le Sage disait qu'il etait
        # corrige. Sixieme fois pour ce defaut, donc la regle n'a plus qu'un
        # domicile et cette ligne n'en tient aucune part.
        verdict = calibration_verdict(report)
        if verdict is not None and verdict["montrable"]:
            progression = calibration_progression(report)
            if progression is not None and progression["corrige"]:
                parts.append(f"calibration {progression['recent']['gap']:+.0%} (corrigee)")
            else:
                parts.append(f"calibration {verdict['gap']:+.0%}")
        return "SINGULAR · " + " · ".join(parts)

    #: The columns of `export_rows`, in order, so callers need not guess.
    #:
    #: La ligne d'en-tete etait recopiee a la main dans `python -m singular
    #: export` pour le cas du journal vide. Les colonnes `expected_gain_eur` et
    #: `reversibility` ont ete ajoutees ici et pas la : un journal vide
    #: exportait donc treize colonnes, un journal rempli quinze. Une feuille de
    #: calcul montee sur le premier decalait ses colonnes au premier export
    #: suivant.
    EXPORT_COLUMNS = (
        "entry_id", "created_at", "due_at", "tier", "title", "action", "predicted",
        "probability", "cost_hours", "expected_gain_eur", "reversibility", "status",
        "resolved_at", "brier_score", "lesson",
    )

    def export_rows(self) -> list[dict]:
        """Every entry, flat, for a spreadsheet or anything else."""
        return [
            {
                "entry_id": e.entry_id,
                "created_at": e.created_at,
                "due_at": e.due_at,
                "tier": e.tier.value,
                "title": e.title,
                "action": e.action,
                "predicted": e.predicted,
                "probability": e.probability,
                "cost_hours": e.cost_hours,
                "expected_gain_eur": "" if e.expected_gain_eur is None else e.expected_gain_eur,
                "reversibility": "" if e.reversibility is None else e.reversibility.value,
                "status": e.status.value,
                "resolved_at": e.resolved_at or "",
                "brier_score": "" if e.brier_score is None else e.brier_score,
                "lesson": e.lesson or "",
            }
            for e in self.entries()
        ]

    # --- the part that tells you something you did not know ------------------

    def review(self, *, now: datetime | None = None) -> dict:
        """Where your hours went, and where your confidence is wrong."""
        moment = now or datetime.now(UTC)
        all_entries = self.entries()
        resolved = [e for e in all_entries if e.status in (Status.HAPPENED, Status.DID_NOT_HAPPEN)]
        open_entries = [e for e in all_entries if e.is_open]
        abandoned = [e for e in all_entries if e.status is Status.ABANDONED]

        by_tier: dict[str, dict] = {}
        for tier in Tier:
            items = [e for e in all_entries if e.tier is tier]
            if not items:
                continue
            settled = [e for e in items if e.status in (Status.HAPPENED, Status.DID_NOT_HAPPEN)]
            worked = [e for e in settled if e.status is Status.HAPPENED]
            by_tier[tier.value] = {
                "rank": tier.rank,
                "decisions": len(items),
                "hours": round(sum(e.cost_hours for e in items), 1),
                "hours_that_worked": round(sum(e.cost_hours for e in worked), 1),
                "hours_unresolved": round(sum(e.cost_hours for e in items if e.is_open), 1),
                "hit_rate": round(len(worked) / len(settled), 2) if settled else None,
            }

        brier = [e.brier_score for e in resolved if e.brier_score is not None]
        mean_probability = sum(e.probability for e in resolved) / len(resolved) if resolved else None
        hit_rate = sum(1 for e in resolved if e.status is Status.HAPPENED) / len(resolved) if resolved else None

        return {
            "decisions": len(all_entries),
            "open": len(open_entries),
            "overdue": len(self.due(now=moment)),
            "abandoned": len(abandoned),
            "resolved": len(resolved),
            "hours_total": round(sum(e.cost_hours for e in all_entries), 1),
            "hours_unresolved": round(sum(e.cost_hours for e in open_entries), 1),
            "hours_that_worked": round(sum(e.cost_hours for e in resolved if e.status is Status.HAPPENED), 1),
            # Le raisonnement d'affaires, tel que la constitution le demande :
            # « Optimisation : options, levier, coût, vitesse, réversibilité. »
            # Le coût et la vitesse étaient là depuis le début ; ce qui suit
            # est ce qui manquait pour qu'une décision puisse être jugée sur
            # autre chose que le temps qu'elle prend.
            "gain_expected_total": round(
                sum(e.expected_gain_eur for e in all_entries if e.expected_gain_eur is not None), 2),
            "gain_expected_open": round(
                sum(e.expected_gain_eur for e in open_entries if e.expected_gain_eur is not None), 2),
            "hours_without_gain": round(
                sum(e.cost_hours for e in all_entries if e.expected_gain_eur is None), 1),
            "irreversible_open": sum(
                1 for e in open_entries if e.reversibility is Reversibility.IRREVERSIBLE),
            # Les probabilités annoncées sur ce qui a été tranché, dans l'ordre.
            # La Notice en a besoin pour répondre exactement à « est-ce que mes
            # 70 % arrivent 7 fois sur 10 ? » : la moyenne seule ne dit pas si
            # un écart vient du hasard, et c'est cette question-là que le
            # journal existe pour trancher.
            "resolved_probabilities": [e.probability for e in resolved],
            # Les mêmes verdicts, dans le même ordre, ramenés à « c'est arrivé
            # ou non ». La moyenne ne dit pas *quand* il s'est trompé : un écart
            # corrigé il y a deux mois pèse encore, à l'identique, dans le
            # chiffre d'aujourd'hui. Répondre à « est-ce que je m'améliore ? »
            # demande les résultats un par un, et l'ordre de ce journal est
            # celui de `created_at` -- l'instant où le jugement a été porté.
            "resolved_outcomes": [1 if e.status is Status.HAPPENED else 0 for e in resolved],
            "mean_brier": round(sum(brier) / len(brier), 4) if brier else None,
            "mean_probability": round(mean_probability, 2) if mean_probability is not None else None,
            "hit_rate": round(hit_rate, 2) if hit_rate is not None else None,
            # Une seule condition, et c'est celle qui decide. `mean_probability` et
            # `hit_rate` valent None exactement ensemble -- tous deux
            # `... if resolved else None` -- donc les tester l'un et l'autre
            # laissait croire que deux cas etaient couverts quand un seul l'est.
            # `gardes_sans_test.py` a nomme les deux moities le meme jour ou il a
            # appris a regarder dans les dictionnaires rendus.
            "overconfidence": round(mean_probability - hit_rate, 2) if resolved else None,
            "by_tier": by_tier,
            "chain_intact": self.verify(),
        }

    # --- plumbing ------------------------------------------------------------

    @staticmethod
    def _head(conn: sqlite3.Connection) -> str:
        row = conn.execute("SELECT fingerprint FROM journal_entries ORDER BY rowid DESC LIMIT 1").fetchone()
        return "" if row is None else row["fingerprint"]

    @staticmethod
    def _entry(row: sqlite3.Row) -> Entry:
        return Entry(
            row["entry_id"], row["title"], row["action"], row["predicted"], float(row["probability"]),
            Tier(row["tier"]), float(row["cost_hours"]), int(row["horizon_days"]), row["created_at"],
            row["due_at"], Status(row["status"]), row["resolved_at"], row["lesson"],
            None if row["brier_score"] is None else float(row["brier_score"]),
            row["previous_fingerprint"], row["fingerprint"],
            # Chaque colonne est gardee par sa presence, pas seulement la
            # derniere arrivee : en lecture seule on ne migre pas, donc une base
            # de trois mois arrive ici avec les colonnes de trois mois.
            _colonne(row, "expected_gain_eur", float),
            _colonne(row, "reversibility", Reversibility),
            _colonne(row, "imported_fingerprint"),
        )


__all__ = ["CALIBRATION_ARRONDI", "CALIBRATION_GAP", "CALIBRATION_HASARD", "CALIBRATION_MINIMUM",
           "DEFAULT_PATH", "SCHEMA_VERSION", "DecisionJournal", "Entry", "Reversibility",
           "Status", "Tier", "calibration_progression", "calibration_verdict",
           "chance_d_un_ecart_moindre", "chance_du_hasard"]
