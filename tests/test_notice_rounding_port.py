"""L'arrondi du port iOS doit rendre les mêmes nombres que le moteur.

Le port Swift ne peut pas être compilé ici : l'environnement n'a pas de
compilateur Swift et le réseau interdit d'en installer un. Ce que ce fichier
peut vérifier, en revanche, c'est l'arithmétique — parce qu'elle ne dépend pas
du langage. Python et Swift manipulent les mêmes doubles IEEE 754, et les deux
formatent en décimal par un `printf` à arrondi correct.

Ce que ces tests prouvent : la formule que `Numbers.round` emploie est
équivalente à `round()` de Python, et celle qu'elle remplace ne l'était pas.
Ce qu'ils ne prouvent pas : que le fichier Swift compile, ni qu'il emploie
bien cette formule. Ça, seul `Cmd + U` sur un Mac le dira — c'est le rôle de
`NoticeVectorTests`, et ce fichier existe pour que le vecteur qui l'y attend
soit lui-même vérifié.
"""
from __future__ import annotations

import itertools
import json
import math
import pathlib
import random

VECTORS = pathlib.Path(__file__).resolve().parent.parent / "ios/SingularSage/Resources/notice_vectors.json"

#: Le domaine réel : les probabilités que le curseur produit, par pas de 5 %.
SLIDER_PROBABILITIES = [index / 20 for index in range(1, 20)]


def multiply_then_round(value: float, places: int) -> float:
    """L'ancienne formule Swift : `(value * factor).rounded(.toNearestOrEven)`.

    Transcrite ici pour qu'on puisse montrer qu'elle est fausse, plutôt que
    l'affirmer. Sans ce témoin, un test qui compare la bonne formule à
    elle-même passerait toujours et ne dirait rien.
    """
    factor = 10.0**places
    scaled = value * factor
    floor = math.floor(scaled)
    remainder = scaled - floor
    if remainder > 0.5:
        floor += 1
    elif remainder == 0.5 and floor % 2 != 0:
        floor += 1
    return floor / factor


def format_then_parse(value: float, places: int) -> float:
    """La formule retenue : `Double(String(format: "%.<places>f", value))`."""
    if not math.isfinite(value):
        return value
    return float("%.*f" % (places, value))


def test_the_retained_formula_matches_the_reference_engine() -> None:
    """Sur tout ce que l'app peut produire, et bien au-delà."""
    random.seed(20260906)
    for places in (1, 2, 4):
        for _ in range(50_000):
            value = random.choice([
                random.randint(-100_000, 100_000) / 10_000,
                random.uniform(-1_000, 1_000),
                random.randint(0, 200_000) / 3,
                random.randint(0, 2_000) / 40,
            ])
            assert format_then_parse(value, places) == round(value, places), (
                f"{value!r} à {places} décimales")


def test_the_replaced_formula_really_was_wrong() -> None:
    """Le témoin. S'il cessait d'échouer, ces tests ne prouveraient plus rien.

    Le domaine est celui d'un journal ordinaire : quelques décisions annoncées
    au curseur, une partie qui arrive. La moyenne de ces probabilités n'est
    pas, elle, un multiple de 5 % — c'est justement là que la formule
    remplacée se déplaçait.
    """
    divergent = [
        (probabilities, hits)
        for count in range(3, 6)
        for probabilities in itertools.combinations_with_replacement(SLIDER_PROBABILITIES, count)
        for hits in range(count + 1)
        if multiply_then_round(sum(probabilities) / count - hits / count, 2)
        != round(sum(probabilities) / count - hits / count, 2)
    ]
    assert divergent, "la formule remplacée devrait diverger sur des écarts atteignables"

    # Et pas sur un cas de coin isolé : l'erreur était courante.
    assert len(divergent) > 1_000, f"seulement {len(divergent)} cas divergents"


def test_the_vector_actually_separates_the_two_formulas() -> None:
    """Le vecteur figé doit distinguer la bonne formule de la mauvaise.

    C'est le point du cas `arrondi_sur_une_moitie` : un port écrit avec la
    multiplication doit échouer dessus. S'il passait avec les deux, il ne
    protégerait de rien et sa présence serait trompeuse.
    """
    cases = json.loads(VECTORS.read_text(encoding="utf-8"))["cases"]
    case = next(c for c in cases if c["name"] == "arrondi_sur_une_moitie")

    settled = [entry for entry in case["entries"] if entry["resolved"] is not None]
    mean = sum(entry["probability"] for entry in settled) / len(settled)
    hit_rate = sum(1 for entry in settled if entry["resolved"]) / len(settled)
    gap = mean - hit_rate

    good, bad = format_then_parse(gap, 2), multiply_then_round(gap, 2)
    assert good != bad, "le vecteur ne distingue plus les deux formules"
    assert f"{good:+.0%}" in case["expected"]["headline"], (
        "le titre attendu ne porte plus le nombre que ce cas doit fixer")
    assert f"{bad:+.0%}" not in case["expected"]["headline"]
