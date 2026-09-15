"""Ce qu'il tape au clavier, et ce que l'outil lui répond.

Il débute en code, il est en France, et `python -m singular add` lui pose huit
questions. Deux fautes s'y payaient cher :

- taper « 75 » en pensant pourcents passait les six questions suivantes, puis
  échouait sur `probability must be strictly between 0 and 1` — en anglais, et
  **après coup**. Tout ce qu'il venait de saisir était perdu, et un outil censé
  prendre trente secondes en redemandait autant.
- taper « 0,75 » avec la virgule décimale de son clavier rendait
  `could not convert string to float: '0,75'`, pour une saisie qui n'avait rien
  de fautif.

Les questions valident donc sur place, dans sa langue. Ce fichier tient la
seule chose qui puisse dériver : ce qui est accepté à la question doit être
exactement ce que le journal accepte à l'écriture. Deux écritures de la même
règle finissent par dire deux choses, et celle qui se tromperait ici lui
ferait perdre sa saisie à la question suivante.
"""
from __future__ import annotations

import pathlib

import pytest

from singular.__main__ import main
from singular.saisie import CONFLIT, CONFLIT_CLAVIER, CONFLIT_PAGE, introuvable
from singular.saisie import (
    entier as _entier,
)
from singular.saisie import (
    nombre as _nombre,
)
from singular.saisie import (
    verifie_gain as _verifie_gain,
)
from singular.saisie import (
    verifie_heures as _verifie_heures,
)
from singular.saisie import (
    verifie_jours as _verifie_jours,
)
from singular.saisie import (
    verifie_probabilite as _verifie_probabilite,
)
from singular.journal import DecisionJournal, Tier
from tests.support import sans_accents

RACINE = pathlib.Path(__file__).resolve().parent.parent


def _accepte_par_le_journal(tmp_path, **champs) -> bool:
    journal = DecisionJournal(tmp_path / f"j{abs(hash(tuple(champs.items())))}.db")
    base = {"title": "t", "action": "a", "predicted": "p", "probability": 0.6,
            "tier": Tier.REVENUS, "cost_hours": 4.0, "horizon_days": 14}
    try:
        journal.add(**{**base, **champs})
    except ValueError:
        return False
    return True


def _accepte_par_la_question(verifie, valeur) -> bool:
    try:
        verifie(valeur)
    except ValueError:
        return False
    return True


# --- ce qu'il tape se lit comme il l'écrit ------------------------------------

@pytest.mark.parametrize(("saisie", "attendu"), [
    ("0.75", 0.75),
    ("0,75", 0.75),      # la virgule de son clavier
    ("4", 4.0),
    ("1 500", 1500.0),   # l'espace des milliers
    ("1 500", 1500.0),
    ("  0,5  ", 0.5),
])
def test_a_number_is_read_the_way_he_writes_it(saisie, attendu):
    assert _nombre(saisie) == attendu


def test_something_that_is_not_a_number_says_so_in_his_language():
    with pytest.raises(ValueError, match="n'est pas un nombre"):
        _nombre("quatre")
    with pytest.raises(ValueError, match="n'est pas un nombre"):
        _entier("beaucoup")


# --- la question accepte exactement ce que le journal accepte -----------------

#: L'infini et le NaN sont dans les trois listes, et ils ne l'etaient que dans
#: une. `saisie.py` refuse les trois cas -- « une probabilite, pas l'infini »,
#: « un nombre d'heures, pas l'infini », « un montant, pas l'infini » -- et deux
#: de ces refus n'avaient aucun temoin : on pouvait les retirer sans qu'un test
#: rougisse. Le mecanisme de ce fichier existait deja ; il etait applique a un
#: cas sur trois. Un clavier tape « inf » plus facilement qu'on ne le croit, et
#: une valeur infinie ecrite dans le journal y reste : la chaine ne se reecrit pas.
PROBABILITES = [0.0, 0.01, 0.05, 0.5, 0.75, 0.95, 0.99, 1.0, 1.5, 60.0, 75.0, 100.0, -0.5,
                float("inf"), float("-inf"), float("nan")]
HEURES = [0.0, 0.5, 4.0, 1000.0, -0.5, -1.0, float("inf"), float("nan")]
JOURS = [0, 1, 14, 365, -1]
GAINS = [None, 0.0, 1500.0, -100.0, -0.01, float("inf"), float("nan")]


def _dans_la_borne(valeur: float) -> bool:
    """La borne de saisie, lue dans la constante et non recopiee ici.

    Elle est **volontairement plus etroite** que celle du journal : le journal
    tient l'invariant mathematique de la chaine -- `0 < p < 1`, ce qu'un score de
    Brier sait calculer -- et la saisie tient ce qu'une prevision honnete
    annonce. Les deux regles ont deux raisons, donc deux domiciles.
    """
    from singular.saisie import PROBABILITE_MAX, PROBABILITE_MIN
    return PROBABILITE_MIN <= valeur <= PROBABILITE_MAX


