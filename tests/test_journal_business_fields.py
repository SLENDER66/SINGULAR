"""Le gain attendu et la réversibilité, sans casser ce qui est déjà écrit.

La constitution demande de juger une décision sur « options, levier, coût,
vitesse, réversibilité ». Le journal ne connaissait que le coût en heures et
l'horizon : il savait ce qu'une décision coûte, jamais ce qu'elle rapporte ni
ce que coûte de s'être trompé. Une dette est le cas le plus net -- 5 000 euros
empruntés ne se jugent pas comme 20 heures passées.

Deux colonnes ont donc été ajoutées à une base qui contenait déjà une décision
réelle. Tout le risque est là, et ces tests le couvrent :

* une entrée écrite avant leur existence doit rester vérifiable, pour toujours ;
* une valeur glissée après coup dans la base doit être vue ;
* la chaîne doit continuer par-dessus la migration.

Le troisième point est le seul qui se voit à l'usage. Les deux premiers ne se
voient jamais : un journal dont la chaîne casse ne prévient pas, il devient
faux.
"""
from __future__ import annotations

import json
import math
import sqlite3

import pytest

from singular.journal import (
    SCHEMA_VERSION,
    DecisionJournal,
    Reversibility,
    Tier,
    _fingerprint,
)

#: Le schéma exact de la v1, tel qu'il a écrit la base qui existe aujourd'hui.
#: Recopié plutôt qu'importé : un test de migration qui lirait le schéma
#: courant ne testerait rien: il migrerait la v2 vers la v2.
V1 = """
CREATE TABLE journal_schema (version INTEGER NOT NULL);
CREATE TABLE journal_entries (
    entry_id TEXT PRIMARY KEY, title TEXT NOT NULL, action TEXT NOT NULL,
    predicted TEXT NOT NULL, probability REAL NOT NULL, tier TEXT NOT NULL,
    cost_hours REAL NOT NULL, horizon_days INTEGER NOT NULL, created_at TEXT NOT NULL,
    due_at TEXT NOT NULL, status TEXT NOT NULL, resolved_at TEXT, lesson TEXT,
    brier_score REAL, previous_fingerprint TEXT NOT NULL, fingerprint TEXT NOT NULL
);
"""


def _base_v1(chemin, *, titre="Postuler", tier="REVENUS") -> str:
    """Une base v1 avec une entrée, empreinte comprise, comme l'ancien code."""
    charge = {
        "entry_id": "DEC-old00001", "title": titre, "action": "Envoyer le CV",
        "predicted": "Un entretien", "probability": 0.75, "tier": tier,
        "cost_hours": 4.0, "horizon_days": 13,
        "created_at": "2026-09-06T20:00:00+00:00",
    }
    empreinte = _fingerprint(charge, "")
    conn = sqlite3.connect(chemin)
    conn.executescript(V1)
    conn.execute("INSERT INTO journal_schema(version) VALUES(1)")
    conn.execute(
        "INSERT INTO journal_entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (*charge.values(), "2026-09-19T20:00:00+00:00", "OPEN", None, None, None, "", empreinte),
    )
    conn.commit()
    conn.close()
    return empreinte


def test_une_base_v1_migre_et_sa_chaine_tient(tmp_path) -> None:
    """Le cas réel : une décision écrite avant que ces champs existent."""
    chemin = tmp_path / "journal.db"
    empreinte = _base_v1(chemin)

    journal = DecisionJournal(chemin)

    assert journal.verify(), "l'entrée d'hier doit rester vérifiable après migration"
    entree = journal.entries()[0]
    assert entree.fingerprint == empreinte, "la migration ne réécrit aucune empreinte"
    assert entree.expected_gain_eur is None
    assert entree.reversibility is None

    with sqlite3.connect(chemin) as conn:
        version = conn.execute("SELECT version FROM journal_schema").fetchone()[0]
    assert version == SCHEMA_VERSION


def test_la_chaine_continue_par_dessus_la_migration(tmp_path) -> None:
    """Une entrée neuve, chiffrée, se chaîne derrière une entrée qui ne l'est pas."""
    chemin = tmp_path / "journal.db"
    ancienne = _base_v1(chemin)
    journal = DecisionJournal(chemin)

    neuve = journal.add(
        title="Emprunter", action="Credit 5000 euros", predicted="Materiel achete",
        probability=0.8, tier=Tier.REVENUS, cost_hours=2, horizon_days=30,
        expected_gain_eur=5000, reversibility=Reversibility.IRREVERSIBLE,
    )

    assert neuve.previous_fingerprint == ancienne
    assert journal.verify()
    assert journal.entries()[1].expected_gain_eur == 5000.0
    assert journal.entries()[1].reversibility is Reversibility.IRREVERSIBLE


def test_un_gain_glisse_apres_coup_dans_la_base_est_vu(tmp_path) -> None:
    """La raison d'être de la chaîne, appliquée aux champs neufs.

    Un gain attendu qu'on peut réviser une fois le résultat connu n'apprend
    rien. C'est le même piège que la probabilité, et il doit se refermer pareil.
    """
    chemin = tmp_path / "journal.db"
    _base_v1(chemin)
    journal = DecisionJournal(chemin)
    assert journal.verify()

    with sqlite3.connect(chemin) as conn:
        conn.execute("UPDATE journal_entries SET expected_gain_eur=9999 WHERE entry_id='DEC-old00001'")

    assert not journal.verify(), "un chiffre ajouté après coup doit casser la vérification"


