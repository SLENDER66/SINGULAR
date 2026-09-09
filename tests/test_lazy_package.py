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


def test_un_journal_vide_dit_ou_il_a_regarde(tmp_path, capsys) -> None:
    """Le corollaire du coeur sans dependance : deux machines, deux journaux.

    Un journal vide et un journal ouvert au mauvais endroit donnent le meme
    ecran. Depuis que SINGULAR tourne aussi sur le telephone, la confusion est
    devenue possible pour de bon -- et elle ne se signale pas toute seule :
    chacun des deux a l'air simplement neuf.
    """
    from singular.__main__ import main

    chemin = tmp_path / "ailleurs.db"

    for commande in sorted(RAPPORTENT_LE_JOURNAL):
        capsys.readouterr()
        assert main(["--db", str(chemin), commande]) == 0
        assert str(chemin) in capsys.readouterr().out, (
            f"`{commande}` dit que le journal est vide sans dire ou il a regarde. "
            "Un chemin mal tape ressemble alors a une bonne nouvelle.")


#: Les commandes dont le travail est de rapporter le contenu du journal.
#:
#: `due` a longtemps manque a cette liste, et c'est la pire absence possible :
#: c'est la commande de chaque matin, celle que le rituel d'`USAGE.md` demande
#: de taper tous les jours. Elle repondait « Rien a trancher » sur un chemin mal
#: tape -- une phrase qui ressemble a une bonne nouvelle.
RAPPORTENT_LE_JOURNAL = {"due", "list", "review"}

#: Et pourquoi les autres n'ont rien a dire d'un journal vide.
SANS_RAPPORT_A_FAIRE = {
    "add": "ecrit une ligne, il n'y a rien a rapporter avant",
    "apply": "idem",
    "resolve": "nomme deja l'identifiant qu'il n'a pas trouve",
    "abandon": "idem",
    "export": "produit du CSV pour une machine, pas une phrase pour lui",
    "status": "une seule ligne, pour l'invite du shell : un chemin y serait du bruit",
    "sage": "affiche l'adresse, et l'app dit le chemin dans sa carte vide",
    "analyse": "part du rapport, pas du journal",
    "offres": "ne lit pas le journal",
    "parle": "idem",
}


def test_toute_commande_est_classee(tmp_path) -> None:
    """Une nouvelle commande doit etre rangee d'un cote ou de l'autre.

    Sans ce test, la liste ci-dessus vieillit en silence : c'est exactement
    comme ca que `due` a manque a l'appel pendant qu'on corrigeait `list` et
    `review`.
    """
    from singular.__main__ import build_parser

    sous_commandes = set()
    for action in build_parser()._actions:
        if getattr(action, "choices", None):
            sous_commandes |= set(action.choices)

    classees = RAPPORTENT_LE_JOURNAL | set(SANS_RAPPORT_A_FAIRE)
    assert sous_commandes == classees, (
        f"non classees : {sorted(sous_commandes - classees)} ; "
        f"disparues : {sorted(classees - sous_commandes)}")


# --- ce que la paresse ne doit pas masquer -----------------------------------

def test_un_module_casse_ne_passe_pas_pour_un_nom_inconnu(tmp_path) -> None:
    """« Unsafe fallback », au sens de CLAUDE.md §7, et il tombait sur son cas.

    Un sous-module qui existe mais echoue a s'importer -- une dependance
    absente -- etait annonce exactement comme un nom mal orthographie. Sur un
    telephone sans `pydantic`, `singular.models` disait « singular n'a pas
    d'attribut models » : on part chercher une faute de frappe pendant que la
    vraie cause est un paquet manquant.
    """
    import subprocess
    import sys
    import textwrap

    resultat = subprocess.run(
        [sys.executable, "-c", textwrap.dedent('''
            import builtins
            _vrai = builtins.__import__
            def _sans(nom, *a, **k):
                if nom.split(".")[0].startswith("pydantic"):
                    raise ModuleNotFoundError("No module named 'pydantic'", name="pydantic")
                return _vrai(nom, *a, **k)
            builtins.__import__ = _sans
            import singular
            try:
                singular.models
            except ModuleNotFoundError as erreur:
                assert "pydantic" in str(erreur), erreur
                print("OK")
            except AttributeError:
                raise SystemExit("la vraie cause a ete masquee")
        ''')],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert resultat.returncode == 0, resultat.stderr[-600:]
    assert "OK" in resultat.stdout


def test_un_nom_vraiment_inconnu_reste_une_erreur_d_attribut() -> None:
    """L'autre moitié : ne pas convertir l'absence réelle en autre chose."""
    with pytest.raises(AttributeError, match="pas_de_module_de_ce_nom"):
        singular.__getattr__("pas_de_module_de_ce_nom")


def test_les_noms_prives_ne_declenchent_aucun_import() -> None:
    """`inspect` et pytest sondent `__wrapped__`, `__bases__` et consorts.

    Chacun coûterait sinon une recherche de module sur le disque, pour rien.
    """
    for sonde in ("__wrapped__", "__bases__", "_interne"):
        with pytest.raises(AttributeError):
            singular.__getattr__(sonde)


def test_l_apercu_d_analyse_marche_sans_la_moindre_dependance(tmp_path) -> None:
    """`analyse --blanc` est le pont vers Claude qui ne coute rien.

    Il assemble le rapport en texte et n'appelle personne : donc il tourne sur
    un telephone, sans SDK, sans cle, sans PC -- on colle le bloc dans l'app
    Claude, deja payee par l'abonnement.

    Ca tient parce que l'import du SDK est tardif. Rien ne le garantissait :
    remonter cet import en tete de `analyse.py` casserait ce chemin sans
    casser un seul autre test, et personne ne le verrait avant le telephone.
    """
    resultat = _sans_les_lourds(f'''
        import sys
        from singular.journal import DecisionJournal, Reversibility, Tier

        journal = DecisionJournal(r"{tmp_path / 'j.db'}")
        journal.add(title="Emprunter", action="Credit", predicted="Materiel en service",
                    probability=0.8, tier=Tier.REVENUS, cost_hours=3, horizon_days=60,
                    expected_gain_eur=0, reversibility=Reversibility.IRREVERSIBLE)

        sys.argv = ["singular", "--db", r"{tmp_path / 'j.db'}", "analyse", "--blanc"]
        from singular.__main__ import main
        raise SystemExit(main())
    ''')
    assert resultat.returncode == 0, resultat.stderr[-800:]
    assert "Rien n'a ete envoye" in resultat.stdout
    assert "irréversible" in resultat.stdout
    assert "chain_intact" in resultat.stdout


def test_un_fichier_qui_n_est_pas_une_base_ne_deroule_pas_de_pile(tmp_path, capsys) -> None:
    """Le cas d'un fichier copie de travers, ou d'une ecriture interrompue.

    `sqlite3.DatabaseError: file is not a database` arrivait sur son ecran avec
    sa pile d'appels. Il debute en code : une pile Python ne se distingue pas
    d'une application cassee, et le geste dangereux -- supprimer le fichier --
    est justement celui qu'on est tente de faire quand on ne comprend pas.
    """
    from singular.__main__ import main

    faux = tmp_path / "pas-une-base.db"
    faux.write_text("ceci n'est pas une base" * 50, encoding="utf-8")

    assert main(["--db", str(faux), "due"]) == 1
    sortie = capsys.readouterr().out
    assert str(faux) in sortie
    assert "Ne le supprime pas" in sortie
    for pile in ("Traceback", "sqlite3", "file is not a database"):
        assert pile not in sortie, f"la pile arrive sur son ecran : {sortie}"
