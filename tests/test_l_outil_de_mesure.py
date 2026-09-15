"""L'instrument qui dit « ce refus n'a aucun temoin » n'en avait aucun lui-meme.

`tools/gardes_sans_test.py` decide quels refus de la frontiere sont prouves.
Tout ce qu'il annonce est cru, donc ses fautes ne se voient pas : il s'est
trompe deux fois le meme jour, dans le sens rassurant les deux fois.

* Sa sous-suite nommait un fichier de tests renomme entre-temps : pytest
  refusait de collecter, et **chaque refus paraissait prouve**.
* Il sabotait le depot lui-meme, donc un garde neutralise se retrouvait dans
  `git status` au moment de committer -- rattrape par un hook de sortie -- et un
  processus tue avant son `finally` laissait ce garde en place.

Troisieme fois qu'une faute de l'instrument me coute un tour : on arrete de
corriger, on ecrit ce qui echoue a la place du prochain lecteur.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

from tools.gardes_sans_test import (
    CIBLES_FRONTIERE,
    CIBLES_MATINS,
    GROUPES,
    RendLaConditionFausse,
    RendLeRefusVrai,
    RendUneMoitieFausse,
    _la_sous_suite_passe,
    moities_d_un_fichier,
    moities_rendues_d_un_fichier,
    refus_booleens_d_un_fichier,
    refus_d_un_fichier,
    _un_groupe,
    copie_a_mesurer,
    fichiers_a_copier,
)

RACINE = pathlib.Path(__file__).resolve().parent.parent


def _dans_un_depot_git() -> bool:
    acheve = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True,
                            text=True, cwd=RACINE, check=False)
    return acheve.returncode == 0


#: Trois tests d'ici mesurent le depot lui-meme, donc ils appellent `git`. Ils
#: doivent sauter la ou il n'y en a pas -- **dans la copie jetable que l'outil
#: fabrique**, qui n'est pas un depot. Sans ce saut, ces trois tests echouaient
#: dans la copie, donc la suite entiere y echouait, donc l'outil ne pouvait plus
#: confirmer aucun survivant : une passe de soixante-douze mutants annoncee sans
#: rien signaler. La faute la plus couteuse de la journee, et elle etait dans
#: l'instrument, encore.
hors_depot = pytest.mark.skipif(not _dans_un_depot_git(),
                                reason="mesure le depot lui-meme ; ici il n'y en a pas")


# --- la copie -----------------------------------------------------------------

@hors_depot
def test_saboter_dans_la_copie_ne_touche_pas_le_depot():
    """Le defaut qu'un hook de sortie a rattrape : un garde sabote pret a etre commite."""
    cible = "singular/execution.py"
    avant = (RACINE / cible).read_bytes()
    with copie_a_mesurer() as copie:
        assert (copie / cible).read_bytes() == avant
        (copie / cible).write_text("raise SystemExit('sabote')\n", encoding="utf-8")
        assert (copie / cible).read_bytes() != avant
        assert (RACINE / cible).read_bytes() == avant
    assert (RACINE / cible).read_bytes() == avant


@hors_depot
def test_la_copie_est_ce_que_python_importe():
    """Mesure, pas deduction : le paquet est installe en editable.

    Un finder de `site-packages` pointe vers l'arbre d'origine, et il est
    consulte avant `sys.path`. Si c'etait lui qui gagnait, l'outil muterait la
    copie, importerait l'original, et declarerait tous les refus prouves. C'est
    `python -m pytest` qui tranche : son repertoire courant passe devant.
    """
    with copie_a_mesurer() as copie:
        acheve = subprocess.run(
            [sys.executable, "-c", "import singular.journal as m; print(m.__file__)"],
            capture_output=True, text=True, cwd=copie, check=True,
        )
        assert acheve.stdout.strip().startswith(str(copie))


