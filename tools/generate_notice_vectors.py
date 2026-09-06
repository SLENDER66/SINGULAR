"""Fige le comportement de la Notice sous forme de vecteurs, pour le port iOS.

Le moteur d'observation existe en Python, prouvé par sa propre suite de tests.
Il va exister une deuxième fois en Swift, sur le téléphone. Deux implémentations
de la même règle divergent au premier oubli, et une divergence ici ne plante
pas : elle donne un conseil légèrement faux, tous les matins, sans rien dire.

Ce script rend la divergence bruyante. Il décrit des journaux, calcule ce que la
Notice en dit, et écrit le tout en JSON. La suite Swift rejoue exactement les
mêmes journaux et exige exactement les mêmes phrases. Un seuil déplacé, un
accord oublié, une observation qui ne se déclenche plus : le test le nomme.

    python tools/generate_notice_vectors.py

Les vecteurs sont committés. `tests/test_notice_vectors.py` vérifie qu'ils
n'ont pas vieilli, pour qu'on ne puisse pas changer la règle sans les régénérer.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from singular.journal import DecisionJournal, Tier
from singular.sage import build_notice

VECTORS = Path(__file__).resolve().parent.parent / "ios" / "SingularSage" / "Resources" / "notice_vectors.json"

#: Un instant fixe : des vecteurs calculés « maintenant » changeraient à chaque
#: exécution et ne prouveraient plus rien.
ORIGIN = datetime(2026, 9, 6, 9, 0, tzinfo=UTC)


def _entry(title: str, *, tier: Tier, probability: float = 0.6, hours: float = 4.0,
           days: int = 14, created_offset: int = 0, resolved: bool | None = None,
           predicted: str = "le résultat observable") -> dict[str, Any]:
    return {
        "title": title,
        "action": "faire la chose",
        "predicted": predicted,
        "probability": probability,
        "tier": tier.value,
        "cost_hours": hours,
        "horizon_days": days,
        "created_offset_days": created_offset,
        "resolved": resolved,
    }


CASES: list[dict[str, Any]] = [
    {
        "name": "journal_vide",
        "why": "Sans entrées, on le dit une fois et on ne reproche rien d'autre.",
        "at_offset_days": 0,
        "entries": [],
    },
    {
        "name": "une_decision_en_retard",
        "why": "Le retard passe avant tout le reste, et il est écrit au singulier.",
        "at_offset_days": 9,
        "entries": [_entry("Refonte", tier=Tier.REVENUS, days=7)],
    },
    {
        "name": "retard_critique",
        "why": "Au-delà d'une semaine, ce n'est plus un oubli.",
        "at_offset_days": 20,
        "entries": [_entry("Refonte", tier=Tier.REVENUS, days=7)],
    },
    {
        "name": "deux_retards",
        "why": "Le pluriel, et le plus ancien qui donne le compte.",
        "at_offset_days": 12,
        "entries": [
            _entry("Refonte", tier=Tier.REVENUS, days=7),
            _entry("Formation", tier=Tier.CAPACITES, days=10),
        ],
    },
    {
        "name": "rangs_fondateurs_vides",
        "why": "Stabilité et Revenus vides est un défaut même quand tout va bien.",
        "at_offset_days": 1,
        "entries": [_entry("Patrimoine", tier=Tier.PATRIMOINE, hours=60.0, days=30)],
    },
    {
        "name": "un_seul_rang_fondateur_vide",
        "why": "Le singulier de la même observation.",
        "at_offset_days": 1,
        "entries": [_entry("Loyer", tier=Tier.STABILITE, days=30)],
    },
    {
        "name": "surconfiance",
        "why": "Quatre verdicts suffisent à le dire ; deux ne suffiraient pas.",
        "at_offset_days": 2,
        "entries": [
            _entry(f"Pari {index}", tier=Tier.REVENUS, probability=0.9, days=14, resolved=False)
            for index in range(4)
        ] + [_entry("Loyer", tier=Tier.STABILITE, days=30)],
    },
    {
        "name": "trop_peu_de_verdicts_pour_juger",
        "why": "Sous le seuil, l'échantillon explique l'écart aussi bien.",
        "at_offset_days": 2,
        "entries": [
            _entry(f"Pari {index}", tier=Tier.REVENUS, probability=0.9, days=14, resolved=False)
            for index in range(2)
        ] + [_entry("Loyer", tier=Tier.STABILITE, days=30)],
    },
    {
        "name": "tout_va_bien",
        "why": "Le Sage doit savoir se taire, sinon on cesse de le lire.",
        "at_offset_days": 1,
        "entries": [
            _entry("Loyer", tier=Tier.STABILITE, days=30, predicted="bail signé"),
            _entry("Client", tier=Tier.REVENUS, days=20, resolved=True),
        ],
    },
    {
        "name": "heures_sans_verdict",
        "why": "L'activité qui n'est jamais devenue un résultat.",
        "at_offset_days": 1,
        "entries": [
            _entry("Gros chantier", tier=Tier.STABILITE, hours=80.0, days=60),
            _entry("Client", tier=Tier.REVENUS, hours=2.0, days=20, resolved=True),
        ],
    },
]


def _build(case: dict[str, Any]) -> tuple[DecisionJournal, datetime]:
    journal = DecisionJournal(":memory:")
    for item in case["entries"]:
        created = ORIGIN + timedelta(days=item["created_offset_days"])
        entry = journal.add(
            title=item["title"], action=item["action"], predicted=item["predicted"],
            probability=item["probability"], tier=Tier(item["tier"]),
            cost_hours=item["cost_hours"], horizon_days=item["horizon_days"], now=created,
        )
        if item["resolved"] is not None:
            journal.resolve(entry.entry_id, happened=item["resolved"],
                            now=created + timedelta(days=item["horizon_days"]))
    return journal, ORIGIN + timedelta(days=case["at_offset_days"])


def build_vectors() -> dict[str, Any]:
    cases = []
    for case in CASES:
        journal, moment = _build(case)
        notice = build_notice(journal, now=moment)
        cases.append({
            "name": case["name"],
            "why": case["why"],
            "at": moment.isoformat(),
            "entries": case["entries"],
            "expected": {
                "headline": notice.headline,
                "severity": notice.severity,
                "items": [
                    {"severity": item.severity, "title": item.title, "detail": item.detail}
                    for item in notice.items
                ],
            },
        })
    return {
        "generated_by": "tools/generate_notice_vectors.py",
        "origin": ORIGIN.isoformat(),
        "note": "Régénérer avec `python tools/generate_notice_vectors.py` après toute "
                "modification de singular/sage/notice.py.",
        "cases": cases,
    }


def main() -> int:
    VECTORS.parent.mkdir(parents=True, exist_ok=True)
    VECTORS.write_text(json.dumps(build_vectors(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(CASES)} vecteurs écrits dans {VECTORS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
