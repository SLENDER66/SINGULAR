"""« Analyse » : la seule faculté qui consomme des jetons, et qu'on peut couper.

Le Sage calcule. Cette faculté commente. La distinction n'est pas cosmétique :
`tests/test_sage_independence.py` interdit à `singular/sage/` et à
`journal.py` d'importer quoi que ce soit qui parle à un service, ou même de
mentionner un nom de clé. Ce fichier vit donc dehors, et rien dans le cœur ne
le connaît. Désinstalle le paquet, révoque la clé, coupe le réseau : le
journal, la chaîne d'intégrité, la Notice et la calibration continuent.

Trois règles tiennent cette faculté :

**Elle lit la Notice, jamais la base.** C'était déjà écrit dans le commentaire
d'ouverture de `notice.py`, avant que ce fichier existe. Les chiffres sont
calculés par un moteur déterministe et vérifiables un par un ; le modèle les
met en phrases et n'a pas le droit d'en produire d'autres.

**Elle ne décide de rien.** SINGULAR observe, analyse, conseille -- il ne
décide jamais à la place de Thomas. Un texte de modèle n'est pas un verdict :
il ne peut ni résoudre une décision, ni en créer une, ni toucher au journal.
Cette faculté n'a aucune écriture, et c'est structurel, pas une consigne dans
un prompt.

**Elle dit ce qu'elle envoie.** `contexte_pour_analyse()` rend exactement le
texte qui quittera la machine, et `python -m singular analyse --blanc`
l'affiche sans rien envoyer. Un outil qui expédie le journal intime de
quelqu'un vers un service distant doit pouvoir montrer quoi, avant, et pas
sur parole.
"""
from __future__ import annotations

import json
import os
from typing import Any

#: Le modèle par défaut. Opus 5 est le plus capable ; c'est aussi le plus cher
#: des deux qui conviennent ici. `claude-sonnet-5` coûte environ deux fois
#: moins, et c'est un choix qui appartient à celui qui paie la facture -- d'où
#: la variable d'environnement plutôt qu'une valeur en dur.
MODELE_PAR_DEFAUT = os.environ.get("SINGULAR_ANALYSE_MODELE", "claude-opus-5")

#: La réponse tient en quelques paragraphes : plafonner la sortie est ici une
#: décision de coût assumée, pas une troncature accidentelle.
JETONS_MAX = 2000

#: Ni un audit exhaustif ni une réponse expédiée. Relevable si les réponses
#: manquent de fond.
EFFORT = os.environ.get("SINGULAR_ANALYSE_EFFORT", "medium")

INSTRUCTION = """\
Tu es la faculté « Analyse » de SINGULAR, l'outil personnel de Thomas.

Ce qui suit vient d'un moteur déterministe : chaque chiffre est calculé à
partir de décisions que Thomas a écrites lui-même, et chacun est vérifiable.
Tu les mets en perspective. Tu n'en inventes aucun, tu n'en recalcules aucun,
et tu ne contredis jamais une observation du moteur.

Sa constitution ordonne ses rangs ainsi, et cet ordre prime :
Stabilité > Revenus > Capacités > Opportunités > Patrimoine > Liberté.
Elle juge une décision sur : options, levier, coût, vitesse, réversibilité.
Elle dit aussi : en cas d'incertitude critique et de conséquence élevée, HALT.

Tu observes, tu analyses, tu conseilles. Tu ne décides jamais à sa place, et
tu ne prétends pas avoir agi : tu n'as accès à rien d'autre que ce texte.

Réponds en français, droit au but, sans flatterie ni récapitulatif de ce qu'il
vient de lire. Six phrases suffisent si six phrases suffisent. Dis ce qui ne va
pas avant ce qui va. Si le rapport ne montre rien d'inquiétant, dis-le et
arrête-toi -- meubler serait le seul vrai défaut possible ici.\
"""