@hors_depot
def test_la_copie_porte_ce_qui_n_est_pas_encore_commite():
    """Un audit lance avant de committer doit mesurer les temoins qu'on vient d'ecrire."""
    temoin = RACINE / ".gardes_temoin_non_suivi"
    temoin.write_text("non suivi\n", encoding="utf-8")
    try:
        assert temoin.name in fichiers_a_copier()
        with copie_a_mesurer() as copie:
            assert (copie / temoin.name).read_text(encoding="utf-8") == "non suivi\n"
    finally:
        temoin.unlink()


# --- ce que l'outil nomme -----------------------------------------------------

def test_chaque_fichier_nomme_par_l_outil_existe():
    """La faute qui rendait tout vert : un fichier de tests renomme."""
    for cible in CIBLES_FRONTIERE + CIBLES_MATINS:
        assert (RACINE / cible).is_file(), f"cible disparue : {cible}"
    for nom, (_, sous_suite) in GROUPES.items():
        for fichier in sous_suite:
            assert (RACINE / fichier).is_file(), f"{nom} : sous-suite disparue : {fichier}"


def test_une_sous_suite_qui_ne_collecte_pas_est_un_echec():
    """Le controle d'entree de l'outil repose sur ca, et c'est ce qui avait manque."""
    assert _la_sous_suite_passe(("tests/test_ce_fichier_n_existe_pas.py",)) is False


# --- les quatre formes de sabotage ---------------------------------------------

SOURCE = """
def refuse(a, b):
    if a or b:
        raise PermissionError("non")
    if a and b:
        raise PermissionError("non non")
    return False

def accepte() -> bool:
    if False:
        return False
    return False

def verdict(a, b, c) -> bool:
    return a or b or c

def imbrique(a, b, c, d) -> bool:
    return a or b or (c and d)
"""


def _mute(transformateur):
    arbre = transformateur.visit(ast.parse(SOURCE))
    assert transformateur.touche, "le transformateur n'a rien touche"
    ast.fix_missing_locations(arbre)
    return ast.unparse(arbre)


def _mute_moitie(collecteur, etiquette: str) -> str:
    """Neutralise la moitie que le collecteur annonce sous cette etiquette.

    Le test vise ce que l'outil **nomme**, pas une ligne choisie a la main : c'est
    l'accord entre le collecteur et le transformateur qui est mesure ici, et c'est
    exactement la ou le defaut se cachait.
    """
    clefs = {quoi: clef for clef, quoi in collecteur(ast.parse(SOURCE))}
    assert etiquette in clefs, f"etiquette absente ; connues : {sorted(clefs)}"
    return _mute(RendUneMoitieFausse(clefs[etiquette]))


def test_la_condition_entiere_devient_fausse():
    assert "if False:\n        raise PermissionError('non')" in _mute(RendLaConditionFausse(3))


def test_un_refus_qui_rend_faux_devient_un_accord():
    """La forme que la premiere version ignorait : un predicat qui cesse de refuser."""
    mute = _mute(RendLeRefusVrai(12))
    assert "return True" in mute
    assert mute.count("return False") == 2  # celui de `refuse` et le dernier, intacts


def test_une_moitie_prend_l_element_neutre_de_son_operateur():
    """`False` dans un `or`, `True` dans un `and` : l'autre moitie continue de garder."""
    assert "if False or b:" in _mute_moitie(moities_d_un_fichier, "moitie 1 du or :: a")
    assert "if a or False:" in _mute_moitie(moities_d_un_fichier, "moitie 2 du or :: b")
    assert "if True and b:" in _mute_moitie(moities_d_un_fichier, "moitie 1 du and :: a")
    assert "if a and True:" in _mute_moitie(moities_d_un_fichier, "moitie 2 du and :: b")


