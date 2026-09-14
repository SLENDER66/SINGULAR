"""Genesis, et surtout ce qu'elle refuse de conclure.

L'hypothèse de la directive est qu'une expérience vérifiée devient une capacité
réutilisable, et qu'une capacité réutilisable rend une mission suivante
objectivement meilleure. Un banc qui ne sait que confirmer ne prouve rien : il
mesure sa propre complaisance.

Ce fichier tient donc les deux bords, et le second est le vrai sujet.

**Ce qui doit marcher.** Les trois missions sur les fichiers réels du dépôt :
ALPHA exécute et vérifie, BETA détecte un manque et récupère sans rien inventer,
GAMMA échoue faute de capacité puis construit la sienne, l'éprouve et l'inscrit.

**Ce qui doit être refusé.** Une amélioration mesurée sur l'instance qui a servi
à apprendre. Une capacité qui a mémorisé au lieu d'apprendre. Un gain de coût
payé par un appel à un humain. Une réponse fausse mais moins chère. Un niveau de
preuve qui monte malgré un échec. Un artefact substitué sous un nom déjà prouvé.

Chaque refus a son test, parce qu'un refus sans test est une intention.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from singular.genesis import (Etape, Mission, Preuve, Registre, SubstitutionRefusee,
                             Trajectoire, banc, executer, constater_naissance)
from singular.genesis.bench import AMELIORATION, AUCUNE, REFUTE
from singular.genesis.capability import PLAFOND_APRES_ECHEC
from singular.genesis.lecteurs import FormatRefuse
from singular.genesis.missions import (GAMMA_APPRENTISSAGE, GAMMA_CONTROLE, LECTEUR_APPRIS,
                                       alpha, apprendre_de_gamma, beta, construire_lecteur,
                                       construire_lecteur_memorisant, gamma, prouver_emploi,
                                       resoudre, sources_du_depot)

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture
def sources() -> dict[str, str]:
    return sources_du_depot(RACINE)


def solveur(mission, trajectoire, registre):
    return resoudre(mission, trajectoire, registre)


def _registre_apres_gamma() -> Registre:
    registre = Registre()
    assert apprendre_de_gamma(registre, Trajectoire("acquisition"))
    return registre


# --- ALPHA : exécuter et vérifier ---------------------------------------------

def test_alpha_repond_et_le_juge_recalcule(sources) -> None:
    """Deux sources, deux formats, et un verdict que le solveur ne donne pas.

    Le vérificateur relit `CHANGELOG.md` et `pyproject.toml` par son propre
    chemin. Un solveur qui déclarerait avoir réussi ne changerait rien au verdict.
    """
    resultat = executer(alpha(sources), lambda m, t: resoudre(m, t, Registre()))
    assert resultat.verifie
    assert resultat.reponse["pyproject.version"] == resultat.reponse["changelog.version"][:1], (
        "le changelog ouvre sur la version publiée : c'est ce que la mission demandait")


def test_alpha_tatonne_et_la_trajectoire_le_montre(sources) -> None:
    """Sans capacité, le solveur essaie des lecteurs et se trompe avant de trouver.

    Ce n'est pas un défaut : c'est la ligne de base contre laquelle une capacité
    apprise sera mesurée. Une trajectoire sans aucun échec signifierait que le
    chemin long n'est pas plus long, et il n'y aurait rien à améliorer.
    """
    resultat = executer(alpha(sources), lambda m, t: resoudre(m, t, Registre()))
    assert resultat.erreurs > 0
    assert resultat.recuperations > 0


def test_un_solveur_qui_ment_ne_passe_pas(sources) -> None:
    """Le point entier de séparer le juge du solveur."""
    resultat = executer(alpha(sources), lambda m, t: {"changelog.version": ["999.0.0"]})
    assert not resultat.verifie
    assert "vérificateur" in resultat.pourquoi


def test_un_solveur_qui_plante_rate_au_lieu_de_tout_interrompre(sources) -> None:
    """Le banc doit pouvoir comparer une mission ratée à une mission réussie."""
    def casse(mission, trajectoire):
        raise RuntimeError("boum")

    resultat = executer(alpha(sources), casse)
    assert not resultat.verifie
    assert resultat.erreurs == 1
    assert "RuntimeError" in resultat.pourquoi


# --- BETA : échouer, diagnostiquer, récupérer ---------------------------------

def test_beta_recupere_sans_rien_inventer(sources) -> None:
    """Une source tronquée, une absente, et une réponse qui ne comble pas les trous.

    Le mandat en fait une règle de vie : ne jamais combler un blanc par une
    déduction. Ici c'est vérifiable — le vérificateur refuse toute réponse qui
    contiendrait une version pour la source qu'on n'a pas pu lire.
    """
    resultat = executer(beta(sources), lambda m, t: resoudre(m, t, Registre()))
    assert resultat.verifie
    assert "pyproject.version" not in resultat.reponse
    assert "notice.version" not in resultat.reponse


def test_beta_voit_l_echec_avant_de_le_contourner(sources) -> None:
    """« Il a récupéré » ne se mesure pas sans un échec enregistré avant."""
    resultat = executer(beta(sources), lambda m, t: resoudre(m, t, Registre()))
    genres = [pas.genre for pas in resultat.trajectoire]
    assert Etape.ECHEC in genres
    assert Etape.RECUPERATION in genres
    assert genres.index(Etape.ECHEC) < genres.index(Etape.RECUPERATION)
    absente = [pas for pas in resultat.trajectoire if pas.detail == "source absente"]
    assert absente, "la source manquante doit être diagnostiquée, pas seulement ratée"


# --- GAMMA : détecter le manque et devenir capable ----------------------------

def test_gamma_echoue_avant_d_avoir_la_capacite() -> None:
    """Sans le manque, il n'y a rien à acquérir et la démonstration est truquée."""
    resultat = executer(gamma(GAMMA_APPRENTISSAGE), lambda m, t: resoudre(m, t, Registre()))
    assert not resultat.verifie


