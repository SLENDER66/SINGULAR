"""Deux journaux ne se fusionnent pas, et `A_FAIRE.md` le promet.

Le 10 septembre 2026, sa machine change et il n'a pas accès à l'ancienne. Son
journal — trois mois de décisions — est sur un disque qu'il ne peut pas
atteindre. La tentation est d'en commencer un neuf sur le Mac et de recoller
les deux plus tard.

Ça ne se recolle pas. Chaque entrée signe la précédente : insérer les lignes
d'une base dans l'autre donne bien toutes les entrées, et `verify()` rend faux
— définitivement, puisque le journal ne se réécrit pas. Il faudrait en jeter un.

`A_FAIRE.md` lui dit donc de ne rien écrire sur le Mac tant que la question
n'est pas tranchée. Ce fichier vérifie que la promesse est vraie, plutôt que de
la laisser reposer sur ma parole : si un jour la fusion devenait possible, le
conseil deviendrait faux et ce test le dirait.
"""
from __future__ import annotations

import pathlib
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from singular.journal import DecisionJournal, Tier

RACINE = pathlib.Path(__file__).resolve().parent.parent
DEBUT = datetime(2026, 6, 1, tzinfo=UTC)


def _journal(chemin: pathlib.Path, prefixe: str, combien: int, decalage: int = 0):
    journal = DecisionJournal(chemin)
    for index in range(combien):
        journal.add(title=f"{prefixe} {index}", action="a", predicted="b", probability=0.6,
                    tier=Tier.REVENUS, cost_hours=2, horizon_days=7,
                    now=DEBUT + timedelta(days=decalage + index))
    return journal


def test_recoller_deux_journaux_rompt_la_chaine(tmp_path) -> None:
    ancien = _journal(tmp_path / "pc.db", "PC", 3)
    neuf = _journal(tmp_path / "mac.db", "Mac", 2, decalage=100)
    assert ancien.verify() and neuf.verify(), "les deux doivent être sains séparément"

    fusion = tmp_path / "fusion.db"
    shutil.copy2(tmp_path / "pc.db", fusion)
    source = sqlite3.connect(tmp_path / "mac.db")
    source.row_factory = sqlite3.Row
    cible = sqlite3.connect(fusion)
    colonnes = [colonne[1] for colonne in cible.execute("PRAGMA table_info(journal_entries)")]
    for ligne in source.execute("SELECT * FROM journal_entries"):
        cible.execute(
            f"INSERT INTO journal_entries({','.join(colonnes)}) "
            f"VALUES({','.join('?' * len(colonnes))})",
            [ligne[colonne] for colonne in colonnes])
    cible.commit()
    cible.close()
    source.close()

    recolle = DecisionJournal(fusion)
    assert len(recolle.entries()) == 5, "les lignes sont bien toutes là"
    assert recolle.verify() is False, (
        "la fusion passe la vérification : le conseil d'`A_FAIRE.md` — ne rien "
        "écrire sur le Mac tant que la question n'est pas tranchée — n'a plus "
        "lieu d'être, et il faut le réécrire.")


def test_un_journal_seul_traverse_le_deplacement(tmp_path) -> None:
    """L'autre moitié : déplacer un journal ne casse rien, le fusionner si.

    Sans ce versant, le test ci-dessus prouverait seulement que `verify()` est
    facile à faire échouer.
    """
    ancien = _journal(tmp_path / "pc.db", "PC", 3)
    empreintes = [entree.fingerprint for entree in ancien.entries()]

    ailleurs = tmp_path / "ailleurs" / "journal.db"
    ailleurs.parent.mkdir()
    shutil.copy2(tmp_path / "pc.db", ailleurs)

    deplace = DecisionJournal(ailleurs)
    assert deplace.verify(), "un déplacement seul ne casse pas la chaîne"
    assert [entree.fingerprint for entree in deplace.entries()] == empreintes
    deplace.add(title="Écrite après le déplacement", action="a", predicted="b",
                probability=0.6, tier=Tier.REVENUS, cost_hours=1, horizon_days=7)
    assert deplace.verify(), "et on peut continuer à écrire derrière"


