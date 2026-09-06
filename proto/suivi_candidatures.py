#!/usr/bin/env python3
"""Suivi de candidatures : ou j'en suis, et quoi faire aujourd'hui.

Prototype jetable, ecrit pour une semaine d'essai. Rien de ce fichier
n'appartient a l'architecture de SINGULAR : bibliotheque standard seule, un
fichier JSON, aucune couche, aucune API. Si l'usage ne prouve pas que c'est
utile, on le supprime sans rien casser.

Ce qu'il fait a chaque lancement : rappeler l'etat des candidatures, puis
proposer UNE action, la plus importante. Une seule, parce qu'une liste de
douze choses a faire est une liste qu'on ne fait pas.

La forme vient d'un fait : les candidatures n'ont pas encore commence, le CV
n'est pas pret. Un outil qui reclamerait des candidatures serait vide et
agacant pendant toute la semaine d'essai, et ne prouverait rien. Tant que le
CV n'est pas fini, l'action du jour porte sur le CV.

Sortie volontairement sans fleche, sans tiret cadratin et sans emoji : la
console de Windows ecrit en cp850 et s'arrete sur le reste.
"""
from __future__ import annotations

import json
import sys
import textwrap
from datetime import date
from pathlib import Path

#: Meme dossier que le journal du Sage : une seule chose a sauvegarder.
FICHIER = Path.home() / ".singular" / "candidatures.json"

#: Sans reponse au-dela de ce delai, on relance. Dix jours ouvres, en gros.
JOURS_AVANT_RELANCE = 10

#: Une relance restee sans reponse aussi longtemps ne viendra plus.
JOURS_AVANT_CLASSEMENT = 14

#: Une candidature preparee mais pas envoyee pourrit vite.
JOURS_AVANT_ENVOI = 2

#: Sans nouvelle candidature depuis ce delai, la recherche s'est arretee.
JOURS_SANS_AJOUT = 7

#: Largeur de repli. L'ecran d'un iPhone en portrait, pas celui d'un PC.
COLONNES = 62

STATUTS = {
    "a_envoyer": "a envoyer",
    "envoyee": "envoyee",
    "relancee": "relancee",
    "entretien": "entretien",
    "refus": "refus",
    "sans_suite": "sans suite",
}

#: Les statuts qui attendent encore quelque chose de moi.
EN_COURS = ("a_envoyer", "envoyee", "relancee", "entretien")

#: Le chantier du moment, decoupe en gestes faisables en une soiree.
#:
#: Ecrit pour le passage terrain -> bureau d'etudes : un recruteur de BE ne
#: sait pas lire une fiche de technicien CVC, il faut la traduire dans ses
#: mots a lui. L'ordre compte, chaque etape se pose sur la precedente.
ETAPES_CV = [
    "Changer le titre du CV : viser « Charge d'etudes / chiffrage CVC »,"
    " pas « Technicien frigoriste »",
    "Traduire trois chantiers terrain en termes de bureau d'etudes :"
    " lecture de plans, dimensionnement, selection de materiel",
    "Chiffrer ces chantiers : puissances, surfaces, budget, delais."
    " Un BE recrute sur des ordres de grandeur",
    "Lister les logiciels, meme en niveau debutant :"
    " AutoCAD, Revit, ClimaWin ou Perrenoud, Excel de chiffrage",
    "Mettre le BTS FED en avant avec les modules qui parlent a un BE",
    "Ecrire deux lignes sur l'alternance visee et le rythme souhaite",
    "Relire a voix haute, couper tout ce qui ne sert pas le poste vise",
    "Faire relire par quelqu'un du metier",
]


# --- le fichier --------------------------------------------------------------

