"""« Notice. » — ce que le Sage voit dans ton journal aujourd'hui.

Un rapport, pas une opinion. Chaque phrase produite ici est calculée à partir
d'entrées que tu as écrites toi-même : aucune n'est inventée, aucune n'est
adoucie, et rien n'a besoin d'un modèle de langage pour être vrai. C'est
volontaire. La facilité serait de faire commenter tes chiffres par un LLM ; tu
aurais alors un texte agréable dont tu ne pourrais pas vérifier une seule
affirmation. L'analyse en langage naturel viendra, et elle lira cette structure
plutôt que la base directement.

L'ordre des observations est celui de ta constitution, pas celui du confort :
une chaîne rompue passe avant un retard, un retard passe avant une statistique,
et l'absence de décision sur Stabilité et Revenus passe avant tout ce qui
concerne les rangs suivants.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..journal import DecisionJournal, Entry, Reversibility, Status, Tier

#: Au-delà, un retard n'est plus un oubli : c'est une décision qu'on évite.
LATE_DAYS = 7

#: Écart de calibration à partir duquel il faut le dire. En deçà, le bruit
#: d'échantillon explique l'écart aussi bien que la surconfiance.
CALIBRATION_GAP = 0.15

#: Nombre de verdicts en dessous duquel une calibration ne veut rien dire.
CALIBRATION_MINIMUM = 3

#: Au-delà de quelle rareté un écart cesse de s'expliquer par le hasard.
#: Une fois sur vingt : le seuil est conventionnel, il est écrit ici plutôt que
#: sous-entendu, et la phrase affichée donne la rareté réelle pour qu'on puisse
#: en juger autrement.
CALIBRATION_HASARD = 0.05

#: Les deux premiers rangs de la constitution. Les négliger est le seul défaut
#: que le Sage signale même quand tout le reste va bien.
FOUNDATION = (Tier.STABILITE, Tier.REVENUS)

SEVERITIES = ("CRITIQUE", "ATTENTION", "INFO")


@dataclass(frozen=True)
class NoticeItem:
    """Une observation, sa gravité, et ce qu'elle appelle comme geste."""

    severity: str
    title: str
    detail: str
    action: str | None = None
    entry_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"gravité inconnue : {self.severity}")
        if not self.title.strip():
            raise ValueError("une observation doit avoir un titre")

    @property
    def rank(self) -> int:
        return SEVERITIES.index(self.severity)

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "action": self.action,
            "entry_ids": list(self.entry_ids),
        }


@dataclass(frozen=True)
class Notice:
    """Le rapport du jour : une phrase d'en-tête, puis ce qui la justifie."""

    headline: str
    items: tuple[NoticeItem, ...]
    report: dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""
    #: `None` tant qu'il n'y a pas de quoi en parler. Voir `calibration_verdict`.
    calibration: dict[str, Any] | None = None

    @property
    def severity(self) -> str:
        return self.items[0].severity if self.items else "INFO"

    def as_dict(self) -> dict[str, Any]:
        return {
            "headline": self.headline,
            "severity": self.severity,
            "items": [item.as_dict() for item in self.items],
            "report": self.report,
            "generated_at": self.generated_at,
            "calibration": self.calibration,
        }


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _chain_item(report: dict[str, Any]) -> NoticeItem | None:
    if report["chain_intact"]:
        return None
    return NoticeItem(
        "CRITIQUE",
        "La chaîne du journal est rompue",
        "Une prédiction a été modifiée ou supprimée après coup. Tant que c'est vrai, "
        "aucune statistique de cette page ne vaut : elles portent sur un passé qui a été réécrit.",
        action="python -m singular export  puis compare avec ce que tu croyais avoir écrit",
    )


def _overdue_item(overdue: tuple[Entry, ...], moment: datetime) -> NoticeItem | None:
    if not overdue:
        return None
    # L'heure de référence est celle du rapport, pas celle de la machine : sans
    # ça, un aperçu daté d'un autre jour affichait « en retard de 0 jour ».
    worst = max(entry.overdue_days(moment) for entry in overdue)
    severity = "CRITIQUE" if worst > LATE_DAYS else "ATTENTION"
    single = len(overdue) == 1
    detail = (
        f"{_plural(len(overdue), 'décision a', 'décisions ont')} dépassé "
        f"{'son' if single else 'leur'} horizon. "
        + (
            f"{'Elle attend' if single else 'La plus ancienne attend'} un verdict depuis aujourd'hui."
            if worst == 0
            else f"{'Elle attend' if single else 'La plus ancienne attend'} "
                 f"depuis {worst} jour{'s' if worst > 1 else ''}."
        )
    )
    if worst > LATE_DAYS:
        detail += (
            " Passé une semaine, un verdict qu'on ne rend pas n'est plus un oubli : "
            "c'est le résultat qu'on préfère ne pas voir."
        )
    return NoticeItem(
        severity,
        "À trancher aujourd'hui",
        detail,
        action=f"resolve {overdue[0].entry_id}",
        entry_ids=tuple(entry.entry_id for entry in overdue),
    )


