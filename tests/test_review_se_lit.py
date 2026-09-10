"""Le bilan du dimanche doit se lire sans être déchiffré.

`USAGE.md` en fait un rituel hebdomadaire : `sj review`, deux minutes. C'est la
seule sortie de l'outil qu'il lit en entier, et deux choses la rendaient fausse
à l'œil sans qu'aucun chiffre soit faux.

1. « 16h encore sans verdict (5 ouvertes, 5 en retard) ». Les décisions en
   retard sont un sous-ensemble des ouvertes — `due()` filtre les OPEN dont
   l'échéance est passée. Cinq ouvertes toutes en retard s'affichaient donc
   comme dix décisions, pour qui lit vite. Les deux chiffres étaient justes ;
   c'est leur juxtaposition qui mentait.

2. Le tableau par rang portait six colonnes de données sous cinq en-têtes. Le
   pourcentage de fin de ligne — la part des verdicts du rang qui sont arrivés —
   n'avait pas de nom, et rien ne permettait de le distinguer des deux colonnes
   d'heures qui le précèdent.

Aucune des deux n'aurait fait échouer un test : les nombres sont exacts. Ce
fichier teste ce que l'œil en fait.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest

from singular.__main__ import main
from singular.journal import DecisionJournal, Tier

NOW = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)

#: Deux espaces ou plus separent deux colonnes ; une seule reste dans un titre.
COLONNES = re.compile(r"\s{2,}")


def _journal_avec(tmp_path, ouvertes: int, tranchees: int) -> DecisionJournal:
    journal = DecisionJournal(tmp_path / "journal.db")
    for index in range(tranchees):
        entree = journal.add(title=f"Tranchee {index}", action="a", predicted="b",
                             probability=0.6, tier=Tier.REVENUS, cost_hours=2,
                             horizon_days=7, now=NOW)
        journal.resolve(entree.entry_id, happened=index % 2 == 0, now=NOW + timedelta(days=8))
    for index in range(ouvertes):
        journal.add(title=f"Ouverte {index}", action="a", predicted="b", probability=0.6,
                    tier=Tier.CAPACITES, cost_hours=3, horizon_days=7, now=NOW)
    return journal


def _review(tmp_path, capsys, **kwargs) -> str:
    _journal_avec(tmp_path, **kwargs)
    capsys.readouterr()
    assert main(["--db", str(tmp_path / "journal.db"), "review"]) == 0
    return capsys.readouterr().out


# --- ce qui est un sous-ensemble se dit comme un sous-ensemble ----------------

def test_les_retards_se_disent_comme_une_partie_des_ouvertes(tmp_path, capsys):
    sortie = _review(tmp_path, capsys, ouvertes=5, tranchees=3)
    ligne = next(t for t in sortie.splitlines() if "sans verdict" in t)

    assert "dont" in ligne, (
        f"« {ligne.strip()} » se lit comme une addition. Les decisions en retard "
        "sont un sous-ensemble des ouvertes : cinq et cinq font cinq.")
    assert "5 ouvertes, dont 5 en retard" in ligne


def test_sans_retard_la_ligne_ne_parle_pas_de_retard(tmp_path, capsys):
    """L'inverse : « dont 0 en retard » serait du bruit chaque semaine."""
    journal = DecisionJournal(tmp_path / "journal.db")
    entree = journal.add(title="Tranchee", action="a", predicted="b", probability=0.6,
                         tier=Tier.REVENUS, cost_hours=2, horizon_days=7, now=NOW)
    journal.resolve(entree.entry_id, happened=True, now=NOW + timedelta(days=8))
    journal.add(title="Encore dans les temps", action="a", predicted="b", probability=0.6,
                tier=Tier.REVENUS, cost_hours=2, horizon_days=3650)

    capsys.readouterr()
    assert main(["--db", str(tmp_path / "journal.db"), "review"]) == 0
    ligne = next(t for t in capsys.readouterr().out.splitlines() if "sans verdict" in t)

    assert "en retard" not in ligne
    assert "1 ouverte)" in ligne, "et le singulier, tant qu'a lire cette ligne"


# --- chaque colonne porte un nom ---------------------------------------------

def test_le_tableau_par_rang_a_autant_d_en_tetes_que_de_colonnes(tmp_path, capsys):
    """Un pourcentage nu en bout de ligne ne s'interprete pas.

    Il vaut la part des verdicts du rang qui sont arrives -- pas une part
    d'heures, contrairement aux deux colonnes qui le precedent.
    """
    sortie = _review(tmp_path, capsys, ouvertes=2, tranchees=4).splitlines()
    depart = next(index for index, t in enumerate(sortie) if t.strip().startswith("rang"))
    entetes = COLONNES.split(sortie[depart].strip())

    lignes = [t for t in sortie[depart + 1:] if t.strip() and t.startswith("  ")]
    assert lignes, "le tableau par rang a disparu"
    for ligne in lignes[:len(Tier)]:
        cellules = COLONNES.split(ligne.strip())
        assert len(cellules) == len(entetes), (
            f"« {ligne.strip()} » a {len(cellules)} colonnes sous {len(entetes)} "
            f"en-tetes ({entetes}) : une colonne sans nom ne se lit pas.")


def test_la_colonne_de_reussite_est_nommee(tmp_path, capsys):
    sortie = _review(tmp_path, capsys, ouvertes=2, tranchees=4)
    entete = next(t for t in sortie.splitlines() if t.strip().startswith("rang"))

    assert "réussite" in entete


@pytest.mark.parametrize("rangs_vides", [True, False])
def test_un_rang_vide_garde_le_meme_nombre_de_colonnes(tmp_path, capsys, rangs_vides):
    """Les lignes en tirets doivent s'aligner comme les autres, sinon le tableau
    se lit de travers exactement les semaines ou il a le plus a dire."""
    sortie = _review(tmp_path, capsys, ouvertes=2, tranchees=4).splitlines()
    depart = next(index for index, t in enumerate(sortie) if t.strip().startswith("rang"))
    entetes = COLONNES.split(sortie[depart].strip())

    interessantes = [t for t in sortie[depart + 1:depart + 1 + len(Tier)]
                     if ("-" in t) is rangs_vides]
    for ligne in interessantes:
        assert len(COLONNES.split(ligne.strip())) == len(entetes), ligne