def test_a_faire_porte_bien_ce_conseil() -> None:
    """Le témoin : un test qui prouve une promesse absente ne garde rien."""
    texte = (RACINE / "A_FAIRE.md").read_text(encoding="utf-8")
    assert "Deux journaux ne se fusionnent pas" in texte
    assert "N'enregistre pas de décision sur le Mac" in texte


# --- reprendre, ce n'est pas recoller -----------------------------------------

def test_reprendre_ajoute_a_la_suite_sans_toucher_a_l_ancien(tmp_path) -> None:
    """Le cas réel : la machine change, l'ancienne revient plus tard.

    Les trois mois gardent leur empreinte d'origine — c'est ce qui compte, ils
    sont irremplaçables. Seules les décisions écrites entre-temps sont resignées,
    parce qu'une entrée ne peut pas suivre deux entrées différentes.
    """
    ancien = _journal(tmp_path / "pc.db", "PC", 3)
    tranchee = ancien.entries()[0]
    ancien.resolve(tranchee.entry_id, happened=True, lesson="ils ont répondu")
    avant = {entree.entry_id: entree.fingerprint for entree in ancien.entries()}
    entre_temps = _journal(tmp_path / "mac.db", "Mac", 2, decalage=100)
    origine = {e.entry_id: e.fingerprint for e in entre_temps.entries()}

    reprises = ancien.import_from(tmp_path / "mac.db")

    assert len(reprises) == 2
    assert len(ancien.entries()) == 5
    assert ancien.verify(), "la chaîne tient, contrairement au recollage"
    for entree in ancien.entries():
        if entree.entry_id in avant:
            assert entree.fingerprint == avant[entree.entry_id], (
                "une entrée ancienne a été resignée : les trois mois doivent "
                "garder exactement l'empreinte qu'ils avaient")
    for entree in reprises:
        assert entree.imported_fingerprint == origine[entree.entry_id], (
            "l'empreinte d'origine doit rester écrite à côté : c'est la preuve "
            "que la reprise n'a rien réécrit")
        assert entree.fingerprint != entree.imported_fingerprint


def test_le_verdict_et_la_lecon_traversent_la_reprise(tmp_path) -> None:
    """Ce que la charge signée ne porte pas doit quand même être repris."""
    ancien = _journal(tmp_path / "pc.db", "PC", 1)
    entre_temps = _journal(tmp_path / "mac.db", "Mac", 1, decalage=100)
    cible = entre_temps.entries()[0]
    entre_temps.resolve(cible.entry_id, happened=False, lesson="ils ne répondent pas en août")

    reprise = ancien.import_from(tmp_path / "mac.db")[0]

    assert reprise.status.value == "DID_NOT_HAPPEN"
    assert reprise.lesson == "ils ne répondent pas en août"
    assert reprise.brier_score is not None


def test_l_ordre_des_decisions_est_conserve(tmp_path) -> None:
    ancien = _journal(tmp_path / "pc.db", "PC", 1)
    _journal(tmp_path / "mac.db", "Mac", 4, decalage=100)

    reprises = ancien.import_from(tmp_path / "mac.db")

    assert [entree.title for entree in reprises] == [f"Mac {index}" for index in range(4)]
    chaine = ancien._chain()
    assert [entree.title for entree in chaine] == ["PC 0", "Mac 0", "Mac 1", "Mac 2", "Mac 3"]


def test_reprendre_deux_fois_est_refuse(tmp_path) -> None:
    """Sinon la même décision compte deux fois, et le journal ment sur son coût."""
    from singular.journal import ImportRefused

    ancien = _journal(tmp_path / "pc.db", "PC", 1)
    _journal(tmp_path / "mac.db", "Mac", 2, decalage=100)
    ancien.import_from(tmp_path / "mac.db")

    with pytest.raises(ImportRefused) as refus:
        ancien.import_from(tmp_path / "mac.db")
    assert refus.value.reason == "duplicates"
    assert len(ancien.entries()) == 3, "et rien n'a été écrit au passage"