def foundation_item(report: dict[str, Any]) -> NoticeItem | None:
    """Un rang fondateur vide, dit quand c'en est un — et pas avant.

    Le lendemain de la première décision de Thomas, cette observation était la
    phrase d'en-tête du rapport : « Aucune décision sur Stabilité », en
    ATTENTION. Il avait écrit une ligne. Une ligne ne peut pas occuper deux
    rangs : le constat portait sur de l'arithmétique, pas sur une conduite, et
    aucun geste de sa part n'aurait pu l'éviter. C'est exactement le défaut
    déjà payé une fois sur `_unresolved_hours_item` — un reproche prématuré est
    un bug — laissé ici parce que la correction n'avait regardé qu'un endroit.

    Sa phrase était fausse en plus d'être prématurée. « 4h sont allées
    ailleurs » comptait `hours_total`, donc toutes les heures du journal, y
    compris les 4h posées sur Revenus — un rang de la fondation. Elle appelait
    « ailleurs » précisément l'endroit où elles étaient.

    Deux conditions, une par défaut. Autant de décisions que de rangs à
    couvrir : en dessous, le vide est une conséquence du compte, pas un choix.
    Et les heures nommées sont celles réellement passées hors fondation ; s'il
    n'y en a aucune, il reste un fait à savoir, pas un reproche à faire.
    """
    missing = [tier for tier in FOUNDATION if tier.value not in report["by_tier"]]
    if not missing or report["decisions"] < len(FOUNDATION):
        return None
    fondation = {tier.value for tier in FOUNDATION}
    elsewhere = round(sum(stats["hours"] for name, stats in report["by_tier"].items()
                          if name not in fondation), 1)
    names = " et ".join(tier.label for tier in missing)
    single = len(missing) == 1
    constat = (
        f"Ta constitution ouvre sur {' → '.join(tier.label for tier in FOUNDATION)}. "
        f"{'Ce rang' if single else 'Ces rangs'} {'n’a' if single else 'n’ont'} reçu aucune décision"
    )
    if not elsewhere:
        return NoticeItem("INFO", f"Aucune décision sur {names}", f"{constat}.", action="add")
    return NoticeItem(
        "ATTENTION",
        f"Aucune décision sur {names}",
        f"{constat}, alors que {elsewhere:g}h sont allées ailleurs.",
        action="add",
    )


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
    distribution = [1.0]
    for p in probabilities:
        suivante = [0.0] * (len(distribution) + 1)
        for reussites, poids in enumerate(distribution):
            suivante[reussites] += poids * (1.0 - p)
            suivante[reussites + 1] += poids * p
        distribution = suivante
    attendu = sum(probabilities)
    ecart = abs(hits - attendu)
    return sum(poids for reussites, poids in enumerate(distribution)
               if abs(reussites - attendu) >= ecart - 1e-9)


def _une_fois_sur(chance: float) -> str:
    """« une fois sur 6 » — le chiffre qu'on lit, pas une probabilité à traduire.

    « 0,038 » demande une conversion mentale avant de vouloir dire quelque
    chose, et ce rapport se lit d'un pouce, le matin. Au-delà du million, le
    compte exact n'apprend plus rien : il devient un nombre qu'on saute.
    """
    if chance <= 0 or 1 / chance > 1_000_000:
        return "moins d'une fois sur un million"
    sur = max(2, round(1 / chance))
    return f"une fois sur {sur:,}".replace(",", "\u202f")


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
        "conclusive": abs(gap) >= CALIBRATION_GAP and hasard <= CALIBRATION_HASARD,
    }