@pytest.mark.parametrize("valeur", PROBABILITES)
def test_the_question_and_the_journal_agree_on_a_probability(tmp_path, valeur):
    """La question accepte ce que le journal accepte, moins la borne -- exactement.

    L'egalite simple a tenu jusqu'a ce que la borne annoncee devienne la borne
    appliquee. Le sens qui compte n'a pas bouge : **ce que la question laisse
    passer, le journal doit l'accepter**, sinon elle ecrirait une decision que
    l'ecriture rejette juste apres. L'autre sens cede a la borne, et la formule
    le dit chiffre par chiffre plutot que de relacher le test en inegalite.
    """
    par_la_question = _accepte_par_la_question(_verifie_probabilite, valeur)
    par_le_journal = _accepte_par_le_journal(tmp_path, probability=valeur)

    if par_la_question:
        assert par_le_journal, "la question laisse passer ce que le journal refuse"
    assert par_la_question is (par_le_journal and _dans_la_borne(valeur))


@pytest.mark.parametrize("valeur", HEURES)
def test_the_question_and_the_journal_agree_on_hours(tmp_path, valeur):
    assert _accepte_par_la_question(_verifie_heures, valeur) is \
        _accepte_par_le_journal(tmp_path, cost_hours=valeur)


@pytest.mark.parametrize("valeur", JOURS)
def test_the_question_and_the_journal_agree_on_a_horizon(tmp_path, valeur):
    assert _accepte_par_la_question(_verifie_jours, valeur) is \
        _accepte_par_le_journal(tmp_path, horizon_days=valeur)


@pytest.mark.parametrize("verifie", [_verifie_probabilite, _verifie_heures, _verifie_gain])
@pytest.mark.parametrize("valeur", [float("inf"), float("-inf"), float("nan")])
def test_un_refus_d_infini_nomme_l_infini(verifie, valeur):
    """Ces trois gardes existent pour le message, et c'est donc lui qu'on teste.

    `nombre("inf")` rend bien l'infini -- mesuré -- donc la valeur arrive jusqu'à
    la vérification. Ce qui suit refuserait de toute façon : une borne de
    probabilité, un signe d'heures, un signe de montant. La garde `isfinite` ne
    change pas le verdict, elle change ce qu'il lui dit.

    Sans elle, « inf » répondrait « entre 0.05 et 0.95 » -- vrai, et inutile :
    il ne s'est pas trompé de borne, il a tapé l'infini. Les deux tests
    d'équivalence au-dessus ne pouvaient pas le voir, puisque des deux côtés la
    décision est refusée.
    """
    with pytest.raises(ValueError, match="l'infini"):
        verifie(valeur)


def test_typing_percent_says_what_to_write_instead():
    """Le cas réel : « 75 » pour 75 %. Le refus doit donner la réponse."""
    with pytest.raises(ValueError) as refus:
        _verifie_probabilite(75)
    assert "pour 75 %, ecris 0.75" in sans_accents(str(refus.value))


@pytest.mark.parametrize("valeur", [0.99, 0.96, 0.01, 0.04])
def test_une_quasi_certitude_est_refusee_comme_le_curseur_la_refuse(valeur):
    """La borne annoncée est désormais la borne appliquée.

    Elle ne l'était qu'au curseur de la page web -- `min=5 max=95` -- pendant que
    les deux refus du clavier la nommaient sans l'appliquer. `0.99` entrait donc
    par le clavier et par l'API après s'être fait répondre, la fois d'avant,
    qu'il fallait rester entre 0.05 et 0.95.

    Tranché en questionnaire : c'est la borne qui devient vraie, pas la phrase
    qui s'efface.
    """
    with pytest.raises(ValueError) as refus:
        _verifie_probabilite(valeur)
    assert "entre 0.05 et 0.95" in str(refus.value)


@pytest.mark.parametrize("valeur", [0.05, 0.95, 0.5])
def test_les_bornes_elles_memes_restent_acceptees(valeur):
    """L'autre bord : le curseur atteint 5 et 95, donc le clavier les accepte."""
    _verifie_probabilite(valeur)


@pytest.mark.parametrize("valeur", [99, 2, 96])
def test_le_conseil_en_pourcents_ne_propose_jamais_un_chiffre_refuse(valeur):
    """« 99 » ne doit pas s'entendre répondre « écris 0.99 », que la borne refuse.

    Le commentaire de `verifie_probabilite` reprochait déjà ça au cas « 100 » :
    un refus qui conseille un chiffre refusé est pire que pas de conseil. Rendre
    la borne vraie a fait renaître le même piège plus bas, à 0.95 -- d'où ce
    test, qui le tient à la place du prochain lecteur.
    """
    with pytest.raises(ValueError) as refus:
        _verifie_probabilite(valeur)
    dit = str(refus.value)
    assert "ecris" not in sans_accents(dit), f"« {valeur:g} » s'est vu conseiller : {dit}"
    assert "sort des bornes" in dit


