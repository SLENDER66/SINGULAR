"""Un reproche prématuré est un bug — et il ne se corrigera plus au cas par cas.

Le défaut a été payé trois fois, dans trois formulations du même oubli :

1. « 4h engagées sans verdict — contre 0h qui ont produit ce que tu attendais »,
   affiché le lendemain de la première décision, dont l'échéance tombait treize
   jours plus tard. Rien n'aurait pu être tranché. Corrigé dans
   `_unresolved_hours_item`.
2. « Aucune décision sur Stabilité », en ATTENTION, en tête du même rapport, le
   même matin. La fondation a deux rangs et une ligne ne peut pas en occuper
   deux : le constat portait sur de l'arithmétique. Corrigé dans
   `foundation_item` — la correction du point 1 n'avait regardé qu'un endroit.
3. La même phrase, en rouge, dans `python -m singular review`, qui tenait sa
   propre copie de la règle : `list(Tier)[:2]`. Une copie ne se corrige pas en
   même temps que l'original ; elle attend d'être relue.

La règle du dépôt dit qu'à la troisième fois on cesse de corriger et on rend
l'erreur impossible. Ce fichier est cette tentative. Il ne vérifie pas que la
règle est juste — `test_sage_notice.py` s'en charge — il vérifie qu'elle n'a
qu'un seul domicile, et que ce qui s'affiche ailleurs vient de là.
"""
from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

from singular.__main__ import main
from singular.journal import DecisionJournal, Tier
from singular.sage.notice import FOUNDATION, foundation_item

RACINE = Path(__file__).resolve().parent.parent
DOMICILE = RACINE / "singular" / "sage" / "notice.py"
NOW = datetime(2026, 9, 6, 20, 0, tzinfo=UTC)


def _journal(tmp_path: Path) -> DecisionJournal:
    return DecisionJournal(tmp_path / "journal.db")


def _add(journal: DecisionJournal, *, tier: Tier, hours: float = 4.0, now: datetime = NOW):
    return journal.add(title="Une décision", action="faire la chose",
                       predicted="le résultat observable", probability=0.75, tier=tier,
                       cost_hours=hours, horizon_days=14, now=now)


# --- la règle n'a qu'un domicile ---------------------------------------------

def _slices_de_tier(source: Path) -> list[int]:
    """Les `list(Tier)[:2]` et consorts : une fondation redéduite à la main."""
    lignes: list[int] = []
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if not (isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice)):
            continue
        if "Tier" in ast.dump(node.value):
            lignes.append(node.lineno)
    return lignes


def test_aucun_module_ne_rededuit_les_rangs_fondateurs() -> None:
    """`list(Tier)[:2]` est la façon dont la troisième copie est née.

    Elle a l'air inoffensive et elle ne l'est pas : elle fixe la fondation
    ailleurs que là où elle est définie, donc elle survit à toute correction
    apportée à `FOUNDATION`, et elle emporte avec elle la condition — ou son
    absence — qui décide quand la dire.
    """
    for source in sorted((RACINE / "singular").rglob("*.py")):
        lignes = _slices_de_tier(source)
        assert not lignes, (
            f"{source.relative_to(RACINE)}:{lignes[0]} découpe les rangs à la main. "
            f"La fondation est `FOUNDATION` dans {DOMICILE.relative_to(RACINE)}, et la "
            "décision de la reprocher est `foundation_item`. Appelle-la.")


def test_la_phrase_ne_s_ecrit_qu_a_un_endroit() -> None:
    """Deux rédactions de la même observation divergent au premier oubli."""
    marqueur = "Ta constitution ouvre sur"
    ailleurs = [source.relative_to(RACINE)
                for source in sorted((RACINE / "singular").rglob("*.py"))
                if source != DOMICILE and marqueur in source.read_text(encoding="utf-8")]
    assert not ailleurs, (
        f"{ailleurs} réécrit la phrase du rang fondateur. Elle se lit sur "
        "`foundation_item(report)`, dont le titre et le détail sont déjà rédigés.")


# --- ce qui s'affiche vient bien de là ---------------------------------------

def test_review_ne_reproche_rien_le_lendemain_de_la_premiere_decision(tmp_path, capsys) -> None:
    """Le cas réel : une ligne écrite le 6 septembre au soir, relue le 7 au matin."""
    journal = _journal(tmp_path)
    _add(journal, tier=Tier.REVENUS, hours=4.0)

    assert main(["--db", str(tmp_path / "journal.db"), "review"]) == 0
    sortie = capsys.readouterr().out
    assert "Aucune décision sur" not in sortie, sortie


def test_review_dit_exactement_ce_que_dit_la_notice(tmp_path, capsys) -> None:
    """Le seul lien qui empêche les deux sorties de se séparer avec le temps."""
    journal = _journal(tmp_path)
    _add(journal, tier=Tier.REVENUS, hours=4.0)
    _add(journal, tier=Tier.PATRIMOINE, hours=30.0)

    attendu = foundation_item(journal.review(now=NOW + timedelta(days=1)))
    assert attendu is not None, "le cas choisi doit déclencher l'observation"

    assert main(["--db", str(tmp_path / "journal.db"), "review"]) == 0
    sortie = capsys.readouterr().out
    assert attendu.title in sortie, sortie
    assert attendu.detail in sortie, sortie
    assert "30h sont allées ailleurs" in sortie, "les heures nommées sont celles hors fondation"


def test_la_fondation_a_bien_plusieurs_rangs() -> None:
    """Le témoin du seuil : à un seul rang, « prématuré » ne voudrait plus rien dire."""
    assert len(FOUNDATION) >= 2