def _calibration_item(report: dict[str, Any]) -> NoticeItem | None:
    """L'écart entre ce qu'il annonce et ce qui arrive — sans conclure trop tôt.

    C'est la question pour laquelle ce journal existe : « est-ce que mes 70 %
    arrivent 7 fois sur 10 ? » Elle mérite donc d'être répondue exactement.

    Elle ne l'était pas. Dès trois verdicts, l'observation affirmait « ce n'est
    plus de la malchance » et enchaînait sur « baisse tes probabilités ». Sur
    trois verdicts à 75 %, n'en réussir qu'un arrive une fois sur six par pur
    hasard : l'outil conseillait de corriger un jugement que rien ne montrait
    faux, et corriger un jugement juste, c'est le dérégler.

    Deux états, donc, et la différence est dite plutôt que sous-entendue : en
    dessous de `CALIBRATION_CERTAIN` verdicts on montre l'écart et on dit qu'il
    est encore mince ; au-delà, on peut affirmer qu'il ne vient plus du hasard.
    """
    verdict = calibration_verdict(report)
    gap = report["overconfidence"]
    if verdict is None or abs(gap) < CALIBRATION_GAP:
        return None
    predicted = report["mean_probability"]
    happened = report["hit_rate"]
    verdicts = report["resolved"]
    hasard = verdict["chance"]
    constat = f"Tu annonces {predicted:.0%} en moyenne ; il en arrive {happened:.0%}."

    if not verdict["conclusive"]:
        return NoticeItem(
            "INFO",
            "Tu annonces plus que ce qui arrive" if gap > 0
            else "Il arrive plus que ce que tu annonces",
            f"{constat} Sur {verdicts} verdicts, un écart pareil sort du pur hasard "
            f"{_une_fois_sur(hasard)} : c'est encore trop peu pour en conclure quoi que "
            "ce soit. Regarde-le sans le corriger.",
        )

    if gap > 0:
        return NoticeItem(
            "ATTENTION",
            f"Tu te surestimes de {gap:+.0%}",
            f"{constat} Sur {verdicts} verdicts, ce n'est plus de la malchance : le "
            f"hasard seul produirait cet écart {_une_fois_sur(hasard)}. "
            "Baisse tes probabilités d'autant, ou choisis des paris plus sûrs.",
        )
    return NoticeItem(
        "INFO",
        f"Tu te sous-estimes de {gap:+.0%}",
        f"{constat} Sur {verdicts} verdicts, ce n'est plus de la malchance : le hasard "
        f"seul produirait cet écart {_une_fois_sur(hasard)}. Tu réussis plus souvent "
        "que tu ne l'oses, tes paris sont trop petits.",
    )


def _unresolved_hours_item(report: dict[str, Any]) -> NoticeItem | None:
    """De l'activité qui ne s'est jamais transformée en résultat.

    Le reproche n'a de sens qu'une fois qu'un verdict a été rendu. Sur un
    journal neuf il se déclenchait dès la première décision : quatre heures
    engagées, zéro heure qui a produit, donc « tu confonds activité et
    résultat » — alors que l'échéance tombait dans treize jours et que rien
    n'aurait pu être tranché. C'était factuellement faux, impossible à éviter,
    et adressé à quelqu'un qui venait d'écrire sa première ligne.

    « Contre 0h qui ont produit ce que tu attendais » compare à un ensemble
    vide tant que rien n'a été tranché. On attend donc d'avoir de quoi
    comparer.
    """
    unresolved = report["hours_unresolved"]
    worked = report["hours_that_worked"]
    if not report["resolved"] or not unresolved or unresolved <= worked:
        return None
    return NoticeItem(
        "ATTENTION" if worked == 0 else "INFO",
        f"{unresolved:g}h engagées sans verdict",
        f"Contre {worked:g}h qui ont produit ce que tu attendais. "
        "C'est ce que ce rapport appelle confondre activité et résultat : ta "
        "constitution nomme le piège dans sa mission, elle ne le mesure pas — la "
        "mesure est celle-ci, et elle vaut ce que vaut ce rapport.",
    )


def _empty_item(report: dict[str, Any]) -> NoticeItem | None:
    if report["decisions"]:
        return None
    return NoticeItem(
        "ATTENTION",
        "Le journal est vide",
        "Je ne peux rien t'apprendre sur toi tant que tu n'as rien prédit. "
        "La première décision est la seule qui demande un effort ; ensuite c'est trente secondes.",
        action="add",
    )


def _quiet_item(open_entries: tuple[Entry, ...], moment: datetime) -> NoticeItem | None:
    if not open_entries:
        return None
    nearest = min(open_entries, key=lambda entry: entry.due_at)
    # En jours de calendrier, comme l'horizon : voir `Entry.due_on`.
    days = nearest.days_until_due(moment)
    when = "aujourd'hui" if days == 0 else f"dans {days} jour{'s' if days > 1 else ''}"
    return NoticeItem(
        "INFO",
        _plural(len(open_entries), "décision ouverte", "décisions ouvertes"),
        f"La prochaine échéance tombe {when} : "
        f"« {nearest.predicted} », que tu donnes à {nearest.probability:.0%}.",
        entry_ids=(nearest.entry_id,),
    )


def _headline(items: tuple[NoticeItem, ...]) -> str:
    """Une seule phrase : la chose qui compte le plus aujourd'hui."""
    if not items:
        return "Notice. Rien ne demande ton attention aujourd'hui."
    return f"Notice. {items[0].title}."


