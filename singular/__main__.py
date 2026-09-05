"""Command line for the decision journal.

    python -m singular add        record a decision before acting on it
    python -m singular due        decisions whose horizon has passed
    python -m singular resolve    record what actually happened
    python -m singular review     where your hours went, where you are wrong
    python -m singular list       everything

A tool that takes more than thirty seconds to use is a tool you stop using, so
`add` asks six questions and nothing else.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

from .journal import DEFAULT_PATH, DecisionJournal, Status, Tier

DIM = "\033[2m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
OFF = "\033[0m"


def _colour(text: str, code: str) -> str:
    return text if not sys.stdout.isatty() else f"{code}{text}{OFF}"


def _ask(prompt: str, *, cast=str, default=None, validate=None):
    while True:
        suffix = f" [{default}]" if default is not None else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw and default is not None:
            raw = str(default)
        try:
            value = cast(raw)
            if validate:
                validate(value)
            return value
        except (ValueError, KeyError) as exc:
            print(_colour(f"  {exc}", RED))


def _tier_prompt() -> Tier:
    print(_colour("\n  Quel rang de la constitution ? (Stabilité → Revenus → … → Liberté)", DIM))
    for tier in Tier:
        print(f"    {tier.rank}. {tier.value.title()}")
    index = _ask("  Rang", cast=int, default=2, validate=lambda v: None if 1 <= v <= len(Tier) else (_ for _ in ()).throw(ValueError("1 à 6")))
    return list(Tier)[index - 1]


def cmd_add(journal: DecisionJournal, args) -> int:
    if args.title:
        entry = journal.add(
            title=args.title, action=args.action, predicted=args.predicted,
            probability=args.probability, tier=Tier(args.tier.upper()),
            cost_hours=args.hours, horizon_days=args.days,
        )
    else:
        print(_colour("\nUne décision, avant de la prendre.\n", BOLD))
        title = _ask("  Décision (une ligne)")
        action = _ask("  Ce que tu vas faire concrètement")
        predicted = _ask("  Ce que tu attends comme résultat observable")
        probability = _ask("  Probabilité que ça arrive (0.05 à 0.95)", cast=float, default=0.6)
        tier = _tier_prompt()
        hours = _ask("  Heures que ça va te coûter", cast=float, default=4)
        days = _ask("  Dans combien de jours on vérifie", cast=int, default=14)
        entry = journal.add(title=title, action=action, predicted=predicted, probability=probability,
                            tier=tier, cost_hours=hours, horizon_days=days)

    due = datetime.fromisoformat(entry.due_at).strftime("%d/%m/%Y")
    print(f"\n  {_colour(entry.entry_id, BOLD)}  verdict attendu le {due}")
    print(_colour(f"  « {entry.predicted} » — tu dis {entry.probability:.0%}\n", DIM))
    return 0


def cmd_due(journal: DecisionJournal, args) -> int:
    pending = journal.due()
    if not pending:
        open_count = len(journal.entries(status=Status.OPEN))
        print(f"\n  Rien à trancher. {open_count} décision(s) encore dans les temps.\n")
        return 0
    print(_colour(f"\n  {len(pending)} décision(s) attendent un verdict\n", BOLD))
    for entry in pending:
        late = entry.overdue_days()
        marker = _colour(f"+{late}j", RED if late > 7 else YELLOW)
        print(f"  {_colour(entry.entry_id, BOLD)}  {marker:>12}  {entry.title}")
        print(_colour(f"      attendu : {entry.predicted}  ({entry.probability:.0%}, {entry.cost_hours:g}h, {entry.tier.value.lower()})", DIM))
    print(_colour(f"\n  python -m singular resolve {pending[0].entry_id} --yes|--no\n", DIM))
    return 0


def cmd_resolve(journal: DecisionJournal, args) -> int:
    if args.yes == args.no:
        print(_colour("  Précise --yes ou --no.", RED))
        return 2
    entry = journal.resolve(args.entry_id, happened=args.yes, lesson=args.lesson or "")
    verdict = _colour("ARRIVÉ", GREEN) if entry.status is Status.HAPPENED else _colour("PAS ARRIVÉ", RED)
    print(f"\n  {entry.entry_id}  {verdict}   tu disais {entry.probability:.0%}   Brier {entry.brier_score:.3f}")
    if entry.lesson:
        print(_colour(f"  {entry.lesson}\n", DIM))
    return 0


def cmd_abandon(journal: DecisionJournal, args) -> int:
    entry = journal.abandon(args.entry_id, reason=args.reason)
    print(f"\n  {entry.entry_id}  abandonné — {entry.lesson}\n")
    return 0


def cmd_list(journal: DecisionJournal, args) -> int:
    entries = journal.entries(status=Status(args.status.upper()) if args.status else None)
    if not entries:
        print("\n  Journal vide. `python -m singular add` pour commencer.\n")
        return 0
    print()
    for entry in entries:
        state = {
            Status.OPEN: _colour("ouvert", YELLOW),
            Status.HAPPENED: _colour("arrivé", GREEN),
            Status.DID_NOT_HAPPEN: _colour("échoué", RED),
            Status.ABANDONED: _colour("abandonné", DIM),
        }[entry.status]
        print(f"  {entry.entry_id}  {state:>18}  {entry.probability:.0%}  {entry.cost_hours:>5g}h  "
              f"{entry.tier.value.lower():<13} {entry.title}")
    print()
    return 0


def cmd_review(journal: DecisionJournal, args) -> int:
    report = journal.review()
    if not report["decisions"]:
        print("\n  Journal vide. `python -m singular add` pour commencer.\n")
        return 0

    print(_colour("\n  OÙ VONT TES HEURES\n", BOLD))
    print(f"  {report['decisions']} décisions   {report['hours_total']:g}h engagées")
    unresolved = report["hours_unresolved"]
    worked = report["hours_that_worked"]
    print(f"  {worked:g}h ont produit le résultat attendu")
    warn = RED if unresolved > worked else DIM
    print(_colour(f"  {unresolved:g}h encore sans verdict ({report['open']} ouvertes, {report['overdue']} en retard)", warn))

    if report["hit_rate"] is not None:
        print(_colour("\n  CE QUE TA CONFIANCE VAUT\n", BOLD))
        print(f"  tu prédis en moyenne {report['mean_probability']:.0%}   il arrive {report['hit_rate']:.0%}")
        gap = report["overconfidence"]
        if abs(gap) < 0.05:
            print(_colour("  calibration correcte", GREEN))
        elif gap > 0:
            print(_colour(f"  surconfiance de {gap:+.0%} — tu crois plus que ce qui arrive", RED))
        else:
            print(_colour(f"  sous-confiance de {gap:+.0%} — tu réussis plus que tu ne l'oses", YELLOW))
        print(_colour(f"  Brier moyen {report['mean_brier']:.3f}  (0 = parfait, 0.25 = pile ou face)", DIM))

    print(_colour("\n  PAR RANG DE LA CONSTITUTION\n", BOLD))
    print(_colour(f"  {'rang':<16}{'décisions':>10}{'heures':>9}{'ont marché':>12}{'sans verdict':>14}", DIM))
    for tier in Tier:
        stats = report["by_tier"].get(tier.value)
        if not stats:
            print(_colour(f"  {tier.value.lower():<16}{'—':>10}{'—':>9}{'—':>12}{'—':>14}", DIM))
            continue
        hit = f"{stats['hit_rate']:.0%}" if stats["hit_rate"] is not None else "—"
        line = (f"  {tier.value.lower():<16}{stats['decisions']:>10}{stats['hours']:>8g}h"
                f"{stats['hours_that_worked']:>11g}h{stats['hours_unresolved']:>13g}h   {hit}")
        print(line)

    empty_high = [t for t in list(Tier)[:2] if t.value not in report["by_tier"]]
    if empty_high:
        names = " et ".join(t.value.lower() for t in empty_high)
        print(_colour(f"\n  ⚠ Aucune décision sur {names} — les deux premiers rangs de ta hiérarchie.", RED))

    if not report["chain_intact"]:
        print(_colour("\n  ⚠ La chaîne du journal est rompue : une prédiction a été réécrite.", RED))
    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="singular", description="Journal de décisions : prédire, puis vérifier.")
    parser.add_argument("--db", default=str(DEFAULT_PATH), help=f"chemin de la base (défaut {DEFAULT_PATH})")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="enregistrer une décision avant d'agir")
    add.add_argument("--title"); add.add_argument("--action"); add.add_argument("--predicted")
    add.add_argument("--probability", type=float, default=0.6)
    add.add_argument("--tier", default="REVENUS", choices=[t.value for t in Tier] + [t.value.lower() for t in Tier])
    add.add_argument("--hours", type=float, default=4.0)
    add.add_argument("--days", type=int, default=14)
    add.set_defaults(func=cmd_add)

    due = sub.add_parser("due", help="décisions dont l'échéance est passée")
    due.set_defaults(func=cmd_due)

    resolve = sub.add_parser("resolve", help="enregistrer ce qui s'est réellement passé")
    resolve.add_argument("entry_id")
    resolve.add_argument("--yes", action="store_true"); resolve.add_argument("--no", action="store_true")
    resolve.add_argument("--lesson", default="")
    resolve.set_defaults(func=cmd_resolve)

    abandon = sub.add_parser("abandon", help="arrêter une décision, en le disant")
    abandon.add_argument("entry_id"); abandon.add_argument("reason")
    abandon.set_defaults(func=cmd_abandon)

    listing = sub.add_parser("list", help="tout le journal")
    listing.add_argument("--status", choices=[s.value.lower() for s in Status])
    listing.set_defaults(func=cmd_list)

    review = sub.add_parser("review", help="où vont tes heures, où ta confiance se trompe")
    review.set_defaults(func=cmd_review)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    journal = DecisionJournal(args.db)
    try:
        return args.func(journal, args)
    except (KeyError, PermissionError, ValueError) as exc:
        print(_colour(f"\n  {exc}\n", RED))
        return 1
    except (KeyboardInterrupt, EOFError):
        print()
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