def test_une_decision_deja_ecrite_hors_borne_se_relit_sans_rien_casser(tmp_path):
    """La borne s'applique a la saisie, jamais a la lecture. Et il en a deja.

    La ligne de commande acceptait `0.99` jusqu'au jour ou cette borne est
    devenue vraie : des decisions hors borne sont donc dans son journal, et une
    chaine d'empreintes ne se reecrit pas. Resserrer une entree ne doit jamais
    rendre illisible ce qui est deja ecrit -- c'est le refus qui bouge, pas
    l'histoire.

    Le test tient les deux bords : l'ecriture directe passe encore (le journal
    garde `0 < p < 1`, son invariant mathematique) et le rapport la compte.
    """
    journal = DecisionJournal(tmp_path / "ancien.db")
    ancienne = journal.add(title="t", action="a", predicted="p", probability=0.99,
                           tier=Tier.REVENUS, cost_hours=4.0, horizon_days=14)
    journal.resolve(ancienne.entry_id, happened=False)

    assert journal.verify(), "la chaine doit rester intacte"
    rapport = journal.review()
    assert rapport["resolved"] == 1
    # Un pari perdu annonce a 99 % : exactement le cas que la borne evite
    # desormais a l'entree, et qui doit rester mesure quand il existe.
    assert rapport["mean_brier"] == pytest.approx(0.9801)
    assert rapport["hit_rate"] == 0.0


def test_the_gain_question_reads_numbers_the_same_way(tmp_path, monkeypatch, capsys):
    """« 1 500 » doit valoir 1500 euros à cette question comme aux autres.

    Elle avait son propre nettoyage. Deux façons de lire un nombre dans le même
    formulaire, c'est une saisie qui passe à une question et échoue à la
    suivante, sans qu'on comprenne pourquoi.
    """
    from singular.__main__ import _gain_prompt

    for saisie, attendu in (("1 500", 1500.0), ("1500,50", 1500.5), ("", None)):
        monkeypatch.setattr("builtins.input", lambda *a, _s=saisie: _s)
        assert _gain_prompt() == attendu

    monkeypatch.setattr("builtins.input", lambda *a: "beaucoup")
    assert _gain_prompt() is None
    assert "Pas un nombre" in capsys.readouterr().out

    monkeypatch.setattr("builtins.input", lambda *a: "-100")
    assert _gain_prompt() is None, "un coût n'est pas un gain"


# --- les trois surfaces disent la meme chose ----------------------------------

def _accepte_par_le_telephone(tmp_path, **champs) -> bool:
    from singular.sage.server import SageApp, SageError

    app = SageApp(DecisionJournal(tmp_path / f"t{abs(hash(tuple(champs.items())))}.db"))
    charge = {"title": "T", "action": "a", "predicted": "p", "probability": 0.6,
              "tier": "REVENUS", "cost_hours": 4, "horizon_days": 14}
    try:
        app.add({**charge, **champs})
    except SageError:
        return False
    return True


@pytest.mark.parametrize("valeur", PROBABILITES)
def test_the_phone_and_the_journal_agree_on_a_probability(tmp_path, valeur):
    """La route du telephone etait la seule sans verification propre.

    Elle laissait le journal lever et renvoyait son message tel quel : de
    l'anglais de machine sur un ecran de six pouces. Elle verifie maintenant,
    et ce qu'elle accepte doit rester ce que le journal accepte, moins la borne
    de saisie -- sinon elle laisserait passer une decision que le journal rejette
    juste apres, ou elle divergerait du clavier et du curseur.
    """
    par_le_telephone = _accepte_par_le_telephone(tmp_path, probability=valeur)
    par_le_journal = _accepte_par_le_journal(tmp_path, probability=valeur)

    if par_le_telephone:
        assert par_le_journal, "le téléphone laisse passer ce que le journal refuse"
    assert par_le_telephone is (par_le_journal and _dans_la_borne(valeur))


@pytest.mark.parametrize("valeur", HEURES)
def test_the_phone_and_the_journal_agree_on_hours(tmp_path, valeur):
    assert _accepte_par_le_telephone(tmp_path, cost_hours=valeur) is \
        _accepte_par_le_journal(tmp_path, cost_hours=valeur)


@pytest.mark.parametrize("valeur", JOURS)
def test_the_phone_and_the_journal_agree_on_a_horizon(tmp_path, valeur):
    assert _accepte_par_le_telephone(tmp_path, horizon_days=valeur) is \
        _accepte_par_le_journal(tmp_path, horizon_days=valeur)


@pytest.mark.parametrize("valeur", GAINS)
def test_the_phone_and_the_journal_agree_on_a_gain(tmp_path, valeur):
    """Le champ du gain est en texte libre, exprès : « vide » doit rester possible.

    C'est ce qui le laissait sans borne, et « -100 » -- un cout, tape de bonne
    foi -- ressortait en anglais.
    """
    envoye = "" if valeur is None else str(valeur)
    assert _accepte_par_le_telephone(tmp_path, expected_gain_eur=envoye) is \
        _accepte_par_le_journal(tmp_path, expected_gain_eur=valeur)


