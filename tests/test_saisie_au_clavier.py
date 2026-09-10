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
from singular.saisie import CONFLIT, introuvable
from singular.saisie import (
    entier as _entier,
)
from singular.saisie import (
    nombre as _nombre,
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

PROBABILITES = [0.0, 0.01, 0.05, 0.5, 0.75, 0.95, 0.99, 1.0, 1.5, 60.0, 75.0, 100.0, -0.5]
HEURES = [0.0, 0.5, 4.0, 1000.0, -0.5, -1.0, float("inf"), float("nan")]
JOURS = [0, 1, 14, 365, -1]


@pytest.mark.parametrize("valeur", PROBABILITES)
def test_the_question_and_the_journal_agree_on_a_probability(tmp_path, valeur):
    assert _accepte_par_la_question(_verifie_probabilite, valeur) is \
        _accepte_par_le_journal(tmp_path, probability=valeur)


@pytest.mark.parametrize("valeur", HEURES)
def test_the_question_and_the_journal_agree_on_hours(tmp_path, valeur):
    assert _accepte_par_la_question(_verifie_heures, valeur) is \
        _accepte_par_le_journal(tmp_path, cost_hours=valeur)


@pytest.mark.parametrize("valeur", JOURS)
def test_the_question_and_the_journal_agree_on_a_horizon(tmp_path, valeur):
    assert _accepte_par_la_question(_verifie_jours, valeur) is \
        _accepte_par_le_journal(tmp_path, horizon_days=valeur)


def test_typing_percent_says_what_to_write_instead():
    """Le cas réel : « 75 » pour 75 %. Le refus doit donner la réponse."""
    with pytest.raises(ValueError) as refus:
        _verifie_probabilite(75)
    assert "pour 75 %, ecris 0.75" in sans_accents(str(refus.value))


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
    et ce qu'elle accepte doit rester exactement ce que le journal accepte --
    sinon elle refuserait une decision valable, ou en laisserait passer une que
    le journal rejette juste apres.
    """
    assert _accepte_par_le_telephone(tmp_path, probability=valeur) is \
        _accepte_par_le_journal(tmp_path, probability=valeur)


@pytest.mark.parametrize("valeur", HEURES)
def test_the_phone_and_the_journal_agree_on_hours(tmp_path, valeur):
    assert _accepte_par_le_telephone(tmp_path, cost_hours=valeur) is \
        _accepte_par_le_journal(tmp_path, cost_hours=valeur)


@pytest.mark.parametrize("valeur", JOURS)
def test_the_phone_and_the_journal_agree_on_a_horizon(tmp_path, valeur):
    assert _accepte_par_le_telephone(tmp_path, horizon_days=valeur) is \
        _accepte_par_le_journal(tmp_path, horizon_days=valeur)


@pytest.mark.parametrize("valeur", [None, 0.0, 1500.0, -100.0, -0.01])
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
    fautifs = [{"probability": 1.0}, {"probability": 0.0}, {"probability": 75},
               {"cost_hours": -1}, {"horizon_days": 0}, {"expected_gain_eur": "-5"}]

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
    """
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
    assert 0 < attribut("probability", "min") / 100 < 1
    assert 0 < attribut("probability", "max") / 100 < 1
    assert attribut("cost_hours", "min") >= 0
    assert attribut("horizon_days", "min") >= 1


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


def test_the_keyboard_explains_an_unknown_identifier(tmp_path, capsys):
    """Il affichait `'DEC-inconnu'`, guillemets compris, et rien d'autre."""
    journal = DecisionJournal(tmp_path / "journal.db")
    assert journal is not None

    assert main(["--db", str(tmp_path / "journal.db"), "resolve", "DEC-inconnu", "--yes"]) == 1
    sortie = capsys.readouterr().out
    assert introuvable("DEC-inconnu") in sortie
    assert "'DEC-inconnu'" not in sortie, "le repr d'une cle absente n'explique rien"


@pytest.mark.parametrize("route", ["resolve", "abandon"])
def test_the_server_answers_a_conflict_in_his_language(tmp_path, route):
    """Le corps JSON partait en anglais ; seule l'app le remplacait, chez elle."""
    from singular.sage.server import SageApp, SageError

    journal, entry_id = _journal_tranche(tmp_path)
    app = SageApp(journal)
    charge = {"happened": False} if route == "resolve" else {"reason": "plus la peine"}

    with pytest.raises(SageError) as refus:
        getattr(app, route)(entry_id, charge)

    assert refus.value.message == CONFLIT
    assert "editable" not in refus.value.message


def test_the_web_copy_of_the_conflict_still_says_the_same_thing():
    """La seule copie qui ne peut pas importer `singular.saisie`.

    L'app doit pouvoir refuser hors connexion, donc elle porte la phrase en
    dur. Une phrase en double se corrige d'un seul cote : ce test est ce qui
    l'empeche.
    """
    app_js = (RACINE / "singular/sage/web/app.js").read_text(encoding="utf-8")
    assert CONFLIT in app_js, (
        "app.js ne dit plus ce que dit `singular.saisie.CONFLIT`. La phrase a "
        "un seul domicile ; la copie du navigateur doit le citer mot pour mot.")


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
])
def test_the_fast_paths_refuse_in_his_language(tmp_path, capsys, commande):
    """Le cas reel : il cherche un poste, donc `sj apply` est ce qu'il tape le plus."""
    DecisionJournal(tmp_path / "journal.db")

    assert main(["--db", str(tmp_path / "journal.db"), *commande]) == 1
    sortie = capsys.readouterr().out
    for anglais in ("must be", "cannot be", "needs a horizon", "is not a forecast"):
        assert anglais not in sortie, f"{commande} rend « {sortie.strip()} »"


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