def test_gamma_suit_le_cycle_en_entier() -> None:
    """Détecter → construire → bac à sable → inscrire, et dans cet ordre."""
    registre = Registre()
    trajectoire = Trajectoire("acquisition")
    assert apprendre_de_gamma(registre, trajectoire)

    genres = [pas.genre for pas in trajectoire.pas]
    assert genres[0] is Etape.ECHEC, "le manque se constate avant qu'on construise"
    assert Etape.CONSTRUCTION in genres
    assert LECTEUR_APPRIS in registre
    assert registre.chercher(LECTEUR_APPRIS).provenance == "GAMMA"


def test_un_lecteur_qui_rate_le_bac_a_sable_n_est_pas_inscrit() -> None:
    """L'inscription se mérite : un contrôle faux ne doit rien laisser au registre.

    Sans ça, le registre accepterait une capacité sur la foi de celui qui l'a
    écrite, et le niveau de preuve mesurerait sa confiance en lui.
    """
    from singular.genesis.missions import acquerir_lecteur

    registre = Registre()
    acquis = acquerir_lecteur(GAMMA_APPRENTISSAGE, ("journal", "une valeur qui n'y est pas"),
                              Trajectoire("acquisition"), registre, provenance="GAMMA")
    assert not acquis
    assert LECTEUR_APPRIS not in registre


def test_la_capacite_sert_sur_une_autre_instance() -> None:
    """Ce qui distingue une capacité d'un souvenir."""
    registre = _registre_apres_gamma()
    resultat = executer(gamma(GAMMA_CONTROLE, attendu="téléphone"),
                        lambda m, t: resoudre(m, t, registre))
    assert resultat.verifie
    assert resultat.capacites_reutilisees == (LECTEUR_APPRIS,)


# --- le test de naissance : ce qu'on a le droit de conclure -------------------

def test_la_naissance_se_constate_sur_une_instance_nouvelle() -> None:
    """Le cas favorable, et il doit exister, sinon le banc ne mesure rien."""
    naissance = constater_naissance(
        gamma(GAMMA_CONTROLE, nom="GAMMA-controle", attendu="téléphone"),
        solveur, _registre_apres_gamma(), instance="soir", apprises_sur={"matin"})
    assert naissance.ne
    assert naissance.capacites == (LECTEUR_APPRIS,)
    assert naissance.comparaison.verdict == AMELIORATION


