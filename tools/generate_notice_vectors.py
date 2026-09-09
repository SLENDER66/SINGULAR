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
from singular.sage.notice import observations

VECTORS = Path(__file__).resolve().parent.parent / "ios" / "SingularSage" / "Resources" / "notice_vectors.json"

#: Un instant fixe : des vecteurs calculés « maintenant » changeraient à chaque
#: exécution et ne prouveraient plus rien.
ORIGIN = datetime(2026, 9, 6, 9, 0, tzinfo=UTC)

#: Ce que le port Swift ne sait pas encore produire, par le nom de la fonction
#: Python qui l'écrit, et pourquoi l'absence est acceptée.
#:
#: Aucun compilateur Swift n'est installable dans l'environnement qui écrit ce
#: dépôt : la passerelle refuse swift.org et les binaires GitHub, c'est vérifié.
#: Écrire ici du Swift qu'on ne peut ni compiler ni exécuter ajouterait du code
#: invérifiable à un port qui n'a jamais été compilé, pour une application qui ne
#: tourne sur aucune machine disponible. L'application web, elle, tourne et sert
#: ces deux observations aujourd'hui.
#:
#: La liste vit ici plutôt que dans les tests parce que c'est le générateur qui
#: doit la respecter : un vecteur qui exige une de ces observations fait échouer
#: la suite Swift sur un Mac, loin d'ici, sans que rien ne le dise ici.
#: `tests/test_notice_port_parity.py` la relit pour vérifier l'autre versant :
#: que l'écart déclaré est bien l'écart réel.
ABSENTES_DU_PORT = {
    "_irreversible_item": "engagement irréversible sans verdict",
    "_unpriced_item": "heures engagées sans gain attendu",
}


