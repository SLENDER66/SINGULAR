"""Ce que l'outil montre avant d'envoyer doit etre ce qu'il envoie.

Trois facultes font sortir quelque chose de sa machine, et les trois affichent
ce qui partirait -- `--blanc` au clavier, un bloc depliable dans l'app. C'est
la seule chose qui lui permette de savoir ce qui est dit de lui : « il a le
droit de relire ce qui est dit de lui avant que ca parte ».

Une promesse d'affichage qui derive de l'envoi est pire que pas d'affichage :
elle rassure sur ce qu'elle ne montre plus. Ce fichier la mesure au lieu de la
croire -- il capture ce que le client recoit reellement et exige que l'apercu
le couvre entierement.

Ce qu'il a deja attrape :

- la conversation n'avait aucun apercu, alors que c'est elle qui envoie le plus
  -- le rapport du jour **et** tout le fil des tours precedents -- et qu'elle
  part de son telephone ;
- `analyse` et `offres` affichaient le contexte mais pas l'instruction
  systeme, qui part aussi. Elle le nomme, elle cite sa constitution, et pour
  la recherche elle porte la garantie qui compte : « tu ne postules jamais ».
"""
from __future__ import annotations

import pathlib
import tempfile
from datetime import UTC, datetime, timedelta

import pytest

from singular.journal import DecisionJournal, Tier
from singular.sage.notice import build_notice


class FauxBloc:
    type = "text"
    text = "une reponse"


class FausseConso:
    input_tokens = output_tokens = 1
    cache_read_input_tokens = cache_creation_input_tokens = 0


class FausseReponse:
    content = [FauxBloc()]
    stop_reason = "end_turn"
    usage = FausseConso()


class ClientQuiEcoute:
    """Il ne repond pas : il note ce qu'on lui a donne."""

    def __init__(self) -> None:
        self.recu: dict = {}

    @property
    def beta(self):
        return self

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        self.recu = kwargs
        return FausseReponse()

    def blocs(self) -> list[str]:
        """Tout le texte qui a quitte la machine, bloc par bloc."""
        morceaux = []
        systeme = self.recu.get("system", "")
        if isinstance(systeme, str):
            morceaux.append(systeme)
        else:
            morceaux += [bloc["text"] for bloc in systeme]
        for message in self.recu.get("messages", []):
            contenu = message["content"]
            if isinstance(contenu, list):
                contenu = "".join(bloc.get("text", "") for bloc in contenu)
            morceaux.append(contenu)
        return [morceau for morceau in morceaux if morceau.strip()]


@pytest.fixture
def notice():
    dossier = pathlib.Path(tempfile.mkdtemp())
    journal = DecisionJournal(dossier / "journal.db")
    journal.add(title="Postuler chez Thermibel", action="candidature + projet",
                predicted="Un entretien avant le 20", probability=0.75,
                tier=Tier.REVENUS, cost_hours=4, horizon_days=14,
                now=datetime.now(UTC) - timedelta(days=20))
    return build_notice(journal).as_dict()


def _rien_ne_part_en_cachette(vu: str, envoye: list[str], quoi: str) -> None:
    manquants = [bloc for bloc in envoye if bloc not in vu]
    assert not manquants, (
        f"{quoi} envoie {len(manquants)} bloc(s) que l'apercu ne montre pas :\n"
        + "\n".join(f"  ...{bloc[:120]}..." for bloc in manquants)
        + "\n\nUn apercu qui derive de l'envoi rassure sur ce qu'il ne montre plus."
    )


def test_the_analysis_shows_everything_it_sends(notice) -> None:
    from singular.analyse import analyser, apercu

    client = ClientQuiEcoute()
    vu = apercu(notice)
    analyser(notice, client=client)

    _rien_ne_part_en_cachette(vu, client.blocs(), "analyse")
    assert "Thomas" in vu, "l'instruction le nomme : il doit la voir"


