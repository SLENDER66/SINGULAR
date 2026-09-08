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

import pytest

from singular.__main__ import (
    _entier,
    _nombre,
    _verifie_heures,
    _verifie_jours,
    _verifie_probabilite,
)
from singular.journal import DecisionJournal, Tier


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
    with pytest.raises(ValueError, match=r"pour 75 %, ecris 0\.75"):
        _verifie_probabilite(75)


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
    assert _gain_prompt() is None, "un cout n'est pas un gain"
