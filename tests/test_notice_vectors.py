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

from tools.generate_notice_vectors import VECTORS, build_vectors


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
    assert any("trancher" in title for title in titles["une_decision_en_retard"])
    assert not any("trancher" in title for title in titles["tout_va_bien"])