def _entry(title: str, *, tier: Tier, probability: float = 0.6, hours: float = 4.0,
           days: int = 14, created_offset: int = 0, created_hour: int = 0,
           resolved: bool | None = None, gain: float | None = 500.0,
           predicted: str = "le résultat observable") -> dict[str, Any]:
    """Une entrée du vecteur. `created_hour` décale l'écriture dans la journée.

    Sans lui, tous les journaux étaient écrits et relus à la même heure, et les
    deux moteurs tombaient d'accord pour une mauvaise raison : l'égalité exacte
    des instants masquait le fait qu'ils ne comptaient pas dans la même unité.
    C'est exactement le cas de Thomas — écrire le soir, lire le matin — qui
    manquait, et c'est là que l'échéance se trompait d'un jour.

    `gain` est chiffré par défaut, et ce n'est pas un détail de fixture : sans
    lui, la moitié des vecteurs déclenchaient `_unpriced_item`, que le port
    Swift ne produit pas. Les vecteurs committés exigeaient donc du port des
    phrases impossibles — le contrat entre les deux moteurs contredisait
    l'écart déclaré, et personne ne pouvait le voir sans un Mac. Un vecteur qui
    veut éprouver cette observation devra attendre que le port la porte : le
    garde-fou de `build_vectors` le refusera d'ici là.
    """
    return {
        "title": title,
        "action": "faire la chose",
        "predicted": predicted,
        "probability": probability,
        "tier": tier.value,
        "cost_hours": hours,
        "horizon_days": days,
        "created_offset_days": created_offset,
        "created_offset_hours": created_hour,
        "expected_gain_eur": gain,
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
        "why": "Stabilité et Revenus vides, avec des heures réellement passées ailleurs.",
        "at_offset_days": 1,
        "entries": [_entry("Patrimoine", tier=Tier.PATRIMOINE, hours=30.0, days=30),
                    _entry("Bourse", tier=Tier.PATRIMOINE, hours=30.0, days=30)],
    },
    {
        "name": "un_seul_rang_fondateur_vide",
        "why": "Le singulier de la même observation.",
        "at_offset_days": 1,
        "entries": [_entry("Loyer", tier=Tier.STABILITE, days=30),
                    _entry("Patrimoine", tier=Tier.PATRIMOINE, days=30)],
    },
    {
        "name": "un_rang_fondateur_vide_sans_heures_ailleurs",
        "why": "Rien n'est allé ailleurs : le rang manque, on le dit, on ne le reproche pas.",
        "at_offset_days": 1,
        "entries": [_entry("Postuler", tier=Tier.REVENUS, days=30),
                    _entry("Relancer", tier=Tier.REVENUS, days=30)],
    },
    {
        "name": "une_seule_decision_ne_peut_pas_couvrir_deux_rangs",
        "why": "Le lendemain de la première ligne, aucun rang vide ne se reproche.",
        "at_offset_days": 1,
        "entries": [_entry("Postuler", tier=Tier.REVENUS, probability=0.75, days=14)],
    },
    {
        "name": "ecrite_le_soir_relue_le_matin_de_l_echeance",
        "why": "Le jour dit, dès le matin : l'horizon est en jours, il tombe un jour.",
        "at_offset_days": 14,
        "entries": [_entry("Postuler", tier=Tier.REVENUS, probability=0.75, hours=4.0,
                           days=14, created_hour=11, predicted="Un entretien")],
    },
    {
        "name": "ecrite_le_soir_relue_la_veille_au_soir",
        "why": "Et pas la veille : le versant qui prouve que le seuil n'a pas glissé.",
        "at_offset_days": 13,
        "entries": [_entry("Postuler", tier=Tier.REVENUS, probability=0.75, hours=4.0,
                           days=14, created_hour=11, predicted="Un entretien")],
    },
    {
        "name": "ecart_qui_peut_encore_etre_du_hasard",
        "why": "Un pari sur trois gagné quand on en annonçait trois quarts : le hasard "
               "seul fait ça une fois sur six. On montre l'écart, on ne conclut pas.",
        "at_offset_days": 2,
        "entries": [
            _entry(f"Pari {index}", tier=Tier.REVENUS, probability=0.75, days=1,
                   resolved=index == 0)
            for index in range(3)
        ],
    },
    {
        "name": "un_pari_sur_qui_tombe",
        "why": "Deux paris à 5 % et un à 95 %, aucun tenu. C'est le 95 % qui parle : "
               "une moyenne les ramènerait tous à 35 % et effacerait le signal.",
        "at_offset_days": 2,
        "entries": [
            _entry("Pari long 1", tier=Tier.REVENUS, probability=0.05, days=1, resolved=False),
            _entry("Pari long 2", tier=Tier.REVENUS, probability=0.05, days=1, resolved=False),
            _entry("Pari sûr", tier=Tier.REVENUS, probability=0.95, days=1, resolved=False),
        ],
    },
    {
        "name": "surconfiance",
        "why": "Quatre paris à 90 % tous perdus : une fois sur dix mille. Là, on conclut.",
        "at_offset_days": 2,
        "entries": [
            _entry(f"Pari {index}", tier=Tier.REVENUS, probability=0.9, days=14, resolved=False)
            for index in range(4)
        ] + [_entry("Loyer", tier=Tier.STABILITE, days=30)],
    },
    {
        "name": "arrondi_sur_une_moitie",
        "why": "L'écart tombe pile sur une moitié : 0,475 → +47 %, pas +48 %. "
               "Un port qui multiplie par 100 avant d'arrondir bascule ici, "
               "et se trompe d'un point tous les matins sans rien signaler. "
               "Huit paris et un seul gagné : assez pour que le titre porte le "
               "nombre, ce qui est la seule raison d'être de ce cas.",
        "at_offset_days": 2,
        "entries": [
            _entry(f"Pari {index}", tier=Tier.REVENUS, probability=0.6, days=1,
                   resolved=index == 0)
            for index in range(8)
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
        "name": "chaine_rompue",
        "why": "L'observation la plus grave, et la seule qui invalide toutes les autres. "
               "Elle passe avant le retard, et elle est CRITIQUE quoi qu'il y ait d'autre.",
        "at_offset_days": 20,
        "chain_intact": False,
        "entries": [
            _entry("Refonte", tier=Tier.REVENUS, days=7),
            _entry("Loyer", tier=Tier.STABILITE, days=30),
        ],
    },
    {
        "name": "premiere_decision_sans_reproche",
        "why": "Le cas réel du premier matin : une décision ouverte, échéance "
               "lointaine, rien de tranché. Le Sage n'a rien à reprocher — un "
               "verdict qu'on ne pouvait pas rendre n'est pas une faute.",
        "at_offset_days": 1,
        "entries": [
            _entry("Postuler", tier=Tier.REVENUS, probability=0.75, hours=4.0, days=14,
                   predicted="Un entretien"),
        ],
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
    first = None
    for item in case["entries"]:
        created = ORIGIN + timedelta(days=item["created_offset_days"],
                                     hours=item.get("created_offset_hours", 0))
        entry = journal.add(
            title=item["title"], action=item["action"], predicted=item["predicted"],
            probability=item["probability"], tier=Tier(item["tier"]),
            cost_hours=item["cost_hours"], horizon_days=item["horizon_days"],
            expected_gain_eur=item.get("expected_gain_eur"), now=created,
        )
        if item["resolved"] is not None:
            journal.resolve(entry.entry_id, happened=item["resolved"],
                            now=created + timedelta(days=item["horizon_days"]))
        first = first or entry
    if case.get("chain_intact", True) is False:
        # On écrit sous le journal plutôt qu'à travers lui : rien dans l'API ne
        # réécrit une entrée, c'est le seul chemin qui existe, et c'est celui
        # que prendrait quelqu'un qui ouvrirait le fichier.
        #
        # Ce qu'on retouche est le maillon, pas la donnée. Une entrée manquante
        # ou déplacée casse la chaîne exactement ainsi, et surtout : le port
        # rejouera ces entrées à leurs valeurs déclarées, qui sont celles
        # d'origine. Retoucher une probabilité ferait calculer le rapport de
        # référence sur une valeur que le port n'a pas, et les phrases
        # divergeraient pour une raison qui n'a rien à voir avec la règle.
        assert first is not None, "un journal vide n'a pas de chaîne à rompre"
        before = journal.review(now=ORIGIN)
        with journal._connect() as conn:
            conn.execute("UPDATE journal_entries SET previous_fingerprint=? WHERE entry_id=?",
                         ("0" * 64, first.entry_id))
        assert not journal.verify(), "la chaîne devait être rompue"

        # Et rien d'autre ne doit avoir bougé : si la rupture déplaçait un
        # chiffre, le vecteur exigerait du port des phrases qu'il ne peut pas
        # produire à partir des entrées qu'on lui donne.
        after = journal.review(now=ORIGIN)
        assert {k: v for k, v in before.items() if k != "chain_intact"} \
            == {k: v for k, v in after.items() if k != "chain_intact"}, \
            "rompre la chaîne a changé autre chose que l'intégrité"
    return journal, ORIGIN + timedelta(days=case["at_offset_days"])


def build_vectors() -> dict[str, Any]:
    cases = []
    for case in CASES:
        journal, moment = _build(case)
        notice = build_notice(journal, now=moment)
        _refuse_les_absentes(case["name"], journal, moment)
        cases.append({
            "name": case["name"],
            "why": case["why"],
            "at": moment.isoformat(),
            "chain_intact": notice.report["chain_intact"],
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


def _refuse_les_absentes(nom: str, journal: DecisionJournal, moment: datetime) -> None:
    """Un vecteur ne demande jamais au port une observation qu'il n'a pas.

    C'est le garde-fou qui manquait. Les vecteurs sont générés depuis Python et
    rejoués par la suite Swift, qui exige exactement les mêmes phrases : un
    vecteur déclenchant une observation absente du port échoue sur un Mac, chez
    quelqu'un d'autre, un jour indéterminé — c'est-à-dire nulle part et jamais.
    """
    produites = set(observations(journal, now=moment)) & set(ABSENTES_DU_PORT)
    if not produites:
        return
    raisons = ", ".join(f"{nom_fonction} ({ABSENTES_DU_PORT[nom_fonction]})"
                        for nom_fonction in sorted(produites))
    raise AssertionError(
        f"le vecteur « {nom} » déclenche {raisons}, que le port Swift ne produit pas. "
        "Change les entrées du cas pour ne plus la déclencher, ou implémente "
        "l'observation côté Swift et retire-la de ABSENTES_DU_PORT.")


def main() -> int:
    VECTORS.parent.mkdir(parents=True, exist_ok=True)
    VECTORS.write_text(json.dumps(build_vectors(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(CASES)} vecteurs écrits dans {VECTORS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