def test_no_refusal_reaches_him_in_the_language_of_the_library(tmp_path):
    """Aucun message du journal ne doit arriver tel quel sur son telephone.

    Les exceptions de `journal.py` sont son contrat de bibliotheque, en anglais
    et testees comme tel. Elles n'ont rien a faire sur un ecran.
    """
    from singular.sage.server import SageApp, SageError

    app = SageApp(DecisionJournal(tmp_path / "journal.db"))
    charge = {"title": "T", "action": "a", "predicted": "p", "probability": 0.6,
              "tier": "REVENUS", "cost_hours": 4, "horizon_days": 14}
    # L'infini et le NaN sont ici parce que c'est le seul endroit ou leur refus
    # se distingue : sans la garde de `saisie.py`, la decision est refusee quand
    # meme -- par le journal, en anglais, sur un ecran de six pouces. Les deux
    # gardes `isfinite` pouvaient donc etre retirees sans qu'un test rougisse.
    fautifs = [{"probability": 1.0}, {"probability": 0.0}, {"probability": 75},
               {"cost_hours": -1}, {"horizon_days": 0}, {"expected_gain_eur": "-5"},
               {"probability": "inf"}, {"probability": "nan"},
               {"cost_hours": "inf"}, {"expected_gain_eur": "inf"}]

    for faute in fautifs:
        with pytest.raises(SageError) as refus:
            app.add({**charge, **faute})
        message = refus.value.message
        for anglais in ("must be", "cannot be", "needs a horizon", "is not a forecast"):
            assert anglais not in message, f"{faute} rend « {message} »"


def test_the_form_can_only_produce_what_the_journal_accepts():
    """Le formulaire est une quatrieme ecriture de la meme regle, en HTML.

    Ses bornes doivent rester dans ce que le journal accepte : un curseur qui
    irait jusqu'a 100 produirait une valeur refusee, et le refus arriverait
    apres l'appui sur « Enregistrer ».

    **Rester dedans ne suffisait pas.** `min=5 max=95` passait cette condition
    pendant que le clavier acceptait `0.99` : le curseur portait la borne, les
    deux refus l'annoncaient sans l'appliquer, et rien ne les comparait. Sur la
    probabilite c'est donc une egalite, lue dans la constante -- deplacer l'un
    sans l'autre fait rougir ici. Les deux autres champs n'ont pas de borne
    haute, donc l'inclusion reste ce qui se verifie.
    """
    from singular.saisie import PROBABILITE_MAX, PROBABILITE_MIN
    import pathlib
    import re

    page = (pathlib.Path(__file__).resolve().parent.parent
            / "singular/sage/web/index.html").read_text(encoding="utf-8")

    def attribut(champ: str, nom: str) -> float:
        balise = re.search(rf'<input name="{champ}"[^>]*>', page, re.S)
        assert balise, f"le champ {champ} a disparu du formulaire"
        trouve = re.search(rf'{nom}="([-\d.]+)"', balise.group(0))
        assert trouve, f"{champ} n'a plus d'attribut {nom}"
        return float(trouve.group(1))

    # Le curseur est en pourcents ; le journal veut une fraction.
    assert attribut("probability", "min") / 100 == PROBABILITE_MIN, (
        "le curseur ne commence pas ou le clavier commence a refuser")
    assert attribut("probability", "max") / 100 == PROBABILITE_MAX, (
        "le curseur ne s'arrete pas ou le clavier commence a refuser")
    assert attribut("cost_hours", "min") >= 0
    assert attribut("horizon_days", "min") >= 1


def test_les_deux_zones_de_texte_s_arretent_ou_le_serveur_refuse():
    """Le meme nombre vit en HTML et en Python, et rien ne les comparait.

    `maxlength` ne previent pas : il **empeche de taper**. Une limite plus basse
    que celle du serveur couperait donc sa question au milieu, en silence, et
    c'est elle qui partirait au modele -- pire qu'un refus. Une limite plus
    haute ferait refuser apres l'envoi, sur un ecran de six pouces.

    Aucune des deux n'est arrivee : les nombres sont egaux aujourd'hui. Ce test
    existe pour qu'ils le restent, parce que la meme divergence avait deja
    laisse le curseur de probabilite porter une borne que le clavier ignorait.
    """
    import pathlib
    import re

    from singular.sage.server import QUESTION_MAX

    page = (pathlib.Path(__file__).resolve().parent.parent
            / "singular/sage/web/index.html").read_text(encoding="utf-8")

    zones = re.findall(r'<textarea[^>]*name="(question|precision)"[^>]*>', page)
    assert sorted(zones) == ["precision", "question"], (
        f"les deux zones de texte du Sage ont change de forme : {zones}")

    for nom in zones:
        balise = re.search(rf'<textarea[^>]*name="{nom}"[^>]*>', page).group(0)
        trouve = re.search(r'maxlength="(\d+)"', balise)
        assert trouve, f"la zone « {nom} » n'a plus de maxlength : rien ne l'arrete"
        assert int(trouve.group(1)) == QUESTION_MAX, (
            f"« {nom} » s'arrete a {trouve.group(1)} et le serveur refuse au-dela "
            f"de {QUESTION_MAX}")


# --- le refus d'ecrire, pas seulement le refus de saisir ----------------------

def _journal_tranche(tmp_path):
    """Un journal d'une ligne, deja tranchee : le cas du double appui."""
    journal = DecisionJournal(tmp_path / "journal.db")
    entree = journal.add(title="Postuler", action="envoyer", predicted="un entretien",
                         probability=0.6, tier=Tier.REVENUS, cost_hours=2, horizon_days=1)
    journal.resolve(entree.entry_id, happened=True)
    return journal, entree.entry_id


