"""Le premier agent : ce qu'il ne peut pas faire compte plus que ce qu'il fait.

Il cherche des offres et il en propose. Il ne postule pas, il n'ecrit rien, et
il ne decide de rien -- c'est la reponse que Thomas a donnee quand la question
lui a ete posee, et c'est aussi ce que la constitution impose : penser n'est
pas decider, decider n'est pas autoriser, autoriser n'est pas executer.

Une instruction systeme qui dit « ne postule jamais » se contourne par une
tournure de phrase. Une absence d'import, non. Ces tests jugent la structure.

Aucun ne touche au reseau : le client est injectable. Un test qui appellerait
le vrai service testerait la meteo, et couterait de l'argent a chaque
execution du CI -- sur un budget de cinq dollars.
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

from singular.analyse import AnalyseIndisponible
from singular.offres import (
    JETONS_MAX,
    MODELE_PAR_DEFAUT,
    RECHERCHES_MAX,
    chercher,
    contexte_pour_recherche,
)

SOURCE = pathlib.Path(__file__).resolve().parent.parent / "singular" / "offres.py"


class FauxBloc:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class FausseReponse:
    def __init__(self, texte: str = "Trois offres.", stop_reason: str = "end_turn") -> None:
        self.content = [FauxBloc(texte)]
        self.stop_reason = stop_reason


class FauxClient:
    def __init__(self, reponse: FausseReponse | None = None) -> None:
        self.appels: list[dict] = []
        self._reponse = reponse or FausseReponse()
        self.beta = self

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        self.appels.append(kwargs)
        return self._reponse


# --- ce qu'il ne peut pas faire ----------------------------------------------

def test_il_ne_connait_ni_le_journal_ni_l_execution() -> None:
    """Proposer n'est pas agir, et la separation est dans les imports.

    S'il pouvait ecrire dans le journal, un agent qui « trouve une offre
    interessante » pourrait enregistrer la decision de postuler. Il n'a pas
    de quoi.
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
                 "execution", "durable_execution", "capabilities", "effects",
                 "providers", "smtplib", "urllib", "requests", "httpx"}
    assert not (importes & interdits), (
        f"cet agent doit proposer, pas agir : {sorted(importes & interdits)}"
    )


def test_le_coeur_ne_charge_pas_l_agent_pour_demarrer() -> None:
    """Aucun import au chargement : le Sage demarre sur une machine sans agent.

    Un import a l'interieur d'une methode ne s'execute que si on appelle la
    route. Un import en tete de fichier s'execute a l'ouverture de l'app, et
    rendrait le journal dependant d'une faculte qui appelle un service. C'est
    la difference que ce test regarde -- l'ancien interdisait les deux, donc
    aussi le branchement que Thomas a demande, sans rien prouver de plus.
    """
    racine = SOURCE.parent
    fautes = []
    for fichier in [*(racine / "sage").rglob("*.py"), racine / "journal.py"]:
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        for noeud in arbre.body:  # le corps du module, pas celui des fonctions
            noms = []
            if isinstance(noeud, ast.ImportFrom):
                noms = [noeud.module or "", *(a.name for a in noeud.names)]
            elif isinstance(noeud, ast.Import):
                noms = [a.name for a in noeud.names]
            fautes += [fichier.name for nom in noms if "offres" in nom]
    assert not fautes, fautes


def test_l_agent_retire_ne_casse_rien_d_autre(tmp_path, monkeypatch) -> None:
    """La preuve par l'acte : on retire le module, tout le gratuit doit marcher.

    Un test d'imports montre que le coeur ne charge pas l'agent. Il ne montre
    pas que le coeur s'en passe : c'est ce que dit la regle du depot -- une
    faculte qui a besoin d'un modele doit pouvoir etre coupee sans rien casser
    d'autre -- et c'est verifiable en coupant pour de bon.
    """
    from http import HTTPStatus

    from singular.journal import DecisionJournal, Tier
    from singular.sage.server import SageApp, SageError

    journal = DecisionJournal(tmp_path / "journal.db")
    app = SageApp(journal)

    # `None` dans sys.modules : tout import de `singular.offres` echoue, comme
    # si le fichier n'avait jamais ete livre.
    monkeypatch.setitem(sys.modules, "singular.offres", None)

    entree = journal.add(title="Postuler", action="candidature", predicted="un entretien",
                         probability=0.75, tier=Tier.REVENUS, cost_hours=4, horizon_days=14)
    assert journal.verify() is True
    assert app.notice()["headline"].startswith("Notice.")
    assert app.entries()["entries"], "la liste des decisions doit encore se lire"
    journal.resolve(entree.entry_id, happened=True)
    assert journal.verify() is True

    for appel in (app.offres_etat, lambda: app.offres({})):
        with pytest.raises(SageError) as refus:
            appel()
        assert refus.value.status == HTTPStatus.SERVICE_UNAVAILABLE
        assert "marchent sans elle" in refus.value.message


