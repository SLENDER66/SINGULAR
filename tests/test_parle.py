"""La conversation : ce qu'elle retient, ce qu'elle coute, ce qu'elle ne peut pas.

C'est la difference entre parler a Claude dans son application et parler a
SINGULAR : le modele est le meme, mais ici le rapport du jour et le fil
precedent sont deja la. Trois choses doivent tenir pour que ca vaille mieux
qu'un chatbot, et aucune n'est verifiable en lisant un prompt.

Aucun test ne touche au reseau : le client est injectable. Sur un budget de
cinq dollars, un test qui appellerait le vrai service couterait de l'argent a
chaque execution du CI.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from singular.analyse import AnalyseIndisponible
from singular.parle import TOURS_GARDES, Conversation, repondre

SOURCE = pathlib.Path(__file__).resolve().parent.parent / "singular" / "parle.py"


class FauxBloc:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class FausseConso:
    input_tokens = 120
    output_tokens = 40
    cache_read_input_tokens = 900
    cache_creation_input_tokens = 0


class FausseReponse:
    def __init__(self, texte: str = "Voila.", stop_reason: str = "end_turn") -> None:
        self.content = [FauxBloc(texte)]
        self.stop_reason = stop_reason
        self.usage = FausseConso()


class FauxClient:
    def __init__(self, reponse: FausseReponse | None = None) -> None:
        self.appels: list[dict] = []
        self._reponse = reponse or FausseReponse()

    @property
    def beta(self):
        return self

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        self.appels.append(kwargs)
        return self._reponse


@pytest.fixture
def fil(tmp_path) -> Conversation:
    return Conversation(tmp_path / "conversation.json")


# --- ce qu'elle ne peut pas faire --------------------------------------------

def test_elle_n_ecrit_rien_dans_le_journal() -> None:
    """Parler d'une decision ne doit pas l'enregistrer.

    Un systeme qui inscrit des decisions parce qu'on en a parle finit par
    contenir des choses que personne n'a decidees -- et la chaine d'integrite
    du journal ne vaut que si chaque entree vient d'un geste volontaire.
    """
    arbre = ast.parse(SOURCE.read_text(encoding="utf-8"))
    importes = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            importes.update(a.name for a in noeud.names)
        elif isinstance(noeud, ast.ImportFrom):
            importes.add(noeud.module or "")
            importes.update(a.name for a in noeud.names)

    interdits = {"journal", "DecisionJournal", "singular.journal", ".journal",
                 "execution", "durable_execution", "effects"}
    assert not (importes & interdits), sorted(importes & interdits)


def test_sans_cle_elle_se_declare_coupee(monkeypatch, fil) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(AnalyseIndisponible, match="ANTHROPIC_API_KEY"):
        repondre("bonjour", "rapport", fil)


# --- ce qu'elle retient -------------------------------------------------------

def test_le_fil_survit_a_un_relancement(tmp_path) -> None:
    """Sans ca, ce serait un chatbot de plus : chaque lancement repartirait a zero."""
    chemin = tmp_path / "conversation.json"
    fil = Conversation(chemin)
    client = FauxClient()

    repondre("ma premiere question", "rapport", fil, client=client)
    fil.sauver()

    repris = Conversation(chemin)
    assert [t["content"] for t in repris.tours] == ["ma premiere question", "Voila."]


def _textes(messages: list[dict]) -> list[str]:
    """Le texte de chaque message, que le contenu soit brut ou en blocs.

    Le dernier tour deja enregistre part en blocs, parce qu'il porte la marque
    de cache. Comparer des chaines ici garderait le test lisible et le rendrait
    faux des qu'on touche a la mise en cache.
    """
    textes = []
    for message in messages:
        contenu = message["content"]
        textes.append(contenu if isinstance(contenu, str)
                      else "".join(bloc["text"] for bloc in contenu))
    return textes


def test_le_tour_precedent_est_renvoye_au_modele(fil) -> None:
    client = FauxClient()
    repondre("premiere", "rapport", fil, client=client)
    repondre("seconde", "rapport", fil, client=client)

    assert _textes(client.appels[1]["messages"]) == ["premiere", "Voila.", "seconde"]


def test_le_fil_est_mis_en_cache_jusqu_au_dernier_tour(fil) -> None:
    """Sinon le fil entier est refacture au plein tarif a chaque tour.

    C'est ce qui decide si une conversation continue tient sur cinq dollars :
    le vingtieme tour coute vingt fois le premier, ou il relit un cache.
    """
    client = FauxClient()
    repondre("premiere", "rapport", fil, client=client)
    repondre("seconde", "rapport", fil, client=client)

    messages = client.appels[1]["messages"]
    marques = [i for i, m in enumerate(messages)
               if isinstance(m["content"], list)
               and any("cache_control" in bloc for bloc in m["content"])]
    assert marques == [len(messages) - 2], (
        "la marque doit etre sur le dernier tour enregistre, pas ailleurs")


def test_la_question_du_moment_n_est_jamais_dans_le_cache(fil) -> None:
    """Le cache est un prefixe : une question qui change a chaque fois, placee
    dedans, invaliderait exactement ce qu'on essaie de garder."""
    client = FauxClient()
    repondre("premiere", "rapport", fil, client=client)
    repondre("seconde", "rapport", fil, client=client)

    derniere = client.appels[1]["messages"][-1]
    assert derniere["content"] == "seconde"
    assert not isinstance(derniere["content"], list)