@pytest.mark.parametrize("commande", [
    lambda eid: ["resolve", eid, "--no"],
    lambda eid: ["abandon", eid, "plus la peine"],
])
def test_the_keyboard_says_a_second_verdict_in_his_language(tmp_path, capsys, commande):
    """Deux onglets, un double appui, la commande apres l'app : le cas est banal.

    Le journal refuse -- l'histoire ne se reecrit pas, c'est sa promesse -- et
    il refusait en anglais jusque sur l'ecran : « history is not editable ».
    L'app avait sa traduction, ecrite chez elle. Le clavier n'avait rien.
    """
    _, entry_id = _journal_tranche(tmp_path)

    assert main(["--db", str(tmp_path / "journal.db"), *commande(entry_id)]) == 1
    sortie = capsys.readouterr().out
    assert CONFLIT in sortie
    assert "history is not editable" not in sortie
    assert "already resolved" not in sortie
    # Ce que la sortie doit dire, et pas seulement la constante : brancher le
    # clavier sur `CONFLIT_PAGE` passait tous les autres tests, puisque les
    # deux phrases partagent leur premier tiers.
    assert "Ferme et rouvre" not in sortie, (
        "le clavier n'a pas d'onglet a rouvrir : il doit lire `CONFLIT_CLAVIER`")
    assert "singular list" in sortie


#: Les deux commandes qui tranchent une décision par son identifiant, avec ce
#: qu'elles demandent en plus. Elles vont toujours par paire et se sont déjà
#: séparées : le test ci-dessous ne jouait que `resolve`, donc le même garde dans
#: `abandon` n'avait aucun témoin -- neutralisé, il rendait une pile Python au
#: lieu de la phrase. Le test juste en dessous, lui, était déjà paramétré sur les
#: deux. Troisième fois que l'aller est prouvé et le retour non, donc la paire
#: cesse d'être une liste qu'on complète à la main.
TRANCHENT_PAR_IDENTIFIANT = (("resolve", ["--yes"]), ("abandon", ["parce que"]))


@pytest.mark.parametrize("commande, reste", TRANCHENT_PAR_IDENTIFIANT,
                         ids=[nom for nom, _ in TRANCHENT_PAR_IDENTIFIANT])
def test_the_keyboard_explains_an_unknown_identifier(tmp_path, capsys, commande, reste):
    """Il affichait `'DEC-inconnu'`, guillemets compris, et rien d'autre."""
    journal = DecisionJournal(tmp_path / "journal.db")
    assert journal is not None

    code = main(["--db", str(tmp_path / "journal.db"), commande, "DEC-inconnu", *reste])
    assert code == 1
    sortie = capsys.readouterr().out
    assert introuvable("DEC-inconnu") in sortie
    assert "'DEC-inconnu'" not in sortie, "le repr d'une cle absente n'explique rien"
    assert "Traceback" not in sortie, "un identifiant tapé de travers n'est pas un bug"


@pytest.mark.parametrize("route", ["resolve", "abandon"])
def test_the_server_answers_a_conflict_in_his_language(tmp_path, route):
    """Le corps JSON partait en anglais ; seule l'app le remplacait, chez elle."""
    from singular.sage.server import SageApp, SageError

    journal, entry_id = _journal_tranche(tmp_path)
    app = SageApp(journal)
    charge = {"happened": False} if route == "resolve" else {"reason": "plus la peine"}

    with pytest.raises(SageError) as refus:
        getattr(app, route)(entry_id, charge)

    assert refus.value.message == CONFLIT_PAGE
    assert "editable" not in refus.value.message


def test_the_web_copy_of_the_conflict_still_says_the_same_thing():
    """La seule copie qui ne peut pas importer `singular.saisie`.

    L'app doit pouvoir refuser hors connexion, donc elle porte la phrase en
    dur. Une phrase en double se corrige d'un seul cote : ce test est ce qui
    l'empeche.
    """
    app_js = (RACINE / "singular/sage/web/app.js").read_text(encoding="utf-8")
    assert CONFLIT_PAGE in app_js, (
        "app.js ne dit plus ce que dit `singular.saisie.CONFLIT_PAGE`. La phrase "
        "a un seul domicile ; la copie du navigateur doit le citer mot pour mot.")


def test_the_keyboard_is_not_told_to_close_and_reopen():
    """Le fait est partagé, le geste qui suit ne l'est pas.

    La phrase entière était écrite pour la page, et le clavier la recevait
    telle quelle : « Ferme et rouvre pour voir le verdict enregistré » n'a rien
    à fermer dans un terminal. Un conseil qu'on ne peut pas suivre se lit comme
    une panne, et c'est la sixième porte par où un message écrit ailleurs
    arrivait sur son écran.
    """
    assert CONFLIT_CLAVIER.startswith(CONFLIT) and CONFLIT_PAGE.startswith(CONFLIT), (
        "les deux doivent dire le même fait avant de diverger sur le geste")
    assert "Ferme et rouvre" not in CONFLIT_CLAVIER
    assert "singular list" in CONFLIT_CLAVIER, "le clavier a une commande, pas un onglet"
    assert "Ferme et rouvre" in CONFLIT_PAGE


# --- une seule porte, et aucune ne la contourne -------------------------------

#: Ce qui n'ecrit pas une decision de Thomas.
#:
#: `journal.py` est la porte elle-meme. `proto/` ne touche pas ce journal.
HORS_JOURNAL = {"journal.py"}


