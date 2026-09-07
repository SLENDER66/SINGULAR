"""Importer SINGULAR ne doit rien charger de ce qu'on ne demande pas.

`singular/__init__.py` importait cinquante-cinq modules au chargement, et
`pydantic` avec eux. Consequence mesurable : `python -m singular` exigeait une
dependance que ni le journal, ni la chaine d'integrite, ni la Notice, ni le
Sage n'utilisent -- ils sont en bibliotheque standard pure.

Ca a coute une reponse fausse a une vraie question, « c'est oblige d'avoir un
ordi ? ». Sur un telephone ou `pip install` ne passe pas, l'outil devenait
injoignable a cause d'un fichier d'imports, pas a cause de ce qu'il fait.

Ces tests tiennent les deux moities :

* la table de resolution paresseuse dit la verite -- sinon `from singular
  import X` casse pour un nom qui marchait hier ;
* le coeur reste joignable sans rien installer -- sinon la paresse se perd au
  premier import ajoute en tete de fichier, sans que personne le voie.

Les deux derniers passent par un sous-processus : une fois `pydantic` charge
dans l'interpreteur du test, plus rien ne peut prouver qu'on s'en passe.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

import singular

#: Ce qui n'a pas le droit d'etre charge par un simple `import singular`.
LOURDS = ("pydantic", "pydantic_core", "anthropic", "openai", "agents")


def _sans_les_lourds(corps: str) -> subprocess.CompletedProcess:
    """Exécute `corps` dans un interpréteur où les paquets lourds n'existent pas."""
    prologue = textwrap.dedent(f'''
        import builtins, sys
        _vrai = builtins.__import__
        def _sans(nom, *a, **k):
            if nom.split(".")[0] in {LOURDS!r}:
                raise ImportError(nom + " indisponible (telephone simule)")
            return _vrai(nom, *a, **k)
        builtins.__import__ = _sans
    ''')
    return subprocess.run(
        [sys.executable, "-c", prologue + textwrap.dedent(corps)],
        capture_output=True, text=True, timeout=120, check=False,
    )


def test_la_table_dit_la_verite() -> None:
    """Chaque nom promis existe vraiment, dans le module annoncé."""
    fautes = []
    for expose, (module, origine) in singular._EXPORTS.items():
        try:
            reel = getattr(singular, expose)
        except AttributeError:
            fautes.append(f"{expose} : introuvable ({module}.{origine})")
            continue
        attendu = getattr(sys.modules[f"singular.{module}"], origine, None)
        if reel is not attendu:
            fautes.append(f"{expose} : ne resout pas vers {module}.{origine}")

    assert not fautes, "la table de __init__.py a diverge du code :\n  " + "\n  ".join(fautes)


def test_tout_ce_qui_est_promis_est_atteignable() -> None:
    assert singular.__all__ == sorted(singular._EXPORTS)
    assert set(dir(singular)) == set(singular.__all__)


def test_un_nom_inconnu_leve_bien_une_erreur_d_attribut() -> None:
    # On appelle le crochet directement : l'acces par attribut est une
    # expression sans effet que le linter refuse, et `getattr` avec une chaine
    # constante aussi. Viser la fonction est de toute facon plus precis.
    with pytest.raises(AttributeError, match="pas_un_nom"):
        singular.__getattr__("pas_un_nom")


def test_les_sous_modules_restent_accessibles_en_attribut() -> None:
    """`import singular; singular.audit` marchait par effet de bord des imports."""
    import types

    assert isinstance(singular.audit, types.ModuleType)
    assert isinstance(singular.journal, types.ModuleType)


# --- le coeur, joignable sans rien installer ---------------------------------

def test_importer_singular_ne_charge_pas_pydantic() -> None:
    resultat = _sans_les_lourds('''
        import singular, sys
        chargés = [m for m in sys.modules if m.split(".")[0] in ("pydantic", "pydantic_core")]
        assert not chargés, chargés
        print("OK")
    ''')
    assert resultat.returncode == 0, resultat.stderr[-800:]
    assert "OK" in resultat.stdout


def test_le_journal_et_la_notice_marchent_sans_dependance(tmp_path) -> None:
    """Le cas réel : SINGULAR sur un téléphone, où `pip install` ne passe pas."""
    resultat = _sans_les_lourds(f'''
        from singular.journal import DecisionJournal, Reversibility, Tier
        from singular.sage.notice import build_notice

        journal = DecisionJournal(r"{tmp_path / 'j.db'}")
        journal.add(title="Sur le telephone", action="A", predicted="B", probability=0.6,
                    tier=Tier.REVENUS, cost_hours=1, horizon_days=7,
                    expected_gain_eur=0, reversibility=Reversibility.REVERSIBLE)
        assert journal.verify()
        assert build_notice(journal).headline
        print("OK")
    ''')
    assert resultat.returncode == 0, resultat.stderr[-800:]
    assert "OK" in resultat.stdout


def test_la_ligne_de_commande_marche_sans_dependance(tmp_path) -> None:
    resultat = _sans_les_lourds(f'''
        import sys
        sys.argv = ["singular", "--db", r"{tmp_path / 'j.db'}", "add",
                    "--title", "Test", "--action", "A", "--predicted", "B",
                    "--probability", "0.6", "--tier", "REVENUS",
                    "--hours", "1", "--days", "7"]
        from singular.__main__ import main
        raise SystemExit(main())
    ''')
    assert resultat.returncode == 0, resultat.stderr[-800:]
    assert "verdict attendu" in resultat.stdout


def test_le_serveur_du_sage_s_importe_sans_dependance() -> None:
    """C'est lui qui sert l'app sur l'ecran d'accueil : il doit tenir aussi."""
    resultat = _sans_les_lourds('''
        from singular.sage.server import SageApp, build_server
        print("OK")
    ''')
    assert resultat.returncode == 0, resultat.stderr[-800:]
    assert "OK" in resultat.stdout
