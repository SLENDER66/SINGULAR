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

import pathlib
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


# --- un seul de quelque chose se dit au singulier ------------------------------

#: « 1 décisions », « 1 verdicts » : un chiffre juste dans une phrase fausse.
UN_PLURIEL = re.compile(r"\b1 ([a-zéèêàçîû]+)s\b")

#: Des mots qui finissent par s au singulier. « 1 mois » est correct.
EN_S_AU_SINGULIER = {"mois", "fois", "puis", "sans", "dans", "jamais", "plus", "moins",
                     "progres", "progrès", "succes", "succès"}


@pytest.mark.parametrize(("ouvertes", "tranchees"), [(1, 0), (0, 1), (1, 1)])
def test_un_seul_de_quelque_chose_ne_se_dit_pas_au_pluriel(tmp_path, capsys, ouvertes, tranchees):
    """Le bilan annonçait « 1 décisions   4h engagées » en tête de l'écran.

    Cinq pluriels étaient écrits à la main dans `__main__.py`, refaits sur place à
    chaque endroit. Trois étaient justes — c'est exactement la forme du défaut :
    une règle recopiée est juste la plupart du temps. Les deux autres s'affichaient
    le dimanche, et le jour de la reprise d'un journal.

    Le test ne liste pas les cas, il refuse la forme : un « 1 » suivi d'un mot au
    pluriel, où que ce soit dans la sortie. Le prochain pluriel oublié tombera
    ici sans que personne ait à y penser.

    Trois formes, parce qu'une seule ne suffisait pas : ma première version jouait
    une ouverte **et** une tranchée, donc le total valait deux et l'en-tête
    — « 1 décisions », la faute de départ — ne s'affichait jamais. Il faut un
    total de un pour l'atteindre, un seul verdict pour la ligne de calibration,
    et une seule ouverte pour celle des heures.
    """
    sortie = _review(tmp_path, capsys, ouvertes=ouvertes, tranchees=tranchees)

    fautes = [mot for mot in UN_PLURIEL.findall(sortie) if f"{mot}s" not in EN_S_AU_SINGULIER]
    assert not fautes, f"« 1 {fautes[0]}s » : un chiffre juste dans une phrase fausse"


def test_le_temoin_du_pluriel_attraperait_la_faute(tmp_path, capsys):
    """Sans lui, le test au-dessus passerait sur une sortie qui ne dit jamais « 1 »."""
    assert UN_PLURIEL.findall("  1 décisions   4h engagées") == ["décision"]
    assert UN_PLURIEL.findall("  1 décision   4h engagées") == []
    assert [m for m in UN_PLURIEL.findall("il y a 1 mois") if f"{m}s" not in EN_S_AU_SINGULIER] == []


# --- et « décision(s) », qui échappait au garde --------------------------------
#
# Le pluriel a un domicile depuis le 13 septembre, et trois phrases gardaient la
# forme parenthésée : `sj due` disait « 2 décision(s) encore dans les temps » et
# « 1 décision(s) attendent un verdict ». Ce n'est pas la même faute que
# « 1 décisions » — le garde au-dessus ne la voit pas, puisqu'il cherche un mot
# au pluriel — et c'est la même paresse : une règle recopiée, juste nulle part.
#
# Trouvé en lançant la commande, pas en relisant le code.

def test_les_echeances_se_disent_au_singulier_quand_il_n_y_en_a_qu_une(tmp_path, capsys):
    journal = DecisionJournal(tmp_path / "journal.db")
    # `due` lit l'horloge reelle, pas NOW : l'echeance doit etre devant nous,
    # sinon la decision est en retard et c'est l'autre phrase qui s'affiche.
    journal.add(title="La seule", action="a", predicted="b", probability=0.5,
                tier=Tier.REVENUS, cost_hours=1, horizon_days=9,
                now=datetime.now(UTC))
    capsys.readouterr()

    assert main(["--db", str(tmp_path / "journal.db"), "due"]) == 0
    sortie = capsys.readouterr().out
    assert "1 décision encore dans les temps" in sortie, sortie


def test_un_verdict_attendu_se_dit_au_singulier(tmp_path, capsys):
    """Le nom **et** le verbe : « 1 décision attendent » serait la meme faute."""
    journal = DecisionJournal(tmp_path / "journal.db")
    journal.add(title="En retard", action="a", predicted="b", probability=0.5,
                tier=Tier.REVENUS, cost_hours=1, horizon_days=1, now=NOW)
    capsys.readouterr()

    assert main(["--db", str(tmp_path / "journal.db"), "due"]) == 0
    sortie = capsys.readouterr().out
    assert "1 décision attend un verdict" in sortie, sortie


def test_aucune_phrase_du_clavier_ne_met_le_pluriel_entre_parentheses():
    """La forme est refusée à la source, pas commande par commande.

    Deux des trois phrases fautives étaient dans `due` et une dans `import` --
    celle-ci ne s'affiche qu'en reprenant un journal exporté, donc aucun
    scénario de test ne passait dessus. Un garde qui lit les chaînes du fichier
    les couvre toutes les trois, et celles que personne n'a encore écrites.
    """
    import ast

    source = (pathlib.Path(__file__).resolve().parent.parent
              / "singular/__main__.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    docstrings = {id(noeud.body[0].value) for noeud in ast.walk(arbre)
                  if isinstance(noeud, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
                  and noeud.body and isinstance(noeud.body[0], ast.Expr)
                  and isinstance(noeud.body[0].value, ast.Constant)
                  and isinstance(noeud.body[0].value.value, str)}

    fautifs = [noeud.value for noeud in ast.walk(arbre)
               if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str)
               and "(s)" in noeud.value and id(noeud) not in docstrings]

    assert not fautifs, (
        "ces phrases mettent le pluriel entre parentheses au lieu de passer par "
        f"`_pluriel` : {fautifs}")


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