def _appels_a_add(source: pathlib.Path) -> list[tuple[str, int]]:
    """Les `journal.add(...)` du fichier, avec la fonction qui les contient."""
    import ast

    arbre = ast.parse(source.read_text(encoding="utf-8"))
    porteur: dict[int, ast.FunctionDef] = {}
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.FunctionDef | ast.AsyncFunctionDef):
            for enfant in ast.walk(noeud):
                porteur.setdefault(id(enfant), noeud)

    trouves = []
    for noeud in ast.walk(arbre):
        if not (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute)):
            continue
        if noeud.func.attr != "add":
            continue
        cible = noeud.func.value
        nom = cible.attr if isinstance(cible, ast.Attribute) else getattr(cible, "id", "")
        if nom != "journal":
            continue
        fonction = porteur.get(id(noeud))
        trouves.append((fonction.name if fonction else "<module>", noeud.lineno))
    return trouves


def _verifie_dans(source: pathlib.Path, nom_fonction: str) -> bool:
    import ast

    arbre = ast.parse(source.read_text(encoding="utf-8"))
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if noeud.name != nom_fonction:
            continue
        for appel in ast.walk(noeud):
            if isinstance(appel, ast.Call):
                appelee = getattr(appel.func, "id", "") or getattr(appel.func, "attr", "")
                if appelee.endswith("verifie_decision"):
                    return True
    return False


def test_no_surface_writes_a_decision_without_crossing_the_door():
    """Chaque surface validait de son cote, donc chacune pouvait oublier.

    Deux l'ont fait, et pas les moins frequentees : `sj apply`, le chemin le
    plus rapide de l'outil, et `sj add --title ...`. Toutes deux passaient
    directement au journal, qui refuse en anglais. Une regle ecrite quatre fois
    a fini par n'etre ecrite que deux fois et demie ; ce test refuse la
    cinquieme porte plutot que d'attendre qu'on la trouve.
    """
    fautifs = []
    for source in sorted((RACINE / "singular").rglob("*.py")):
        if source.name in HORS_JOURNAL:
            continue
        for fonction, ligne in _appels_a_add(source):
            if not _verifie_dans(source, fonction):
                fautifs.append(f"{source.relative_to(RACINE)}:{ligne} dans {fonction}()")

    assert not fautifs, (
        "ces appels ecrivent une decision sans passer par "
        "`singular.saisie.verifie_decision` :\n  " + "\n  ".join(fautifs)
        + "\nLe journal refuserait en anglais, sur son ecran.")


def test_the_scan_actually_sees_the_writes():
    """Le temoin : un analyseur qui ne trouverait aucun appel passerait au vert."""
    appels = _appels_a_add(RACINE / "singular/__main__.py")
    assert {fonction for fonction, _ in appels} >= {"cmd_add", "cmd_apply"}
    assert _appels_a_add(RACINE / "singular/sage/server.py")


@pytest.mark.parametrize("commande", [
    ["apply", "Boite", "Charge d'etudes", "--probability", "30"],
    ["apply", "Boite", "Charge d'etudes", "--days", "0"],
    ["apply", "Boite", "Charge d'etudes", "--hours", "-2"],
    ["add", "--title", "T", "--action", "a", "--predicted", "p", "--probability", "30"],
    # Les textes vides, la ou le journal refusait en anglais apres coup.
    ["add", "--title", "   ", "--action", "a", "--predicted", "p"],
    ["add", "--title", "T", "--action", " ", "--predicted", "p"],
    ["add", "--title", "T", "--action", "a", "--predicted", ""],
    ["apply", "   ", "Charge d'etudes"],
    ["apply", "Boite", ""],
])
def test_the_fast_paths_refuse_in_his_language(tmp_path, capsys, commande):
    """Le cas reel : il cherche un poste, donc `sj apply` est ce qu'il tape le plus."""
    DecisionJournal(tmp_path / "journal.db")

    assert main(["--db", str(tmp_path / "journal.db"), *commande]) == 1
    sortie = capsys.readouterr().out
    for anglais in ("must be", "cannot be", "needs a horizon", "is not a forecast"):
        assert anglais not in sortie, f"{commande} rend « {sortie.strip()} »"


def test_un_titre_vide_refuse_au_lieu_de_demarrer_l_entretien(tmp_path, capsys, monkeypatch):
    """Le pire des trois : `sj add --title ""` ne refusait pas, il posait des questions.

    `if args.title:` lit la verite de la chaine, donc la chaine vide passait pour
    une option absente et la branche interactive demarrait -- huit questions a un
    stdin qui n'est peut-etre pas un terminal, apres une commande qui nommait
    pourtant tous ses champs. Le refus doit arriver tout de suite, et rien ne doit
    etre lu au clavier.
    """
    def pas_de_question(*args, **kwargs):
        raise AssertionError("l'entretien a demarre alors que la commande etait complete")

    monkeypatch.setattr("builtins.input", pas_de_question)

    assert main(["--db", str(tmp_path / "journal.db"), "add", "--title", "",
                 "--action", "a", "--predicted", "p"]) == 1
    sortie = capsys.readouterr().out
    assert "La décision" in sortie, sortie
    assert not DecisionJournal(tmp_path / "journal.db").entries()


# --- plus aucune porte ne parle la langue de la bibliotheque -------------------

