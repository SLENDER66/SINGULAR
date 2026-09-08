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

from .analyse import AnalyseIndisponible, _sdk, effort_valide
from .parle import _consommation

#: Comme pour l'analyse : le modèle est un arbitrage de celui qui paie.
MODELE_PAR_DEFAUT = os.environ.get("SINGULAR_OFFRES_MODELE", "claude-opus-5")

#: Chercher sur le web coûte plus qu'analyser un journal : chaque recherche
#: ramène des pages entières dans le contexte. Le plafond n'est pas de la
#: prudence décorative, c'est ce qui rend la facture prévisible.
RECHERCHES_MAX = 5

#: Une liste courte se lit ; une liste longue se survole puis s'abandonne.
JETONS_MAX = 4000

EFFORT = effort_valide("SINGULAR_OFFRES_EFFORT")

#: Ce qu'il cherche, dit par lui. Rien ici n'est déduit -- même règle que le
#: profil du prototype, et pour la même raison : deux déductions non demandées
#: lui ont déjà coûté un CV faux et un marché écarté.
CRITERES = [
    "Poste vise : charge d'etudes en bureau d'etudes CVC, chiffrage et",
    "dimensionnement.",
    "Region : Toulouse et sa peripherie.",
    "Experience : 2 ans en bureau d'etudes CVC, plus 5 ans de terrain dans",
    "l'Armee -- chambres froides positif et negatif, groupes electrogenes,",
    "bruleurs. Il dimensionne, selectionne et chiffre des centrales de",
    "traitement d'air de 600 a 50 000 m3/h, avec recuperation par echangeur",
    "a plaques, roue enthalpique ou batteries a eau glycolee.",
    "Diplome : BTS Fluides Energies Domotique.",
    # Ce qu'il a dit, mot pour mot, est plus ouvert que ce qui etait ecrit ici :
    # « une reprise d'etudes en alternance m'interesse, mais je n'ai ni ecole
    # ni entreprise a ce jour ». C'etait devenu « il ne cherche pas
    # d'alternance » -- une deduction non marquee, qui faisait ecarter des
    # annonces qu'il aurait voulu voir. La provenance de chaque ligne est dans
    # `proto/suivi_candidatures.py`, ou celle-ci est marquee DIT.
    "Une reprise d'etudes en alternance l'interesse, mais il n'a ni ecole ni",
    "entreprise a ce jour : une offre d'alternance ne se retient que si elle",
    "dit prendre en charge la recherche d'ecole, et il faut le signaler.",
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

Cinq offres au maximum, classees de la plus pertinente a la moins. Mieux vaut
trois offres justes que dix approximatives.

Si tu ne trouves rien de serieux, dis-le et arrete-toi. Une liste remplie pour
ne pas revenir les mains vides lui ferait perdre une demi-journee.

Ne fabrique jamais une offre, un employeur ou un lien. Si tu n'es pas sur
qu'une annonce existe, ne la cite pas. Reponds en francais, sans preambule.\
"""


def contexte_pour_recherche(question: str = "") -> str:
    """Exactement ce qui quittera la machine, comme pour l'analyse."""
    lignes = ["Voici qui je suis et ce que je cherche.", "", *CRITERES]
    if question.strip():
        lignes += ["", "Precision pour cette recherche :", question.strip()]
    return "\n".join(lignes)


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
    if client is None:
        cle = os.environ.get("ANTHROPIC_API_KEY")
        if not cle:
            raise AnalyseIndisponible(
                "aucune cle dans ANTHROPIC_API_KEY. Le reste de SINGULAR marche sans."
            )
        client = _sdk().Anthropic(api_key=cle)

    anthropic = _sdk()
    try:
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
    except anthropic.AuthenticationError:
        raise AnalyseIndisponible("la cle est refusee. Verifie ANTHROPIC_API_KEY.") from None
    except anthropic.RateLimitError:
        raise AnalyseIndisponible("trop de requetes. Reessaie dans une minute.") from None
    except anthropic.APIConnectionError:
        raise AnalyseIndisponible("pas de reseau. Le reste de SINGULAR marche sans.") from None
    except anthropic.APIStatusError as erreur:
        raise AnalyseIndisponible(f"le service a repondu {erreur.status_code}.") from None
    except anthropic.AnthropicError:
        # Le filet. Les quatre familles ci-dessus ne couvrent pas tout l'arbre
        # du SDK, et ce qui s'echappe remonte tel quel jusqu'a l'ecran :
        # l'explication est dans `analyse.py`, au meme endroit.
        raise AnalyseIndisponible(
            "le service a echoue d'une facon imprevue. Rien n'a ete ecrit."
        ) from None

    if reponse.stop_reason == "refusal":
        raise AnalyseIndisponible("le modele a refuse de repondre. Rien n'a ete enregistre.")
    texte = "\n".join(b.text for b in reponse.content if b.type == "text").strip()
    return texte, _consommation(reponse)


__all__ = ["CRITERES", "JETONS_MAX", "MODELE_PAR_DEFAUT", "RECHERCHES_MAX",
           "chercher", "contexte_pour_recherche"]