def test_the_job_search_shows_everything_it_sends() -> None:
    from singular.offres import apercu, chercher

    client = ClientQuiEcoute()
    vu = apercu("plutot du tertiaire")
    chercher("plutot du tertiaire", client=client)

    _rien_ne_part_en_cachette(vu, client.blocs(), "offres")
    assert "plutot du tertiaire" in vu, "sa precision doit se relire avant de partir"
    assert "postules jamais" in vu, (
        "la garantie qui compte est dans l'instruction : elle doit se lire")


def test_the_conversation_shows_everything_it_sends(notice, tmp_path, monkeypatch) -> None:
    """La faculte qui envoie le plus, et la seule qui n'avait pas d'apercu.

    Au deuxieme tour, ce qui part contient le rapport du jour, l'instruction,
    la question precedente, la reponse precedente, et la nouvelle question.
    """
    from singular import parle
    from singular.analyse import contexte_pour_analyse

    monkeypatch.setattr(parle, "FICHIER", tmp_path / "fil.json")
    monkeypatch.setattr(parle, "FICHIER_QUOTA", tmp_path / "quota.json")

    contexte = contexte_pour_analyse(notice)
    fil = parle.Conversation()
    parle.repondre("ma premiere question", contexte, fil, client=ClientQuiEcoute())
    fil.sauver()

    client = ClientQuiEcoute()
    vu = parle.apercu(contexte, fil, "ma seconde question")
    parle.repondre("ma seconde question", contexte, fil, client=client)

    _rien_ne_part_en_cachette(vu, client.blocs(), "parle")
    assert "ma premiere question" in vu, "le fil part aussi : il doit se voir"
    assert "ma seconde question" in vu


def test_the_preview_shows_nothing_that_does_not_leave(notice) -> None:
    """L'inverse compte : un apercu qui montre plus que ce qui part ment aussi.

    Il ferait croire a une fuite qui n'existe pas, et la prochaine fois qu'il
    lira ce bloc il le sautera.
    """
    from singular.analyse import analyser, apercu

    client = ClientQuiEcoute()
    vu = apercu(notice)
    analyser(notice, client=client)

    tout_ce_qui_part = "\n".join(client.blocs())
    inventes = [ligne for ligne in vu.splitlines()
                if ligne.strip() and ligne not in tout_ce_qui_part]
    assert not inventes, f"l'apercu montre {inventes[:3]} qui ne part pas"


def test_the_journal_itself_never_leaves(notice) -> None:
    """On envoie la Notice, pas la base : les agregats, pas l'historique.

    Ce qui part porte quand meme du texte a lui -- le resultat qu'il attend est
    dans les observations -- et c'est assume. Ce qui ne doit pas partir, c'est
    la base : les empreintes de la chaine, les identifiants internes en vrac,
    les lecons ecrites apres coup.
    """
    from singular.analyse import apercu

    vu = apercu(notice)
    assert "fingerprint" not in vu
    assert "previous_fingerprint" not in vu
    assert "brier_score" not in vu, "le detail par decision reste a la maison"


def test_the_path_of_his_journal_never_leaves(tmp_path) -> None:
    """L'app dit ou elle a regarde. Ce chemin porte son nom d'utilisateur.

    Un journal vide et un mauvais journal donnent le meme ecran, et deux
    fichiers existent -- le PC et le telephone -- qui ne se parlent pas. Dire
    ou l'on a cherche coute une ligne et rend la confusion impossible a rater.

    Mais le chemin est `C:\\Users\\<son nom>\\...`. Il s'affiche chez lui ; il
    n'a rien a faire dans ce qui part vers un service. Il est donc pose en
    dehors de `items` et de `report`, qui sont exactement ce que le contexte
    recopie.
    """
    from singular.analyse import contexte_pour_analyse
    from singular.journal import DecisionJournal
    from singular.sage.server import SageApp

    journal = DecisionJournal(tmp_path / "journal.db")
    rendu = SageApp(journal).notice()

    assert rendu["journal"] == str(journal.path), "l'app doit dire ou elle a regarde"
    assert str(tmp_path) not in contexte_pour_analyse(rendu), (
        "le chemin de son journal part vers le service")
