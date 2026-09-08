"""Une règle affichée à deux endroits finit par dire deux choses.

Ce fichier ne teste pas une règle, il teste qu'il n'y en a qu'une. Le défaut
s'est produit trois fois, toujours de la même façon : une phrase du rapport est
corrigée, et la vignette dorée qui l'accompagne garde l'ancienne condition.

1. « Xh engagées sans verdict » a cessé de s'alarmer avant qu'un verdict ait pu
   être rendu ; la vignette voisine, elle, continuait de s'allumer dès la
   première décision. Gardé depuis par
   `test_the_hours_figure_waits_for_a_verdict_before_warning`.
2. « Aucune décision sur Stabilité » a cessé de reprocher un rang qu'une seule
   décision ne pouvait pas remplir ; `python -m singular review` tenait sa
   propre copie de la règle et reprochait toujours.
3. La calibration a cessé d'affirmer « ce n'est plus de la malchance » sur trois
   verdicts ; les deux vignettes — web et iOS — gardaient « écart ≥ 15 % et
   3 verdicts » et s'allumaient en alerte pendant que la phrase, juste en
   dessous, expliquait qu'il était trop tôt pour conclure.

Trois fois, donc on arrête de corriger. Le moteur calcule le verdict une fois,
les interfaces le lisent, et ce fichier échoue si l'une d'elles le refait.
"""
from __future__ import annotations

import json
import pathlib
import re
from datetime import UTC, datetime, timedelta

import pytest

from singular.journal import DecisionJournal, Tier
from singular.sage import build_notice
from singular.sage.notice import CALIBRATION_GAP, CALIBRATION_MINIMUM, calibration_verdict

RACINE = pathlib.Path(__file__).resolve().parent.parent
DOMICILE = RACINE / "singular/sage/notice.py"

#: Tout ce qui affiche la calibration sans être le moteur.
INTERFACES = [
    RACINE / "singular/sage/web/app.js",
    RACINE / "ios/SingularSage/App/BriefView.swift",
    RACINE / "singular/__main__.py",
]

#: Ce qui désigne la calibration dans une de ces interfaces.
PARLE_DE_CALIBRATION = re.compile(r"surconfiance|sous-confiance|overconfidence|calibration",
                                  re.IGNORECASE)

#: Un seuil comparé sur place : « >= 0.15 », « < 0.05 », « abs(gap) >= ... ».
COMPARE_UN_SEUIL = re.compile(r"[<>]=?\s*0\.\d|abs\([^)]*\)\s*[<>]|Math\.abs\(")


def _region_calibration(source: str) -> str:
    """Les lignes qui parlent de calibration, avec de quoi voir leur condition."""
    lignes = source.splitlines()
    garde = set()
    for index, ligne in enumerate(lignes):
        if PARLE_DE_CALIBRATION.search(ligne):
            garde.update(range(max(0, index - 4), min(len(lignes), index + 5)))
    return "\n".join(lignes[index] for index in sorted(garde))

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _journal(tmp_path, paris):
    journal = DecisionJournal(tmp_path / "journal.db")
    for index, (probability, gagne) in enumerate(paris):
        entry = journal.add(title=f"Pari {index}", action="faire", predicted="le résultat",
                            probability=probability, tier=Tier.REVENUS, cost_hours=2,
                            horizon_days=7, now=NOW + timedelta(days=index))
        journal.resolve(entry.entry_id, happened=gagne, now=NOW + timedelta(days=index + 8))
    return journal


# --- la règle n'est écrite qu'une fois ---------------------------------------