def test_une_moitie_rendue_prend_aussi_l_element_neutre():
    """La quatrieme forme : un predicat qui **rend** un booleen compose.

    Les trois premieres ne voient que ce qui refuse -- un `raise`, un `return
    False`. Celle-ci voit ce qui decide, et c'est la seule qui trouve quoi que ce
    soit dans `global_control.py`, ou `requires_human` reunit cinq raisons d'exiger
    un humain par des `or`.
    """
    rendu = "moitie {} du or rendu (verdict) :: {}"
    assert "return False or b or c" in _mute_moitie(moities_rendues_d_un_fichier, rendu.format(1, "a"))
    assert "return a or False or c" in _mute_moitie(moities_rendues_d_un_fichier, rendu.format(2, "b"))
    assert "return a or b or False" in _mute_moitie(moities_rendues_d_un_fichier, rendu.format(3, "c"))


def test_une_ligne_a_deux_boolops_mute_celui_que_l_etiquette_nomme():
    """Le defaut trouve le 14 septembre 2026, et il etait dans l'instrument.

    La clef ne portait que la ligne, et `generic_visit` visite les enfants avant
    leur parent : viser « la ligne 45, moitie 2 » mutait donc le `and` imbrique au
    lieu du `or` exterieur. Le rapport nommait une moitie et en neutralisait une
    autre -- et les deux premieres moities du `or` n'etaient jamais mutees du tout.

    Mesure sur `GlobalDecisionReport.requires_human`, l'exemple meme dont l'outil
    se reclame : trois de ses cinq raisons annoncees comme mesurees ne l'etaient
    pas. Une passe entiere de la frontiere a ete triee sur ces etiquettes.

    Les collecteurs se croyaient a l'abri : leur docstring disait sauter les lignes
    ambigues, mais ils ne regardaient que le `BoolOp` de tete et ne voyaient donc
    jamais les imbriques. Ils ne sautaient rien. La colonne les distingue, et
    l'imbrique devient mesurable au lieu d'etre confondu.
    """
    clefs = {quoi: clef for clef, quoi in moities_rendues_d_un_fichier(ast.parse(SOURCE))}
    exterieur = clefs["moitie 1 du or rendu (imbrique) :: a"]
    interieur = clefs["moitie 1 du and rendu (imbrique) :: c"]
    assert exterieur[0] == interieur[0], "le cas ne vaut que si les deux sont sur la meme ligne"
    assert exterieur[1] != interieur[1], "la colonne doit les distinguer"

    assert "return False or b or (c and d)" in _mute(RendUneMoitieFausse(exterieur))
    assert "return a or b or (True and d)" in _mute(RendUneMoitieFausse(interieur))


def test_la_quatrieme_forme_ne_ramasse_que_les_predicats_declares():
    """Le meme critere que la forme 2 : `-> bool` declare un predicat.

    Sans lui, tout `return a or b` du depot deviendrait un mutant -- y compris ceux
    qui rendent autre chose qu'un booleen, ou muter ne dirait plus la meme chose.
    """
    trouves = moities_rendues_d_un_fichier(ast.parse(SOURCE))
    assert {quoi.split(" :: ")[0] for _, quoi in trouves} == {
        "moitie 1 du or rendu (verdict)", "moitie 2 du or rendu (verdict)",
        "moitie 3 du or rendu (verdict)",
        "moitie 1 du or rendu (imbrique)", "moitie 2 du or rendu (imbrique)",
        "moitie 3 du or rendu (imbrique)",
        "moitie 1 du and rendu (imbrique)", "moitie 2 du and rendu (imbrique)",
    }

    sans_annotation = ast.parse("def v(a, b):\n    return a or b\n")
    assert moities_rendues_d_un_fichier(sans_annotation) == []