def test_reprendre_un_journal_falsifie_est_refuse(tmp_path) -> None:
    """Reprendre un journal modifié après coup y blanchirait la modification."""
    from singular.journal import ImportRefused

    ancien = _journal(tmp_path / "pc.db", "PC", 1)
    falsifie = _journal(tmp_path / "mac.db", "Mac", 2, decalage=100)
    cible = falsifie.entries()[0]
    base = sqlite3.connect(tmp_path / "mac.db")
    base.execute("UPDATE journal_entries SET probability=0.99 WHERE entry_id=?",
                 (cible.entry_id,))
    base.commit()
    base.close()

    with pytest.raises(ImportRefused) as refus:
        ancien.import_from(tmp_path / "mac.db")
    assert refus.value.reason == "source_broken"
    assert len(ancien.entries()) == 1, "rien n'a été écrit"


def test_on_n_ajoute_rien_derriere_une_chaine_rompue(tmp_path) -> None:
    from singular.journal import ImportRefused

    rompu = _journal(tmp_path / "pc.db", "PC", 2)
    _journal(tmp_path / "mac.db", "Mac", 1, decalage=100)
    base = sqlite3.connect(tmp_path / "pc.db")
    base.execute("UPDATE journal_entries SET title='réécrit' WHERE entry_id=?",
                 (rompu.entries()[0].entry_id,))
    base.commit()
    base.close()

    with pytest.raises(ImportRefused) as refus:
        rompu.import_from(tmp_path / "mac.db")
    assert refus.value.reason == "self_broken"


def test_le_refus_ne_parle_pas_de_verdict_deja_rendu(tmp_path, capsys) -> None:
    """Le defaut trouve en jouant la commande deux fois de suite.

    `main()` traduit `PermissionError` par « cette decision a deja ete
    tranchee » -- juste pour `resolve`, absurde pour une reprise. Trois refus,
    trois phrases, et `ImportRefused` les distingue.
    """
    from singular.__main__ import main
    from singular.saisie import CONFLIT, REPRISE_REFUSEE

    _journal(tmp_path / "pc.db", "PC", 1)
    _journal(tmp_path / "mac.db", "Mac", 1, decalage=100)
    assert main(["--db", str(tmp_path / "pc.db"), "import", str(tmp_path / "mac.db")]) == 0
    capsys.readouterr()

    assert main(["--db", str(tmp_path / "pc.db"), "import", str(tmp_path / "mac.db")]) == 1
    sortie = capsys.readouterr().out
    assert REPRISE_REFUSEE["duplicates"] in sortie
    assert CONFLIT not in sortie, "le message de `resolve` n'a rien a faire ici"
    assert set(REPRISE_REFUSEE) == {"source_broken", "self_broken", "duplicates"}


def test_une_base_d_avant_migre_et_reste_verifiable(tmp_path) -> None:
    """Son journal a trois mois : il a été écrit par le schéma d'avant.

    `CREATE TABLE IF NOT EXISTS` ne migre rien — `CLAUDE.md` §13 l'interdit
    explicitement. Sans la migration, sa base s'ouvrirait sans la colonne neuve
    et la première lecture échouerait, sur le fichier le moins remplaçable
    qu'il possède.
    """
    from singular.journal import SCHEMA_VERSION

    chemin = tmp_path / "ancienne.db"
    base = sqlite3.connect(chemin)
    base.execute("CREATE TABLE journal_schema (version INTEGER NOT NULL)")
    base.execute("INSERT INTO journal_schema(version) VALUES(2)")
    base.execute("""CREATE TABLE journal_entries (
      entry_id TEXT PRIMARY KEY, title TEXT NOT NULL, action TEXT NOT NULL,
      predicted TEXT NOT NULL, probability REAL NOT NULL, tier TEXT NOT NULL,
      cost_hours REAL NOT NULL, horizon_days INTEGER NOT NULL, created_at TEXT NOT NULL,
      due_at TEXT NOT NULL, status TEXT NOT NULL, resolved_at TEXT, lesson TEXT,
      brier_score REAL, previous_fingerprint TEXT NOT NULL, fingerprint TEXT NOT NULL,
      expected_gain_eur REAL, reversibility TEXT)""")
    base.commit()
    base.close()

    journal = DecisionJournal(chemin)

    relu = sqlite3.connect(chemin)
    assert relu.execute("SELECT version FROM journal_schema").fetchone()[0] == SCHEMA_VERSION
    colonnes = {ligne[1] for ligne in relu.execute("PRAGMA table_info(journal_entries)")}
    relu.close()
    assert "imported_fingerprint" in colonnes

    entree = journal.add(title="Après migration", action="a", predicted="b", probability=0.6,
                         tier=Tier.REVENUS, cost_hours=1, horizon_days=7)
    assert entree.imported_fingerprint is None, "une décision écrite ici ne vient d'ailleurs"
    assert journal.verify()


