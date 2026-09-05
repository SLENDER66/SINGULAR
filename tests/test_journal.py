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


def test_overdue_days_are_counted(tmp_path):
    entry = _add(_journal(tmp_path), days=7)
    assert entry.overdue_days(now=NOW + timedelta(days=20)) == 13


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
    assert "surconfiance" in output


def test_the_cli_refuses_an_ambiguous_verdict(tmp_path, capsys):
    from singular.__main__ import main

    db = str(tmp_path / "journal.db")
    main(["--db", db, "add", "--title", "t", "--action", "a", "--predicted", "p"])
    entry_id = DecisionJournal(db).entries()[0].entry_id
    assert main(["--db", db, "resolve", entry_id]) == 2
    assert main(["--db", db, "resolve", entry_id, "--yes", "--no"]) == 2
