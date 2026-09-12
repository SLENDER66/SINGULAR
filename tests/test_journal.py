"""The journal must be usable, honest, and impossible to quietly rewrite."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from singular.journal import DecisionJournal, Status, Tier

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def _journal(tmp_path):
    return DecisionJournal(tmp_path / "journal.db")


def _add(journal, *, probability=0.6, tier=Tier.REVENUS, hours=4.0, days=14, now=NOW, title="Une décision"):
    return journal.add(title=title, action="faire la chose", predicted="le résultat observable",
                       probability=probability, tier=tier, cost_hours=hours, horizon_days=days, now=now)


# --- a prediction has to be checkable ----------------------------------------

@pytest.mark.parametrize("probability", [0.0, 1.0, -0.1, 1.5])
def test_certainty_is_not_a_forecast(tmp_path, probability):
    with pytest.raises(ValueError, match="certainty is not a forecast"):
        _add(_journal(tmp_path), probability=probability)


def test_a_decision_needs_a_horizon(tmp_path):
    with pytest.raises(ValueError, match="horizon"):
        _add(_journal(tmp_path), days=0)


def test_non_finite_inputs_are_refused(tmp_path):
    with pytest.raises(ValueError, match="must be finite"):
        _add(_journal(tmp_path), probability=float("nan"))
    with pytest.raises(ValueError, match="must be finite"):
        _add(_journal(tmp_path), hours=float("inf"))


def test_an_entry_without_a_predicted_outcome_is_refused(tmp_path):
    journal = _journal(tmp_path)
    with pytest.raises(ValueError, match="required"):
        journal.add(title="x", action="y", predicted="   ", probability=0.5,
                    tier=Tier.REVENUS, cost_hours=1, horizon_days=1)


# --- the activity / result detector ------------------------------------------

def test_a_decision_comes_back_when_its_horizon_passes(tmp_path):
    journal = _journal(tmp_path)
    entry = _add(journal, days=14)
    assert journal.due(now=NOW + timedelta(days=13)) == ()
    assert journal.due(now=NOW + timedelta(days=15)) == (entry,)


def test_the_horizon_lands_on_a_day_and_not_at_an_hour(tmp_path):
    """Le jour dit, dès le matin. C'est le seul geste que l'outil réclame.

    Le test au-dessus vérifiait le treizième jour et le quinzième, et sautait
    le quatorzième — la frontière même. C'est là que c'était faux.

    `due_at` vaut `created_at + horizon_days`, donc il porte l'heure de
    l'écriture. Comparé comme un instant, un horizon de 14 jours pris un soir
    à 20 h n'échoyait qu'à 20 h le quatorzième jour. Thomas écrit ses décisions
    le soir et ouvre son rapport le matin : le verdict lui était donc réclamé
    le lendemain de l'échéance, à chaque fois, alors qu'`A_FAIRE.md` lui
    promet la carte en tête « le 20 septembre ».

    Sa première décision réelle est exactement ce cas : écrite le 6 septembre
    à 20 h, horizon 14 jours, verdict attendu le 20.
    """
    journal = _journal(tmp_path)
    soir = datetime(2026, 9, 6, 20, 0, tzinfo=UTC)
    entry = journal.add(title="Postuler", action="candidature", predicted="Un entretien",
                        probability=0.75, tier=Tier.REVENUS, cost_hours=4,
                        horizon_days=14, now=soir)

    veille_au_soir = datetime(2026, 9, 19, 23, 0, tzinfo=UTC)
    assert journal.due(now=veille_au_soir) == (), "réclamé la veille"

    le_jour_dit_au_matin = datetime(2026, 9, 20, 7, 0, tzinfo=UTC)
    assert journal.due(now=le_jour_dit_au_matin) == (entry,), (
        "le jour de l'échéance, au réveil, l'outil ne demande pas le verdict"
    )
    assert entry.overdue_days(now=le_jour_dit_au_matin) == 0
    assert entry.is_due(now=le_jour_dit_au_matin) is True


def test_overdue_days_are_counted(tmp_path):
    entry = _add(_journal(tmp_path), days=7)
    assert entry.overdue_days(now=NOW + timedelta(days=20)) == 13


def test_a_late_verdict_is_counted_in_whole_days_not_in_hours(tmp_path):
    """« Elle attend depuis 6 jours » alors que l'échéance était il y a 7.

    Même cause : une soustraction d'instants, tronquée. Une demi-journée
    manquait à chaque compte, et le seuil au-delà duquel le rapport passe en
    CRITIQUE — sept jours — arrivait donc un jour trop tard lui aussi.
    """
    journal = _journal(tmp_path)
    soir = datetime(2026, 9, 6, 20, 0, tzinfo=UTC)
    entry = journal.add(title="Postuler", action="candidature", predicted="Un entretien",
                        probability=0.75, tier=Tier.REVENUS, cost_hours=4,
                        horizon_days=14, now=soir)

    # Échéance le 20. Une semaine plus tard, c'est sept jours, pas six.
    assert entry.overdue_days(now=datetime(2026, 9, 27, 8, 0, tzinfo=UTC)) == 7
    assert entry.overdue_days(now=datetime(2026, 9, 21, 8, 0, tzinfo=UTC)) == 1
    # Et jamais négatif avant l'heure.
    assert entry.overdue_days(now=datetime(2026, 9, 10, 8, 0, tzinfo=UTC)) == 0
    assert entry.days_until_due(now=datetime(2026, 9, 19, 8, 0, tzinfo=UTC)) == 1
    assert entry.days_until_due(now=datetime(2026, 9, 20, 8, 0, tzinfo=UTC)) == 0


def test_resolved_decisions_stop_coming_back(tmp_path):
    journal = _journal(tmp_path)
    entry = _add(journal, days=1)
    journal.resolve(entry.entry_id, happened=True, now=NOW + timedelta(days=2))
    assert journal.due(now=NOW + timedelta(days=30)) == ()


# --- history is not editable --------------------------------------------------

def test_a_resolved_decision_cannot_be_resolved_again(tmp_path):
    journal = _journal(tmp_path)
    entry = _add(journal)
    journal.resolve(entry.entry_id, happened=False)
    with pytest.raises(PermissionError, match="history is not editable"):
        journal.resolve(entry.entry_id, happened=True)


def test_the_chain_detects_a_rewritten_prediction(tmp_path):
    """A journal you can edit afterwards teaches you nothing."""
    journal = _journal(tmp_path)
    entry = _add(journal, probability=0.9)
    assert journal.verify() is True

    with journal._connect() as conn:
        conn.execute("UPDATE journal_entries SET probability=0.3 WHERE entry_id=?", (entry.entry_id,))
    assert journal.verify() is False


def test_the_chain_detects_a_deleted_entry(tmp_path):
    journal = _journal(tmp_path)
    first = _add(journal, now=NOW, title="première")
    _add(journal, now=NOW + timedelta(hours=1), title="seconde")
    with journal._connect() as conn:
        conn.execute("DELETE FROM journal_entries WHERE entry_id=?", (first.entry_id,))
    assert journal.verify() is False


def test_abandoning_is_a_result_not_a_delete(tmp_path):
    journal = _journal(tmp_path)
    entry = _add(journal)
    abandoned = journal.abandon(entry.entry_id, reason="le contexte a changé")
    assert abandoned.status is Status.ABANDONED
    assert abandoned.lesson == "le contexte a changé"
    assert len(journal.entries()) == 1


# --- what the review is for ---------------------------------------------------

def test_review_scores_overconfidence(tmp_path):
    journal = _journal(tmp_path)
    for _ in range(4):
        entry = _add(journal, probability=0.9)
        journal.resolve(entry.entry_id, happened=False)
    report = journal.review()
    assert report["mean_probability"] == 0.9
    assert report["hit_rate"] == 0.0
    assert report["overconfidence"] == 0.9
    assert report["mean_brier"] > 0.7


def test_review_scores_underconfidence(tmp_path):
    journal = _journal(tmp_path)
    for _ in range(4):
        entry = _add(journal, probability=0.2)
        journal.resolve(entry.entry_id, happened=True)
    assert journal.review()["overconfidence"] == -0.8


def test_review_shows_hours_sunk_into_unresolved_work(tmp_path):
    """The number that would have shown 13 000 lines against zero outcomes."""
    journal = _journal(tmp_path)
    _add(journal, tier=Tier.PATRIMOINE, hours=90)
    settled = _add(journal, tier=Tier.REVENUS, hours=10)
    journal.resolve(settled.entry_id, happened=True)

    report = journal.review()
    assert report["hours_total"] == 100
    assert report["hours_unresolved"] == 90
    assert report["hours_that_worked"] == 10
    assert report["by_tier"]["PATRIMOINE"]["hours_unresolved"] == 90
    assert report["by_tier"]["REVENUS"]["hit_rate"] == 1.0


def test_review_ranks_tiers_by_the_constitution_order(tmp_path):
    journal = _journal(tmp_path)
    _add(journal, tier=Tier.LIBERTE)
    _add(journal, tier=Tier.STABILITE)
    report = journal.review()
    assert report["by_tier"]["STABILITE"]["rank"] == 1
    assert report["by_tier"]["LIBERTE"]["rank"] == 6


def test_review_of_an_empty_journal_says_nothing_rather_than_guessing(tmp_path):
    report = _journal(tmp_path).review()
    assert report["decisions"] == 0
    assert report["hit_rate"] is None
    assert report["overconfidence"] is None
    assert report["chain_intact"] is True


# --- persistence --------------------------------------------------------------

def test_the_journal_survives_a_restart(tmp_path):
    path = tmp_path / "journal.db"
    entry = _add(DecisionJournal(path))
    reopened = DecisionJournal(path)
    assert reopened.entries()[0].entry_id == entry.entry_id
    assert reopened.verify() is True


def test_a_schema_from_another_version_is_refused(tmp_path):
    path = tmp_path / "journal.db"
    journal = DecisionJournal(path)
    with journal._connect() as conn:
        conn.execute("UPDATE journal_schema SET version=99")
    with pytest.raises(RuntimeError, match="does not match"):
        DecisionJournal(path)


# --- the CLI ------------------------------------------------------------------

def test_the_cli_records_and_reviews_without_a_terminal(tmp_path, capsys):
    from singular.__main__ import main

    db = str(tmp_path / "journal.db")
    assert main(["--db", db, "add", "--title", "Parler à 5 personnes", "--action", "publier",
                 "--predicted", "2 réponses", "--probability", "0.5", "--tier", "REVENUS",
                 "--hours", "12", "--days", "21"]) == 0
    entry_id = DecisionJournal(db).entries()[0].entry_id

    assert main(["--db", db, "resolve", entry_id, "--no", "--lesson", "personne n'a répondu"]) == 0
    assert main(["--db", db, "review"]) == 0
    output = capsys.readouterr().out
    assert "OÙ VONT TES HEURES" in output
    assert "CE QUE TA CONFIANCE VAUT" in output
    # Ce test exigeait « surconfiance » ici. Sur **un** verdict : il figeait donc
    # exactement le défaut. Un pari à 50 % perdu ne dit rien de son jugement, et
    # l'imprimer en rouge lui conseillait de corriger ce que rien ne montre faux.
    assert "surconfiance" not in output, output
    assert "rien a conclure" in output


def test_the_command_line_only_calls_him_overconfident_when_it_can(tmp_path, capsys):
    """Le rouge du clavier suit la même règle que la phrase du rapport.

    `review` tenait son propre seuil — 5 %, sans minimum de verdicts — et
    imprimait « surconfiance de +75 % - tu crois plus que ce qui arrive » après
    la première décision tranchée. C'est le pire cas de la série, parce que
    c'est la commande qu'il lance le dimanche pour faire le point.
    """
    from singular.__main__ import main

    db = str(tmp_path / "journal.db")
    journal = DecisionJournal(db)
    for index in range(6):
        entry = _add(journal, probability=0.9, title=f"Pari {index}")
        journal.resolve(entry.entry_id, happened=False, now=NOW + timedelta(days=1))

    assert main(["--db", db, "review"]) == 0
    output = capsys.readouterr().out
    # Six paris à 90 % tous perdus : 0,1^6. Là, le rouge est mérité.
    assert "surconfiance" in output, output


def test_the_cli_refuses_an_ambiguous_verdict(tmp_path, capsys):
    from singular.__main__ import main

    db = str(tmp_path / "journal.db")
    main(["--db", db, "add", "--title", "t", "--action", "a", "--predicted", "p"])
    entry_id = DecisionJournal(db).entries()[0].entry_id
    assert main(["--db", db, "resolve", entry_id]) == 2
    assert main(["--db", db, "resolve", entry_id, "--yes", "--no"]) == 2


# --- the fast path you will actually use --------------------------------------

def test_apply_records_an_interview_not_a_reply(tmp_path):
    """A rejection is an answer, not the result you were after.

    Scoring applications on replies would let you feel productive while nothing
    moves, which is the exact failure the journal exists to catch.
    """
    from singular.__main__ import main

    db = str(tmp_path / "journal.db")
    assert main(["--db", db, "apply", "Anthropic", "Ingénieur agents"]) == 0
    entry = DecisionJournal(db).entries()[0]
    # Tiret simple, pas cadratin : le titre s'affiche dans une console Windows,
    # dont la page de code française ne connaît pas le second.
    assert entry.title == "Anthropic - Ingénieur agents"
    assert "entretien" in entry.predicted
    assert entry.tier is Tier.STABILITE
    assert 0 < entry.probability < 0.5, "the default should be an honest base rate"


def test_apply_defaults_are_overridable(tmp_path):
    from singular.__main__ import main

    db = str(tmp_path / "journal.db")
    main(["--db", db, "apply", "Mistral", "Infra", "--probability", "0.35", "--days", "10", "--hours", "3"])
    entry = DecisionJournal(db).entries()[0]
    assert entry.probability == 0.35
    assert entry.horizon_days == 10
    assert entry.cost_hours == 3


# --- the line that puts it in front of you ------------------------------------

def test_summary_line_of_an_empty_journal_says_so(tmp_path):
    assert _journal(tmp_path).summary_line() == "SINGULAR · journal vide"


def test_summary_line_counts_what_needs_a_verdict(tmp_path):
    journal = _journal(tmp_path)
    _add(journal, days=1, hours=8)
    line = journal.summary_line(now=NOW + timedelta(days=5))
    assert "1 à trancher" in line
    assert "8h sans verdict" in line


def test_summary_line_surfaces_calibration_once_it_is_meaningful(tmp_path):
    journal = _journal(tmp_path)
    for _ in range(3):
        entry = _add(journal, probability=0.9)
        journal.resolve(entry.entry_id, happened=False)
    assert "calibration +90%" in journal.summary_line()


def test_summary_line_stays_quiet_when_calibration_is_fine(tmp_path):
    """Two coin-flips at 50%, one each way: nothing to report."""
    journal = _journal(tmp_path)
    for happened in (True, False):
        entry = _add(journal, probability=0.5)
        journal.resolve(entry.entry_id, happened=happened)
    assert journal.review()["overconfidence"] == 0.0
    assert "calibration" not in journal.summary_line()


# --- export -------------------------------------------------------------------

def test_export_carries_every_entry_and_its_verdict(tmp_path):
    journal = _journal(tmp_path)
    settled = _add(journal, title="résolue")
    _add(journal, title="ouverte")
    journal.resolve(settled.entry_id, happened=True, lesson="ça a marché")

    rows = journal.export_rows()
    assert len(rows) == 2
    done = next(r for r in rows if r["entry_id"] == settled.entry_id)
    assert done["status"] == "HAPPENED"
    assert done["lesson"] == "ça a marché"
    assert done["brier_score"] != ""
    still_open = next(r for r in rows if r["entry_id"] != settled.entry_id)
    assert still_open["resolved_at"] == "" and still_open["brier_score"] == ""


def test_export_of_an_empty_journal_is_still_valid_csv(tmp_path, capsys):
    from singular.__main__ import main

    assert main(["--db", str(tmp_path / "journal.db"), "export"]) == 0
    header = capsys.readouterr().out.strip()
    assert header.split(",") == list(DecisionJournal.EXPORT_COLUMNS)


def test_the_header_is_the_same_whether_the_journal_is_empty_or_not(tmp_path, capsys):
    """La ligne du cas vide etait recopiee a la main, et avait deux colonnes de retard.

    `expected_gain_eur` et `reversibility` ont ete ajoutees a `export_rows` et
    pas a la copie. Un journal vide exportait treize colonnes, un journal rempli
    quinze : une feuille de calcul montee sur le premier decalait ses colonnes
    au premier export suivant, sans rien dire.
    """
    from singular.__main__ import main

    chemin = tmp_path / "journal.db"
    journal = _journal(tmp_path)
    assert main(["--db", str(chemin), "export"]) == 0
    vide = capsys.readouterr().out.splitlines()[0]

    _add(journal, title="une decision")
    assert main(["--db", str(chemin), "export"]) == 0
    rempli = capsys.readouterr().out.splitlines()

    assert vide == rempli[0]
    assert vide.split(",") == list(DecisionJournal.EXPORT_COLUMNS)
    assert len(rempli[1].split(",")) == len(DecisionJournal.EXPORT_COLUMNS)


def test_the_columns_are_those_the_rows_actually_carry(tmp_path):
    """Le temoin : une liste figee pourrait mentir aussi bien que la copie."""
    journal = _journal(tmp_path)
    _add(journal, title="une decision")

    assert list(journal.export_rows()[0]) == list(DecisionJournal.EXPORT_COLUMNS)


def test_the_export_leaves_the_line_endings_to_the_console(tmp_path, capsys):
    """Sur Windows, `\r\n` ecrit par csv devient `\r\r\n` en sortie standard.

    Le tableur affiche alors une ligne blanche entre chaque decision. On ecrit
    donc `\n` et on laisse la console traduire : le fichier est juste des deux
    cotes. Ce test verifie ce qui est verifiable ici -- aucun retour chariot
    dans ce que la commande ecrit ; c'est Windows qui ajoute le sien.
    """
    from singular.__main__ import main

    journal = _journal(tmp_path)
    _add(journal, title="une decision")

    assert main(["--db", str(tmp_path / "journal.db"), "export"]) == 0
    assert "\r" not in capsys.readouterr().out


def test_concurrent_entries_keep_one_unbroken_chain(tmp_path):
    """Two writers reading the same head would each link to it, and entries are never rewritten."""
    import threading

    journal = _journal(tmp_path)
    errors: list[Exception] = []
    barrier = threading.Barrier(6)

    def add(index: int) -> None:
        try:
            barrier.wait(timeout=10)
            _add(journal, title=f"Décision {index}", now=NOW + timedelta(seconds=index))
        except Exception as exc:  # noqa: BLE001 - reported through the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=add, args=(index,)) for index in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert len(journal.entries()) == 6
    assert journal.verify()


def test_recording_a_decision_after_the_fact_does_not_break_the_chain(tmp_path):
    """created_at is supplied by the caller; the chain follows insertion, not the clock."""
    journal = _journal(tmp_path)
    _add(journal, title="aujourd'hui", now=NOW + timedelta(days=1))
    _add(journal, title="hier, noté après coup", now=NOW)

    assert journal.verify()
    assert [entry.title for entry in journal.entries()] == ["hier, noté après coup", "aujourd'hui"]


# --- the chain must survive ordinary use ------------------------------------

def test_an_integer_cost_does_not_break_the_chain(tmp_path):
    """The row is read back as a float, so it must be written as one.

    `add(cost_hours=60)` fingerprinted the integer and `_entry` returned 60.0;
    json renders those differently, so verify() called an untouched journal
    rewritten -- from its first entry, permanently, because entries are never
    rewritten. The CLI passes floats through argparse and never met it; every
    other caller broke the chain by using it.
    """
    journal = DecisionJournal(tmp_path / "journal.db")
    journal.add(title="A", action="a", predicted="p", probability=0.8,
                tier=Tier.REVENUS, cost_hours=60, horizon_days=14)
    assert journal.verify() is True

    journal.add(title="B", action="b", predicted="q", probability=0.7,
                tier=Tier.CAPACITES, cost_hours=2.5, horizon_days=30)
    assert journal.verify() is True


def test_a_reopened_journal_still_verifies(tmp_path):
    path = tmp_path / "journal.db"
    first = DecisionJournal(path)
    for index in range(3):
        first.add(title=f"A{index}", action="a", predicted="p", probability=0.6,
                  tier=Tier.STABILITE, cost_hours=index, horizon_days=7)
    assert DecisionJournal(path).verify() is True


def test_a_probability_that_is_not_a_number_is_still_refused(tmp_path):
    """Canonicalising must not become a way of accepting anything."""
    journal = DecisionJournal(tmp_path / "journal.db")
    with pytest.raises(TypeError):
        journal.add(title="A", action="a", predicted="p", probability="0.8",
                    tier=Tier.REVENUS, cost_hours=1.0, horizon_days=14)


# --- la leçon est la sienne ---------------------------------------------------

def test_the_lesson_field_holds_his_words_or_nothing(tmp_path):
    """« Forecast DEC-138fee1a was incorrect: predicted 0.75, observed 0. »

    C'est ce que le journal écrivait dans le champ « leçon » quand il n'en
    donnait pas : une phrase de machine, en anglais, dans un outil français,
    gravée pour de bon puisqu'une entrée tranchée ne se réécrit plus.

    Elle n'apprend rien — la probabilité, le statut et le score de Brier sont
    déjà dans l'entrée, et elle ne fait que les redire. Elle coûte, en
    revanche, la seule chose qui compte : on ne distinguait plus « il n'a rien
    noté » de « il a noté ceci ». C'est la règle de provenance du dépôt, celle
    qui lui a déjà coûté un CV faux et un marché écarté, appliquée à ce que
    l'outil écrit sur lui.

    Le port Swift, lui, faisait déjà juste : `lesson.isEmpty ? nil : lesson`.
    """
    journal = _journal(tmp_path)

    muet = _add(journal, title="Sans leçon")
    tranche = journal.resolve(muet.entry_id, happened=False, now=NOW + timedelta(days=15))
    assert not tranche.lesson, f"la machine a écrit à sa place : {tranche.lesson!r}"

    # Ce que la phrase prétendait apprendre est déjà là, et vérifiable à la main.
    assert tranche.brier_score == pytest.approx((0.6 - 0.0) ** 2)
    assert tranche.status is Status.DID_NOT_HAPPEN
    assert tranche.probability == 0.6

    sienne = _add(journal, title="Avec leçon")
    ecrite = journal.resolve(sienne.entry_id, happened=True, lesson="j'ai relancé trop tard",
                             now=NOW + timedelta(days=15))
    assert ecrite.lesson == "j'ai relancé trop tard"

    # Et la chaîne ne bouge pas : la leçon n'entre pas dans l'empreinte.
    assert journal.verify() is True


def test_abandoning_still_records_the_reason_he_gave(tmp_path):
    """Abandonner est un résultat, et la raison est la sienne : elle reste."""
    journal = _journal(tmp_path)
    entry = _add(journal, title="Arrêtée")
    arretee = journal.abandon(entry.entry_id, reason="l'offre a été retirée",
                              now=NOW + timedelta(days=3))
    assert arretee.lesson == "l'offre a été retirée"


# --- l'échéance ne se recalcule pas ailleurs ---------------------------------

def test_no_module_does_instant_arithmetic_on_a_deadline():
    """Un horizon en jours, comparé en instants, se trompe d'une journée.

    La faute était à trois endroits à la fois — `due()`, `overdue_days()` et la
    phrase « prochaine échéance » — parce que chacun refaisait le calcul à
    partir de `due_at`, qui porte l'heure de l'écriture. Trois copies d'une même
    règle : elles se sont trompées ensemble, et une correction à un seul endroit
    en aurait laissé deux.

    La règle vit désormais sur `Entry` : `due_on`, `is_due`, `days_until_due`,
    `overdue_days`. Hors de `journal.py`, `due_at` peut être **affiché** — c'est
    une date qu'on imprime — mais pas reconverti pour être comparé ou soustrait.

    Ce test lit le source parce que c'est ce qui rend la faute impossible plutôt
    que corrigée : le prochain module qui écrira `fromisoformat(entry.due_at) <=
    maintenant` échouera ici, et pas dans dix jours, un matin d'échéance, sur le
    téléphone de quelqu'un.
    """
    import ast
    import pathlib

    racine = pathlib.Path(__file__).resolve().parent.parent / "singular"
    domicile = racine / "journal.py"

    fautes = []
    for source in sorted(racine.rglob("*.py")):
        if source == domicile:
            continue
        arbre = ast.parse(source.read_text(encoding="utf-8"))

        parent = {}
        for noeud in ast.walk(arbre):
            for enfant in ast.iter_child_nodes(noeud):
                parent[enfant] = noeud

        for noeud in ast.walk(arbre):
            convertit = (isinstance(noeud, ast.Call)
                         and isinstance(noeud.func, ast.Attribute)
                         and noeud.func.attr == "fromisoformat"
                         and any(isinstance(a, ast.Attribute) and a.attr == "due_at"
                                 for a in noeud.args))
            if not convertit:
                continue
            dessus = parent.get(noeud)
            imprime = (isinstance(dessus, ast.Attribute) and dessus.attr == "strftime")
            if not imprime:
                fautes.append(f"{source.relative_to(racine.parent)}:{noeud.lineno}")

    assert not fautes, (
        f"{fautes} reconvertit une échéance pour la calculer. L'échéance est un "
        "jour, pas un instant : passe par `Entry.due_on`, `is_due`, "
        "`days_until_due` ou `overdue_days`, qui portent la règle et sa raison."
    )
