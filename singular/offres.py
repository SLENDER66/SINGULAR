"""Un agent qui cherche des offres, et qui ne postule jamais.

Le premier agent de SINGULAR, et il tient dans une phrase : il lit les
annonces, il écarte, il propose. Thomas décide. C'est ce qu'il a répondu quand
la question lui a été posée -- « moi, toujours, avant toute action » -- et
c'est aussi ce que la constitution impose depuis le début : penser n'est pas
décider, décider n'est pas autoriser, autoriser n'est pas exécuter.

Cette séparation n'est pas une consigne dans l'instruction système, qui se
contourne par une tournure de phrase. Elle est structurelle : ce module
n'importe ni le journal, ni la frontière d'exécution, ni rien qui écrive quoi
que ce soit. Il rend du texte. `tests/test_offres.py` le vérifie sur les
imports plutôt que sur les intentions.

Pourquoi celui-ci en premier plutôt qu'une flotte : le dépôt contient déjà
dix mille lignes d'orchestration, d'autopilote et de gouvernance d'agents,
écrites sur quatre versions, et jamais exécutées une seule fois. Aucune ne
contient d'appel à un modèle. Construire la délégation avant qu'un agent ait
servi referait exactement ça.
"""
from __future__ import annotations

import os
from typing import Any

from .analyse import (
    REFUS,
    AnalyseIndisponible,
    _consommation,
    client_par_defaut,
    effort_valide,
    traduit_les_pannes,
)

#: Comme pour l'analyse : le modèle est un arbitrage de celui qui paie.
MODELE_PAR_DEFAUT = os.environ.get("SINGULAR_OFFRES_MODELE", "claude-opus-5")

#: Chercher sur le web coûte plus qu'analyser un journal : chaque recherche
#: ramène des pages entières dans le contexte. Le plafond n'est pas de la
#: prudence décorative, c'est ce qui rend la facture prévisible.
RECHERCHES_MAX = 5

#: Une liste courte se lit ; une liste longue se survole puis s'abandonne.
JETONS_MAX = 4000

EFFORT = effort_valide("SINGULAR_OFFRES_EFFORT")

#: Les deux seules provenances possibles pour une ligne de profil. Memes noms
#: et meme sens que dans `proto/suivi_candidatures.py`, qui les a introduits.
#:
#: DIT    : il l'a ecrit lui-meme. C'est un fait.
#: DEDUIT : personne ne l'a dit. A confirmer, et transmis comme tel.
DIT = "dit"
DEDUIT = "deduit"

#: Ce qu'il cherche. Chaque ligne porte sa provenance, et ce n'est pas de la
#: ceremonie.
#:
#: Le prototype de suivi porte ces marques depuis que deux deductions non
#: demandees lui ont coute un CV faux et un marche ecarte. Ce fichier-ci, plus
#: recent, decrit la meme vie et l'**envoie a un service distant** -- et il
#: n'avait ni marque ni test. Son commentaire disait « rien ici n'est deduit » :
#: une promesse, pas une garantie, et elle etait fausse.
#:
#: Le 9 septembre 2026, profil relu ligne par ligne avec lui. Une seule
#: correction : la roue est **hygroscopique**, pas enthalpique. C'est son
#: metier et c'est son mot ; les deux existent et ce ne sont pas les memes.
#: Le reste, il l'a confirme.
#:
#: Le meme jour, il a tranche lui-meme, a la question posee : les deux,
#: sans hierarchie. Le profil ne dit donc plus « poste vise », qui rangeait
#: l'alternance en second.
#:
#: Ce qui s'y etait glisse en deux jours, sur la meme ligne :
#:
#:   - « il ne cherche pas d'alternance », alors qu'il a dit qu'une reprise
#:     d'etudes l'interessait. Corrige.
#:   - puis « une offre d'alternance ne se retient que si elle dit prendre en
#:     charge la recherche d'ecole » -- une regle de filtrage inventee ici,
#:     posee au milieu de ce qu'il aurait dit, qui ecartait des annonces que
#:     personne n'avait demande d'ecarter. Retiree.
#:
#: `tests/test_offres.py` refuse desormais une ligne sans provenance, ici comme
#: dans le prototype.
CRITERES = [
    ("Il cherche deux choses, sans preference entre les deux : un poste de", DIT),
    ("charge d'etudes en bureau d'etudes CVC -- chiffrage, dimensionnement --", DIT),
    ("et une alternance en reprise d'etudes. Ne classe pas l'une avant l'autre.", DIT),
    ("Region : Toulouse et sa peripherie.", DIT),
    ("Experience : 2 ans en bureau d'etudes CVC, plus 5 ans de terrain dans", DIT),
    ("l'Armee -- chambres froides positif et negatif, groupes electrogenes,", DIT),
    ("bruleurs. Il dimensionne, selectionne et chiffre des centrales de", DIT),
    ("traitement d'air de 600 a 50 000 m3/h, avec recuperation par echangeur", DIT),
    ("a plaques, roue hygroscopique ou batteries a eau glycolee.", DIT),
    ("Diplome : BTS Fluides Energies Domotique.", DIT),
    ("Pour l'alternance : il n'a ni ecole ni entreprise a ce jour.", DIT),
]