#: Ce qui trahit un message de bibliotheque arrive sur son ecran.
#:
#: La liste est faite de ce qu'on a reellement vu passer :
#: `probability must be strictly between 0 and 1`,
#: `expected_gain_eur cannot be negative`,
#: `DEC-... was already resolved as HAPPENED; history is not editable`,
#: `OperationalError: database is locked`, `file is not a database`.
LANGUE_DE_LA_MACHINE = ("must be", "cannot be", "is not a", "was already",
                        "not editable", "Error:", "locked", "database",
                        "needs a horizon", "Traceback")

#: Chaque route d'ecriture, avec de quoi la faire refuser.
#:
#: Les routes de lecture n'ont pas d'entree a refuser, et les deux facultes
#: payantes refusent deja en francais quand la cle manque -- c'est teste
#: ailleurs. Ce qui reste ici est ce qui ecrit dans le journal.
REFUS_ATTENDUS = [
    ("add", {"title": "T", "action": "a", "predicted": "p", "probability": 30,
             "tier": "REVENUS", "cost_hours": 4, "horizon_days": 14}),
    ("add", {"title": "T", "action": "a", "predicted": "p", "probability": 0.6,
             "tier": "REVENUS", "cost_hours": -1, "horizon_days": 14}),
    ("add", {"title": "T", "action": "a", "predicted": "p", "probability": 0.6,
             "tier": "REVENUS", "cost_hours": 4, "horizon_days": 0}),
    ("add", {"title": "T", "action": "a", "predicted": "p", "probability": 0.6,
             "tier": "REVENUS", "cost_hours": 4, "horizon_days": 14,
             "expected_gain_eur": "-100"}),
    # Les trois textes, vides et blancs : le formulaire du telephone les laissait
    # passer et c'est le journal qui refusait, en anglais.
    ("add", {"title": "", "action": "a", "predicted": "p", "probability": 0.6,
             "tier": "REVENUS", "cost_hours": 4, "horizon_days": 14}),
    ("add", {"title": "T", "action": "   ", "predicted": "p", "probability": 0.6,
             "tier": "REVENUS", "cost_hours": 4, "horizon_days": 14}),
    ("add", {"title": "T", "action": "a", "predicted": " ", "probability": 0.6,
             "tier": "REVENUS", "cost_hours": 4, "horizon_days": 14}),
]


def test_plus_aucune_ecriture_ne_refuse_dans_la_langue_de_la_bibliotheque(tmp_path):
    """Le meme defaut a ete corrige a quatre portes : la saisie du telephone, le
    clavier, les refus d'ecriture, les pannes imprevues. La regle du depot dit
    qu'a la troisieme fois on cesse de corriger et on rend l'erreur impossible.

    Ce test balaie ce qui ecrit dans le journal, cote serveur et cote clavier,
    et refuse un message ou l'anglais de la bibliotheque affleure.
    """
    from singular.sage.server import SageApp, SageError

    app = SageApp(DecisionJournal(tmp_path / "journal.db"))
    messages = []

    for route, charge in REFUS_ATTENDUS:
        with pytest.raises(SageError) as refus:
            getattr(app, route)(charge)
        messages.append((route, charge, refus.value.message))

    # Le meme journal, la meme faute, par le clavier.
    entree = DecisionJournal(tmp_path / "journal.db").entries()
    assert not entree, "aucune de ces ecritures ne doit avoir abouti"

    fautifs = [(route, message) for route, _, message in messages
               if any(mot in message for mot in LANGUE_DE_LA_MACHINE)]
    assert not fautifs, f"ces refus arrivent en anglais sur son ecran : {fautifs}"


def test_le_balayage_declenche_bien_des_refus(tmp_path):
    """Le temoin : une charge devenue valide ferait passer le test au vert."""
    from singular.sage.server import SageApp, SageError

    app = SageApp(DecisionJournal(tmp_path / "journal.db"))
    for route, charge in REFUS_ATTENDUS:
        with pytest.raises(SageError):
            getattr(app, route)(charge)
    assert len(REFUS_ATTENDUS) >= 4


# --- et le nom du champ, lu a l'ecran et pas dans le JSON ----------------------

def test_le_serveur_nomme_le_champ_comme_il_s_affiche(tmp_path):
    """Le refus du formulaire nommait la clef JSON : « « title » est obligatoire ».

    Une phrase francaise autour d'un mot anglais qu'il ne voit sur aucun ecran --
    le formulaire affiche « La décision ». Et c'etait une deuxieme ecriture de la
    meme regle : le clavier refusait deja avec la phrase de `singular.saisie`.
    """
    from singular.saisie import CHAMP_ACTION, CHAMP_ATTENDU, CHAMP_DECISION
    from singular.sage.server import SageApp, SageError

    app = SageApp(DecisionJournal(tmp_path / "journal.db"))
    complet = {"title": "T", "action": "a", "predicted": "p", "probability": 0.6,
               "tier": "REVENUS", "cost_hours": 2, "horizon_days": 14}

    for clef, nom in (("title", CHAMP_DECISION), ("action", CHAMP_ACTION),
                      ("predicted", CHAMP_ATTENDU)):
        with pytest.raises(SageError) as refus:
            app.add(complet | {clef: "   "})
        assert refus.value.message.startswith(nom), refus.value.message
        assert clef not in refus.value.message, (
            f"le refus nomme la clef JSON « {clef} » : ce mot n'est sur aucun ecran")