def test_une_amelioration_sur_l_instance_apprise_n_est_pas_une_naissance() -> None:
    """Rejouer ce qu'on a vu mesure une mémoire, pas une capacité.

    Le banc tourne quand même et le chiffre reste vrai ; c'est le mot qui est
    refusé, et la raison est écrite plutôt que sous-entendue.
    """
    naissance = constater_naissance(
        gamma(GAMMA_APPRENTISSAGE, nom="GAMMA-rejeu"),
        solveur, _registre_apres_gamma(), instance="matin", apprises_sur={"matin"})
    assert not naissance.ne
    assert "mémorisation" in naissance.pourquoi
    assert naissance.comparaison.verdict == AMELIORATION, (
        "le chiffre reste ce qu'il est : c'est la conclusion qu'on refuse")


def test_une_capacite_qui_a_memorise_est_refutee() -> None:
    """Le cas que ce fichier existe pour attraper.

    Une capacité qui a retenu la réponse réussit la mission d'apprentissage et
    rate la suivante. Le banc doit dire REFUTE, pas AMELIORATION.
    """
    registre = Registre()
    registre.inscrire(LECTEUR_APPRIS, "lire un format clé/valeur",
                      construire_lecteur_memorisant(GAMMA_APPRENTISSAGE,
                                                    {"machine": ["mac"]}),
                      provenance="GAMMA")
    naissance = constater_naissance(
        gamma(GAMMA_CONTROLE, nom="GAMMA-controle", attendu="téléphone"),
        solveur, registre, instance="soir", apprises_sur={"matin"})
    assert not naissance.ne
    assert naissance.comparaison.verdict == REFUTE


def test_une_amelioration_sans_capacite_employee_n_est_pas_une_naissance() -> None:
    """Si l'expérience n'y est pour rien, ce n'est pas l'expérience qui a payé.

    Le solveur va plus vite quand le registre n'est pas vide, mais il n'emploie
    aucune capacité : il regarde seulement s'il y en a. Le chiffre s'améliore,
    et pourtant rien de ce qui a été appris n'a servi. C'est la corrélation
    qu'un banc naïf appellerait un progrès.
    """
    def verifier(reponse, _sources):
        return reponse == "bon"

    mission = Mission("CORRELATION", "peu importe", {"a": "x"}, verifier)

    def solveur_chanceux(mission, trajectoire, registre):
        for _ in range(1 if len(registre) else 4):
            trajectoire.note(Etape.LECTURE, "je cherche")
        return "bon"

    naissance = constater_naissance(mission, solveur_chanceux, _registre_apres_gamma(),
                                    instance="soir", apprises_sur={"matin"})
    assert naissance.comparaison.verdict == AMELIORATION, "le coût a bien baissé"
    assert not naissance.ne
    assert "l'expérience n'y est pour rien" in naissance.pourquoi


def test_un_gain_de_cout_paye_par_un_humain_est_refuse() -> None:
    """Moins d'étapes en appelant plus souvent à l'aide n'est pas une autonomie.

    C'est la métrique optimisée contre la réalité que la directive interdit
    nommément, et c'est le seul refus du banc qu'aucune donnée réelle ne
    produirait toute seule : il se construit.
    """
    def verifier(reponse, _sources):
        return reponse == "bon"

    mission = Mission("PIEGE", "peu importe", {"a": "x"}, verifier)

    def solveur_piege(mission, trajectoire, registre):
        if len(registre):
            trajectoire.note(Etape.HUMAIN, "je demande", cout=0.5)
            return "bon"
        for _ in range(4):
            trajectoire.note(Etape.LECTURE, "je cherche")
        return "bon"

    comparaison = banc(mission, solveur_piege, _registre_apres_gamma())
    assert comparaison.verdict == REFUTE
    assert "interventions_humaines" in comparaison.pourquoi