def test_le_temoin_du_retrait() -> None:
    """Sans le sabotage ci-dessus, le test passerait meme s'il ne coupait rien."""
    import importlib

    assert importlib.import_module("singular.offres") is not None


# --- ce qui part, et ce qui revient ------------------------------------------

def test_sans_cle_il_se_declare_coupe(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(AnalyseIndisponible, match="ANTHROPIC_API_KEY"):
        chercher()


def test_le_contexte_porte_les_criteres_et_la_precision() -> None:
    texte = contexte_pour_recherche("je peux aller jusqu'a Montauban")

    assert "Toulouse" in texte
    assert "50 000 m3/h" in texte
    assert "Montauban" in texte


def test_le_contexte_est_exactement_ce_qui_est_envoye() -> None:
    """L'apercu doit etre la meme chaine que ce qui part, pas une approximation."""
    client = FauxClient()
    chercher("une precision", client=client)

    assert client.appels[0]["messages"][0]["content"] == contexte_pour_recherche("une precision")


def test_la_recherche_web_est_bornee() -> None:
    """Chaque recherche ramene des pages entieres : le plafond rend la facture
    previsible, sur un budget de cinq dollars."""
    client = FauxClient()
    chercher(client=client)

    outils = client.appels[0]["tools"]
    assert len(outils) == 1
    assert outils[0]["type"] == "web_search_20260209"
    assert outils[0]["max_uses"] == RECHERCHES_MAX
    assert RECHERCHES_MAX <= 10, "au-dela, le cout d'un appel n'est plus previsible"
    assert client.appels[0]["max_tokens"] == JETONS_MAX


def test_aucun_outil_d_execution_de_code_n_est_declare() -> None:
    """`web_search_20260209` fait tourner du code chez Anthropic pour filtrer.

    En declarer un second embrouille le modele -- c'est ecrit dans la
    documentation de l'outil -- et surtout, executer du code n'a rien a faire
    dans un agent qui doit seulement lire et proposer.
    """
    client = FauxClient()
    chercher(client=client)

    types = {outil["type"] for outil in client.appels[0]["tools"]}
    assert not any(t.startswith("code_execution") for t in types), types


def test_le_modele_et_le_repli_sont_ceux_attendus() -> None:
    client = FauxClient()
    chercher(client=client)

    appel = client.appels[0]
    assert appel["model"] == MODELE_PAR_DEFAUT
    assert appel["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in appel["betas"]


def test_un_refus_ne_devient_pas_une_liste_vide() -> None:
    client = FauxClient(FausseReponse("", stop_reason="refusal"))
    with pytest.raises(AnalyseIndisponible, match="refuse"):
        chercher(client=client)


def test_l_instruction_interdit_d_inventer_une_offre() -> None:
    """Une annonce fabriquee couterait une journee, et la confiance avec.

    Le prompt ne garantit rien a lui seul -- mais son absence garantirait
    l'inverse, et une reecriture qui l'enleverait passerait sans bruit.
    """
    from singular.offres import INSTRUCTION

    assert "fabrique jamais" in INSTRUCTION
    assert "postule" in INSTRUCTION


# --- ce que l'agent croit savoir de lui ---------------------------------------

def test_chaque_ligne_du_profil_porte_sa_provenance() -> None:
    """Le meme garde-fou que le prototype, dans le module qui transmet.

    `proto/suivi_candidatures.py` marque chaque ligne DIT ou DEDUIT depuis que
    deux deductions non demandees ont coute a Thomas un CV faux et un marche
    ecarte. Ce fichier-ci decrit la meme vie, plus recemment, et il l'envoie a
    un service distant -- sans marque, et sans test. Son commentaire promettait
    « rien ici n'est deduit ». Une promesse n'est pas une garantie.

    Ce qu'elle laissait passer, verifie apres coup : « une offre d'alternance
    ne se retient que si elle dit prendre en charge la recherche d'ecole »
    etait une regle de filtrage inventee dans ce fichier, posee au milieu de ce
    qu'il aurait dit. Elle ecartait des annonces que personne n'avait demande
    d'ecarter -- exactement la faute deja payee, refaite.
    """
    from singular.offres import CRITERES, DEDUIT, DIT

    fautes = [
        repr(entree) for entree in CRITERES
        if not (isinstance(entree, tuple) and len(entree) == 2
                and isinstance(entree[0], str) and entree[1] in (DIT, DEDUIT))
    ]
    assert not fautes, (
        "chaque ligne de CRITERES doit dire d'ou elle vient -- DIT ou DEDUIT :\n  "
        + "\n  ".join(fautes)
        + "\n  Une chaine seule voudrait dire « quelqu'un l'a ecrit, on ne sait plus qui »."
    )


def test_une_deduction_part_avec_son_etiquette() -> None:
    """Si une deduction entre quand meme, elle ne doit pas voyager deguisee."""
    from singular import offres

    veritables = list(offres.CRITERES)
    try:
        offres.CRITERES.append(("Il vise plutot l'industriel.", offres.DEDUIT))
        texte = offres.contexte_pour_recherche()
    finally:
        offres.CRITERES[:] = veritables

    assert "Ceci n'est pas verifie" in texte
    assert "- Il vise plutot l'industriel." in texte

    # Et **seulement** la. La premiere version de ce test se contentait de la
    # trouver quelque part : une deduction posee dans le corps du profil ET
    # repetee sous l'etiquette passait, alors que l'agent l'aurait lue comme un
    # fait avant d'arriver a l'avertissement.
    avant, _, apres = texte.partition("Ceci n'est pas verifie")
    assert "industriel" not in avant, (
        "la deduction apparait dans le corps du profil, avant son etiquette")
    assert "industriel" in apres


def test_le_profil_ne_porte_aucune_consigne_de_filtrage() -> None:
    """Un profil dit qui il est. Il ne dit pas ce qu'il faut ecarter.

    La regle inventee s'etait glissee la parce qu'une consigne ressemble a un
    fait quand on la pose au milieu d'une liste de faits. Elle n'y a pas sa
    place : ce que l'agent doit faire est dans `INSTRUCTION`, ce que Thomas est
    est dans `CRITERES`, et melanger les deux fait passer une decision pour une
    biographie.
    """
    from singular.offres import CRITERES

    verbes = ("ne se retient que", "il faut", "tu dois", "ecarte", "ignore",
              "ne retiens", "privilegie", "exclus")
    fautes = [texte for texte, _ in CRITERES
              if any(verbe in texte.lower() for verbe in verbes)]
    assert not fautes, (
        f"{fautes} sont des consignes, pas des faits sur lui. "
        "Ce que l'agent doit faire va dans INSTRUCTION.")


def test_les_deux_profils_du_depot_ne_se_contredisent_pas() -> None:
    """Deux fichiers decrivent sa vie. Ils doivent dire la meme chose.

    `proto/suivi_candidatures.py` et `singular/offres.py` portent chacun leur
    copie. Une correction faite a l'un et pas a l'autre laisse la contradiction
    ailleurs -- et c'est celle qui part vers le service distant qui compte.
    """
    import importlib.util
    import pathlib

    from singular.offres import CRITERES, DIT

    chemin = pathlib.Path(__file__).resolve().parent.parent / "proto/suivi_candidatures.py"
    spec = importlib.util.spec_from_file_location("suivi_profil", chemin)
    suivi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(suivi)

    dit_ici = " ".join(texte for texte, source in CRITERES if source == DIT).lower()
    dit_la = " ".join(texte for texte, source in suivi.PROFIL
                      if source == suivi.DIT).lower()

    # Les faits que les deux doivent porter pareil. Chacun a coute une session.
    for fait in ("2 ans en bureau d'etudes", "bts fluides energies domotique",
                 "chambres froides", "alternance", "ni ecole ni"):
        assert (fait in dit_ici) == (fait in dit_la), (
            f"« {fait} » n'est pas dit pareil des deux cotes : "
            "une correction n'a ete faite qu'a un endroit")
