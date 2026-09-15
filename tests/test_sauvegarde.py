"""Une sauvegarde qu'on n'a pas restaurée n'est pas une sauvegarde.

Le journal est le seul actif irremplaçable du dépôt : le code se reprend d'un
`git clone`, trois mois de prédictions chaînées non. Et jusqu'au 15 septembre
2026 il n'existait aucun chemin de retour -- `export` écrit un CSV que `import`
refuse, et `cmd_import` le dit lui-même. Le registre de réalité nommait déjà ce
manque comme la seule dette du socle durable « qui puisse coûter des mois de
journal ».

Ce fichier garde la propriété que la directive exige mot pour mot : « un backup
n'est considéré fiable qu'après restauration vérifiée ». Il ne se contente donc
pas de vérifier qu'un fichier a été écrit -- il **rejoue la restauration par le
vrai chemin**, `import`, et compare ce qui en ressort.

Les deux moitiés du contrat, séparées exprès :

* la **fidélité** -- la copie rend exactement ce que rend la source -- commande
  le refus ;
* l'**état de la chaîne** -- le journal va bien, ou pas -- est rapporté et ne
  commande rien. Refuser de copier un journal abîmé détruirait la seule pièce à
  conviction en même temps que la donnée, et c'est le test le plus important
  d'ici.
"""
from __future__ import annotations

import hashlib
import sqlite3

import pytest

from singular.journal import DecisionJournal, Tier
from singular.sauvegarde import SauvegardeRefusee, sauvegarder


def _journal(chemin, combien: int = 3) -> DecisionJournal:
    journal = DecisionJournal(chemin)
    for rang in range(combien):
        journal.add(title=f"Décision {rang}", action=f"action {rang}",
                    predicted=f"prédit {rang}", probability=0.5 + rang / 100,
                    tier=Tier.REVENUS, cost_hours=1 + rang, horizon_days=7)
    return journal


def _empreinte_du_fichier(chemin) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def _restes(dossier) -> list[str]:
    """Tout fichier laissé dans le dossier de sauvegarde, y compris les cachés."""
    return sorted(p.name for p in dossier.iterdir()) if dossier.exists() else []


# --- la propriété centrale ---------------------------------------------------

def test_la_sauvegarde_se_restaure_vraiment_par_le_chemin_reel(tmp_path) -> None:
    """Le seul test qui prouve quelque chose : on la reprend, et tout est là.

    Rejouer la restauration par `import` plutôt que par une comparaison interne
    est délibéré. C'est le geste que le fondateur ferait un jour de panne, et
    c'est donc le seul qui démontre que la sauvegarde sert à quelque chose.
    """
    source = _journal(tmp_path / "journal.db", 3)
    attendu = [entree.title for entree in source.entries()]

    faite = sauvegarder(tmp_path / "journal.db", dossier=tmp_path / "sauvegardes")
    assert faite.decisions == 3
    assert faite.chaine_intacte is True

    neuf = DecisionJournal(tmp_path / "apres-la-panne.db")
    reprises = neuf.import_from(faite.chemin)

    assert [entree.title for entree in reprises] == attendu
    assert neuf.verify() is True, "le journal restauré ne se vérifie pas"
    assert len(neuf.entries()) == 3


def test_la_copie_est_un_journal_lisible_tel_quel(tmp_path) -> None:
    """Sans passer par `import` non plus : le fichier est une base valide."""
    _journal(tmp_path / "journal.db", 2)
    faite = sauvegarder(tmp_path / "journal.db", dossier=tmp_path / "sauvegardes")

    copie = DecisionJournal(faite.chemin, lecture_seule=True)
    assert copie.verify() is True
    assert len(copie.entries()) == 2


def test_sauvegarder_ne_touche_pas_l_original(tmp_path) -> None:
    """La leçon déjà payée par `import_from`, et payée sur un vrai journal.

    Ouvrir une base la migrait : trois `ALTER TABLE` partaient sur le seul
    exemplaire de trois mois de décisions, avant le moindre contrôle. Une
    sauvegarde qui modifie ce qu'elle sauvegarde est un défaut même quand elle
    n'abîme rien -- et ici l'original peut être sur une clé protégée en écriture.
    """
    source = tmp_path / "journal.db"
    _journal(source, 2)
    avant = _empreinte_du_fichier(source)

    sauvegarder(source, dossier=tmp_path / "sauvegardes")

    assert _empreinte_du_fichier(source) == avant, (
        "la sauvegarde a réécrit le journal qu'elle copiait")


# --- la distinction qui compte : fidèle ≠ en bonne santé ---------------------

def test_un_journal_a_la_chaine_rompue_est_quand_meme_sauvegarde(tmp_path) -> None:
    """Le test le plus important de ce fichier, et le moins intuitif.

    Le réflexe fail-closed voudrait refuser de sauvegarder un journal qui ne se
    vérifie plus. Ce serait ici le pire comportement possible : le seul
    exemplaire d'un journal abîmé est exactement ce qu'il faut copier **avant**
    d'y toucher. Un garde qui supprime la copie au motif que l'original est
    abîmé détruit la preuve en même temps que la donnée.

    La copie est donc faite, et `chaine_intacte` dit la vérité à côté.
    """
    source = tmp_path / "journal.db"
    journal = _journal(source, 2)
    vise = journal.entries()[0].entry_id
    with sqlite3.connect(source) as conn:
        conn.execute("UPDATE journal_entries SET title='réécrit' WHERE entry_id=?", (vise,))
    assert DecisionJournal(source, lecture_seule=True).verify() is False

    faite = sauvegarder(source, dossier=tmp_path / "sauvegardes")

    assert faite.chemin.exists(), (
        "le journal abîmé n'a pas été sauvegardé : la pièce à conviction est perdue")
    assert faite.chaine_intacte is False, (
        "la sauvegarde annonce une chaîne intacte alors que l'original est rompu")
    assert DecisionJournal(faite.chemin, lecture_seule=True).verify() is False, (
        "la copie d'un journal rompu devrait être rompue elle aussi : elle a été réparée "
        "en silence, donc elle ne photographie plus ce qui s'est passé")