def test_une_reponse_fausse_moins_chere_est_refusee() -> None:
    """Un coût plus bas sur une réponse fausse est un coût plus bas sur une réponse fausse."""
    def verifier(reponse, _sources):
        return reponse == "bon"

    mission = Mission("PIEGE", "peu importe", {"a": "x"}, verifier)

    def solveur_piege(mission, trajectoire, registre):
        if len(registre):
            trajectoire.note(Etape.LECTURE, "vite")
            return "faux"
        for _ in range(5):
            trajectoire.note(Etape.LECTURE, "lentement")
        return "bon"

    assert banc(mission, solveur_piege, _registre_apres_gamma()).verdict == REFUTE


def test_un_banc_sans_rien_a_gagner_dit_aucune() -> None:
    """Le verdict neutre existe, et ce n'est pas un bug du banc."""
    def verifier(reponse, _sources):
        return reponse == "bon"

    mission = Mission("PLAT", "peu importe", {"a": "x"}, verifier)

    def solveur_plat(mission, trajectoire, registre):
        trajectoire.note(Etape.LECTURE, "pareil des deux côtés")
        return "bon"

    comparaison = banc(mission, solveur_plat, _registre_apres_gamma())
    assert comparaison.verdict == AUCUNE


# --- le registre : l'échelle de preuve et l'identité de l'artefact ------------

def test_le_niveau_ne_monte_que_sur_des_instances_distinctes() -> None:
    """Deux emplois sur la même instance font un rejeu, pas une répétition."""
    registre = _registre_apres_gamma()
    for _ in range(4):
        prouver_emploi(registre, instance="matin", domaine="releve", abimee=False, reussi=True)
    assert registre.chercher(LECTEUR_APPRIS).niveau == "E1"


def test_l_echelle_monte_jusqu_a_E5_et_pas_avant() -> None:
    """Chaque barreau demande quelque chose de plus, et le dit."""
    registre = _registre_apres_gamma()
    capacite = registre.chercher
    assert capacite(LECTEUR_APPRIS).niveau == "E0"

    prouver_emploi(registre, instance="a", domaine="releve", abimee=False, reussi=True)
    assert capacite(LECTEUR_APPRIS).niveau == "E1"
    prouver_emploi(registre, instance="b", domaine="releve", abimee=False, reussi=True)
    assert capacite(LECTEUR_APPRIS).niveau == "E2"
    prouver_emploi(registre, instance="c", domaine="releve", abimee=False, reussi=True)
    assert capacite(LECTEUR_APPRIS).niveau == "E3", "trois instances, aucun échec"
    prouver_emploi(registre, instance="d", domaine="releve", abimee=True, reussi=True)
    assert capacite(LECTEUR_APPRIS).niveau == "E4", "une instance abîmée tenue"
    prouver_emploi(registre, instance="e", domaine="config", abimee=False, reussi=True)
    assert capacite(LECTEUR_APPRIS).niveau == "E5", "un deuxième domaine"


def test_un_seul_echec_plafonne_le_niveau() -> None:
    """« Vérifiée » et « robuste » sont des affirmations de fiabilité, pas des compteurs."""
    registre = _registre_apres_gamma()
    for nom in "abcde":
        prouver_emploi(registre, instance=nom, domaine="releve", abimee=True, reussi=True)
    assert registre.chercher(LECTEUR_APPRIS).niveau == "E4"

    prouver_emploi(registre, instance="f", domaine="releve", abimee=False, reussi=False)
    assert registre.chercher(LECTEUR_APPRIS).niveau == PLAFOND_APRES_ECHEC


def test_un_niveau_ne_se_pose_pas_a_la_main() -> None:
    """Il est recalculé à chaque lecture depuis les preuves : il n'y a rien à écrire."""
    registre = _registre_apres_gamma()
    capacite = registre.chercher(LECTEUR_APPRIS)
    with pytest.raises((AttributeError, TypeError)):
        capacite.niveau = "E5"