@pytest.mark.parametrize("interface", INTERFACES, ids=lambda p: p.name)
def test_no_interface_rewrites_the_calibration_rule(interface):
    """Les seuils appartiennent au moteur ; une interface lit son verdict.

    Le test ne cherche pas un nombre dans tout le fichier — `__main__.py` porte
    un `0.15` qui est le taux de base d'une candidature, sans rapport, et un
    test qui crie au loup finit désactivé. Il regarde les lignes qui parlent de
    calibration, et rien d'autre.
    """
    region = _region_calibration(interface.read_text(encoding="utf-8"))
    assert region, f"{interface.name} ne parle plus de calibration : ce test ne garde plus rien"

    assert "conclusive" in region, (
        f"{interface.relative_to(RACINE)} affiche la calibration sans lire le verdict "
        "du moteur. `calibration_verdict` le calcule une fois ; lis `conclusive`."
    )
    compare = COMPARE_UN_SEUIL.search(region)
    assert not compare, (
        f"{interface.relative_to(RACINE)} recompose la condition sur place "
        f"({compare.group(0)!r}). Deux écritures de la même règle finissent par "
        "dire deux choses : c'est arrivé trois fois, d'où ce test."
    )


def test_the_command_line_waits_for_a_verdict_before_going_red():
    """La même garde que la vignette de l'app, sur la ligne des heures.

    `python -m singular review` passait « 4h encore sans verdict » en rouge dès
    la première décision, alors que son échéance était dans deux semaines et que
    rien n'aurait pu être tranché. C'est le défaut déjà payé, à un quatrième
    endroit — le seul que personne ne regardait parce qu'il est au clavier.
    """
    source = (RACINE / "singular/__main__.py").read_text(encoding="utf-8")
    ligne = next((texte for texte in source.splitlines() if "warn = RED" in texte), None)
    assert ligne is not None, "la ligne des heures a changé de forme : ce test ne la voit plus"
    assert 'report["resolved"]' in ligne, (
        "la ligne des heures s'alarme avant qu'un verdict ait pu être rendu")


def test_the_engine_still_owns_the_thresholds():
    """Le témoin : sans lui, le test ci-dessus passerait sur un moteur vidé."""
    source = DOMICILE.read_text(encoding="utf-8")
    assert "CALIBRATION_GAP" in source and "CALIBRATION_HASARD" in source


# --- ce que l'interface reçoit correspond à ce que la phrase dit ---------------

def test_the_notice_hands_over_its_verdict(tmp_path):
    """La vignette a besoin du verdict, pas des ingrédients."""
    notice = build_notice(_journal(tmp_path, [(0.75, False)] * 3), now=NOW + timedelta(days=30))
    rendu = notice.as_dict()

    assert set(rendu["calibration"]) == {"gap", "chance", "conclusive"}
    assert rendu["calibration"]["conclusive"] is True
    # Sérialisable : c'est du JSON qui traverse le réseau local.
    assert json.loads(json.dumps(rendu))["calibration"] == rendu["calibration"]


def test_the_tile_and_the_sentence_never_disagree(tmp_path):
    """Le cœur du problème : une alerte dorée au-dessus d'un « trop tôt pour conclure ».

    Trois paris à 75 % dont un gagné : l'écart dépasse le seuil, donc l'ancienne
    vignette s'allumait ; mais le hasard seul produit cet écart une fois sur six,
    donc la phrase, elle, ne conclut pas.
    """
    journal = _journal(tmp_path, [(0.75, True), (0.75, False), (0.75, False)])
    notice = build_notice(journal, now=NOW + timedelta(days=30))
    verdict = notice.calibration

    assert verdict is not None
    assert abs(verdict["gap"]) >= CALIBRATION_GAP, "l'ancienne vignette se serait allumée"
    assert verdict["conclusive"] is False, "et la phrase disait l'inverse"

    dit = next(item for item in notice.items
               if "annonces plus" in item.title or "estimes" in item.title)
    assert dit.severity == "INFO"
    assert ("trop peu pour en conclure" in dit.detail) is not verdict["conclusive"]


def test_below_the_minimum_there_is_nothing_to_hand_over(tmp_path):
    journal = _journal(tmp_path, [(0.75, False)] * (CALIBRATION_MINIMUM - 1))
    assert build_notice(journal, now=NOW + timedelta(days=30)).calibration is None
    assert calibration_verdict(journal.review(now=NOW + timedelta(days=30))) is None
