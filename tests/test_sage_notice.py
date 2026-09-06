"""« Notice. » — chaque phrase doit être un fait tiré du journal.

Le Sage a le droit d'être dur ; il n'a pas le droit d'être faux. Ces tests
portent donc sur deux choses : ce qu'il dit quand il y a quelque chose à dire,
et son silence quand il n'y a rien. Un rapport qui trouve toujours un reproche
n'est plus lu.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from singular.journal import DecisionJournal, Tier
from singular.sage import build_notice
from singular.sage.notice import NoticeItem

NOW = datetime(2026, 9, 6, 9, 0, tzinfo=UTC)


def _journal(tmp_path):
    return DecisionJournal(tmp_path / "journal.db")


def _add(journal, *, tier=Tier.REVENUS, probability=0.6, hours=4.0, days=14, now=NOW, title="Une décision"):
    return journal.add(title=title, action="faire la chose", predicted="le résultat observable",
                       probability=probability, tier=tier, cost_hours=hours, horizon_days=days, now=now)


def _titles(notice) -> list[str]:
    return [item.title for item in notice.items]


# --- le journal vide ---------------------------------------------------------

def test_an_empty_journal_is_told_once_and_not_scolded_twice(tmp_path):
    """Sans entrées, « aucune décision sur Stabilité » dirait deux fois la même chose."""
    notice = build_notice(_journal(tmp_path), now=NOW)
    assert _titles(notice) == ["Le journal est vide"]
    assert notice.headline == "Notice. Le journal est vide."


# --- ce qui attend un verdict ------------------------------------------------

def test_an_overdue_decision_comes_first(tmp_path):
    journal = _journal(tmp_path)
    entry = _add(journal, days=7)
    notice = build_notice(journal, now=NOW + timedelta(days=9))

    first = notice.items[0]
    assert first.title == "À trancher aujourd'hui"
    assert first.entry_ids == (entry.entry_id,)
    assert first.action == f"resolve {entry.entry_id}"


def test_a_late_verdict_is_critical_and_says_why(tmp_path):
    journal = _journal(tmp_path)
    _add(journal, days=7)
    notice = build_notice(journal, now=NOW + timedelta(days=20))

    first = notice.items[0]
    assert first.severity == "CRITIQUE"
    assert "13 jours" in first.detail
    assert "préfère ne pas voir" in first.detail


def test_the_delay_is_counted_from_the_report_not_from_the_machine(tmp_path):
    """Un rapport daté d'un autre jour affichait « en retard de 0 jour »."""
    journal = _journal(tmp_path)
    _add(journal, days=7)
    notice = build_notice(journal, now=NOW + timedelta(days=12))
    assert "5 jours" in notice.items[0].detail


def test_one_overdue_decision_is_written_in_the_singular(tmp_path):
    journal = _journal(tmp_path)
    _add(journal, days=7)
    detail = build_notice(journal, now=NOW + timedelta(days=9)).items[0].detail
    assert "1 décision a dépassé son horizon" in detail
    assert "Elle attend depuis 2 jours" in detail


# --- les rangs de la constitution --------------------------------------------

def test_the_two_founding_ranks_are_named_when_empty(tmp_path):
    journal = _journal(tmp_path)
    _add(journal, tier=Tier.PATRIMOINE, hours=60)
    notice = build_notice(journal, now=NOW)

    item = next(item for item in notice.items if item.title.startswith("Aucune décision sur"))
    assert item.title == "Aucune décision sur Stabilité et Revenus"
    assert "60h sont allées ailleurs" in item.detail


def test_a_single_missing_rank_is_written_in_the_singular(tmp_path):
    journal = _journal(tmp_path)
    _add(journal, tier=Tier.STABILITE)
    item = next(item for item in build_notice(journal, now=NOW).items
                if item.title.startswith("Aucune décision sur"))
    assert item.title == "Aucune décision sur Revenus"
    assert "Ce rang n’a reçu" in item.detail


def test_nothing_is_said_when_both_founding_ranks_are_served(tmp_path):
    journal = _journal(tmp_path)
    _add(journal, tier=Tier.STABILITE)
    _add(journal, tier=Tier.REVENUS)
    assert not any(item.title.startswith("Aucune décision sur")
                   for item in build_notice(journal, now=NOW).items)


# --- ce que vaut la confiance ------------------------------------------------

def test_overconfidence_is_named_once_there_is_enough_to_say_it(tmp_path):
    journal = _journal(tmp_path)
    for index in range(4):
        entry = _add(journal, probability=0.9, tier=Tier.REVENUS, title=f"Décision {index}")
        journal.resolve(entry.entry_id, happened=False, now=NOW + timedelta(days=1))
    _add(journal, tier=Tier.STABILITE)

    item = next(item for item in build_notice(journal, now=NOW + timedelta(days=2)).items
                if "surestimes" in item.title)
    assert "90%" in item.detail and "0%" in item.detail


def test_two_verdicts_are_not_enough_to_call_someone_overconfident(tmp_path):
    """En dessous du seuil, l'écart s'explique aussi bien par l'échantillon."""
    journal = _journal(tmp_path)
    for index in range(2):
        entry = _add(journal, probability=0.9, title=f"Décision {index}")
        journal.resolve(entry.entry_id, happened=False, now=NOW + timedelta(days=1))
    assert not any("surestimes" in item.title
                   for item in build_notice(journal, now=NOW + timedelta(days=2)).items)


# --- l'intégrité passe avant tout --------------------------------------------

def test_a_broken_chain_outranks_everything_else(tmp_path):
    journal = _journal(tmp_path)
    entry = _add(journal, days=7)
    with journal._connect() as conn:
        conn.execute("UPDATE journal_entries SET probability=0.05 WHERE entry_id=?", (entry.entry_id,))

    notice = build_notice(journal, now=NOW + timedelta(days=30))
    assert notice.items[0].title == "La chaîne du journal est rompue"
    assert notice.severity == "CRITIQUE"


def test_an_ordinary_journal_does_not_report_a_broken_chain(tmp_path):
    """Le mécanisme d'intégrité ne doit pas accuser l'usage normal."""
    journal = _journal(tmp_path)
    _add(journal, hours=60, tier=Tier.STABILITE)
    _add(journal, hours=2.5, tier=Tier.REVENUS)
    assert not any("chaîne" in item.title for item in build_notice(journal, now=NOW).items)


# --- la forme ----------------------------------------------------------------

def test_a_notice_item_refuses_an_unknown_severity():
    with pytest.raises(ValueError, match="gravité inconnue"):
        NoticeItem("URGENT", "titre", "détail")


def test_the_report_is_serialisable(tmp_path):
    journal = _journal(tmp_path)
    _add(journal)
    payload = build_notice(journal, now=NOW).as_dict()
    assert payload["headline"].startswith("Notice.")
    assert payload["severity"] in {"CRITIQUE", "ATTENTION", "INFO"}
    assert isinstance(payload["items"], list)
    assert payload["report"]["decisions"] == 1
