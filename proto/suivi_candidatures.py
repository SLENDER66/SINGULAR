#!/usr/bin/env python3
"""Suivi de candidatures : ou j'en suis, et quoi faire aujourd'hui.

Prototype jetable, ecrit pour une semaine d'essai. Rien de ce fichier
n'appartient a l'architecture de SINGULAR : bibliotheque standard seule, un
fichier JSON, aucune couche, aucune API. Si l'usage ne prouve pas que c'est
utile, on le supprime sans rien casser.

Ce qu'il fait a chaque lancement : rappeler l'etat des candidatures, puis
proposer UNE action, la plus importante. Une seule, parce qu'une liste de
douze choses a faire est une liste qu'on ne fait pas.

La forme vient d'un fait : les candidatures n'ont pas encore commence, les CV
ne sont pas prets. Un outil qui reclamerait des candidatures serait vide et
agacant pendant toute la semaine d'essai, et ne prouverait rien. Tant qu'un CV
n'est pas fini, l'action du jour porte sur lui.

Il y a deux CV depuis le 9 septembre 2026 -- un pour les postes, un pour les
alternances -- et aucun ne passe devant l'autre.

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
#: Ces etapes ont d'abord ete ecrites pour un passage terrain -> bureau
#: d'etudes. C'etait faux : les 2 ans de BE etaient deja faits, et un CV
#: qui s'excuse d'arriver du terrain sous-vend deux ans d'experience du
#: poste vise. La deduction avait remplace la question.
#:
#: Elles disent maintenant l'inverse : mettre le BE devant, et se servir du
#: terrain Armee comme d'un differenciateur, pas d'un passe a traduire.
#:
#: Trois etapes de contenu -- detailler les affaires, lister les logiciels,
#: chiffrer le terrain -- ont ete retirees a la demande : ce contenu est deja
#: sur le CV. Ce qui manquait etait le cadrage, pas la matiere. Une liste qui
#: fait refaire ce qui est fait ne se coche jamais.
#:
#: Les deux seules provenances possibles pour une ligne de profil.
#:
#: DIT   : il l'a ecrit lui-meme, dans une conversation. C'est un fait.
#: DEDUIT: personne ne l'a dit ; ca a ete infere. A confirmer avant de s'en
#:         servir, et affiche comme tel dans le bloc colle a Claude.
DIT = "dit"
DEDUIT = "deduit"

#: L'ordre compte, chaque etape se pose sur la precedente.
#:
#: Chaque etape porte sa provenance, pour la meme raison que `PROFIL` : ce sont
#: des conseils sur sa vie, ils partent dans le bloc colle a Claude, et deux
#: deductions non demandees lui ont deja coute un CV faux et un marche ecarte.
#: `ETAPES_CV` n'etait pas marquee -- seul `PROFIL` l'etait, et la correction
#: s'etait arretee la.
#:
#: **Deux CV, deux listes.** Il l'a tranche lui-meme, en questionnaire, le
#: 9 septembre 2026 : un CV pour les postes, sans mention d'alternance, et un
#: CV pour les alternances qui l'assume. La liste unique portait une etape
#: -- « retirer toute mention d'alternance » -- que personne ne montrait qu'il
#: avait dite, et qui contredisait sa reponse du meme jour sur les offres :
#: postes et alternances, sans hierarchie.
#:
#: Les quatre etapes communes figurent dans les deux listes, et ce n'est pas
#: une redondance de comptabilite : ce sont deux documents. Relire a voix haute
#: le CV « poste » ne relit pas le CV « alternance ».
CV_POSTE = "poste"
CV_ALTERNANCE = "alternance"

#: Le nom de chaque CV tel qu'il s'affiche.
NOMS_CV = {CV_POSTE: "CV poste", CV_ALTERNANCE: "CV alternance"}

_TITRE = ("Titre : « Charge d'etudes CVC - chiffrage & dimensionnement »."
          " Les 2 ans de BE en premier, le terrain juste apres", DIT)
_MATERIEL = ("Nommer le materiel au lieu d'ecrire « CVC » : chambres froides, groupes"
             " electrogenes, bruleurs, CTA double flux. Avec les puissances et volumes", DIT)
_VOIX_HAUTE = ("Relire a voix haute, couper tout ce qui ne sert pas le poste vise", DIT)
_RELECTURE = ("Faire relire par quelqu'un du metier", DIT)

ETAPES_CV = {
    CV_POSTE: [
        _TITRE,
        ("Retirer toute mention d'alternance : ce CV vise un poste", DIT),
        _MATERIEL,
        _VOIX_HAUTE,
        _RELECTURE,
    ],
    CV_ALTERNANCE: [
        _TITRE,
        ("Assumer l'alternance : dire que c'est une reprise d'etudes, et que"
         " l'ecole reste a trouver", DIT),
        _MATERIEL,
        _VOIX_HAUTE,
        _RELECTURE,
    ],
}

#: Le texte des etapes, par CV. C'est ce que le fichier de donnees garde.
#:
#: La lecture tolere une etape sans provenance plutot que de lever a l'import.
#: Ce n'est pas de l'indulgence : une session qui oublie la marque doit faire
#: echouer `tests/test_proto_suivi.py`, pas empecher son outil de demarrer sur
#: son telephone. Le refus a sa place, et ce n'est pas ici.
TEXTES_CV = {
    nom: [entree[0] if isinstance(entree, tuple) else entree for entree in etapes]
    for nom, etapes in ETAPES_CV.items()
}

#: De quoi retrouver la provenance d'une etape relue depuis le fichier.
#:
#: La provenance se lit ici et jamais dans le fichier : un fichier ecrit avant
#: ce marquage n'en porte pas, et une etape dont le texte a change depuis n'est
#: plus l'etape d'ici. Inconnue veut dire « pas de marque », pas « fait ».
PROVENANCE_CV = {
    entree[0]: entree[1]
    for etapes in ETAPES_CV.values() for entree in etapes
    if isinstance(entree, tuple) and len(entree) == 2
}


def etapes_a_plat(donnees: dict) -> list[tuple[str, dict]]:
    """Les etapes des deux CV, dans l'ordre ou elles sont numerotees a l'ecran."""
    return [(nom, etape) for nom in TEXTES_CV for etape in donnees["cv"][nom]]


def restantes_par_cv(donnees: dict) -> dict[str, list[dict]]:
    return {nom: [e for e in etapes if not e["fait"]] for nom, etapes in donnees["cv"].items()}


def marque(texte: str) -> str:
    """L'etape, suivie de sa reserve quand elle n'a pas ete dite."""
    return texte if PROVENANCE_CV.get(texte, DIT) == DIT else f"{texte} (deduit, a confirmer)"

#: Ce que Claude ne peut pas deviner, et que tu ne dois pas retaper a chaque
#: conversation.
#:
#: Chaque ligne porte sa provenance, et ce n'est pas de la ceremonie. Deux fois
#: dans la meme journee, une session a deduit un fait de sa vie au lieu de le
#: demander, et l'a ecrit ici comme s'il etait acquis :
#:
#:   - « il vient du terrain, donc c'est une reconversion » -- ses deux ans de
#:     bureau d'etudes ont ete effaces, et le CV s'excusait d'arriver du terrain ;
#:   - « chambre froide, groupe electrogene, bruleur, donc pas de tertiaire » --
#:     il fait des CTA double flux, et le conseil qui en sortait l'ecartait du
#:     marche toulousain le plus large.
#:
#: Sa constitution classe deja tout element du modele du monde en FACT,
#: HYPOTHESIS, ESTIMATE... Ce fichier ne le faisait pas. Il le fait maintenant,
#: et `tests/test_proto_suivi.py` refuse une ligne sans provenance : ajouter une
#: deduction en la faisant passer pour un fait n'est plus possible en silence.
#: Le 9 septembre 2026, relu ligne par ligne avec lui. Une seule correction :
#: la roue est **hygroscopique**, pas enthalpique. C'est son metier, c'est son
#: mot, et une session qui trouverait « enthalpique » plus courant se
#: tromperait -- les deux existent et ce ne sont pas les memes.
PROFIL = [
    ("2 ans en bureau d'études CVC : chiffrage, dimensionnement.", DIT),
    ("Avant cela, 5 ans de terrain dans l'Armée : chambre froide, groupe", DIT),
    ("électrogène, brûleur -- froid, énergie, combustion.", DIT),
    ("Et du tertiaire : je dimensionne, sélectionne et chiffre des centrales", DIT),
    ("de traitement d'air, de 600 à 50 000 m3/h. C'est du bureau d'études,", DIT),
    ("pas de l'entretien. Récupération : échangeur à plaques, roue", DIT),
    ("hygroscopique, batteries à eau glycolée -- les trois.", DIT),
    ("Les chambres froides étaient en positif et en négatif.", DIT),
    ("Les brûleurs : je ne me souviens plus du combustible, donc ça ne va", DIT),
    ("nulle part -- ne me le redemande pas.", DIT),
    ("BTS Fluides Énergies Domotique. Actuellement au chômage.", DIT),
    ("Je cherche un poste en bureau d'études dans la région toulousaine.", DIT),
    ("Une reprise d'études en alternance m'intéresse, mais je n'ai ni école", DIT),
    ("ni entreprise à ce jour.", DIT),
    ("Débutant en code, j'utilise un iPhone.", DIT),
]


# --- le fichier --------------------------------------------------------------

def _cv_neuf() -> dict[str, list[dict]]:
    return {nom: [{"etape": texte, "fait": False} for texte in textes]
            for nom, textes in TEXTES_CV.items()}


def _cv_relu(brut: object) -> dict[str, list[dict]]:
    """Le CV du fichier, ramene a deux listes quoi qu'il contienne.

    Un fichier ecrit avant le 9 septembre 2026 porte une seule liste. Elle a ete
    ecrite pour le CV « poste » -- c'est elle qui disait de retirer la mention
    d'alternance -- donc elle le devient, avec ses cases cochees, et la liste
    « alternance » demarre a zero. Rien de coche ne se perd, et rien n'est
    invente : personne n'a jamais coche une etape de la seconde liste.
    """
    if isinstance(brut, dict):
        return {nom: brut.get(nom) or [{"etape": texte, "fait": False} for texte in textes]
                for nom, textes in TEXTES_CV.items()}
    if isinstance(brut, list):
        return {CV_POSTE: brut,
                CV_ALTERNANCE: [{"etape": texte, "fait": False}
                                for texte in TEXTES_CV[CV_ALTERNANCE]]}
    return _cv_neuf()


def charger() -> dict:
    """Lit le fichier, ou rend un etat neuf. Ne perd jamais rien en silence."""
    if not FICHIER.exists():
        return {"candidatures": [], "cv": _cv_neuf()}
    try:
        donnees = json.loads(FICHIER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erreur:
        print(f"  Fichier illisible : {erreur}")
        print(f"  Il est ici : {FICHIER}")
        print("  Rien n'a ete efface. Corrige-le ou renomme-le, puis relance.")
        raise SystemExit(1) from None
    donnees.setdefault("candidatures", [])
    donnees["cv"] = _cv_relu(donnees.get("cv"))
    # Les etapes ont ete ecrites sur une lecture fausse du profil -- une
    # reconversion depuis le terrain, alors que les 2 ans de bureau d'etudes
    # etaient deja faits -- puis corrigees. Un fichier deja cree gardait
    # l'ancienne liste pour toujours : le seul moyen de voir la nouvelle aurait
    # ete d'effacer ses donnees. Tant qu'aucune etape n'est cochee, il n'y a
    # rien a perdre. Des qu'une l'est, on ne touche plus a rien : le travail
    # deja fait vaut mieux qu'une liste a jour.
    for nom, etapes in donnees["cv"].items():
        if not any(etape["fait"] for etape in etapes) \
                and [etape["etape"] for etape in etapes] != TEXTES_CV[nom]:
            donnees["cv"][nom] = [{"etape": texte, "fait": False}
                                  for texte in TEXTES_CV[nom]]
    return donnees


def sauver(donnees: dict) -> None:
    """Ecrit tout, ou rien. Le fichier n'existe jamais a moitie.

    `write_text` tronque puis ecrit ; entre les deux, il n'y a rien. Une
    interruption a cet instant -- Ctrl+C, un portable qu'on referme -- laissait
    un JSON coupe en deux, et `charger()` refusait alors de demarrer en
    renvoyant une erreur de parseur a quelqu'un qui debute en code. Reproduit :
    1266 octets sains, 635 apres coupure, l'outil ne se lance plus.

    Ce fichier n'importe rien de `singular/` -- c'est ce qui lui permet de
    tourner seul, et son en-tete le promet. La copie de six lignes est donc
    volontaire ; `singular/fichiers.py` porte la meme, et
    `test_ecriture_atomique.py` verifie que les deux existent.

    Par `pathlib` et non par `os` : ajouter `os` aux imports elargirait la
    promesse « ce script ne contacte aucun serveur » que garde
    `test_proto_suivi.py`, pour un gain nul -- `Path.replace` appelle
    `os.replace`. Le nom du provisoire est fixe, faute de numero de processus :
    ce script est interactif et n'a qu'un ecrivain a la fois, contrairement au
    compteur du Sage que le serveur et le clavier se partagent.
    """
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    provisoire = FICHIER.with_name(FICHIER.name + ".tmp")
    try:
        provisoire.write_text(json.dumps(donnees, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    except BaseException:
        # Y compris Ctrl+C : c'est l'interruption dont cette fonction protege.
        provisoire.unlink(missing_ok=True)
        raise
    provisoire.replace(FICHIER)  # atomique, sur Windows comme ailleurs


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
            ("Un mail court : rappel de la candidature, disponibilite, une phrase"
            " sur ce que tu peux leur apporter."),
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

    restantes = restantes_par_cv(donnees)
    en_retard = [nom for nom, reste in restantes.items() if reste]
    if en_retard:
        # Les deux CV sont a egalite : ni l'un ni l'autre ne passe devant. C'est
        # sa reponse du 9 septembre -- postes et alternances, sans hierarchie --
        # et un tri arbitraire ici la contredirait en silence chaque matin.
        # Quand les deux attendent la meme etape, elle se dit une fois.
        prochaines = {nom: restantes[nom][0]["etape"] for nom in en_retard}
        if len(set(prochaines.values())) == 1:
            nom = en_retard[0]
            place = len(donnees["cv"][nom]) - len(restantes[nom]) + 1
            portee = "des deux CV" if len(en_retard) == 2 else f"du {NOMS_CV[nom]}"
            dit = [f"Avancer le CV. Etape {place} sur {len(donnees['cv'][nom])}, {portee} :",
                   f"  {marque(prochaines[nom])}"]
        else:
            dit = ["Avancer les deux CV. Ils ne demandent pas la meme chose :"]
            for nom in en_retard:
                dit.append(f"  {NOMS_CV[nom]} : {marque(prochaines[nom])}")
        dit.append("Tant que le CV n'est pas pret, candidater brule des entreprises"
                   " que tu ne pourras pas redemander.")
        return dit

    if not candidatures:
        return [
            "Le CV est pret. Ajouter la premiere candidature.",
            ("Vise trois bureaux d'etudes fluides de la region toulousaine :"
            " un gros, un moyen, un petit."),
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
            (f"{len(ouvertes)} candidature(s) en cours, aucune ne demande de relance"
            " pour l'instant."),
            ("Si tu as une heure : prepare la suivante plutot que de verifier"
            " tes mails."),
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
    restantes = sum(len(reste) for reste in restantes_par_cv(donnees).values())
    if closes or restantes:
        ligne()
    if closes:
        ligne(f"({closes} classee(s) : refus ou sans suite)")
    if restantes:
        # Le CV reste sous les yeux tant qu'il n'est pas fini, meme quand
        # l'action du jour porte sur autre chose : c'est lui qui decide de la
        # qualite de tout ce qui part ensuite.
        for nom, etapes in donnees["cv"].items():
            faites = sum(1 for e in etapes if e["fait"])
            ligne(f"({NOMS_CV[nom]} : {faites} etape(s) sur {len(etapes)})")

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
    ligne("LES DEUX CV")
    numero = 0
    for nom, etapes in donnees["cv"].items():
        ligne()
        ligne(NOMS_CV[nom].upper())
        for etape in etapes:
            numero += 1
            coche = "[x]" if etape["fait"] else "[ ]"
            ligne(f"{numero:>2}. {coche} {marque(etape['etape'])}")
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
    toutes = etapes_a_plat(donnees)
    if not brut.isdigit() or not 1 <= int(brut) <= len(toutes):
        return
    nom, etape = toutes[int(brut) - 1]
    etape["fait"] = not etape["fait"]
    sauver(donnees)
    ligne(f"{NOMS_CV[nom]} : fait." if etape["fait"] else f"{NOMS_CV[nom]} : remis a faire.")

# --- parler a Claude, sans que ce script parle a personne -------------------

def texte_pour_claude(donnees: dict, question: str) -> str:
    """Le bloc a coller dans l'app Claude.

    Claude oublie tout d'une conversation a l'autre ; ce fichier, non. Le pont
    ne fait que reunir ce qu'il faudrait retaper : qui tu es, ou tu en es, et
    ta question.

    Il ne consomme rien et ne contacte personne. Une faculte qui appellerait
    l'API ferait la meme chose en coutant de l'argent tous les mois, alors que
    l'app Claude est deja sur le telephone.
    """
    lignes = ["Voici ma situation. Reponds en francais, droit au but.", ""]
    lignes += [texte for texte, source in PROFIL if source == DIT]
    a_confirmer = [texte for texte, source in PROFIL if source != DIT]
    if a_confirmer:
        # L'incertitude voyage avec le fait. Sans ca, une deduction collee dans
        # une conversation en ressort comme une chose etablie.
        lignes.append("")
        lignes.append("Ceci n'est pas verifie, ne t'appuie pas dessus sans me demander :")
        lignes += [f"- {texte}" for texte in a_confirmer]
    lignes.append("")

    ouvertes = [c for c in donnees["candidatures"] if c["statut"] in EN_COURS]
    if ouvertes:
        lignes.append("Mes candidatures en cours :")
        for c in ouvertes:
            lignes.append(
                f"- {c['entreprise']}, {c['poste']} : {STATUTS[c['statut']]}"
                f" depuis {jours(depuis(c['date_statut']))}"
            )
            for note in c.get("notes", []):
                lignes.append(f"  note : {note}")
    else:
        lignes.append("Aucune candidature en cours : je n'ai pas encore commence.")
    lignes.append("")

    restantes = restantes_par_cv(donnees)
    if any(restantes.values()):
        lignes.append("J'ai deux CV : un pour les postes, un pour les alternances.")
        for nom, reste in restantes.items():
            total = len(donnees["cv"][nom])
            if not reste:
                lignes.append(f"Mon {NOMS_CV[nom]} est termine.")
                continue
            lignes.append(f"Mon {NOMS_CV[nom]} : {total - len(reste)} etape(s) sur {total}."
                          " Il me reste :")
            lignes += [f"- {marque(e['etape'])}" for e in reste]
    else:
        lignes.append("Mes deux CV sont termines.")
    lignes.append("")

    lignes.append("Ma question :")
    lignes.append(question)
    return "\n".join(lignes)


def preparer_question(donnees: dict) -> None:
    ligne("Ta question, en une phrase. Par exemple :")
    ligne("  relis l'etape 1 de mon CV")
    ligne("  ecris-moi un mail de relance pour telle entreprise")
    ligne("  prepare mon entretien de jeudi")
    ligne()
    question = demander("Question :")
    if not question:
        ligne("Annule.")
        return
    # Volontairement sans indentation ni repli : ce bloc est fait pour etre
    # selectionne et colle, pas pour etre joli dans le terminal.
    print()
    print("----- copie a partir d'ici -----")
    print(texte_pour_claude(donnees, question))
    print("----- jusqu'ici -----")
    print()
    ligne("Colle ce bloc dans l'app Claude.")
    ligne("Rien n'est parti d'ici : ce script ne contacte aucun serveur.")


# --- le menu -----------------------------------------------------------------

CHOIX = {
    "1": ("Ajouter une candidature", ajouter),
    "2": ("Changer un statut", changer_statut),
    "3": ("Ajouter une note", noter),
    "4": ("Le CV", cocher_cv),
    "5": ("Tout voir", afficher_tout),
    "6": ("Preparer une question pour Claude", preparer_question),
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