INSTRUCTION = """\
Tu cherches des offres d'emploi pour Thomas, et tu ne postules jamais.

Tu lis, tu ecartes, tu proposes. Il decide. Tu n'as aucun moyen d'agir et tu
ne dois pas faire comme si : pas de « j'ai envoye », pas de « je te recommande
de laisser faire ». Une proposition, et lui tranche.

Utilise la recherche web pour trouver des offres reelles et actuelles. Pour
chacune de celles que tu retiens, donne :

1. l'intitule et l'employeur ;
2. le lieu, et la distance approximative de Toulouse si ce n'est pas Toulouse ;
3. en une phrase, ce qui correspond a son profil ;
4. en une phrase, ce qui manque ou ce qui coince -- il n'y a pas d'offre
   parfaite, et une annonce presentee sans reserve est une annonce mal lue ;
5. le lien.

Couvre les deux -- postes et alternances -- sans mettre un genre avant
l'autre. Il triera : c'est lui qui decide, et une liste qui a deja choisi a sa
place lui cache la moitie du marche.

Cinq offres au maximum, classees de la plus pertinente a la moins. Mieux vaut
trois offres justes que dix approximatives.

Si tu ne trouves rien de serieux, dis-le et arrete-toi. Une liste remplie pour
ne pas revenir les mains vides lui ferait perdre une demi-journee.

Ne fabrique jamais une offre, un employeur ou un lien. Si tu n'es pas sur
qu'une annonce existe, ne la cite pas. Reponds en francais, sans preambule.\
"""


def contexte_pour_recherche(question: str = "") -> str:
    """Exactement ce qui quittera la machine, comme pour l'analyse.

    Une deduction voyage avec son etiquette. Sans ca, elle sort d'ici comme un
    fait etabli, et l'agent ecarte des annonces sur une chose que personne n'a
    verifiee -- c'est exactement ce qui a coute un marche.
    """
    lignes = ["Voici qui je suis et ce que je cherche.", ""]
    lignes += [texte for texte, source in CRITERES if source == DIT]
    a_confirmer = [texte for texte, source in CRITERES if source != DIT]
    if a_confirmer:
        lignes += ["", "Ceci n'est pas verifie, ne t'appuie pas dessus :"]
        lignes += [f"- {texte}" for texte in a_confirmer]
    if question.strip():
        lignes += ["", "Precision pour cette recherche :", question.strip()]
    return "\n".join(lignes)


def apercu(question: str = "") -> str:
    """Exactement ce qui quittera la machine : l'instruction et son profil.

    L'instruction porte la garantie qui compte -- « tu ne postules jamais » --
    et il ne la voyait pas. Elle part pourtant a chaque recherche.
    """
    return f"{INSTRUCTION}\n\n{contexte_pour_recherche(question)}"


def chercher(question: str = "", *, modele: str | None = None,
             client: Any = None) -> tuple[str, dict[str, int]]:
    """Les offres retenues, et ce que la recherche a coute. Aucune ecriture.

    Le cout est rendu pour la meme raison que dans `parle.repondre`, dont
    cette fonction est la jumelle : ce qui n'est pas compte ne se voit pas sur
    le budget, et une recherche web coute nettement plus qu'un tour de
    conversation -- chaque recherche ramene des pages entieres. Une faculte
    qui depense sans etre comptee viderait les cinq dollars en silence.

    `client` est injectable pour que les tests n'aient besoin ni de reseau ni
    de cle : un test qui appellerait le vrai service testerait la meteo, et
    coûterait de l'argent a chaque execution du CI.
    """
    client = client_par_defaut(client)
    with traduit_les_pannes():
        reponse = client.beta.messages.create(
            model=modele or MODELE_PAR_DEFAUT,
            max_tokens=JETONS_MAX,
            system=INSTRUCTION,
            output_config={"effort": EFFORT},
            tools=[{
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": RECHERCHES_MAX,
                "user_location": {"type": "approximate", "country": "FR", "city": "Toulouse"},
            }],
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": contexte_pour_recherche(question)}],
        )

    if reponse.stop_reason == "refusal":
        raise AnalyseIndisponible(REFUS["refus_du_modele"])
    texte = "\n".join(b.text for b in reponse.content if b.type == "text").strip()
    return texte, _consommation(reponse)


__all__ = ["CRITERES", "DEDUIT", "DIT", "JETONS_MAX", "MODELE_PAR_DEFAUT",
           "RECHERCHES_MAX",
           "apercu", "chercher", "contexte_pour_recherche"]
