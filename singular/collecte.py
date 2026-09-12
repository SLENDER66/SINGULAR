"""Le Scout : il collecte, il n'agit jamais.

Le troisième rôle que SINGULAR n'avait pas. Le journal sait ce que Thomas y
écrit ; la Notice le lui relit. Rien n'allait chercher un fait **hors** du
journal, et sa recherche d'emploi vivait donc dans un terminal, sur un autre
écran, dans un fichier que rien ne lisait.

Trois règles, et elles sont structurelles plutôt que promises :

**Lecture seule.** Ce module n'écrit nulle part. Il ne connaît ni `open(...,
"w")`, ni le journal, ni aucune faculté qui dépense. `tests/test_collecte.py`
le vérifie sur l'arbre syntaxique, comme `test_sage_independence.py` le fait
pour le cœur déterministe -- une consigne se lit ou ne se lit pas, un test
échoue.

**Chaque fait porte sa source et sa date.** Un chiffre sans provenance est un
chiffre qu'on ne peut pas contredire, et c'est exactement ce que ce dépôt
reproche à une déduction non demandée.

**Ce qui n'est pas vérifiable est marqué, jamais estimé.** Un fichier illisible
donne un fait `verifie=False` qui dit ce qui s'est passé. Il ne donne pas zéro :
zéro est un chiffre, et un zéro inventé ressemble à un zéro vrai.

**Il ne juge pas.** « Trois candidatures envoyées, la plus ancienne il y a douze
jours » est un fait. « Il faut les relancer » est un jugement, et le seuil qui
le déclenche vit chez celui qui juge -- aujourd'hui `proto/suivi_candidatures.py`.
Recopier ce seuil ici serait la neuvième occurrence d'une règle à deux
domiciles dans ce dépôt.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

#: Le suivi de candidatures, écrit par `proto/suivi_candidatures.py`.
#:
#: Le Scout lit le **fichier**, pas le module. Le prototype est déclaré jetable
#: par `proto/README.md`, et `tests/test_proto_suivi.py` lui interdit d'importer
#: quoi que ce soit du paquet -- il doit tourner seul dans a-Shell. Dépendre de
#: son code mettrait SINGULAR à la merci d'un fichier qu'on a le droit de
#: supprimer ; dépendre de ses données, non : elles sont à Thomas.
CANDIDATURES = Path.home() / ".singular" / "candidatures.json"

#: Le code de statut tel qu'il s'écrit dans le fichier, et son mot français.
#:
#: Deuxième copie assumée de `STATUTS` dans `proto/suivi_candidatures.py`, pour
#: la même raison que la copie JavaScript de `CONFLIT` : l'original ne peut pas
#: être importé. Le prototype doit tourner seul dans a-Shell, et
#: `tests/test_proto_suivi.py` lui interdit d'importer quoi que ce soit du
#: paquet. Une copie qu'on ne peut pas éviter se garde par un test, pas par la
#: vigilance : `tests/test_collecte.py` les compare clé par clé.
STATUTS = {
    "a_envoyer": "à envoyer",
    "envoyee": "envoyée",
    "relancee": "relancée",
    "entretien": "entretien",
    "refus": "refus",
    "sans_suite": "sans suite",
}


@dataclass(frozen=True)
class Fait:
    """Une observation, d'où elle vient, et de quand elle date.

    `verifie=False` est le « UNAVAILABLE » du Scout : le fait n'a pas pu être
    établi, et il le dit au lieu de se taire ou d'estimer.
    """

    sujet: str
    texte: str
    source: str
    date: str = ""
    verifie: bool = True
    #: Les nombres derriere la phrase, pour qui doit en juger.
    #:
    #: Le Scout ne juge pas, mais le Conseiller doit pouvoir le faire sans
    #: relire le fichier lui-meme -- deux lectures de la meme source finiraient
    #: par diverger. Le fait se dit donc deux fois : en francais pour l'ecran,
    #: en chiffres pour celui qui decide.
    mesure: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.sujet.strip():
            raise ValueError("un fait sans sujet ne se range nulle part")
        if not self.texte.strip():
            raise ValueError("un fait sans texte n'apprend rien")
        if not self.source.strip():
            raise ValueError("un fait sans source est un fait qu'on ne peut pas contredire")


def _jours(depuis: str, aujourdhui: date) -> int | None:
    """L'âge d'une date ISO, ou None si elle n'en est pas une.

    Le fichier est écrit par un autre programme et relu par un humain : une
    date abîmée ne doit pas faire tomber la collecte, elle doit rendre le fait
    non vérifié.
    """
    try:
        return (aujourdhui - datetime.fromisoformat(depuis).date()).days
    except (TypeError, ValueError):
        return None


def _age(candidatures: list[dict], aujourdhui: date) -> tuple[str, int | None]:
    """La date de mouvement la plus ancienne du lot, et son âge."""
    dates = [c.get("date_statut", "") for c in candidatures]
    connues = sorted(d for d in dates if _jours(d, aujourdhui) is not None)
    if not connues:
        return "", None
    return connues[0], _jours(connues[0], aujourdhui)


def candidatures(chemin: Path | None = None, *,
                 aujourdhui: date | None = None) -> tuple[Fait, ...]:
    """Ce que le suivi de candidatures dit, sans rien en conclure."""
    source = Path(chemin) if chemin is not None else CANDIDATURES
    # Le jour d'UTC, comme `Entry.due_on` : le journal compte ses échéances
    # ainsi, et deux « aujourd'hui » différents se contrediraient près de
    # minuit sur le même écran.
    jour = aujourdhui or datetime.now(UTC).date()

    if not source.exists():
        # L'absence est un fait vérifié, et il vaut mieux que zéro : « aucun
        # suivi ici » et « zéro candidature » ne demandent pas le même geste.
        return (Fait("candidatures", "aucun suivi de candidatures sur cette machine",
                     str(source), jour.isoformat()),)
    try:
        donnees = json.loads(source.read_text(encoding="utf-8"))
        lot = list(donnees["candidatures"])
        cv = dict(donnees.get("cv") or {})
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as panne:
        return (Fait("candidatures", f"suivi illisible : {type(panne).__name__}",
                     str(source), jour.isoformat(), verifie=False),)

    faits: list[Fait] = []
    par_statut: dict[str, list[dict]] = {}
    for c in lot:
        par_statut.setdefault(str(c.get("statut", "?")), []).append(c)

    for statut in sorted(par_statut):
        groupe = par_statut[statut]
        depuis, age = _age(groupe, jour)
        combien = f"{len(groupe)} candidature{'s' if len(groupe) > 1 else ''}"
        # Un code inconnu se montre tel quel plutôt que d'être traduit de
        # travers : le fichier peut venir d'une version plus récente.
        mot = STATUTS.get(statut, statut)
        if age is None:
            faits.append(Fait("candidatures", f"{combien} en « {mot} », sans date lisible",
                              str(source), "", verifie=False,
                              mesure={"statut": statut, "combien": len(groupe)}))
        else:
            faits.append(Fait("candidatures",
                              f"{combien} en « {mot} », la plus ancienne depuis "
                              f"{age} jour{'s' if age > 1 else ''}",
                              str(source), depuis,
                              mesure={"statut": statut, "combien": len(groupe),
                                      "age_max": age}))

    for nom in sorted(cv):
        etapes = cv[nom] or []
        faites = sum(1 for e in etapes if isinstance(e, dict) and e.get("fait"))
        accord = "" if faites <= 1 else "s"
        faits.append(Fait("cv", f"CV {nom} : {faites} étape{accord} faite{accord} "
                                f"sur {len(etapes)}",
                          str(source), jour.isoformat(),
                          mesure={"cv": nom, "faites": faites, "total": len(etapes)}))

    if not faits:
        faits.append(Fait("candidatures", "suivi ouvert, aucune candidature dedans",
                          str(source), jour.isoformat()))
    return tuple(faits)


def collecter(*, aujourdhui: date | None = None,
              candidatures_chemin: Path | None = None) -> tuple[Fait, ...]:
    """Tout ce que le Scout sait aller chercher aujourd'hui.

    Une seule source pour l'instant, et c'est voulu : le carrousel dont vient
    cette architecture le dit comme le mandat -- un agent à la fois, chacun
    mérite le suivant. Une source de plus se branche ici.
    """
    return candidatures(candidatures_chemin, aujourdhui=aujourdhui)


__all__ = ["CANDIDATURES", "STATUTS", "Fait", "candidatures", "collecter"]
