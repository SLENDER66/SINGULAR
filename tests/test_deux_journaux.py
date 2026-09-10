"""Deux journaux ne se fusionnent pas, et `A_FAIRE.md` le promet.

Le 10 septembre 2026, sa machine change et il n'a pas accès à l'ancienne. Son
journal — trois mois de décisions — est sur un disque qu'il ne peut pas
atteindre. La tentation est d'en commencer un neuf sur le Mac et de recoller
les deux plus tard.

Ça ne se recolle pas. Chaque entrée signe la précédente : insérer les lignes
d'une base dans l'autre donne bien toutes les entrées, et `verify()` rend faux
— définitivement, puisque le journal ne se réécrit pas. Il faudrait en jeter un.

`A_FAIRE.md` lui dit donc de ne rien écrire sur le Mac tant que la question
n'est pas tranchée. Ce fichier vérifie que la promesse est vraie, plutôt que de
la laisser reposer sur ma parole : si un jour la fusion devenait possible, le
conseil deviendrait faux et ce test le dirait.
"""
from __future__ import annotations

import pathlib
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta

from singular.journal import DecisionJournal, Tier

RACINE = pathlib.Path(__file__).resolve().parent.parent
DEBUT = datetime(2026, 6, 1, tzinfo=UTC)


def _journal(chemin: pathlib.Path, prefixe: str, combien: int, decalage: int = 0):
    journal = DecisionJournal(chemin)
    for index in range(combien):
        journal.add(title=f"{prefixe} {index}", action="a", predicted="b", probability=0.6,
                    tier=Tier.REVENUS, cost_hours=2, horizon_days=7,
                    now=DEBUT + timedelta(days=decalage + index))
    return journal


def test_recoller_deux_journaux_rompt_la_chaine(tmp_path) -> None:
    ancien = _journal(tmp_path / "pc.db", "PC", 3)
    neuf = _journal(tmp_path / "mac.db", "Mac", 2, decalage=100)
    assert ancien.verify() and neuf.verify(), "les deux doivent être sains séparément"

    fusion = tmp_path / "fusion.db"
    shutil.copy2(tmp_path / "pc.db", fusion)
    source = sqlite3.connect(tmp_path / "mac.db")
    source.row_factory = sqlite3.Row
    cible = sqlite3.connect(fusion)
    colonnes = [colonne[1] for colonne in cible.execute("PRAGMA table_info(journal_entries)")]
    for ligne in source.execute("SELECT * FROM journal_entries"):
        cible.execute(
            f"INSERT INTO journal_entries({','.join(colonnes)}) "
            f"VALUES({','.join('?' * len(colonnes))})",
            [ligne[colonne] for colonne in colonnes])
    cible.commit()
    cible.close()
    source.close()

    recolle = DecisionJournal(fusion)
    assert len(recolle.entries()) == 5, "les lignes sont bien toutes là"
    assert recolle.verify() is False, (
        "la fusion passe la vérification : le conseil d'`A_FAIRE.md` — ne rien "
        "écrire sur le Mac tant que la question n'est pas tranchée — n'a plus "
        "lieu d'être, et il faut le réécrire.")


def test_un_journal_seul_traverse_le_deplacement(tmp_path) -> None:
    """L'autre moitié : déplacer un journal ne casse rien, le fusionner si.

    Sans ce versant, le test ci-dessus prouverait seulement que `verify()` est
    facile à faire échouer.
    """
    ancien = _journal(tmp_path / "pc.db", "PC", 3)
    empreintes = [entree.fingerprint for entree in ancien.entries()]

    ailleurs = tmp_path / "ailleurs" / "journal.db"
    ailleurs.parent.mkdir()
    shutil.copy2(tmp_path / "pc.db", ailleurs)

    deplace = DecisionJournal(ailleurs)
    assert deplace.verify(), "un déplacement seul ne casse pas la chaîne"
    assert [entree.fingerprint for entree in deplace.entries()] == empreintes
    deplace.add(title="Écrite après le déplacement", action="a", predicted="b",
                probability=0.6, tier=Tier.REVENUS, cost_hours=1, horizon_days=7)
    assert deplace.verify(), "et on peut continuer à écrire derrière"


def test_a_faire_porte_bien_ce_conseil() -> None:
    """Le témoin : un test qui prouve une promesse absente ne garde rien."""
    texte = (RACINE / "A_FAIRE.md").read_text(encoding="utf-8")
    assert "Deux journaux ne se fusionnent pas" in texte
    assert "N'enregistre pas de décision sur le Mac" in texte
