"""Les vecteurs figés pour iOS doivent rester le reflet du moteur Python.

Ils existent parce que la Notice va vivre deux fois : ici, et en Swift sur le
téléphone. Des vecteurs périmés seraient pires que pas de vecteurs -- la suite
Swift passerait au vert en confirmant une règle que Python n'applique plus.

Ce test échoue dès que `singular/sage/notice.py` change sans que les vecteurs
soient régénérés :

    python tools/generate_notice_vectors.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from singular.journal import Tier
from singular.sage.notice import observations
from tools import generate_notice_vectors as generateur
from tools.generate_notice_vectors import (
    ABSENTES_DU_PORT,
    CASES,
    VECTORS,
    _build,
    _entry,
    build_vectors,
)


def test_the_committed_vectors_match_the_engine():
    if not VECTORS.exists():
        pytest.fail("les vecteurs sont absents : lance python tools/generate_notice_vectors.py")
    committed = json.loads(Path(VECTORS).read_text(encoding="utf-8"))
    assert committed["cases"] == build_vectors()["cases"], (
        "la Notice a changé depuis la dernière génération des vecteurs ; "
        "relance python tools/generate_notice_vectors.py"
    )


def test_every_vector_asserts_something():
    """Un vecteur sans attente ne prouve rien et donnerait un faux vert."""
    for case in build_vectors()["cases"]:
        assert case["expected"]["headline"].startswith("Notice.")
        assert case["expected"]["severity"] in {"CRITIQUE", "ATTENTION", "INFO"}
        assert case["why"].strip(), f"{case['name']} n'explique pas ce qu'il défend"


def test_the_vectors_cover_both_sides_of_each_rule():
    """Chaque règle doit avoir un cas qui la déclenche et un qui ne la déclenche pas."""
    cases = {case["name"]: case for case in build_vectors()["cases"]}
    titles = {name: {item["title"] for item in case["expected"]["items"]}
              for name, case in cases.items()}

    assert any("surestimes" in title for title in titles["surconfiance"])
    assert not any("surestimes" in title for title in titles["trop_peu_de_verdicts_pour_juger"])
    assert any(title.startswith("Aucune décision sur") for title in titles["rangs_fondateurs_vides"])
    assert not any(title.startswith("Aucune décision sur") for title in titles["tout_va_bien"])
    # Le rang vide a deux versants depuis qu'il ne se reproche plus tout seul :
    # il se dit quand rien n'est allé ailleurs, il se tait quand une seule
    # décision ne pouvait pas couvrir deux rangs. Le port doit tenir les deux,
    # et un seuil déplacé d'un côté se verra ici.
    sans_ailleurs = cases["un_rang_fondateur_vide_sans_heures_ailleurs"]["expected"]["items"]
    dit = next(item for item in sans_ailleurs if item["title"].startswith("Aucune décision sur"))
    assert dit["severity"] == "INFO" and "ailleurs" not in dit["detail"]
    assert not any(title.startswith("Aucune décision sur")
                   for title in titles["une_seule_decision_ne_peut_pas_couvrir_deux_rangs"])
    assert any("trancher" in title for title in titles["une_decision_en_retard"])
    assert not any("trancher" in title for title in titles["tout_va_bien"])


def test_the_vectors_cover_the_broken_chain():
    """L'observation la plus grave doit être figée comme les autres.

    Elle est la seule qui invalide toutes les autres, et la seule que le
    générateur doit fabriquer en écrivant sous le journal. Sans un cas, le port
    pourrait ne jamais la produire et la suite Swift resterait verte.
    """
    cases = {case["name"]: case for case in build_vectors()["cases"]}
    broken = cases["chaine_rompue"]

    assert broken["chain_intact"] is False
    items = broken["expected"]["items"]
    assert items[0]["title"] == "La chaîne du journal est rompue"
    assert items[0]["severity"] == "CRITIQUE"
    assert broken["expected"]["severity"] == "CRITIQUE"

    # Elle passe devant un retard déjà critique : c'est l'ordre de
    # construction qui départage à gravité égale, et un tri instable côté port
    # inverserait ces deux-là sans rien casser d'autre.
    assert [item["title"] for item in items[:2]] == [
        "La chaîne du journal est rompue", "À trancher aujourd'hui"]

    assert all(case["chain_intact"] is True
               for name, case in cases.items() if name != "chaine_rompue"), (
        "un journal écrit à travers l'API doit se vérifier")


def test_no_vector_expects_a_number_the_port_cannot_reach():
    """Le port reconstruit chaque journal à partir des seules entrées du vecteur.

    Le générateur, lui, écrit parfois sous le journal — c'est le seul moyen de
    rompre une chaîne. Si cette écriture déplaçait un chiffre du rapport, les
    phrases attendues seraient hors de portée du port : il rejouerait des
    entrées correctes et échouerait quand même, en accusant la règle plutôt
    que le vecteur.

    On le vérifie en reconstruisant le même journal sans altération et en
    comparant les rapports. Seule l'intégrité a le droit de différer.
    """
    for spec in CASES:
        altered, moment = _build(spec)
        clean, _ = _build({**spec, "chain_intact": True})
        expected = {key: value for key, value in altered.review(now=moment).items()
                    if key != "chain_intact"}
        obtained = {key: value for key, value in clean.review(now=moment).items()
                    if key != "chain_intact"}
        assert expected == obtained, (
            f"{spec['name']} : le rapport de référence dépend d'une donnée que "
            "le vecteur ne transmet pas")


# --- aucun vecteur ne réclame au port ce qu'il ne sait pas produire -----------

#: Un cas qui déclenche `_unpriced_item` : un gros chantier sans gain estimé.
CAS_INTERDIT = {
    "name": "cas_qui_reclame_une_observation_absente",
    "why": "fabriqué par le test, jamais committé",
    "at_offset_days": 1,
    "entries": [_entry("Chantier", tier=Tier.REVENUS, hours=40.0, days=30, gain=None)],
}


def test_les_vecteurs_committes_ne_reclament_rien_d_absent():
    """Le contrat entre les deux moteurs ne doit pas contredire l'écart déclaré.

    Il l'a fait longtemps : `ABSENTES_DU_PORT` déclarait deux observations
    manquantes côté Swift pendant que cinq vecteurs committés les exigeaient.
    La suite Swift échouait pour de bon — sur un Mac, chez quelqu'un d'autre,
    c'est-à-dire nulle part.
    """
    for case in CASES:
        journal, moment = _build(case)
        produites = set(observations(journal, now=moment)) & set(ABSENTES_DU_PORT)
        assert not produites, f"{case['name']} réclame {sorted(produites)}"


def test_le_generateur_refuse_d_ecrire_un_vecteur_impossible(monkeypatch):
    """Le garde-fou, éprouvé sur un cas qui le déclenche vraiment."""
    monkeypatch.setattr(generateur, "CASES", [*CASES, CAS_INTERDIT])

    with pytest.raises(AssertionError) as refus:
        build_vectors()

    assert CAS_INTERDIT["name"] in str(refus.value)
    assert "_unpriced_item" in str(refus.value)


def test_le_cas_interdit_declenche_bien_ce_qu_on_croit():
    """Le témoin : sans lui, un cas devenu inoffensif ferait passer le test ci-dessus."""
    journal, moment = _build(CAS_INTERDIT)
    assert "_unpriced_item" in observations(journal, now=moment)


def test_l_ecart_declare_n_est_pas_vide():
    """Et le témoin du témoin : une liste vide rendrait tout ce qui précède creux."""
    assert ABSENTES_DU_PORT
