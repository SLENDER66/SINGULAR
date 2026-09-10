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
texte qui quittera la machine, et `python3 -m singular analyse --blanc`
l'affiche sans rien envoyer. Un outil qui expédie le journal intime de
quelqu'un vers un service distant doit pouvoir montrer quoi, avant, et pas
sur parole.
"""
from __future__ import annotations

import contextlib
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

#: Les seules valeurs que l'API accepte. Une faute de frappe dans la variable
#: d'environnement -- « moyen » au lieu de « medium », le réflexe naturel ici --
#: partirait sinon jusqu'au service, reviendrait en 400, et aurait coûté une
#: requête pour un message d'erreur illisible. On le refuse ici, gratuitement.
EFFORTS = ("low", "medium", "high", "xhigh", "max")


def effort_valide(variable: str) -> str:
    """L'effort demandé par l'environnement, ou « medium » si on l'a mal écrit.

    Une fonction plutôt que trois lignes au niveau du module, pour une raison
    de test : vérifier le repli obligeait sinon à recharger ce module avec
    `importlib.reload`, ce qui recrée `AnalyseIndisponible`. Les modules qui
    avaient importé l'ancienne classe ne la reconnaissaient plus, et un
    `except AnalyseIndisponible` cessait de rattraper -- une contamination
    entre tests qui ne se voit qu'a l'ordre d'exécution.
    """
    demande = os.environ.get(variable, "medium")
    return demande if demande in EFFORTS else "medium"


#: Ni un audit exhaustif ni une réponse expédiée. Relevable si les réponses
#: manquent de fond.
EFFORT = effort_valide("SINGULAR_ANALYSE_EFFORT")

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
        raise AnalyseIndisponible(REFUS["paquet"]) from None
    return anthropic

#: Ce que Thomas lit quand une faculté qui a besoin d'un modèle s'arrête.
#:
#: Les six phrases vivaient en double, mot pour mot, dans `analyse.py` et dans
#: `parle.py`. Une copie a déjà divergé -- « le modèle a refusé de répondre. »
#: d'un côté, la même phrase suivie de « Rien n'a été écrit dans ton journal. »
#: de l'autre -- ce qui est exactement ce qu'une règle recopiée finit par faire.
#: Elles ont maintenant un seul domicile, et `test_refus_des_facultes.py`
#: interdit qu'un deuxième s'ouvre.
REFUS = {
    "paquet": ("le paquet « anthropic » n'est pas installé. "
               "python3 -m pip install -e \".[analyse]\" -- ou laisse la faculté coupée."),
    "sans_cle": "aucune clé dans ANTHROPIC_API_KEY. Le reste de SINGULAR marche sans.",
    "cle_refusee": "la clé est refusée. Vérifie ANTHROPIC_API_KEY.",
    "trop_vite": "trop de requêtes. Réessaie dans une minute.",
    "sans_reseau": "pas de réseau. Le reste de SINGULAR marche sans.",
    # Message fixe, sans interpolation : voir `traduit_les_pannes`.
    "imprevu": "le service a échoué d'une façon imprévue. Rien n'a été écrit.",
    "refus_du_modele": "le modèle a refusé de répondre. Rien n'a été écrit dans ton journal.",
}


@contextlib.contextmanager
def traduit_les_pannes():
    """Les pannes du SDK, dites en français, une fois pour les deux facultés.

    Le filet final est le plus important, et c'est lui qu'on oublie : les
    quatre familles nommées ne couvrent pas tout l'arbre du SDK --
    `APIResponseValidationError` descend d'`APIError` sans passer par
    `APIStatusError` ni `APIConnectionError`, et s'échappait donc d'ici. Ce qui
    s'échappe remonte tel quel : en traceback dans la console, et en clair dans
    le corps JSON du Sage, qui renvoie `f"{type(exc).__name__}: {exc}"` sur
    toute exception imprévue. Le texte brut d'une exception du SDK peut porter
    l'en-tête d'authentification selon les versions -- d'où un message fixe :
    le détail qu'on afficherait est exactement celui qu'on ne veut pas voir
    sortir.
    """
    anthropic = _sdk()
    try:
        yield
    except anthropic.AuthenticationError:
        raise AnalyseIndisponible(REFUS["cle_refusee"]) from None
    except anthropic.RateLimitError:
        raise AnalyseIndisponible(REFUS["trop_vite"]) from None
    except anthropic.APIConnectionError:
        raise AnalyseIndisponible(REFUS["sans_reseau"]) from None
    except anthropic.APIStatusError as erreur:
        raise AnalyseIndisponible(f"le service a répondu {erreur.status_code}.") from None
    except anthropic.AnthropicError:
        raise AnalyseIndisponible(REFUS["imprevu"]) from None


def client_par_defaut(client: Any) -> Any:
    """Le client injecté, ou celui que la clé d'environnement permet.

    Les deux facultés ouvrent pareil : `client` injecté par les tests, sinon
    une clé lue dans l'environnement, sinon un refus.
    """
    if client is not None:
        return client
    cle = os.environ.get("ANTHROPIC_API_KEY")
    if not cle:
        raise AnalyseIndisponible(REFUS["sans_cle"])
    return _sdk().Anthropic(api_key=cle)


def apercu(notice: dict[str, Any]) -> str:
    """Exactement ce qui quittera la machine : l'instruction et le rapport.

    `contexte_pour_analyse` disait deja « exactement ce qui quittera la
    machine », et c'etait faux d'un bloc : l'instruction systeme part aussi.
    Elle le nomme, elle cite sa constitution, et il ne la voyait nulle part.

    Mesure a l'appui : `test_ce_qui_part.py` capture ce que le client recoit
    reellement et exige que cet apercu le couvre entierement. Une promesse
    d'affichage qui derive de l'envoi est pire que pas d'affichage.
    """
    return f"{INSTRUCTION}\n\n{contexte_pour_analyse(notice)}"


def _consommation(reponse: Any) -> dict[str, int]:
    """Ce que l'appel a coûté, en jetons.

    Ici plutôt que dans `parle` : les trois facultés qui dépensent le lisent, et
    `analyse` est celle dont les deux autres dépendent déjà. Le compteur vivait
    dans `parle`, ce qui obligeait `offres` à importer un nom privé du module
    voisin et interdisait à `analyse` de s'en servir — donc `analyse` ne
    comptait rien du tout, et ce qu'elle dépensait n'apparaissait nulle part.
    """
    usage = getattr(reponse, "usage", None)
    return {
        "entree": getattr(usage, "input_tokens", 0) or 0,
        "sortie": getattr(usage, "output_tokens", 0) or 0,
        "cache_lu": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_ecrit": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }


def analyser(notice: dict[str, Any], *, modele: str | None = None,
             client: Any = None) -> tuple[str, dict[str, int]]:
    """Le commentaire du modèle sur un rapport déjà calculé, et ce qu'il a coûté.

    Le coût est rendu comme par `parle.repondre` et `offres.chercher` : cette
    commande dépensait de l'argent réel sans que rien ne l'enregistre, donc le
    solde affiché sur le téléphone était faux de tout ce qui avait été analysé
    au clavier.

    `client` est injectable pour que les tests n'aient jamais besoin d'un
    réseau ni d'une clé : un test qui appellerait le vrai service ne testerait
    pas ce fichier, il testerait la météo.
    """
    client = client_par_defaut(client)
    with traduit_les_pannes():
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

    if reponse.stop_reason == "refusal":
        raise AnalyseIndisponible(REFUS["refus_du_modele"])
    texte = "\n".join(bloc.text for bloc in reponse.content if bloc.type == "text").strip()
    return texte, _consommation(reponse)


__all__ = [
    "EFFORT", "EFFORTS", "JETONS_MAX", "MODELE_PAR_DEFAUT",
    "AnalyseIndisponible", "analyser", "apercu", "contexte_pour_analyse",
    "effort_valide",
]