def test_la_porte_globale_est_desormais_visible():
    """Le defaut qui a motive la quatrieme forme, verifie sur le vrai fichier.

    `global_control.py` ne leve aucun refus : les trois premieres formes n'y
    trouvaient rien, donc l'instrument disait « rien a signaler » sur le module qui
    decide si une action peut etre preparee et si un humain est requis.
    """
    source = (RACINE / "singular" / "global_control.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    assert refus_d_un_fichier(arbre) == []
    assert refus_booleens_d_un_fichier(arbre) == []
    assert moities_d_un_fichier(arbre) == []

    rendus = moities_rendues_d_un_fichier(arbre)
    predicats = {quoi.split(" :: ")[0].rsplit("(", 1)[1].rstrip(")") for _, quoi in rendus}
    assert predicats == {"can_prepare", "requires_human"}


def test_une_suite_entiere_deja_rouge_arrete_l_outil(monkeypatch: pytest.MonkeyPatch):
    """Le controle d'entree qui manquait, et qui a coute une passe entiere.

    Si la suite entiere echoue sans mutant, chaque survivant du sous-ensemble est
    annonce comme un faux positif : l'outil ne mesure plus rien et dit que tout
    va bien. Il doit refuser de mesurer, et le dire.
    """
    import tools.gardes_sans_test as outil

    monkeypatch.setattr(outil, "_JUGES_VERIFIES", set())
    monkeypatch.setattr(outil, "_la_sous_suite_passe", lambda *args, **kwargs: True)
    monkeypatch.setattr(outil, "_la_suite_entiere_passe", lambda *args, **kwargs: False)

    assert _un_groupe("frontiere") == -1


# --- ce qu'un `raise` peut refuser ---------------------------------------------

def test_les_refus_du_depot_entrent_sans_qu_on_les_ecrive():
    """La liste des exceptions de refus est derivee, plus ecrite a la main.

    Elle ne portait que quatre noms du langage, et la forme 1 compare le nom
    **ecrit dans le `raise`**, pas la classe. Un `raise ExecutionRecoveryRequired`
    -- qui est un `RuntimeError` -- etait donc invisible, comme `ImportRefused`,
    `SauvegardeRefusee`, `EffectInProgress`, `FormatRefuse`.

    Mesure du 15 septembre 2026 : `singular/sauvegarde.py`, 261 lignes qui
    gardent le seul fichier irremplacable du depot, rendait zero mutant. Le
    silence de l'outil se lisait comme une couverture ; c'etait une cecite, et
    elle s'aggravait toute seule -- plus le depot nomme ses refus, moins l'outil
    en voit.
    """
    from tools.gardes_sans_test import REFUS, REFUS_DU_LANGAGE, refus_du_depot

    assert REFUS_DU_LANGAGE <= REFUS, "les refus du langage doivent rester dedans"
    propres = REFUS - REFUS_DU_LANGAGE
    assert {"SauvegardeRefusee", "ImportRefused", "ExecutionRecoveryRequired",
            "EffectInProgress", "FormatRefuse", "SubstitutionRefusee"} <= propres, (
        f"des refus du depot manquent a la derivation : {sorted(propres)}")

    # La fermeture est transitive : une exception qui herite d'une exception de
    # refus refuse aussi, si loin qu'elle soit de la racine.
    derives = refus_du_depot()
    assert derives == REFUS, "la derivation doit etre stable d'un appel a l'autre"


def test_un_refus_nomme_par_le_depot_est_bien_mute():
    """Le bout qui compte : le derive doit produire un mutant, pas juste un nom."""
    source = (
        "class SauvegardeRefusee(Exception):\n"
        "    pass\n"
        "\n"
        "def copie(actif):\n"
        "    if not actif.exists():\n"
        "        raise SauvegardeRefusee('source absente')\n"
        "    return actif\n"
    )
    trouves = refus_d_un_fichier(ast.parse(source))
    assert trouves, "un refus nomme par le depot doit etre mutable"

    mutant = RendLaConditionFausse(trouves[0][0])
    arbre = mutant.visit(ast.parse(source))
    assert mutant.touche
    ast.fix_missing_locations(arbre)
    assert "if False:" in ast.unparse(arbre)
