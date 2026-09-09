"""Command line for the decision journal.

    python -m singular add        record a decision before acting on it
    python -m singular due        decisions whose horizon has passed
    python -m singular resolve    record what actually happened
    python -m singular review     where your hours went, where you are wrong
    python -m singular list       everything
    python -m singular sage       the same journal as an app, installable on a phone

A tool that takes more than thirty seconds to use is a tool you stop using, so
`add` asks six questions and nothing else.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime

from .journal import DEFAULT_PATH, DecisionJournal, Reversibility, Status, Tier
from .saisie import entier as _entier
from .saisie import nombre as _nombre
from .saisie import verifie_gain as _verifie_gain
from .saisie import verifie_heures as _verifie_heures
from .saisie import verifie_jours as _verifie_jours
from .saisie import verifie_probabilite as _verifie_probabilite
from .sage import notice as _notice
from .sage.notice import calibration_verdict, foundation_item

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
    print(_colour("\n  Quel rang de la constitution ? (Stabilité > Revenus > ... > Liberté)", DIM))
    for tier in Tier:
        print(f"    {tier.rank}. {tier.value.title()}")
    index = _ask("  Rang", cast=int, default=2, validate=lambda v: None if 1 <= v <= len(Tier) else (_ for _ in ()).throw(ValueError("1 à 6")))
    return list(Tier)[index - 1]


#: Ce que la constitution appelle « réversibilité ». Le mot est abstrait ; la
#: question qu'il faut réellement se poser ne l'est pas, alors c'est elle qu'on
#: pose.
REVERSIBILITES = (
    (Reversibility.REVERSIBLE, "je peux annuler sans que ça coûte"),
    (Reversibility.COUTEUSE, "je peux revenir en arrière, mais ça se paie"),
    (Reversibility.IRREVERSIBLE, "c'est fait, on ne revient pas dessus"),
)


def _reversibility_prompt() -> Reversibility | None:
    print(_colour("\n  Si tu te trompes, tu peux revenir en arrière ?", DIM))
    for numero, (_, phrase) in enumerate(REVERSIBILITES, start=1):
        print(f"    {numero}. {phrase}")
    print(_colour("    0. je ne sais pas encore", DIM))
    index = _ask(
        "  Réponse", cast=int, default=1,
        validate=lambda v: None if 0 <= v <= len(REVERSIBILITES)
        else (_ for _ in ()).throw(ValueError("0 à 3")),
    )
    return None if index == 0 else REVERSIBILITES[index - 1][0]


def _gain_prompt() -> float | None:
    """Facultatif, et il doit le rester.

    Exiger un chiffre ferait enregistrer moins de décisions, et une décision
    non écrite est pire qu'une décision sans chiffre. Ne rien répondre laisse
    « non chiffré », que la Notice sait reprocher -- ce qui n'est pas la même
    chose qu'un gain de zéro.
    """
    print(_colour("\n  Ce que ça rapporte si ça marche, en euros. Vide si tu ne sais pas.", DIM))
    brut = input(_colour("  Gain attendu ", BOLD)).strip()
    if not brut:
        return None
    try:
        # `_nombre` et pas un nettoyage de plus : la virgule et les espaces se
        # lisent partout de la même façon, sinon « 1 500 » passe à une question
        # et échoue à la suivante.
        valeur = _nombre(brut)
    except ValueError:
        print(_colour("  Pas un nombre : laissé non chiffré.", RED))
        return None
    try:
        _verifie_gain(valeur)
    except ValueError as refus:
        print(_colour(f"  {refus} : laisse non chiffre.", RED))
        return None
    return valeur


def cmd_parle(journal: DecisionJournal, args) -> int:
    """Une conversation, pas un rapport. Le fil survit entre deux lancements.

    Elle n'écrit rien dans le journal : c'est `add` qui enregistre, et c'est
    volontaire. Un système qui inscrit des décisions parce qu'on en a parlé
    finit par contenir des choses que personne n'a décidées.
    """
    from .analyse import AnalyseIndisponible, contexte_pour_analyse
    from .parle import (
        FICHIER_TARIFS,
        apercu,
        modele_de_tarifs,
        MODELE_PAR_DEFAUT,
        Conversation,
        Quota,
        bilan,
        phrase_de_bilan,
        repondre,
    )
    from .sage.notice import build_notice

    if args.tarifs:
        # Aucun prix n'est ecrit dans ce depot : ils changent, et un chiffre
        # faux ici servirait a decider quand s'arreter. Les siens, releves sur
        # la console, sont les seuls justes.
        print(_colour(f"\n  Colle ceci dans {FICHIER_TARIFS}, avec tes chiffres :\n", BOLD))
        print(modele_de_tarifs())
        print(_colour("  Les prix sont sur console.anthropic.com, en dollars par"
                      " million de jetons.\n", DIM))
        return 0

    fil = Conversation()
    if args.oubli:
        fil.oublier()
        print(_colour("\n  Fil effacé. Le journal, lui, n'a pas bougé.\n", DIM))
        if not args.question:
            return 0

    contexte = contexte_pour_analyse(build_notice(journal).as_dict())

    if args.blanc:
        # `analyse` et `offres` ont leur `--blanc` depuis le debut ; la
        # conversation ne l'avait pas, alors que c'est elle qui envoie le plus
        # -- le rapport du jour et tout le fil -- et depuis son telephone.
        print(_colour("\n  Ce qui serait envoye, et rien d'autre :\n", BOLD))
        print(apercu(contexte, fil, args.question or "<ta question>"))
        print(_colour("\n  Rien n'a ete envoye.\n", DIM))
        return 0

    def un_tour(question: str) -> bool:
        try:
            texte, cout = repondre(question, contexte, fil, modele=args.modele)
        except AnalyseIndisponible as exc:
            print(_colour(f"\n  {exc}\n", DIM))
            return False
        fil.sauver()
        # Le clavier n'a pas de plafond -- une commande se tape, un bouton se
        # tapote -- mais la depense se compte partout, sinon le total affiché
        # sur le téléphone serait faux de tout ce qui a été dit ici.
        #
        # `ajouter_depense` et pas `consommer` : passer par le second faisait
        # manger au clavier le plafond du téléphone, qui lit le même fichier.
        Quota().ajouter_depense(cout=cout, modele=args.modele or MODELE_PAR_DEFAUT)
        print(f"\n{texte}\n")
        # Le cout de chaque tour, sous les yeux : une conversation renvoie tout
        # son historique, et sans ce chiffre on ne voit pas la facture monter.
        economise = f", {cout['cache_lu']} relus du cache" if cout["cache_lu"] else ""
        print(_colour(f"  [{cout['entree']} jetons envoyés{economise},"
                      f" {cout['sortie']} rendus] {phrase_de_bilan(bilan())}\n", DIM))
        return True

    if args.question:
        return 0 if un_tour(args.question) else 1

    print(_colour("\n  Parle. Ligne vide ou Ctrl+C pour sortir.\n", BOLD))
    while True:
        try:
            question = input(_colour("  > ", BOLD)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not question:
            print()
            return 0
        un_tour(question)


def cmd_offres(journal: DecisionJournal, args) -> int:
    """Le premier agent : il cherche, il ecarte, il propose. Tu decides.

    Il ne touche pas au journal -- il ne l'importe meme pas. Ce qu'il rend est
    du texte, et rien d'autre ne se produit tant que tu n'as rien fait.
    """
    from .analyse import AnalyseIndisponible
    from .offres import MODELE_PAR_DEFAUT, RECHERCHES_MAX, apercu, chercher
    from .parle import Quota, bilan, phrase_de_bilan

    if args.blanc:
        print(_colour("\n  Ce qui serait envoye, et rien d'autre :\n", BOLD))
        print(apercu(args.precision))
        print(_colour(f"\n  Rien n'a ete envoye. Jusqu'a {RECHERCHES_MAX} recherches web"
                      " seraient faites.\n", DIM))
        return 0

    print(_colour("\n  Recherche en cours. Quelques dizaines de secondes.\n", DIM))
    try:
        texte, cout = chercher(args.precision, modele=args.modele)
    except AnalyseIndisponible as exc:
        print(_colour(f"\n  Recherche impossible : {exc}\n", DIM))
        return 1

    # Meme raison que pour un tour de conversation : la depense se compte
    # partout, sinon le total affiche sur le telephone est faux de tout ce qui
    # a ete cherche ici. `ajouter_depense` et pas `consommer` -- le clavier ne
    # mange pas le plafond du telephone.
    Quota().ajouter_depense(cout=cout, modele=args.modele or MODELE_PAR_DEFAUT)

    print(texte)
    economise = f", {cout['cache_lu']} relus du cache" if cout["cache_lu"] else ""
    print(_colour(f"\n  [{cout['entree']} jetons envoyes{economise},"
                  f" {cout['sortie']} rendus] {phrase_de_bilan(bilan())}", DIM))
    print(_colour("  Rien n'a ete envoye a personne. A toi de decider.\n", DIM))
    return 0


def cmd_analyse(journal: DecisionJournal, args) -> int:
    """La seule commande qui coûte de l'argent, et la seule qui peut être coupée.

    Elle appelle un modèle. Tout le reste de cet outil marche sans, et doit
    continuer à marcher sans : c'est pour ça que l'échec ici s'affiche comme
    un fait et rend 1, au lieu de remonter une trace de pile.
    """
    from .analyse import MODELE_PAR_DEFAUT, AnalyseIndisponible, analyser, apercu
    from .parle import Quota, bilan, phrase_de_bilan
    from .sage.notice import build_notice

    notice = build_notice(journal).as_dict()

    if args.blanc:
        print(_colour("\n  Ce qui serait envoye, et rien d'autre :\n", BOLD))
        print(apercu(notice))
        print(_colour("\n  Rien n'a ete envoye.\n", DIM))
        return 0

    try:
        texte, cout = analyser(notice, modele=args.modele)
    except AnalyseIndisponible as exc:
        print(_colour(f"\n  Analyse coupee : {exc}", DIM))
        print(_colour("  La Notice ci-dessous est calculee sans elle.\n", DIM))
        print(_colour(f"  {notice['headline']}", BOLD))
        for item in notice["items"]:
            print(f"  [{item['severity']}] {item['title']}")
        print()
        return 1

    # Meme raison que pour un tour de conversation et pour une recherche : ce
    # qui n'est pas compte ne se voit pas sur le budget. Cette commande
    # depensait sans que rien ne l'enregistre.
    Quota().ajouter_depense(cout=cout, modele=args.modele or MODELE_PAR_DEFAUT)

    print(_colour(f"\n  {notice['headline']}\n", BOLD))
    print(texte)
    economise = f", {cout['cache_lu']} relus du cache" if cout["cache_lu"] else ""
    print(_colour(f"\n  [{cout['entree']} jetons envoyes{economise},"
                  f" {cout['sortie']} rendus] {phrase_de_bilan(bilan())}\n", DIM))
    return 0


def cmd_add(journal: DecisionJournal, args) -> int:
    if args.title:
        entry = journal.add(
            title=args.title, action=args.action, predicted=args.predicted,
            probability=args.probability, tier=Tier(args.tier.upper()),
            cost_hours=args.hours, horizon_days=args.days,
            expected_gain_eur=args.gain,
            reversibility=None if args.reversibility is None
            else Reversibility(args.reversibility.upper()),
        )
    else:
        print(_colour("\nUne décision, avant de la prendre.\n", BOLD))
        title = _ask("  Décision (une ligne)")
        action = _ask("  Ce que tu vas faire concrètement")
        predicted = _ask("  Ce que tu attends comme résultat observable")
        probability = _ask("  Probabilité que ça arrive (0.05 à 0.95)", cast=_nombre,
                           default=0.6, validate=_verifie_probabilite)
        tier = _tier_prompt()
        hours = _ask("  Heures que ça va te coûter", cast=_nombre, default=4,
                     validate=_verifie_heures)
        days = _ask("  Dans combien de jours on vérifie", cast=_entier, default=14,
                    validate=_verifie_jours)
        gain = _gain_prompt()
        reversibility = _reversibility_prompt()
        entry = journal.add(title=title, action=action, predicted=predicted, probability=probability,
                            tier=tier, cost_hours=hours, horizon_days=days,
                            expected_gain_eur=gain, reversibility=reversibility)

    due = datetime.fromisoformat(entry.due_at).strftime("%d/%m/%Y")
    print(f"\n  {_colour(entry.entry_id, BOLD)}  verdict attendu le {due}")
    print(_colour(f"  « {entry.predicted} » - tu dis {entry.probability:.0%}\n", DIM))
    return 0


#: A cold application that gets an interview is roughly one in six. Starting
#: from an honest base rate is the point: it is the first thing your own record
#: will correct.
DEFAULT_APPLICATION_ODDS = 0.15


def cmd_apply(journal: DecisionJournal, args) -> int:
    """The fastest path in the tool, because it is the one you use most.

    An application is a decision with a predicted outcome like any other. The
    outcome recorded is an interview, not a reply: a rejection is an answer, not
    the result you were after, and scoring yourself on replies would let you feel
    productive while nothing moves.
    """
    entry = journal.add(
        title=f"{args.company} - {args.role}",
        action=args.action or "candidature envoyée",
        predicted=f"entretien décroché sous {args.days} jours",
        probability=args.probability,
        tier=Tier(args.tier.upper()),
        cost_hours=args.hours,
        horizon_days=args.days,
    )
    due = datetime.fromisoformat(entry.due_at).strftime("%d/%m")
    print(f"  {_colour(entry.entry_id, BOLD)}  {entry.title}   {entry.probability:.0%}  verdict le {due}")
    return 0


def _vide(journal: DecisionJournal) -> str:
    """« Journal vide », plus l'endroit où l'on a regardé.

    Un journal vide et un mauvais journal donnent exactement le même écran.
    Depuis que le coeur tourne sans rien installer, la même personne peut en
    ouvrir un sur son PC et un autre sur son téléphone, et les deux
    divergeraient en silence -- chacun ayant l'air simplement neuf. Dire où
    l'on a cherché coûte une ligne et rend la confusion impossible à rater.
    """
    return (f"\n  Journal vide : {journal.path}\n"
            "  `python -m singular add` pour commencer.\n")


def cmd_status(journal: DecisionJournal, args) -> int:
    """One line, for your shell profile."""
    print(journal.summary_line())
    return 0


def cmd_export(journal: DecisionJournal, args) -> int:
    rows = journal.export_rows()
    if not rows:
        print("entry_id,created_at,due_at,tier,title,action,predicted,probability,cost_hours,status,resolved_at,brier_score,lesson")
        return 0
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
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
        # Le rouge dit la même chose que le CRITIQUE du rapport : au-delà de
        # LATE_DAYS, un verdict qu'on ne rend pas n'est plus un oubli. Le seuil
        # se lit dans le moteur, il ne se recopie pas ici.
        marker = _colour(f"+{late}j", RED if late > _notice.LATE_DAYS else YELLOW)
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
    print(f"\n  {entry.entry_id}  abandonné - {entry.lesson}\n")
    return 0


def cmd_list(journal: DecisionJournal, args) -> int:
    entries = journal.entries(status=Status(args.status.upper()) if args.status else None)
    if not entries:
        print(_vide(journal))
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


def cmd_sage(journal: DecisionJournal, args) -> int:
    """Le même journal, en app, ouvrable depuis le téléphone.

    Importé ici et pas en tête de fichier : les commandes du terminal ne doivent
    rien payer pour un serveur qu'elles n'utilisent pas.
    """
    from .sage.server import serve

    return serve(db=args.db, host=args.host, port=args.port, lan=args.lan)


def cmd_review(journal: DecisionJournal, args) -> int:
    report = journal.review()
    if not report["decisions"]:
        print(_vide(journal))
        return 0

    print(_colour("\n  OÙ VONT TES HEURES\n", BOLD))
    print(f"  {report['decisions']} décisions   {report['hours_total']:g}h engagées")
    unresolved = report["hours_unresolved"]
    worked = report["hours_that_worked"]
    print(f"  {worked:g}h ont produit le résultat attendu")
    # Même garde que la Notice et que la vignette de l'app : s'alarmer d'heures
    # sans verdict n'a de sens qu'une fois qu'un verdict a pu être rendu.
    # Cette ligne-ci ne l'avait pas et passait au rouge dès la première
    # décision, dont l'échéance était dans deux semaines.
    warn = RED if report["resolved"] and unresolved > worked else DIM
    print(_colour(f"  {unresolved:g}h encore sans verdict ({report['open']} ouvertes, {report['overdue']} en retard)", warn))

    if report["hit_rate"] is not None:
        print(_colour("\n  CE QUE TA CONFIANCE VAUT\n", BOLD))
        print(f"  tu prédis en moyenne {report['mean_probability']:.0%}   il arrive {report['hit_rate']:.0%}")
        # Le verdict vient du moteur. Cette ligne tenait sa propre regle -- un
        # seuil de 5 %, sans minimum de verdicts -- et imprimait donc en rouge
        # « surconfiance de +75 % - tu crois plus que ce qui arrive » apres un
        # seul verdict. Un jugement corrige sur une observation, c'est un
        # jugement deregle.
        gap = report["overconfidence"]
        verdict = calibration_verdict(report)
        if verdict is None or not verdict["conclusive"]:
            print(_colour(f"  ecart de {gap:+.0%} sur {report['resolved']} verdict"
                          f"{'s' if report['resolved'] > 1 else ''}"
                          " - le hasard seul en produit autant, rien a conclure", DIM))
        elif gap > 0:
            print(_colour(f"  surconfiance de {gap:+.0%} - tu crois plus que ce qui arrive", RED))
        else:
            print(_colour(f"  sous-confiance de {gap:+.0%} - tu réussis plus que tu ne l'oses", YELLOW))
        print(_colour(f"  Brier moyen {report['mean_brier']:.3f}  (0 = parfait, 0.25 = pile ou face)", DIM))

    print(_colour("\n  PAR RANG DE LA CONSTITUTION\n", BOLD))
    print(_colour(f"  {'rang':<16}{'décisions':>10}{'heures':>9}{'ont marché':>12}{'sans verdict':>14}", DIM))
    for tier in Tier:
        stats = report["by_tier"].get(tier.value)
        if not stats:
            print(_colour(f"  {tier.value.lower():<16}{'-':>10}{'-':>9}{'-':>12}{'-':>14}", DIM))
            continue
        hit = f"{stats['hit_rate']:.0%}" if stats["hit_rate"] is not None else "-"
        line = (f"  {tier.value.lower():<16}{stats['decisions']:>10}{stats['hours']:>8g}h"
                f"{stats['hours_that_worked']:>11g}h{stats['hours_unresolved']:>13g}h   {hit}")
        print(line)

    # La règle vient de la Notice, elle ne se réécrit pas ici. Cette ligne
    # portait sa propre version -- `list(Tier)[:2]`, reproche dès la première
    # décision -- et c'était la troisième fois que le même défaut se payait :
    # d'abord « heures engagées sans verdict », puis le même constat dans la
    # Notice, puis celui-ci. Une règle recopiée est une règle qui divergera ;
    # `test_reproche_premature.py` interdit désormais qu'elle vive à deux endroits.
    fondation = foundation_item(report)
    if fondation is not None:
        print(_colour(f"\n  /!\\ {fondation.title} - {fondation.detail}",
                      RED if fondation.severity == "ATTENTION" else DIM))

    if not report["chain_intact"]:
        print(_colour("\n  /!\\ La chaîne du journal est rompue : une prédiction a été réécrite.", RED))
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
    add.add_argument("--gain", type=float, default=None, help="gain attendu en euros")
    add.add_argument("--reversibility", default=None,
                     choices=[r.value for r in Reversibility] + [r.value.lower() for r in Reversibility])
    add.set_defaults(func=cmd_add)

    apply = sub.add_parser("apply", help="enregistrer une candidature (chemin rapide)")
    apply.add_argument("company"); apply.add_argument("role")
    apply.add_argument("--probability", type=float, default=DEFAULT_APPLICATION_ODDS)
    apply.add_argument("--days", type=int, default=21)
    apply.add_argument("--hours", type=float, default=1.5)
    apply.add_argument("--tier", default="STABILITE", choices=[t.value for t in Tier] + [t.value.lower() for t in Tier])
    apply.add_argument("--action", default="")
    apply.set_defaults(func=cmd_apply)

    status = sub.add_parser("status", help="une ligne, pour ton shell")
    status.set_defaults(func=cmd_status)

    export = sub.add_parser("export", help="tout le journal en CSV sur la sortie standard")
    export.set_defaults(func=cmd_export)

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

    sage = sub.add_parser("sage", help="ouvrir le Sage, l'app à installer sur ton téléphone")
    sage.add_argument("--port", type=int, default=8765)
    sage.add_argument("--host", default="127.0.0.1", help="ignoré avec --lan")
    sage.add_argument("--lan", action="store_true",
                      help="rendre l'app joignable depuis ton téléphone sur le même wifi")
    sage.set_defaults(func=cmd_sage)

    analyse = sub.add_parser("analyse", help="faire commenter la Notice par un modele (consomme des jetons)")
    analyse.add_argument("--blanc", action="store_true",
                         help="afficher ce qui serait envoye, sans rien envoyer")
    analyse.add_argument("--modele", default=None)
    analyse.set_defaults(func=cmd_analyse)

    offres = sub.add_parser("offres", help="chercher des offres d'emploi (consomme des jetons)")
    offres.add_argument("--blanc", action="store_true",
                        help="afficher ce qui serait envoye, sans rien envoyer")
    offres.add_argument("--modele", default=None)
    offres.add_argument("precision", nargs="?", default="",
                        help="une precision pour cette recherche, facultative")
    offres.set_defaults(func=cmd_offres)

    parle = sub.add_parser("parle", help="une conversation qui connait ton journal")
    parle.add_argument("question", nargs="?", default="")
    parle.add_argument("--oubli", action="store_true", help="effacer le fil et repartir a zero")
    parle.add_argument("--modele", default=None)
    parle.add_argument("--blanc", action="store_true",
                       help="montre ce qui partirait, n'envoie rien")
    parle.add_argument("--tarifs", action="store_true",
                       help="afficher le fichier de tarifs a remplir")
    parle.set_defaults(func=cmd_parle)
    return parser


def _survive_narrow_consoles() -> None:
    """Ne jamais planter parce qu'un caractère ne rentre pas dans la console.

    La console de Windows écrit dans la page de code du système -- cp850 en
    France -- et Python lève `UnicodeEncodeError` sur ce qu'elle ne sait pas
    représenter. Cela suffit à interrompre une commande au moment d'afficher
    son résultat.

    Les messages de ce fichier sont tenus dans ce que cp850 accepte, et un
    test le vérifie. Mais le journal contient tes mots, pas les miens : un
    titre avec un emoji, une leçon copiée-collée d'ailleurs, et l'affichage
    casse alors que l'écriture avait réussi. Remplacer un caractère par un
    point d'interrogation est une gêne ; perdre la commande n'en est pas une.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="replace")
        except (OSError, ValueError):  # flux redirigé qui n'accepte pas d'être reconfiguré
            pass


def main(argv: list[str] | None = None) -> int:
    _survive_narrow_consoles()
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
