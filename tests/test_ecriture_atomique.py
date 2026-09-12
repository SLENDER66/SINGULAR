"""Un fichier d'etat ne doit jamais exister a moitie.

Trois fichiers portent quelque chose qu'il ne peut pas reconstituer : son fil
de conversation, sa cle d'acces, ses candidatures. Les trois etaient ecrits par
un `write_text`, qui tronque le fichier puis ecrit dedans. Entre les deux, il
n'y a rien.

Reproduit sur le suivi de candidatures avant correction : 1266 octets sains,
635 apres une coupure au milieu de l'ecriture, et l'outil refuse alors de
demarrer en renvoyant `Unterminated string starting at: line 27` -- une erreur
de parseur JSON, a quelqu'un qui debute en code. Son historique n'est pas perdu
au sens strict ; il est illisible, ce qui revient au meme.

`Quota` faisait deja l'ecriture en deux temps, exactement pour cette raison.
C'etait donc la troisieme fois que le meme oubli se payait : on arrete de le
corriger, et ce fichier echoue a la place du prochain lecteur.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent

#: Ce qui porte un etat qu'il ne peut pas reconstituer, et le nom de la
#: fonction qui a le droit d'y ecrire.
ETATS = {
    "singular/fichiers.py": "ecrire_atomique",
    "singular/parle.py": None,          # passe par `ecrire_atomique`
    "singular/sage/server.py": None,    # idem
    "proto/suivi_candidatures.py": "sauver",  # copie assumee, voir sa docstring
}


def _ecritures(source: pathlib.Path) -> list[tuple[int, str]]:
    """Les appels qui creent un fichier sur le disque, avec leur ligne.

    `write_text` et `open(..., "w")` seulement. Un `.write` nu serait plus
    large et attraperait `wfile.write` -- la socket HTTP du Sage, qui n'est pas
    un fichier -- et un test qui crie au loup finit desactive. Pour poser un
    contenu sur le disque il faut de toute facon passer par l'un des deux, et
    `os.write` sur un descripteur ne vit que dans `ecrire_atomique`.
    """
    trouvees = []
    for noeud in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if not isinstance(noeud, ast.Call):
            continue
        nom = ""
        if isinstance(noeud.func, ast.Attribute):
            nom = noeud.func.attr
        elif isinstance(noeud.func, ast.Name):
            nom = noeud.func.id
        ouverture_en_ecriture = nom == "open" and any(
            isinstance(argument, ast.Constant) and isinstance(argument.value, str)
            and "w" in argument.value for argument in noeud.args)
        if nom == "write_text" or ouverture_en_ecriture:
            trouvees.append((noeud.lineno, nom))
    return trouvees


def _fonction_contenant(source: pathlib.Path, ligne: int) -> str:
    arbre = ast.parse(source.read_text(encoding="utf-8"))
    portee = ""
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.FunctionDef) and noeud.lineno <= ligne <= (
                noeud.end_lineno or noeud.lineno):
            portee = noeud.name
    return portee


@pytest.mark.parametrize("relatif", sorted(ETATS))
def test_no_state_file_is_written_in_place(relatif: str) -> None:
    """Une ecriture directe sur le fichier final le laisse tronque si ca coupe."""
    source = RACINE / relatif
    autorisee = ETATS[relatif]

    fautes = []
    for ligne, nom in _ecritures(source):
        dans = _fonction_contenant(source, ligne)
        if dans == autorisee:   # `None` n'egale aucun nom de fonction
            continue
        fautes.append(f"{relatif}:{ligne} ecrit par `{nom}` dans `{dans or '<module>'}`")

    assert not fautes, (
        f"{fautes} ecrit un fichier d'etat en place. Passe par "
        "`singular.fichiers.ecrire_atomique` : une coupure au milieu laisserait "
        "un fichier a moitie ecrit, et l'outil refuserait de demarrer."
    )


def test_the_atomic_writer_writes_beside_then_replaces() -> None:
    """Le temoin : sans ca, `ecrire_atomique` pourrait ne plus rien garantir."""
    source = (RACINE / "singular/fichiers.py").read_text(encoding="utf-8")
    assert "os.replace(provisoire, chemin)" in source
    assert "O_EXCL" in source, "deux ecrivains doivent se voir"
    assert "unlink(missing_ok=True)" in source, "un provisoire abandonne bloquerait O_EXCL"


def test_an_interrupted_write_leaves_the_previous_file_intact(tmp_path) -> None:
    """Ce que la correction achete, joue pour de bon.

    L'interruption est simulee la ou elle fait mal : le contenu est ecrit, puis
    tout s'arrete avant le remplacement.
    """
    from singular.fichiers import ecrire_atomique

    chemin = tmp_path / "etat.json"
    ecrire_atomique(chemin, json.dumps({"candidatures": ["A", "B", "C"]}))
    sain = chemin.read_text(encoding="utf-8")

    class Coupure(BaseException):
        """Ni `Exception` ni `KeyboardInterrupt` : ce qui interrompt vraiment."""

    def refuse(*_args, **_kwargs):
        raise Coupure

    import os as _os

    vrai = _os.replace
    _os.replace = refuse
    try:
        with pytest.raises(Coupure):
            ecrire_atomique(chemin, "{}")
    finally:
        _os.replace = vrai

    assert chemin.read_text(encoding="utf-8") == sain, "l'ancien fichier doit survivre"
    assert json.loads(chemin.read_text(encoding="utf-8"))["candidatures"] == ["A", "B", "C"]


def test_the_secret_is_never_briefly_readable_by_everyone(tmp_path) -> None:
    """La cle etait ecrite en clair, puis resserree. Entre les deux, une fenetre."""
    import os
    import stat

    from singular.fichiers import ecrire_atomique

    chemin = tmp_path / "sage_token"
    ecrire_atomique(chemin, "un-jeton", permissions=0o600)
    droits = stat.S_IMODE(os.stat(chemin).st_mode)

    assert not droits & stat.S_IRGRP, "lisible par le groupe"
    assert not droits & stat.S_IROTH, "lisible par tout le monde"


def test_the_tracker_survives_an_interruption(tmp_path, monkeypatch) -> None:
    """Le cas reel : ses candidatures, coupees au milieu d'une sauvegarde."""
    import importlib.util

    chemin_module = RACINE / "proto/suivi_candidatures.py"
    spec = importlib.util.spec_from_file_location("suivi_atomique", chemin_module)
    suivi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(suivi)
    monkeypatch.setattr(suivi, "FICHIER", tmp_path / "candidatures.json")

    depart = {"candidatures": [{"entreprise": "Bureau X", "poste": "CVC",
                                "statut": "envoyee", "date": "2026-09-01", "notes": []}],
              "cv": suivi._cv_neuf()}
    suivi.sauver(depart)

    provisoire = suivi.FICHIER.with_name(suivi.FICHIER.name + ".tmp")
    vrai = type(provisoire).replace

    def refuse(self, cible):
        raise KeyboardInterrupt

    monkeypatch.setattr(type(provisoire), "replace", refuse)
    with pytest.raises(KeyboardInterrupt):
        suivi.sauver({"candidatures": [], "cv": []})
    monkeypatch.setattr(type(provisoire), "replace", vrai)

    assert suivi.charger()["candidatures"] == depart["candidatures"], (
        "une sauvegarde interrompue a emporte son historique")