#: Les trois nombres d'une decision : leur clef JSON et ce que le refus doit dire.
NOMBRES_DU_FORMULAIRE = ("probability", "cost_hours", "horizon_days")


@pytest.mark.parametrize("clef", NOMBRES_DU_FORMULAIRE)
def test_le_serveur_refuse_un_nombre_absent_en_le_nommant(tmp_path, clef):
    """Le garde n'avait aucun temoin, et il refusait sous un mot invisible.

    `_number` leve quand la clef manque. Neutralise, `payload[clef]` leve un
    `KeyError` nu : le formulaire recoit un 500 au lieu d'un refus qui dit quoi
    corriger. Aucun test ne postait un corps sans l'un des trois nombres.

    Et le refus nommait la clef JSON -- « probability » est obligatoire -- un mot
    qui n'est sur aucun ecran : le formulaire dit « Probabilité que ça arrive ».
    C'est exactement le defaut que `singular.saisie` a corrige pour les trois
    textes, cite dans son propre commentaire, et reste pour les trois nombres.
    """
    from singular.sage.server import SageApp, SageError
    from singular.saisie import CHAMPS_NOMBRES

    app = SageApp(DecisionJournal(tmp_path / "journal.db"))
    complet = {"title": "T", "action": "a", "predicted": "p", "probability": 0.6,
               "tier": "REVENUS", "cost_hours": 2, "horizon_days": 14}
    sans = {c: v for c, v in complet.items() if c != clef}

    with pytest.raises(SageError) as refus:
        app.add(sans)
    assert refus.value.message.startswith(CHAMPS_NOMBRES[clef]), refus.value.message
    assert clef not in refus.value.message, (
        f"le refus nomme la clef JSON « {clef} » : ce mot n'est sur aucun ecran")


@pytest.mark.parametrize("clef", NOMBRES_DU_FORMULAIRE)
def test_le_serveur_refuse_un_nombre_illisible_en_le_nommant(tmp_path, clef):
    """L'autre moitie du meme garde : present mais pas un nombre."""
    from singular.sage.server import SageApp, SageError
    from singular.saisie import CHAMPS_NOMBRES

    app = SageApp(DecisionJournal(tmp_path / "journal.db"))
    complet = {"title": "T", "action": "a", "predicted": "p", "probability": 0.6,
               "tier": "REVENUS", "cost_hours": 2, "horizon_days": 14}

    with pytest.raises(SageError) as refus:
        app.add(complet | {clef: "pas un nombre"})
    assert refus.value.message.startswith(CHAMPS_NOMBRES[clef]), refus.value.message
    assert clef not in refus.value.message


def test_aucun_nombre_du_serveur_ne_refuse_sans_nom_d_ecran():
    """Un quatrieme nombre ajoute demain ne doit pas pouvoir refuser en anglais.

    La liste ci-dessus est ecrite a la main ; celle-ci est lue dans le code. Si
    `_number` est appele sur une clef qui n'a pas de nom d'ecran, `nom_du_nombre`
    leve -- mais il leverait en production, devant l'utilisateur. Ce test le dit
    avant, et il dit aussi quand la liste parametree ci-dessus a vieilli.
    """
    import ast

    from singular.saisie import CHAMPS_NOMBRES

    racine = pathlib.Path(__file__).resolve().parent.parent
    arbre = ast.parse((racine / "singular/sage/server.py").read_text(encoding="utf-8"))
    lues = {noeud.args[1].value for noeud in ast.walk(arbre)
            if isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name)
            and noeud.func.id == "_number" and len(noeud.args) >= 2
            and isinstance(noeud.args[1], ast.Constant)}

    assert lues, "plus aucun appel a `_number` : ce test ne prouve plus rien"
    orphelines = sorted(lues - set(CHAMPS_NOMBRES))
    assert not orphelines, (
        f"ces nombres refuseraient sous leur clef JSON : {orphelines}. "
        "Ajoute-les a CHAMPS_NOMBRES dans `singular.saisie`.")
    assert lues == set(NOMBRES_DU_FORMULAIRE), (
        f"la liste parametree de ce fichier a vieilli : le serveur lit {sorted(lues)}")


def test_les_noms_des_champs_n_ont_qu_un_domicile():
    """Trois chaines recopiees dans deux surfaces sont deux surfaces qui divergent."""
    from singular.saisie import (CHAMP_ACTION, CHAMP_ATTENDU, CHAMP_DECISION,
                                 CHAMP_HEURES, CHAMP_HORIZON, CHAMP_PROBABILITE)

    racine = pathlib.Path(__file__).resolve().parent.parent
    domicile = (racine / "singular/saisie.py").read_text(encoding="utf-8")
    surfaces = [racine / "singular/__main__.py", racine / "singular/sage/server.py"]

    for nom in (CHAMP_DECISION, CHAMP_ACTION, CHAMP_ATTENDU,
                CHAMP_PROBABILITE, CHAMP_HEURES, CHAMP_HORIZON):
        assert f'"{nom}"' in domicile, f"« {nom} » a quitté `singular.saisie`"
        for surface in surfaces:
            assert f'"{nom}"' not in surface.read_text(encoding="utf-8"), (
                f"{surface.name} récrit « {nom} » au lieu de le lire")