def test_le_premier_tour_n_a_rien_a_mettre_en_cache(fil) -> None:
    """Aucun fil derriere lui : marquer quoi que ce soit serait marquer la
    question elle-meme."""
    client = FauxClient()
    repondre("premiere", "rapport", fil, client=client)

    messages = client.appels[0]["messages"]
    assert messages == [{"role": "user", "content": "premiere"}]


def test_le_fil_est_borne(fil) -> None:
    """Une conversation renvoie tout son historique a chaque tour : sans borne,
    le centieme tour coute cent fois le premier."""
    client = FauxClient()
    for i in range(TOURS_GARDES + 5):
        repondre(f"question {i}", "rapport", fil, client=client)

    assert len(fil.tours) == TOURS_GARDES * 2
    assert fil.tours[-2]["content"] == f"question {TOURS_GARDES + 4}"


def test_un_fil_illisible_ne_fait_pas_perdre_la_parole(tmp_path) -> None:
    """Le journal refuserait de s'ouvrir ; lui porte des faits, pas une discussion."""
    chemin = tmp_path / "conversation.json"
    chemin.write_text("{ceci n'est pas du json", encoding="utf-8")

    assert Conversation(chemin).tours == []


def test_oublier_efface_le_fil_et_rien_d_autre(tmp_path, fil) -> None:
    client = FauxClient()
    repondre("une question", "rapport", fil, client=client)
    fil.sauver()
    assert fil.chemin.exists()

    fil.oublier()

    assert fil.tours == []
    assert not fil.chemin.exists()


# --- ce qu'elle coute ---------------------------------------------------------

def test_le_rapport_est_mis_en_cache_et_la_question_reste_dehors(fil) -> None:
    """Le cache est un prefixe : le moindre octet qui change avant ce point le
    perd. La question, qui change a chaque tour, ne doit donc jamais y entrer."""
    client = FauxClient()
    repondre("ma question", "LE RAPPORT DU JOUR", fil, client=client)

    systeme = client.appels[0]["system"]
    assert len(systeme) == 1
    assert systeme[0]["cache_control"] == {"type": "ephemeral"}
    assert "LE RAPPORT DU JOUR" in systeme[0]["text"]
    assert "ma question" not in systeme[0]["text"]


def test_la_consommation_est_rendue_a_l_appelant(fil) -> None:
    """Sur cinq dollars, on ne corrige pas ce qu'on ne voit pas."""
    _, cout = repondre("une question", "rapport", fil, client=FauxClient())

    assert cout == {"entree": 120, "sortie": 40, "cache_lu": 900, "cache_ecrit": 0}


def test_une_reponse_sans_compteur_ne_fait_pas_echouer_le_tour(fil) -> None:
    """Un fournisseur qui ne rend pas d'`usage` ne doit pas couper la parole."""
    reponse = FausseReponse()
    del reponse.usage

    _, cout = repondre("une question", "rapport", fil, client=FauxClient(reponse))

    assert cout == {"entree": 0, "sortie": 0, "cache_lu": 0, "cache_ecrit": 0}


def test_un_refus_ne_devient_pas_une_reponse_vide(fil) -> None:
    with pytest.raises(AnalyseIndisponible, match="refus"):
        repondre("x", "rapport", fil, client=FauxClient(FausseReponse("", "refusal")))


def test_le_fil_ecrit_est_relisible(tmp_path, fil) -> None:
    repondre("une question", "rapport", fil, client=FauxClient())
    fil.sauver()

    donnees = json.loads(fil.chemin.read_text(encoding="utf-8"))
    assert donnees["tours"][0]["role"] == "user"
    assert donnees["maj"]