def test_reinscrire_un_autre_artefact_remet_les_preuves_a_zero() -> None:
    """« Candidat X, évalué, approuvé » ne doit pas activer autre chose que X.

    Les preuves avaient été gagnées par l'ancien code. Les laisser au nouveau
    serait exactement la substitution d'artefact que la directive demande de
    rendre impossible.
    """
    registre = _registre_apres_gamma()
    for nom in "abc":
        prouver_emploi(registre, instance=nom, domaine="releve", abimee=False, reussi=True)
    assert registre.chercher(LECTEUR_APPRIS).niveau == "E3"

    registre.inscrire(LECTEUR_APPRIS, "lire un format clé/valeur",
                      construire_lecteur("="), provenance="autre")
    remplacee = registre.chercher(LECTEUR_APPRIS)
    assert remplacee.niveau == "E0"
    assert remplacee.version == 2
    assert remplacee.preuves == ()


def test_deux_lecteurs_sur_deux_separateurs_sont_deux_artefacts() -> None:
    """La capture de fermeture fait partie de l'identité, sinon l'empreinte ment."""
    registre = Registre()
    un = registre.inscrire("lecteur", "lire", construire_lecteur(": "))
    deux = registre.inscrire("lecteur", "lire", construire_lecteur("="))
    assert un.empreinte != deux.empreinte


def test_reinscrire_le_meme_artefact_ne_perd_rien() -> None:
    """Une réinscription à l'identique n'est pas un changement, donc ne coûte rien."""
    registre = Registre()
    lecteur = construire_lecteur(": ")
    registre.inscrire("lecteur", "lire", lecteur)
    registre.prouver("lecteur", Preuve(instance="a", domaine="releve"))
    registre.inscrire("lecteur", "lire", lecteur)
    assert registre.chercher("lecteur").version == 1
    assert registre.chercher("lecteur").niveau == "E1"


def test_employer_refuse_un_artefact_substitue() -> None:
    """Le contrôle du côté de l'appelant, pour qui a gardé une référence."""
    registre = _registre_apres_gamma()
    with pytest.raises(SubstitutionRefusee):
        registre.employer(LECTEUR_APPRIS, construire_lecteur("="))


def test_employer_une_capacite_inconnue_leve() -> None:
    """Fail-closed : un nom inconnu n'est pas une capacité vide, c'est une erreur."""
    with pytest.raises(KeyError):
        Registre().employer("rien")


# --- numérique et formes limites ----------------------------------------------

@pytest.mark.parametrize("cout", [float("nan"), float("inf"), float("-inf"), -1.0])
def test_un_pas_refuse_un_cout_qui_n_est_pas_un_nombre(cout) -> None:
    """Un coût NaN empoisonnerait toutes les comparaisons du banc en silence."""
    from singular.genesis.mission import Pas

    with pytest.raises(ValueError):
        Pas(Etape.LECTURE, "quoi", cout)


def test_un_lecteur_refuse_ce_qui_n_est_pas_de_son_format() -> None:
    """Sans refus, le tâtonnement serait invisible et tout texte serait lisible."""
    for _, lecteur in __import__("singular.genesis.lecteurs", fromlist=["TOUS"]).TOUS:
        with pytest.raises(FormatRefuse):
            lecteur("")


def test_le_registre_vide_ne_trouve_rien() -> None:
    assert Registre().chercher(LECTEUR_APPRIS) is None
    assert len(Registre()) == 0


# --- l'expérience doit pouvoir être lancée ------------------------------------

def test_l_experience_entiere_se_lance_et_rend_son_verdict() -> None:
    """Une expérience qu'on ne lance pas est une expérience qui n'existe pas.

    Le mandat garde le souvenir d'une application web finie et jamais lancée
    pendant qu'une session réparait l'autre. Ce test est ce qui empêche
    `tools/genesis_experiment.py` de devenir la même chose : il le fait tourner
    en entier, sur les vrais fichiers du dépôt.
    """
    from tools.genesis_experiment import experience

    rapport = experience(RACINE)
    assert rapport["acquise"], "GAMMA doit avoir acquis sa capacité"
    assert [resultat.verifie for resultat in rapport["resultats"]] == [True, True, False, True], (
        "ALPHA et BETA passent, GAMMA échoue sans capacité puis réussit avec")
    assert rapport["naissance"].ne
    assert rapport["registre"].chercher(LECTEUR_APPRIS).niveau == "E1", (
        "une instance vérifiée, donc E1 : le niveau ne doit pas monter tout seul")
