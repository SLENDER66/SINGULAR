"""Le Scout collecte, et il ne peut rien faire d'autre.

Trois promesses, chacune vérifiée sur le code plutôt que sur l'intention.

**Lecture seule.** C'est la moitié qui compte. Un collecteur qui pourrait
écrire est un collecteur qui écrira, un jour, dans un fichier qu'on croyait
seulement lu — et ce dépôt tient une règle plus forte que la prudence :
`singular/journal.py` est la seule porte par où une décision entre.

**Chaque fait porte sa source.** Un chiffre sans provenance est un chiffre
qu'on ne peut pas contredire.

**Ce qui n'est pas vérifiable est marqué, jamais estimé.** Un fichier illisible
ne doit pas rendre zéro : zéro est un chiffre, et un zéro inventé ressemble à
un zéro vrai.
"""
from __future__ import annotations

import ast
import json
import pathlib
from datetime import UTC, datetime, timedelta

import pytest

from singular.collecte import STATUTS, Fait, candidatures, collecter

RACINE = pathlib.Path(__file__).resolve().parent.parent
SOURCE = RACINE / "singular" / "collecte.py"


def _suivi(chemin: pathlib.Path, lot: list[dict], cv: dict | None = None) -> pathlib.Path:
    chemin.write_text(json.dumps({"candidatures": lot, "cv": cv or {}},
                                 ensure_ascii=False), encoding="utf-8")
    return chemin


def _il_y_a(jours: int) -> str:
    return (datetime.now(UTC).date() - timedelta(days=jours)).isoformat()


# --- il ne peut rien ecrire ---------------------------------------------------

def test_le_scout_n_a_aucun_moyen_d_ecrire() -> None:
    """Vérifié sur l'arbre, pas sur la docstring.

    Les trois portes d'écriture de ce dépôt : `open(..., "w")`, les méthodes
    d'écriture de `Path`, et le journal lui-même. Aucune n'est ici, et c'est
    ce qui fait du « lecture seule » une propriété plutôt qu'une phrase.
    """
    arbre = ast.parse(SOURCE.read_text(encoding="utf-8"))
    fautes = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            nom = getattr(noeud.func, "attr", None) or getattr(noeud.func, "id", None)
            if nom in {"write_text", "write_bytes", "mkdir", "touch", "unlink",
                       "rename", "replace", "rmdir", "chmod"}:
                fautes.append(f"ligne {noeud.lineno} : {nom}()")
            if nom == "open":
                mode = next((a.value for a in noeud.args[1:2]
                             if isinstance(a, ast.Constant)), "r")
                if "r" not in str(mode):
                    fautes.append(f"ligne {noeud.lineno} : open(..., {mode!r})")
    assert not fautes, "le Scout doit rester en lecture seule :\n  " + "\n  ".join(fautes)