def test_une_reversibilite_glissee_apres_coup_est_vue(tmp_path) -> None:
    chemin = tmp_path / "journal.db"
    _base_v1(chemin)
    journal = DecisionJournal(chemin)

    with sqlite3.connect(chemin) as conn:
        conn.execute("UPDATE journal_entries SET reversibility='REVERSIBLE' WHERE entry_id='DEC-old00001'")

    assert not journal.verify()


def test_un_gain_entier_est_signe_comme_il_sera_relu(tmp_path) -> None:
    """`5000` signé, `5000.0` relu : le piège qui avait déjà cassé cost_hours."""
    journal = DecisionJournal(tmp_path / "journal.db")
    journal.add(
        title="Emprunter", action="Credit", predicted="Materiel", probability=0.8,
        tier=Tier.REVENUS, cost_hours=2, horizon_days=30, expected_gain_eur=5000,
    )
    assert journal.verify()


@pytest.mark.parametrize("valeur", [float("nan"), float("inf"), -float("inf")])
def test_un_gain_non_fini_est_refuse(tmp_path, valeur: float) -> None:
    """NaN ne lève pas tout seul : il contaminerait le total sans rien dire."""
    journal = DecisionJournal(tmp_path / "journal.db")
    with pytest.raises(ValueError, match="finite"):
        journal.add(title="X", action="Y", predicted="Z", probability=0.5, tier=Tier.REVENUS,
                    cost_hours=1, horizon_days=1, expected_gain_eur=valeur)


def test_un_gain_negatif_est_refuse(tmp_path) -> None:
    journal = DecisionJournal(tmp_path / "journal.db")
    with pytest.raises(ValueError, match="negative"):
        journal.add(title="X", action="Y", predicted="Z", probability=0.5, tier=Tier.REVENUS,
                    cost_hours=1, horizon_days=1, expected_gain_eur=-1)


def test_une_reversibilite_en_chaine_brute_est_refusee(tmp_path) -> None:
    """« IRREVERSIBLE » mal orthographié deviendrait une valeur muette en base."""
    journal = DecisionJournal(tmp_path / "journal.db")
    with pytest.raises(TypeError):
        journal.add(title="X", action="Y", predicted="Z", probability=0.5, tier=Tier.REVENUS,
                    cost_hours=1, horizon_days=1, reversibility="IRREVERSIBLE")


def test_une_base_plus_recente_que_le_code_est_refusee(tmp_path) -> None:
    """Descendre de version doit refuser, pas lire des colonnes qu'il ignore."""
    chemin = tmp_path / "journal.db"
    _base_v1(chemin)
    with sqlite3.connect(chemin) as conn:
        conn.execute("UPDATE journal_schema SET version=?", (SCHEMA_VERSION + 1,))

    with pytest.raises(RuntimeError, match="does not match"):
        DecisionJournal(chemin)


def test_le_bilan_distingue_ce_qui_est_chiffre_de_ce_qui_ne_l_est_pas(tmp_path) -> None:
    """« None » veut dire non chiffré, pas zéro : c'est ce que la Notice reproche."""
    journal = DecisionJournal(tmp_path / "journal.db")
    journal.add(title="Chiffre", action="A", predicted="B", probability=0.6, tier=Tier.REVENUS,
                cost_hours=3, horizon_days=10, expected_gain_eur=2000,
                reversibility=Reversibility.REVERSIBLE)
    journal.add(title="Pas chiffre", action="C", predicted="D", probability=0.6, tier=Tier.CAPACITES,
                cost_hours=7, horizon_days=10)
    journal.add(title="Dette", action="E", predicted="F", probability=0.6, tier=Tier.PATRIMOINE,
                cost_hours=1, horizon_days=10, expected_gain_eur=5000,
                reversibility=Reversibility.IRREVERSIBLE)

    bilan = journal.review()

    assert bilan["gain_expected_total"] == 7000.0
    assert bilan["hours_without_gain"] == 7.0
    assert bilan["irreversible_open"] == 1
    assert not math.isnan(bilan["gain_expected_total"])


def test_l_export_porte_les_deux_champs(tmp_path) -> None:
    journal = DecisionJournal(tmp_path / "journal.db")
    journal.add(title="X", action="Y", predicted="Z", probability=0.5, tier=Tier.REVENUS,
                cost_hours=1, horizon_days=1, expected_gain_eur=5000,
                reversibility=Reversibility.IRREVERSIBLE)
    journal.add(title="Sans", action="Y", predicted="Z", probability=0.5, tier=Tier.REVENUS,
                cost_hours=1, horizon_days=1)

    lignes = journal.export_rows()

    assert lignes[0]["expected_gain_eur"] == 5000.0
    assert lignes[0]["reversibility"] == "IRREVERSIBLE"
    assert lignes[1]["expected_gain_eur"] == ""
    assert json.dumps(lignes)