class AnalyseIndisponible(RuntimeError):
    """La faculté est coupée, et ce n'est pas une panne.

    Pas de clé, pas de paquet, pas de réseau : le reste de SINGULAR doit
    continuer exactement comme avant. Cette exception existe pour que
    l'appelant puisse le dire à Thomas au lieu de planter.
    """


def contexte_pour_analyse(notice: dict[str, Any]) -> str:
    """Exactement ce qui quittera la machine. Rien de plus, rien d'implicite.

    On envoie la Notice, pas la base : les observations et les agrégats, pas
    l'historique complet des décisions. C'est déjà personnel -- d'où
    `--blanc`, qui affiche ce texte sans appeler personne.
    """
    rapport = notice.get("report", {})
    interessant = {
        cle: rapport[cle]
        for cle in (
            "decisions", "open", "overdue", "resolved", "abandoned",
            "hours_total", "hours_unresolved", "hours_that_worked",
            "hours_without_gain", "gain_expected_total", "gain_expected_open",
            "irreversible_open", "hit_rate", "mean_probability",
            "overconfidence", "mean_brier", "chain_intact", "by_tier",
        )
        if cle in rapport
    }
    lignes = [
        f"Date du rapport : {notice.get('generated_at', 'inconnue')}",
        f"En-tête du moteur : {notice.get('headline', '')}",
        "",
        "Observations, dans l'ordre de gravité :",
    ]
    for item in notice.get("items", []):
        lignes.append(f"- [{item['severity']}] {item['title']} : {item['detail']}")
        if item.get("action"):
            lignes.append(f"  geste proposé par le moteur : {item['action']}")
    if not notice.get("items"):
        lignes.append("- aucune")
    lignes += ["", "Chiffres calculés :", json.dumps(interessant, ensure_ascii=False, indent=2)]
    return "\n".join(lignes)


def _sdk():
    """Le SDK officiel, importé tard pour que ce module s'importe sans lui.

    Il sert à deux choses et les deux passent par ici : construire le client,
    et nommer les exceptions à rattraper. Les chercher séparément laisserait
    un chemin -- client injecté, paquet absent -- qui lève `ImportError` au
    lieu de dire proprement que la faculté est coupée.
    """
    try:
        import anthropic
    except ImportError:
        raise AnalyseIndisponible(
            "le paquet « anthropic » n'est pas installe. "
            "pip install -e '.[analyse]' -- ou laisse la faculte coupee."
        ) from None
    return anthropic


def analyser(notice: dict[str, Any], *, modele: str | None = None, client: Any = None) -> str:
    """Le commentaire du modèle sur un rapport déjà calculé.

    `client` est injectable pour que les tests n'aient jamais besoin d'un
    réseau ni d'une clé : un test qui appellerait le vrai service ne testerait
    pas ce fichier, il testerait la météo.
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
            # Repli côté serveur : si le modèle décline, la requête est rejouée
            # sur un autre au lieu de rendre une réponse vide.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": contexte_pour_analyse(notice)}],
        )
    except anthropic.AuthenticationError:
        raise AnalyseIndisponible("la cle est refusee. Verifie ANTHROPIC_API_KEY.") from None
    except anthropic.RateLimitError:
        raise AnalyseIndisponible("trop de requetes. Reessaie dans une minute.") from None
    except anthropic.APIConnectionError:
        raise AnalyseIndisponible("pas de reseau. Le reste de SINGULAR marche sans.") from None
    except anthropic.APIStatusError as erreur:
        raise AnalyseIndisponible(f"le service a repondu {erreur.status_code}.") from None

    if reponse.stop_reason == "refusal":
        raise AnalyseIndisponible(
            "le modele a refuse de repondre. Rien n'a ete ecrit dans ton journal."
        )
    return "\n".join(bloc.text for bloc in reponse.content if bloc.type == "text").strip()


__all__ = [
    "EFFORT", "JETONS_MAX", "MODELE_PAR_DEFAUT",
    "AnalyseIndisponible", "analyser", "contexte_pour_analyse",
]