def test_deux_reprises_simultanees_refusent_dans_sa_langue(tmp_path, monkeypatch) -> None:
    """Le controle des doublons se fait hors transaction : les deux le passent.

    La cle primaire tient -- aucune entree en double, chaine intacte -- mais le
    perdant recevait `UNIQUE constraint failed: journal_entries.entry_id`. C'est
    la sixieme porte par ou un message de bibliotheque arrivait sur son ecran, et
    je venais de l'ouvrir moi-meme.

    La fenetre est elargie a la main : sans ca les deux fils se suivent en file
    indienne et le test ne peut pas echouer.
    """
    import threading
    import time

    from singular.journal import ImportRefused

    cible = _journal(tmp_path / "cible.db", "ici", 1)
    _journal(tmp_path / "source.db", "la", 3, decalage=10)
    assert cible is not None

    # `monkeypatch` et pas une restauration a la main : `DecisionJournal._head`
    # est une `staticmethod`, et la relire depuis la classe rend la fonction nue.
    # La reposer telle quelle la transforme en methode d'instance, donc `self`
    # part en premier argument -- et tout le reste de la suite casse, dans le
    # meme processus, longtemps apres ce test. Mesure : 140 echecs.
    vrai_head = DecisionJournal.__dict__["_head"].__func__
    retarde = threading.Event()

    def head_lent(conn):
        if not retarde.is_set():
            retarde.set()
            time.sleep(0.4)
        return vrai_head(conn)

    resultats: list[object] = []
    barriere = threading.Barrier(2)

    def reprendre() -> None:
        journal = DecisionJournal(tmp_path / "cible.db")
        barriere.wait()
        try:
            journal.import_from(tmp_path / "source.db")
            resultats.append("accepte")
        except Exception as refus:  # noqa: BLE001 - c'est le sujet du test
            resultats.append(refus)

    monkeypatch.setattr(DecisionJournal, "_head", staticmethod(head_lent))
    fils = [threading.Thread(target=reprendre) for _ in range(2)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join(timeout=10)
    monkeypatch.undo()
    assert isinstance(DecisionJournal.__dict__["_head"], staticmethod), (
        "`_head` doit redevenir une staticmethod : reposee en fonction nue, elle "
        "recoit `self` en premier argument et casse tout le reste de la suite")

    assert resultats.count("accepte") == 1, f"une seule reprise doit passer : {resultats}"
    refus = next(r for r in resultats if r != "accepte")
    assert isinstance(refus, ImportRefused), (
        f"le perdant recoit {type(refus).__name__} : « {refus} ». Une erreur SQLite "
        "brute arrive telle quelle sur son ecran.")
    assert refus.reason == "duplicates"

    final = DecisionJournal(tmp_path / "cible.db")
    identifiants = [entree.entry_id for entree in final.entries()]
    assert len(identifiants) == len(set(identifiants)), "aucune entree en double"
    assert len(identifiants) == 4
    assert final.verify(), "et la chaine tient"