# --- les refus, et ce qu'ils laissent derrière eux --------------------------

def test_sans_journal_il_n_y_a_rien_a_sauvegarder(tmp_path) -> None:
    with pytest.raises(SauvegardeRefusee) as refus:
        sauvegarder(tmp_path / "rien.db", dossier=tmp_path / "sauvegardes")
    assert refus.value.reason == "source_absente"


def test_une_copie_infidele_est_refusee_et_ne_reste_pas(tmp_path, monkeypatch) -> None:
    """Le cas qui justifie tout le module : la copie ne rend pas la source.

    Il ne se produit pas tout seul -- c'est bien pourquoi il faut le fabriquer.
    Une copie silencieusement incomplète est le pire des défauts possibles ici :
    elle ne se voit que le jour où l'on en a besoin, c'est-à-dire trop tard.
    """
    import singular.sauvegarde as module

    source = tmp_path / "journal.db"
    _journal(source, 2)
    dossier = tmp_path / "sauvegardes"

    vraie = module._photographie
    appels = {"n": 0}

    def truquee(journal):
        appels["n"] += 1
        lignes, chaine = vraie(journal)
        if appels["n"] > 1:  # la relecture de la copie
            return lignes[:-1], chaine  # une décision manque
        return lignes, chaine

    monkeypatch.setattr(module, "_photographie", truquee)

    with pytest.raises(SauvegardeRefusee) as refus:
        sauvegarder(source, dossier=dossier)

    assert refus.value.reason == "copie_infidele"
    assert _restes(dossier) == [], (
        "une copie non vérifiée est restée sur le disque : elle sera prise pour "
        "une sauvegarde le jour où l'on en aura besoin")


def test_une_copie_illisible_est_refusee_et_ne_reste_pas(tmp_path, monkeypatch) -> None:
    """Le disque ment, la copie n'est pas une base : rien n'est gardé, rien n'est promis."""
    import singular.sauvegarde as module

    source = tmp_path / "journal.db"
    _journal(source, 2)
    dossier = tmp_path / "sauvegardes"

    def sabotage(_source, vers):
        # Ce que le disque rend un mauvais jour : un fichier qui porte le bon nom
        # et qui n'est pas une base.
        vers.write_bytes(b"ceci n'est pas une base")

    monkeypatch.setattr(module, "_copier", sabotage)

    with pytest.raises(SauvegardeRefusee) as refus:
        sauvegarder(source, dossier=dossier)

    assert refus.value.reason == "copie_illisible"
    assert _restes(dossier) == [], "une copie illisible est restée sur le disque"


# --- ce qui doit marcher sans surprise --------------------------------------

def test_un_journal_vide_se_sauvegarde(tmp_path) -> None:
    """Le premier matin aussi. Un cas vide qui lève est un cas vide oublié."""
    DecisionJournal(tmp_path / "journal.db")
    faite = sauvegarder(tmp_path / "journal.db", dossier=tmp_path / "sauvegardes")
    assert faite.decisions == 0
    assert faite.chemin.exists()


def test_deux_sauvegardes_de_suite_ne_se_marchent_pas_dessus(tmp_path) -> None:
    """Relancer la commande ne doit jamais abîmer la sauvegarde déjà là."""
    from datetime import datetime

    source = tmp_path / "journal.db"
    _journal(source, 2)
    dossier = tmp_path / "sauvegardes"
    instant = datetime(2026, 9, 15, 6, 0, 0)

    premiere = sauvegarder(source, dossier=dossier, maintenant=instant)
    seconde = sauvegarder(source, dossier=dossier, maintenant=instant)

    assert premiere.chemin == seconde.chemin
    assert DecisionJournal(seconde.chemin, lecture_seule=True).verify() is True
    assert _restes(dossier) == [premiere.chemin.name], (
        "un fichier partiel traîne à côté de la sauvegarde")


def test_un_chemin_mal_tape_ne_ressemble_pas_a_une_sauvegarde_reussie(tmp_path, capsys) -> None:
    """Le défaut trouvé en lançant la commande pour de vrai, pas en la testant.

    Le CLI ouvre le journal avant de le sauvegarder, donc il le **crée** :
    `source.exists()` ne peut plus distinguer « pas encore de journal » d'un
    chemin mal tapé. La commande annonçait alors « 0 décision sauvegardée » et
    rendait 0 -- une bonne nouvelle apparente, sur un journal qui n'était pas le
    sien.

    C'est exactement le piège que `due` a déjà payé ici, et le recréer dans la
    commande censée protéger le journal aurait été le pire endroit. Les neuf
    tests précédents étaient verts pendant que ce défaut existait : ils
    appelaient l'API, jamais l'écran.
    """
    from singular.__main__ import main

    ailleurs = tmp_path / "pas-le-bon-journal.db"
    capsys.readouterr()

    code = main(["--db", str(ailleurs), "sauvegarde", "--vers", str(tmp_path / "s")])
    sortie = capsys.readouterr().out

    assert code == 0
    assert str(ailleurs) in sortie, (
        "la commande ne dit pas où elle a regardé : un chemin mal tapé ressemble "
        "à une bonne nouvelle")
    assert "sauvegardée" not in sortie, (
        "elle annonce une sauvegarde alors qu'il n'y a rien à sauvegarder")
    assert not (tmp_path / "s").exists(), (
        "un dossier de sauvegarde a été créé pour un journal vide")
