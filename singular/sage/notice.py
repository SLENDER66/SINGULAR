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

from ..journal import DecisionJournal, Entry, Status, Tier

#: Au-delà, un retard n'est plus un oubli : c'est une décision qu'on évite.
LATE_DAYS = 7

#: Écart de calibration à partir duquel il faut le dire. En deçà, le bruit
#: d'échantillon explique l'écart aussi bien que la surconfiance.
CALIBRATION_GAP = 0.15

#: Nombre de verdicts en dessous duquel une calibration ne veut rien dire.
CALIBRATION_MINIMUM = 3

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


def _foundation_item(report: dict[str, Any]) -> NoticeItem | None:
    """Les deux premiers rangs vides sont un défaut, même quand tout va bien.

    Sauf sur un journal vide, où ce serait dire deux fois la même chose : rien
    n'est renseigné nulle part, et `_empty_item` le dit déjà mieux.
    """
    if not report["decisions"]:
        return None
    missing = [tier for tier in FOUNDATION if tier.value not in report["by_tier"]]
    if not missing:
        return None
    names = " et ".join(tier.label for tier in missing)
    single = len(missing) == 1
    return NoticeItem(
        "ATTENTION",
        f"Aucune décision sur {names}",
        f"Ta constitution ouvre sur {' → '.join(tier.label for tier in FOUNDATION)}. "
        f"{'Ce rang' if single else 'Ces rangs'} {'n’a' if single else 'n’ont'} reçu aucune décision, "
        f"alors que {report['hours_total']:g}h sont allées ailleurs.",
        action="add",
    )


def _calibration_item(report: dict[str, Any]) -> NoticeItem | None:
    gap = report["overconfidence"]
    if gap is None or report["resolved"] < CALIBRATION_MINIMUM or abs(gap) < CALIBRATION_GAP:
        return None
    predicted = report["mean_probability"]
    happened = report["hit_rate"]
    if gap > 0:
        return NoticeItem(
            "ATTENTION",
            f"Tu te surestimes de {gap:+.0%}",
            f"Tu annonces {predicted:.0%} en moyenne ; il en arrive {happened:.0%}. "
            f"Sur {report['resolved']} verdicts, ce n'est plus de la malchance. "
            "Baisse tes probabilités d'autant, ou choisis des paris plus sûrs.",
        )
    return NoticeItem(
        "INFO",
        f"Tu te sous-estimes de {gap:+.0%}",
        f"Tu annonces {predicted:.0%} ; il en arrive {happened:.0%}. "
        "Tu réussis plus souvent que tu ne l'oses : tes paris sont trop petits.",
    )


def _unresolved_hours_item(report: dict[str, Any]) -> NoticeItem | None:
    """De l'activité qui ne s'est jamais transformée en résultat."""
    unresolved = report["hours_unresolved"]
    worked = report["hours_that_worked"]
    if not unresolved or unresolved <= worked:
        return None
    return NoticeItem(
        "ATTENTION" if worked == 0 else "INFO",
        f"{unresolved:g}h engagées sans verdict",
        f"Contre {worked:g}h qui ont produit ce que tu attendais. "
        "C'est la définition que ta constitution donne de confondre activité et résultat.",
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
    days = max((datetime.fromisoformat(nearest.due_at) - moment).days, 0)
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
        _empty_item(report),
        _foundation_item(report),
        _calibration_item(report),
        _unresolved_hours_item(report),
        _quiet_item(open_entries, moment),
    )
    items = tuple(item for item in candidates if item is not None)
    ordered = tuple(sorted(items, key=lambda item: item.rank))
    return Notice(
        headline=_headline(ordered),
        items=ordered,
        report=report,
        generated_at=moment.isoformat(),
    )


__all__ = ["CALIBRATION_GAP", "FOUNDATION", "LATE_DAYS", "Notice", "NoticeItem", "build_notice"]