#: Au-delà, des heures non chiffrées ne sont plus un oubli ponctuel : c'est une
#: façon de travailler qui ne dit jamais si le travail rapporte quelque chose.
#: Le seuil est volontairement haut -- le reproche doit être rare pour être lu.
UNPRICED_HOURS = 20.0


def _irreversible_item(overdue: tuple[Entry, ...], open_entries: tuple[Entry, ...]) -> NoticeItem | None:
    """L'application de « HALT » de la constitution, enfin possible.

    Une décision irréversible dont on ne rend pas le verdict est le pire cas du
    journal : l'engagement est pris, et on ne regarde pas s'il a servi. Toutes
    les autres observations portent sur du temps qu'on peut encore réaffecter ;
    celle-ci porte sur du temps qu'on ne peut plus.
    """
    engagees = tuple(e for e in overdue + open_entries
                     if e.reversibility is Reversibility.IRREVERSIBLE)
    if not engagees:
        return None

    en_retard = tuple(e for e in engagees if e in overdue)
    if en_retard:
        return NoticeItem(
            "CRITIQUE",
            f"{_plural(len(en_retard), 'engagement irréversible', 'engagements irréversibles')}"
            " sans verdict",
            "Tu as pris une décision sur laquelle tu ne peux pas revenir, et son horizon est "
            "passé sans que tu dises ce qu'elle a donné. C'est le seul cas où ne pas trancher "
            "coûte deux fois : l'engagement est déjà payé, et tu n'en tires même pas la leçon.",
            action="Rends le verdict maintenant, même s'il est mauvais.",
            entry_ids=tuple(e.entry_id for e in en_retard),
        )
    return NoticeItem(
        "ATTENTION",
        f"{_plural(len(engagees), 'engagement irréversible', 'engagements irréversibles')} en cours",
        "Rien à corriger aujourd'hui : c'est là pour rester sous les yeux. "
        "Ce qui est irréversible ne se rattrape pas au moment où l'on s'en aperçoit.",
        entry_ids=tuple(e.entry_id for e in engagees),
    )


def _unpriced_item(report: dict[str, Any]) -> NoticeItem | None:
    """Des heures dont personne n'a estimé le rendement.

    « Non chiffré » n'est pas « ne rapporte rien » : le journal garde la
    différence, et c'est justement elle qui se reproche. Un gain estimé faux
    s'apprend en le comparant au résultat ; un gain jamais estimé ne s'apprend
    pas du tout.
    """
    heures = report["hours_without_gain"]
    if heures < UNPRICED_HOURS:
        return None
    part = heures / report["hours_total"] if report["hours_total"] else 0
    return NoticeItem(
        "INFO",
        f"{heures:g} h engagées sans gain attendu",
        f"Soit {part:.0%} de tes heures. La constitution demande de juger une décision sur "
        "son levier et son coût ; sans estimation de ce qu'elle rapporte, il ne reste que le "
        "coût, et tout finit par se valoir.",
        action="Au prochain enregistrement, mets un ordre de grandeur même approximatif.",
    )


def build_notice(journal: DecisionJournal, *, now: datetime | None = None) -> Notice:
    """Ce que le Sage a à te dire, dans l'ordre où ça compte.

    Chaque observation est un fait tiré du journal. L'ordre est fixé par la
    gravité puis par l'ordre de construction, qui est celui de la constitution :
    intégrité, puis ce qui attend un verdict, puis les rangs fondateurs, puis ce
    que vaut ta confiance.
    """
    moment = now or datetime.now(UTC)
    report = journal.review(now=moment)
    overdue = journal.due(now=moment)
    open_entries = tuple(entry for entry in journal.entries(status=Status.OPEN) if entry not in overdue)

    candidates = (
        _chain_item(report),
        _overdue_item(overdue, moment),
        _irreversible_item(overdue, open_entries),
        _empty_item(report),
        foundation_item(report),
        _calibration_item(report),
        _unresolved_hours_item(report),
        _unpriced_item(report),
        _quiet_item(open_entries, moment),
    )
    items = tuple(item for item in candidates if item is not None)
    ordered = tuple(sorted(items, key=lambda item: item.rank))
    return Notice(
        headline=_headline(ordered),
        items=ordered,
        report=report,
        generated_at=moment.isoformat(),
        calibration=calibration_verdict(report),
    )


__all__ = ["CALIBRATION_GAP", "CALIBRATION_HASARD", "FOUNDATION", "LATE_DAYS", "UNPRICED_HOURS", "foundation_item",
           "Notice", "NoticeItem", "build_notice", "calibration_verdict", "chance_du_hasard"]