def test_le_scout_ne_connait_pas_le_journal() -> None:
    """Il observe la vie de Thomas ; il n'écrit pas son histoire.

    Comme `parle`, qui ne peut pas enregistrer une décision : ce n'est pas une
    consigne donnée au modèle, c'est une absence d'import.
    """
    importes = set()
    for noeud in ast.walk(ast.parse(SOURCE.read_text(encoding="utf-8"))):
        if isinstance(noeud, ast.Import):
            importes.update(a.name.split(".")[0] for a in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            importes.add(noeud.module.split(".")[0])
        elif isinstance(noeud, ast.ImportFrom) and noeud.level:
            importes.update(a.name for a in noeud.names)
    assert "journal" not in importes and "DecisionJournal" not in importes
    assert importes <= {"__future__", "json", "dataclasses", "datetime", "pathlib"}, (
        f"le Scout importe plus que la bibliotheque standard : {sorted(importes)}")


def test_le_temoin_de_lecture_seule_attraperait_une_ecriture() -> None:
    """Sans lui, les deux tests ci-dessus passeraient sur un fichier vide."""
    arbre = ast.parse('from pathlib import Path\nPath("x").write_text("y")\n')
    ecrit = [n for n in ast.walk(arbre)
             if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "write_text"]
    assert ecrit, "le motif cherche par le test doit exister quelque part"


# --- chaque fait porte sa source ----------------------------------------------

def test_un_fait_sans_source_est_refuse() -> None:
    with pytest.raises(ValueError, match="contredire"):
        Fait("candidatures", "trois candidatures", "")


def test_chaque_fait_collecte_nomme_son_fichier(tmp_path) -> None:
    chemin = _suivi(tmp_path / "c.json",
                    [{"statut": "envoyee", "date_statut": _il_y_a(5)}])
    for fait in candidatures(chemin):
        assert fait.source == str(chemin)
        assert fait.date, "un fait sans date ne se situe pas dans le temps"


# --- ce qui n'est pas verifiable est marque -----------------------------------

def test_un_fichier_illisible_ne_rend_pas_zero(tmp_path) -> None:
    """Le piège : « 0 candidature » et « je n'ai pas pu lire » se ressemblent."""
    chemin = tmp_path / "casse.json"
    chemin.write_text("{ceci n'est pas du JSON", encoding="utf-8")

    faits = candidatures(chemin)

    assert len(faits) == 1
    assert faits[0].verifie is False
    assert "illisible" in faits[0].texte
    assert "0" not in faits[0].texte, "un zero invente ressemble a un zero vrai"


def test_une_date_abimee_rend_le_fait_non_verifie(tmp_path) -> None:
    """Le fichier est relu par un humain : une date cassée ne fait pas tomber."""
    chemin = _suivi(tmp_path / "c.json", [{"statut": "envoyee", "date_statut": "hier"}])

    faits = candidatures(chemin)

    assert [f.verifie for f in faits] == [False]
    assert "sans date lisible" in faits[0].texte


def test_un_fichier_absent_se_distingue_d_un_fichier_vide(tmp_path) -> None:
    """« Aucun suivi ici » et « zéro candidature » ne demandent pas le même geste."""
    absent = candidatures(tmp_path / "jamais.json")
    vide = candidatures(_suivi(tmp_path / "vide.json", []))

    assert absent[0].texte != vide[0].texte
    assert all(f.verifie for f in absent + vide), "les deux sont des faits etablis"


# --- il ne juge pas -----------------------------------------------------------

def test_le_scout_ne_conseille_rien(tmp_path) -> None:
    """Le seuil de relance est un jugement, et il vit chez celui qui juge.

    Le recopier ici en ferait la neuvième règle à deux domiciles de ce dépôt.
    Le Scout dit « envoyée depuis 40 jours » ; que ce soit trop long ne lui
    appartient pas.
    """
    chemin = _suivi(tmp_path / "c.json",
                    [{"statut": "envoyee", "date_statut": _il_y_a(40)}])

    texte = " ".join(f.texte for f in candidatures(chemin)).lower()

    assert "40 jours" in texte
    for verbe in ("relance", "il faut", "tu dois", "pense à", "urgent"):
        assert verbe not in texte, f"« {verbe} » est un conseil, pas un fait"


# --- la copie des libelles se compare a son original --------------------------

def test_les_libelles_disent_la_meme_chose_que_le_prototype() -> None:
    """La seule copie qui ne peut pas importer son original.

    `proto/suivi_candidatures.py` doit tourner seul dans a-Shell, sans le
    paquet : `tests/test_proto_suivi.py` le lui impose. La table est donc en
    double, comme la phrase du conflit l'est dans `app.js`, et se garde pareil.
    """
    import importlib.util

    chemin = RACINE / "proto" / "suivi_candidatures.py"
    spec = importlib.util.spec_from_file_location("suivi_libelles", chemin)
    suivi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(suivi)

    assert STATUTS == suivi.STATUTS, (
        "les deux tables de statuts ont diverge ; elles sont lues par la meme "
        "personne sur deux ecrans")


def test_un_statut_inconnu_se_montre_tel_quel(tmp_path) -> None:
    """Le fichier peut venir d'une version plus récente que ce module."""
    chemin = _suivi(tmp_path / "c.json",
                    [{"statut": "negociation", "date_statut": _il_y_a(2)}])

    assert "negociation" in candidatures(chemin)[0].texte


def test_collecter_rend_ce_que_les_sources_savent(tmp_path) -> None:
    """Le témoin : une collecte qui ne ramène rien passerait en silence."""
    chemin = _suivi(tmp_path / "c.json",
                    [{"statut": "entretien", "date_statut": _il_y_a(1)}],
                    cv={"poste": [{"etape": "Titre", "fait": True}]})

    faits = collecter(candidatures_chemin=chemin)

    assert {f.sujet for f in faits} == {"candidatures", "cv"}
    assert any("entretien" in f.texte for f in faits)
    assert any("1 étape faite sur 1" in f.texte for f in faits)


# --- et l'ecran la recoit -----------------------------------------------------

def test_la_route_du_sage_rend_les_faits(tmp_path, monkeypatch) -> None:
    """La route n'avait aucun test, et elle a casse deux fois de suite.

    D'abord `self.app.collecte()` au lieu de `self.collecte()` -- le motif
    d'une autre classe, recopie sans regarder. Puis l'import manquant, parce
    que l'ancre de la retouche visait une parenthese qui n'existe pas. Les deux
    fois, 1484 tests passaient et la page rendait « Quelque chose a casse de
    mon cote ».

    Une route sans test est une route qui marche jusqu'a ce qu'on la regarde.
    """
    from singular.journal import DecisionJournal
    from singular.sage.server import SageApp

    monkeypatch.setenv("HOME", str(tmp_path))
    dossier = tmp_path / ".singular"
    dossier.mkdir()
    _suivi(dossier / "candidatures.json",
           [{"statut": "entretien", "date_statut": _il_y_a(2)}])
    monkeypatch.setattr("singular.collecte.CANDIDATURES", dossier / "candidatures.json")

    app = SageApp(DecisionJournal(dossier / "journal.db"), token="jeton")
    reponse = app.route("GET", "/api/collecte", {}, {})

    assert [c["texte"] for c in reponse["faits"]], "la route doit ramener des faits"
    fait = reponse["faits"][0]
    assert set(fait) == {"sujet", "texte", "source", "date", "verifie"}
    assert "entretien" in fait["texte"]
    assert fait["verifie"] is True


def test_la_route_ne_tombe_pas_sans_fichier_de_suivi(tmp_path, monkeypatch) -> None:
    """C'est le cas normal tant qu'il n'a pas ouvert le suivi ici.

    Une page qui affiche une panne parce qu'un fichier facultatif manque est
    une page qu'on arrete d'ouvrir.
    """
    from singular.journal import DecisionJournal
    from singular.sage.server import SageApp

    monkeypatch.setenv("HOME", str(tmp_path))
    dossier = tmp_path / ".singular"
    dossier.mkdir()
    monkeypatch.setattr("singular.collecte.CANDIDATURES", dossier / "absent.json")

    reponse = SageApp(DecisionJournal(dossier / "journal.db"),
                      token="jeton").route("GET", "/api/collecte", {}, {})

    assert len(reponse["faits"]) == 1
    assert reponse["faits"][0]["verifie"] is True
    assert "aucun suivi" in reponse["faits"][0]["texte"]
