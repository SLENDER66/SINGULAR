"""Ce que la Notice sait dire depuis que le gain et la réversibilité existent.

Deux champs sans observation ne servent à rien : ils seraient saisis et jamais
relus. Ces tests tiennent les deux phrases que le Sage peut désormais produire,
et surtout leur silence -- une observation qui parle tout le temps ne se lit
plus.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from singular.journal import DecisionJournal, Reversibility, Tier
from singular.sage.notice import UNPRICED_HOURS, build_notice


@pytest.fixture
def journal(tmp_path) -> DecisionJournal:
    return DecisionJournal(tmp_path / "journal.db")


def _titres(notice) -> str:
    return " | ".join(item.title for item in notice.items)


def test_un_engagement_irreversible_sans_verdict_est_critique(journal) -> None:
    """La règle « HALT » de la constitution, appliquée au cas qui compte."""
    depart = datetime(2026, 9, 1, tzinfo=UTC)
    entree = journal.add(
        title="Emprunter 5000", action="Credit consommation", predicted="Materiel achete",
        probability=0.8, tier=Tier.REVENUS, cost_hours=2, horizon_days=5,
        expected_gain_eur=5000, reversibility=Reversibility.IRREVERSIBLE, now=depart,
    )

    notice = build_notice(journal, now=depart + timedelta(days=30))

    engagement = next(i for i in notice.items if "irréversible" in i.title)
    assert engagement.severity == "CRITIQUE"
    assert entree.entry_id in engagement.entry_ids


def test_un_engagement_irreversible_dans_les_temps_reste_visible_sans_alarmer(journal) -> None:
    depart = datetime(2026, 9, 1, tzinfo=UTC)
    journal.add(
        title="Emprunter", action="Credit", predicted="Materiel", probability=0.8,
        tier=Tier.REVENUS, cost_hours=2, horizon_days=60,
        reversibility=Reversibility.IRREVERSIBLE, now=depart,
    )

    notice = build_notice(journal, now=depart + timedelta(days=1))

    engagement = next(i for i in notice.items if "irréversible" in i.title)
    assert engagement.severity == "ATTENTION"


def test_une_decision_reversible_ne_declenche_rien(journal) -> None:
    """Le silence est la moitié du travail : sinon la page devient un bruit."""
    depart = datetime(2026, 9, 1, tzinfo=UTC)
    journal.add(
        title="Envoyer un CV", action="Postuler", predicted="Un entretien", probability=0.3,
        tier=Tier.REVENUS, cost_hours=2, horizon_days=5,
        reversibility=Reversibility.REVERSIBLE, now=depart,
    )

    notice = build_notice(journal, now=depart + timedelta(days=30))

    assert "irréversible" not in _titres(notice)


def test_les_heures_non_chiffrees_se_reprochent_au_dela_du_seuil(journal) -> None:
    journal.add(title="Un gros chantier", action="A", predicted="B", probability=0.6,
                tier=Tier.CAPACITES, cost_hours=UNPRICED_HOURS + 1, horizon_days=90)

    notice = build_notice(journal)

    chiffre = next(i for i in notice.items if "sans gain attendu" in i.title)
    assert chiffre.severity == "INFO"
    assert "100%" in chiffre.detail  # sans espace, comme partout ailleurs dans la Notice


def test_sous_le_seuil_la_notice_se_tait(journal) -> None:
    journal.add(title="Petit geste", action="A", predicted="B", probability=0.6,
                tier=Tier.CAPACITES, cost_hours=UNPRICED_HOURS - 1, horizon_days=90)

    assert "sans gain attendu" not in _titres(build_notice(journal))


def test_des_heures_chiffrees_ne_se_reprochent_pas(journal) -> None:
    """Estimer faux s'apprend ; ne pas estimer ne s'apprend pas. Seul le second se dit."""
    journal.add(title="Chiffre", action="A", predicted="B", probability=0.6,
                tier=Tier.REVENUS, cost_hours=UNPRICED_HOURS * 2, horizon_days=90,
                expected_gain_eur=3000)

    assert "sans gain attendu" not in _titres(build_notice(journal))


def test_le_bilan_de_la_notice_porte_les_agregats_d_affaires(journal) -> None:
    journal.add(title="Chiffre", action="A", predicted="B", probability=0.6, tier=Tier.REVENUS,
                cost_hours=3, horizon_days=10, expected_gain_eur=2000,
                reversibility=Reversibility.IRREVERSIBLE)

    rapport = build_notice(journal).report

    assert rapport["gain_expected_total"] == 2000.0
    assert rapport["irreversible_open"] == 1