def charger() -> dict:
    """Lit le fichier, ou rend un etat neuf. Ne perd jamais rien en silence."""
    if not FICHIER.exists():
        return {"candidatures": [], "cv": [{"etape": e, "fait": False} for e in ETAPES_CV]}
    try:
        donnees = json.loads(FICHIER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erreur:
        print(f"  Fichier illisible : {erreur}")
        print(f"  Il est ici : {FICHIER}")
        print("  Rien n'a ete efface. Corrige-le ou renomme-le, puis relance.")
        raise SystemExit(1) from None
    donnees.setdefault("candidatures", [])
    donnees.setdefault("cv", [{"etape": e, "fait": False} for e in ETAPES_CV])
    return donnees


def sauver(donnees: dict) -> None:
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    FICHIER.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")


# --- les dates ---------------------------------------------------------------

def aujourdhui() -> date:
    return date.today()


def depuis(iso: str) -> int:
    """Nombre de jours ecoules depuis une date ISO. Tolere une date absente."""
    try:
        return (aujourdhui() - date.fromisoformat(iso)).days
    except (TypeError, ValueError):
        return 0


def en_francais(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return "?"


def jours(nombre: int) -> str:
    return "1 jour" if nombre == 1 else f"{nombre} jours"


# --- ce qu'il y a a faire aujourd'hui ---------------------------------------

def action_du_jour(donnees: dict) -> list[str]:
    """L'action la plus importante, et elle seule.

    L'ordre est l'essentiel de ce fichier. Ce qui a une date passe avant ce qui
    n'en a pas ; ce qui est deja engage passe avant ce qui reste a commencer ;
    et le CV passe avant les nouvelles candidatures, parce qu'envoyer un CV
    qu'on sait mauvais brule l'entreprise pour six mois.
    """
    candidatures = donnees["candidatures"]

    entretiens = [c for c in candidatures if c["statut"] == "entretien"]
    if entretiens:
        c = entretiens[0]
        return [
            f"Preparer l'entretien : {c['entreprise']} ({c['poste']}).",
            "Relis l'annonce, prepare deux questions sur leurs affaires en cours,",
            "et un exemple de chantier que tu sais raconter en trois minutes.",
        ]

    a_envoyer = [c for c in candidatures
                 if c["statut"] == "a_envoyer" and depuis(c["date_statut"]) >= JOURS_AVANT_ENVOI]
    if a_envoyer:
        c = a_envoyer[0]
        attente = depuis(c["date_statut"])
        return [
            f"Envoyer la candidature preparee pour {c['entreprise']} ({c['poste']}).",
            f"Elle attend depuis {jours(attente)}. Une candidature non envoyee ne compte pas.",
        ]

    relancer = sorted(
        (c for c in candidatures
         if c["statut"] == "envoyee" and depuis(c["date_statut"]) >= JOURS_AVANT_RELANCE),
        key=lambda c: c["date_statut"],
    )
    if relancer:
        c = relancer[0]
        return [
            f"Relancer {c['entreprise']} ({c['poste']}).",
            f"Envoyee il y a {jours(depuis(c['date_statut']))}, sans reponse.",
            "Un mail court : rappel de la candidature, disponibilite, une phrase"
            " sur ce que tu peux leur apporter.",
        ]

    a_classer = [c for c in candidatures
                 if c["statut"] == "relancee" and depuis(c["date_statut"]) >= JOURS_AVANT_CLASSEMENT]
    if a_classer:
        c = a_classer[0]
        return [
            f"Classer {c['entreprise']} sans suite.",
            f"Relancee il y a {jours(depuis(c['date_statut']))}, toujours rien.",
            "Ce n'est pas un echec, c'est de la place libre dans ta liste.",
        ]

    restantes = [e for e in donnees["cv"] if not e["fait"]]
    if restantes:
        faites = len(donnees["cv"]) - len(restantes)
        return [
            f"Avancer le CV. Etape {faites + 1} sur {len(donnees['cv'])} :",
            f"  {restantes[0]['etape']}",
            "Tant que le CV n'est pas pret, candidater brule des entreprises"
            " que tu ne pourras pas redemander.",
        ]

    if not candidatures:
        return [
            "Le CV est pret. Ajouter la premiere candidature.",
            "Vise trois bureaux d'etudes fluides de la region toulousaine :"
            " un gros, un moyen, un petit.",
            "Le petit repond souvent le premier.",
        ]

    dernier = max(depuis(c["date_ajout"]) for c in candidatures)
    if dernier >= JOURS_SANS_AJOUT:
        return [
            f"Ajouter une candidature. La derniere date d'il y a {jours(dernier)}.",
            "Une recherche qui s'arrete une semaine met un mois a repartir.",
        ]

    ouvertes = [c for c in candidatures if c["statut"] in EN_COURS]
    if ouvertes:
        return [
            "Rien d'urgent aujourd'hui.",
            f"{len(ouvertes)} candidature(s) en cours, aucune ne demande de relance"
            " pour l'instant.",
            "Si tu as une heure : prepare la suivante plutot que de verifier"
            " tes mails.",
        ]

    return ["Rien en cours et le CV est pret. Ajoute une candidature."]


# --- affichage ---------------------------------------------------------------

def ligne(texte: str = "") -> None:
    """Affiche en repliant : cet outil se lit surtout sur un telephone.

    Le repli conserve l'indentation de la premiere ligne, sinon la suite d'une
    phrase revient coller a la marge et on ne sait plus a quoi elle se rattache.
    """
    if not texte:
        print()
        return
    creux = " " * (len(texte) - len(texte.lstrip()))
    print(textwrap.fill(
        texte, width=COLONNES,
        initial_indent="  ", subsequent_indent="  " + creux + "  ",
    ))


def afficher_point(donnees: dict) -> None:
    candidatures = donnees["candidatures"]
    ouvertes = [c for c in candidatures if c["statut"] in EN_COURS]

    ligne()
    ligne(f"OU J'EN SUIS      {aujourdhui().strftime('%d/%m/%Y')}")
    ligne()

    if not ouvertes:
        ligne("Aucune candidature en cours.")
    for numero, c in enumerate(candidatures, start=1):
        if c["statut"] not in EN_COURS:
            continue
        attente = depuis(c["date_statut"])
        detail = f"depuis {jours(attente)}" if attente else "aujourd'hui"
        ligne(f"{numero:>2}. {c['entreprise']}  -  {c['poste']}")
        ligne(f"    {STATUTS[c['statut']]}, {detail}")
        for note in c.get("notes", [])[-1:]:
            ligne(f"    note : {note}")

    closes = len(candidatures) - len(ouvertes)
    restantes = sum(1 for e in donnees["cv"] if not e["fait"])
    if closes or restantes:
        ligne()
    if closes:
        ligne(f"({closes} classee(s) : refus ou sans suite)")
    if restantes:
        # Le CV reste sous les yeux tant qu'il n'est pas fini, meme quand
        # l'action du jour porte sur autre chose : c'est lui qui decide de la
        # qualite de tout ce qui part ensuite.
        faites = len(donnees["cv"]) - restantes
        ligne(f"(CV : {faites} etape(s) sur {len(donnees['cv'])})")

    ligne()
    ligne("AUJOURD'HUI")
    ligne()
    for texte in action_du_jour(donnees):
        ligne(texte)
    ligne()


def afficher_tout(donnees: dict) -> None:
    if not donnees["candidatures"]:
        ligne("Aucune candidature.")
        return
    ligne()
    for numero, c in enumerate(donnees["candidatures"], start=1):
        ligne(f"{numero:>2}. {c['entreprise']}  -  {c['poste']}")
        ligne(f"    {STATUTS[c['statut']]}  |  ajoutee le {en_francais(c['date_ajout'])}"
              f"  |  maj {en_francais(c['date_statut'])}")
        for note in c.get("notes", []):
            ligne(f"    note : {note}")
    ligne()


def afficher_cv(donnees: dict) -> None:
    ligne()
    ligne("LE CV")
    ligne()
    for numero, etape in enumerate(donnees["cv"], start=1):
        marque = "[x]" if etape["fait"] else "[ ]"
        ligne(f"{numero:>2}. {marque} {etape['etape']}")
    ligne()


# --- ce que je peux faire ----------------------------------------------------

def demander(question: str) -> str:
    try:
        return input(f"  {question} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0) from None


def ajouter(donnees: dict) -> None:
    entreprise = demander("Entreprise :")
    if not entreprise:
        ligne("Annule.")
        return
    poste = demander("Poste :") or "poste non precise"
    envoyee = demander("Deja envoyee ? (o/N) :").lower().startswith("o")
    note = demander("Une note (facultatif) :")

    jour = aujourdhui().isoformat()
    donnees["candidatures"].append({
        "entreprise": entreprise,
        "poste": poste,
        "statut": "envoyee" if envoyee else "a_envoyer",
        "date_ajout": jour,
        "date_statut": jour,
        "notes": [note] if note else [],
    })
    sauver(donnees)
    ligne(f"Ajoutee : {entreprise}.")


def choisir(donnees: dict) -> dict | None:
    if not donnees["candidatures"]:
        ligne("Aucune candidature.")
        return None
    afficher_tout(donnees)
    brut = demander("Numero :")
    if not brut.isdigit() or not 1 <= int(brut) <= len(donnees["candidatures"]):
        ligne("Numero inconnu.")
        return None
    return donnees["candidatures"][int(brut) - 1]


def changer_statut(donnees: dict) -> None:
    candidature = choisir(donnees)
    if candidature is None:
        return
    ligne()
    codes = list(STATUTS)
    for numero, code in enumerate(codes, start=1):
        ligne(f"{numero}. {STATUTS[code]}")
    brut = demander("Nouveau statut :")
    if not brut.isdigit() or not 1 <= int(brut) <= len(codes):
        ligne("Statut inconnu.")
        return
    candidature["statut"] = codes[int(brut) - 1]
    candidature["date_statut"] = aujourdhui().isoformat()
    sauver(donnees)
    ligne(f"{candidature['entreprise']} : {STATUTS[candidature['statut']]}.")


def noter(donnees: dict) -> None:
    candidature = choisir(donnees)
    if candidature is None:
        return
    note = demander("Note :")
    if not note:
        ligne("Annule.")
        return
    candidature.setdefault("notes", []).append(note)
    sauver(donnees)
    ligne("Note ajoutee.")


def cocher_cv(donnees: dict) -> None:
    afficher_cv(donnees)
    brut = demander("Numero de l'etape faite (vide pour revenir) :")
    if not brut.isdigit() or not 1 <= int(brut) <= len(donnees["cv"]):
        return
    etape = donnees["cv"][int(brut) - 1]
    etape["fait"] = not etape["fait"]
    sauver(donnees)
    ligne("Fait." if etape["fait"] else "Remis a faire.")


# --- le menu -----------------------------------------------------------------

CHOIX = {
    "1": ("Ajouter une candidature", ajouter),
    "2": ("Changer un statut", changer_statut),
    "3": ("Ajouter une note", noter),
    "4": ("Le CV", cocher_cv),
    "5": ("Tout voir", afficher_tout),
}


def main() -> int:
    donnees = charger()
    afficher_point(donnees)

    if not sys.stdin.isatty():
        # Lance sans clavier (tache planifiee, script) : le point du jour suffit.
        return 0

    while True:
        for touche, (libelle, _) in CHOIX.items():
            ligne(f"{touche}. {libelle}")
        ligne("0. Quitter")
        ligne()
        touche = demander("Choix :")
        if touche in {"0", ""}:
            ligne()
            return 0
        if touche not in CHOIX:
            ligne("Choix inconnu.")
            ligne()
            continue
        CHOIX[touche][1](donnees)
        ligne()
        afficher_point(donnees)


if __name__ == "__main__":
    raise SystemExit(main())
