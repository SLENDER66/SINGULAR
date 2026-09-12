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

4. Le retard : `python -m singular due` passait une échéance au rouge après
   « 7 jours », écrit en toutes lettres dans la commande, pendant que le
   rapport escalade en CRITIQUE au-delà de `LATE_DAYS`. Deux copies du même
   nombre : déplacer le seuil aurait teint la ligne sur l'ancien.

Quatre fois, donc on arrête de corriger. Le moteur calcule le verdict une fois,
les interfaces le lisent, et ce fichier échoue si l'une d'elles le refait.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from datetime import UTC, datetime, timedelta

import pytest

from singular.journal import DecisionJournal, Tier
from singular.sage import build_notice
from singular.sage import notice as notice_module
from singular.sage.notice import (
    CALIBRATION_GAP,
    CALIBRATION_HASARD,
    CALIBRATION_MINIMUM,
    calibration_verdict,
)

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
    assert "LATE_DAYS" in source


# --- le retard : le même seuil que le rapport ---------------------------------

#: Une variable de retard comparée à un nombre écrit sur place.
COMPARE_UN_RETARD = re.compile(
    r"\b(?:late|overdue\w*|retard\w*|worst)\b\s*[<>]=?\s*(\d+)"
    r"|(\d+)\s*[<>]=?\s*\b(?:late|overdue\w*|retard\w*|worst)\b")


@pytest.mark.parametrize("interface", INTERFACES, ids=lambda p: p.name)
def test_no_interface_rewrites_the_late_threshold(interface):
    """« En retard » et « trop en retard » ne sont pas la même question.

    Comparer un retard à zéro reste permis : c'est la ligne échue, que les trois
    interfaces affichent. Le comparer à autre chose, c'est refaire l'escalade du
    rapport avec sa propre copie du nombre.
    """
    for ligne in interface.read_text(encoding="utf-8").splitlines():
        trouve = COMPARE_UN_RETARD.search(ligne)
        if trouve is None:
            continue
        seuil = trouve.group(1) or trouve.group(2)
        assert int(seuil) == 0, (
            f"{interface.relative_to(RACINE)} compare un retard à {seuil} : "
            f"{ligne.strip()!r}. Le seuil d'escalade appartient au moteur "
            "(`LATE_DAYS`), sinon la ligne rougit sur un nombre et le rapport "
            "s'alarme sur un autre.")


def test_the_command_line_reddens_where_the_notice_escalates(tmp_path, monkeypatch, capsys):
    """Preuve par déplacement : on bouge le seuil, les deux doivent suivre.

    Le test ne vérifie pas que le rouge tombe sur sept jours — il vérifie qu'il
    tombe au même endroit que le CRITIQUE du rapport, quel que soit l'endroit.
    C'est ce qu'une deuxième copie du nombre ne peut pas tenir.
    """
    from singular import __main__ as cli

    monkeypatch.setattr(notice_module, "LATE_DAYS", 3)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    maintenant = datetime.now(UTC)

    for retard, attendu_rouge in ((3, False), (4, True)):
        journal = DecisionJournal(tmp_path / f"retard{retard}.db")
        journal.add(title="Rendre le verdict", action="trancher", predicted="oui",
                    probability=0.5, tier=Tier.REVENUS, cost_hours=1, horizon_days=7,
                    now=maintenant - timedelta(days=7 + retard))
        capsys.readouterr()
        cli.cmd_due(journal, argparse.Namespace())
        ligne = next(texte for texte in capsys.readouterr().out.splitlines()
                     if f"+{retard}j" in texte)

        severite = next(item.severity for item in build_notice(journal, now=maintenant).items
                        if item.title == "À trancher aujourd'hui")
        assert (severite == "CRITIQUE") is attendu_rouge, "le rapport a changé d'avis"
        assert (cli.RED in ligne) is attendu_rouge, (
            f"retard de {retard} jours : le rapport dit {severite}, la commande "
            f"affiche {'du rouge' if cli.RED in ligne else 'du jaune'}")


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


# --- « conclusif » veut dire démontré, et rien d'autre -------------------------

def test_un_ecart_prouve_se_dit_meme_quand_il_est_petit(tmp_path):
    """Le cas sur lequel le Sage se taisait, et la raison d'être du journal.

    Seize paris annoncés à 95 %, trois perdus : quatorze points d'écart, que le
    hasard seul produirait une fois sur vingt-trois. Sous les quinze points de
    `CALIBRATION_GAP`, donc rien ne s'affichait — dans l'outil construit pour
    répondre à « est-ce que mes 70 % arrivent sept fois sur dix ? ».

    Thomas a tranché le 9 septembre : le Sage parle dès que c'est prouvé.
    """
    journal = _journal(tmp_path, [(0.95, index >= 3) for index in range(16)])
    notice = build_notice(journal, now=NOW + timedelta(days=40))
    verdict = notice.calibration

    assert verdict is not None
    assert abs(verdict["gap"]) < CALIBRATION_GAP, "le cas doit rester sous l'ancien seuil"
    assert verdict["chance"] <= CALIBRATION_HASARD, "et rester démontré"
    assert verdict["conclusive"] is True

    dit = next(item for item in notice.items if "surestimes" in item.title)
    assert dit.severity == "ATTENTION"
    assert "plus de la malchance" in dit.detail


def test_un_ecart_petit_et_non_prouve_reste_muet(tmp_path):
    """L'autre versant : sans lui, « dès que c'est prouvé » deviendrait « toujours ».

    Quatre paris à 60 % dont un perdu de plus que prévu : l'écart existe, le
    hasard l'explique une fois sur trois. Rien ne doit s'afficher.
    """
    journal = _journal(tmp_path, [(0.6, True), (0.6, True), (0.6, False), (0.6, False)])
    notice = build_notice(journal, now=NOW + timedelta(days=40))
    verdict = notice.calibration

    assert verdict is not None
    assert verdict["chance"] > CALIBRATION_HASARD
    assert verdict["conclusive"] is False
    assert not [item for item in notice.items if "surestimes" in item.title]


def test_le_seuil_voyant_garde_son_autre_emploi(tmp_path):
    """Montrer un écart voyant sans conclure : la correction précédente tient.

    Trois paris à 75 %, un seul gagné. L'écart saute aux yeux, le hasard seul le
    produit une fois sur six. On le montre, on ne conclut pas.
    """
    journal = _journal(tmp_path, [(0.75, True), (0.75, False), (0.75, False)])
    notice = build_notice(journal, now=NOW + timedelta(days=40))

    assert notice.calibration["conclusive"] is False
    dit = next(item for item in notice.items if "annonces plus" in item.title)
    assert dit.severity == "INFO"
    assert "trop peu pour en conclure" in dit.detail


def test_le_port_ios_applique_la_meme_condition():
    """La règle vit deux fois : ici et en Swift. Elle doit dire la même chose.

    Les vecteurs le prouvent sur un Mac ; ce test le lit ici, aujourd'hui, parce
    qu'aucun compilateur Swift n'est installable dans cet environnement.
    """
    swift = (RACINE / "ios/SingularSage/Core/Notice.swift").read_text(encoding="utf-8")
    assert "conclusive: hasard <= calibrationHasard && abs(gap) >= calibrationArrondi" in swift, (
        "le port conclut encore sur `calibrationGap` : un écart démontré de dix "
        "points parlerait sur le PC et se tairait sur le téléphone")
    assert "verdict.conclusive || abs(verdict.gap) >= calibrationGap" in swift
