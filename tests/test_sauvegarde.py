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
import pathlib
import sqlite3

import pytest

from singular.journal import DecisionJournal, Tier
from singular.sauvegarde import SauvegardeRefusee, sauvegarder

#: Le dépôt lui-même : `A_FAIRE.md` est la source que la liste blanche doit suivre.
RACINE_DEPOT = pathlib.Path(__file__).resolve().parent.parent


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
    reprises = neuf.import_from(faite.journal)

    assert [entree.title for entree in reprises] == attendu
    assert neuf.verify() is True, "le journal restauré ne se vérifie pas"
    assert len(neuf.entries()) == 3


def test_la_copie_est_un_journal_lisible_tel_quel(tmp_path) -> None:
    """Sans passer par `import` non plus : le fichier est une base valide."""
    _journal(tmp_path / "journal.db", 2)
    faite = sauvegarder(tmp_path / "journal.db", dossier=tmp_path / "sauvegardes")

    copie = DecisionJournal(faite.journal, lecture_seule=True)
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

    assert faite.journal.exists(), (
        "le journal abîmé n'a pas été sauvegardé : la pièce à conviction est perdue")
    assert faite.chaine_intacte is False, (
        "la sauvegarde annonce une chaîne intacte alors que l'original est rompu")
    assert DecisionJournal(faite.journal, lecture_seule=True).verify() is False, (
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
    assert faite.journal.exists()


def test_deux_sauvegardes_de_suite_ne_se_marchent_pas_dessus(tmp_path) -> None:
    """Relancer la commande ne doit jamais abîmer la sauvegarde déjà là."""
    from datetime import datetime

    source = tmp_path / "journal.db"
    _journal(source, 2)
    dossier = tmp_path / "sauvegardes"
    instant = datetime(2026, 9, 15, 6, 0, 0)

    premiere = sauvegarder(source, dossier=dossier, maintenant=instant)
    seconde = sauvegarder(source, dossier=dossier, maintenant=instant)

    assert premiere.dossier == seconde.dossier
    assert DecisionJournal(seconde.journal, lecture_seule=True).verify() is True
    assert _restes(dossier) == [premiere.dossier.name], (
        "un dossier partiel traîne à côté de la sauvegarde")


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


# --- ce qu'une sauvegarde emporte, et ce qu'elle n'emporte jamais ------------

def test_le_second_actif_irremplacable_est_sauvegarde(tmp_path) -> None:
    """Le journal n'était que le premier trou.

    `candidatures.json` porte la même étiquette « irremplaçable » dans
    `A_FAIRE.md` et n'avait, lui non plus, aucun chemin de retour. Un actif
    irremplaçable sans copie vérifiée est exactement ce que l'invariant de
    continuité interdit : aucun actif critique ne doit avoir un seul chemin
    d'accès non récupérable.
    """
    source = tmp_path / "journal.db"
    _journal(source, 1)
    candidatures = tmp_path / "candidatures.json"
    candidatures.write_text('{"envoyees": [{"entreprise": "Une boîte"}]}', encoding="utf-8")

    faite = sauvegarder(source, dossier=tmp_path / "sauvegardes")

    assert "candidatures.json" in faite.copies
    restaure = faite.dossier / "candidatures.json"
    assert restaure.read_bytes() == candidatures.read_bytes(), (
        "le suivi de candidatures n'est pas revenu octet pour octet")


def test_un_actif_absent_n_est_pas_une_erreur(tmp_path) -> None:
    """`candidatures.json` n'existe que si le prototype a servi."""
    _journal(tmp_path / "journal.db", 1)
    faite = sauvegarder(tmp_path / "journal.db", dossier=tmp_path / "sauvegardes")
    assert "candidatures.json" in faite.absents
    assert "journal.db" in faite.copies


def test_le_jeton_du_sage_ne_part_jamais_dans_une_sauvegarde(tmp_path) -> None:
    """Une sauvegarde finit sur une clé USB. Un secret n'y a rien à faire.

    `A_FAIRE.md` le dit déjà — « ne le copie pas » — mais le dire ne l'empêche
    pas. Le contenu est vérifié autant que le nom : un secret recopié dans un
    autre fichier serait exfiltré tout aussi sûrement, et c'est le genre de
    défaut qu'on ne découvre jamais par hasard.
    """
    source = tmp_path / "journal.db"
    _journal(source, 1)
    secret = "jeton-tres-secret-a-ne-jamais-copier"
    (tmp_path / "sage_token").write_text(secret, encoding="utf-8")

    faite = sauvegarder(source, dossier=tmp_path / "sauvegardes")

    assert "sage_token" not in faite.copies
    assert not (faite.dossier / "sage_token").exists(), "le jeton a été copié"

    for fichier in faite.dossier.rglob("*"):
        if fichier.is_file():
            assert secret.encode() not in fichier.read_bytes(), (
                f"le contenu du jeton se retrouve dans {fichier.name}")


def test_la_liste_blanche_suit_ce_que_le_depot_declare_irremplacable() -> None:
    """Le prix de la liste blanche, payé par un test au lieu d'une panne.

    Sauvegarder « tout sauf » ferait entrer tout seul un fichier de secret qui
    n'existe pas encore. La liste blanche l'empêche, mais elle peut oublier un
    actif -- et un oubli ici ne se découvre que le jour de la perte.

    `A_FAIRE.md` tient déjà le tableau des fichiers de `~/.singular/` avec, pour
    chacun, ce qu'il en coûte de le perdre. Ce test confronte le code à ce
    tableau dans les deux sens : tout ce qui est marqué « irremplaçable » doit
    être sauvegardé, et ce qui est marqué « ne le copie pas » ne doit jamais
    l'être.
    """
    import re

    from singular.sauvegarde import ACTIFS, JAMAIS_SAUVEGARDE

    tableau = (RACINE_DEPOT / "A_FAIRE.md").read_text(encoding="utf-8")
    lignes = re.findall(r"^\|\s*`([^`]+)`\s*\|([^|]*)\|([^|]*)\|\s*$", tableau, re.MULTILINE)
    assert lignes, "le tableau des fichiers a disparu d'A_FAIRE.md : ce test ne prouve plus rien"

    irremplacables = {nom for nom, _, perte in lignes if "irremplaçable" in perte}
    interdits = {nom for nom, _, perte in lignes if "ne le copie pas" in perte}
    assert irremplacables and interdits, "le tableau ne marque plus ni l'un ni l'autre"

    oublies = sorted(irremplacables - set(ACTIFS))
    assert not oublies, (
        f"A_FAIRE.md déclare ces fichiers irremplaçables et rien ne les sauvegarde : "
        f"{oublies}. Ajoute-les à ACTIFS, ou corrige le tableau s'il a vieilli.")

    emportes = sorted(interdits & set(ACTIFS))
    assert not emportes, (
        f"A_FAIRE.md dit de ne pas copier ces fichiers, et ils sont dans ACTIFS : {emportes}")

    assert set(JAMAIS_SAUVEGARDE) >= interdits, (
        f"ces fichiers sont interdits de copie sans être dans JAMAIS_SAUVEGARDE : "
        f"{sorted(interdits - set(JAMAIS_SAUVEGARDE))}")


# --- la sauvegarde que la machine lance seule --------------------------------

def test_le_premier_matin_avec_des_decisions_declenche_la_sauvegarde(tmp_path, capsys) -> None:
    """Le registre déclarait la même prochaine étape pour deux capacités.

    « Que la sauvegarde parte seule. » Le geste existait, l'automatisme non — et
    c'est l'automatisme qui protège les jours où l'on oublie, c'est-à-dire ceux
    qui comptent.
    """
    from singular.__main__ import main

    source = tmp_path / "journal.db"
    _journal(source, 2)
    capsys.readouterr()

    assert main(["--db", str(source), "due"]) == 0
    sortie = capsys.readouterr().out

    sauvegardes = source.parent / "sauvegardes"
    faites = [p for p in sauvegardes.iterdir() if p.is_dir()]
    assert len(faites) == 1, "le premier matin n'a pas déclenché de sauvegarde"
    assert "Sauvegarde de la semaine" in sortie
    assert DecisionJournal(faites[0] / "journal.db", lecture_seule=True).verify() is True


def test_elle_ne_repart_pas_le_lendemain(tmp_path) -> None:
    """Hebdomadaire, pas quotidienne. `due` se tape tous les matins."""
    from singular.__main__ import main

    source = tmp_path / "journal.db"
    _journal(source, 1)

    main(["--db", str(source), "due"])
    main(["--db", str(source), "due"])

    faites = [p for p in (source.parent / "sauvegardes").iterdir() if p.is_dir()]
    assert len(faites) == 1, "une sauvegarde par jour : le seuil ne tient plus"


def test_un_journal_vide_ne_declenche_rien(tmp_path) -> None:
    """Rien à perdre, et une sauvegarde vide masquerait un chemin mal tapé."""
    from singular.__main__ import main
    from singular.sauvegarde import sauvegarde_attendue

    source = tmp_path / "journal.db"
    DecisionJournal(source)

    assert sauvegarde_attendue(source) is False
    main(["--db", str(source), "due"])
    assert not (source.parent / "sauvegardes").exists()


def test_l_echeance_se_lit_sur_le_nom_et_pas_sur_le_disque(tmp_path) -> None:
    """Copier ses sauvegardes sur une machine neuve ne doit pas les rajeunir.

    L'horodatage du système repart à aujourd'hui après une copie ; l'outil
    croirait alors venir de sauvegarder, et ne le referait pas. La date vit donc
    dans le nom du dossier, qui voyage avec lui.
    """
    from datetime import datetime

    from singular.sauvegarde import derniere_sauvegarde, sauvegarde_attendue

    source = tmp_path / "journal.db"
    _journal(source, 1)
    dossier = source.parent / "sauvegardes"
    vieille = dossier / "2026-01-01-000000"
    vieille.mkdir(parents=True)

    assert derniere_sauvegarde(dossier) == datetime(2026, 1, 1, 0, 0, 0)
    assert sauvegarde_attendue(source, maintenant=datetime(2026, 1, 2)) is False
    assert sauvegarde_attendue(source, maintenant=datetime(2026, 1, 9)) is True


def test_un_echec_de_sauvegarde_ne_prive_pas_du_rapport_du_matin(tmp_path, capsys, monkeypatch) -> None:
    """Deux règles qui tirent en sens contraire, et les deux tiennent.

    Un matin où la sauvegarde échoue est un matin où il faut quand même voir ses
    verdicts : l'échec ne remonte pas. Mais une sauvegarde qu'on croit faite et
    qui ne l'est pas est pire que pas de sauvegarde du tout : il ne se tait pas
    non plus.
    """
    import singular.__main__ as cli
    from singular.__main__ import main

    source = tmp_path / "journal.db"
    _journal(source, 2)

    def echoue(*_args, **_reste):
        raise OSError("disque plein")

    monkeypatch.setattr(cli, "sauvegarder", echoue)
    capsys.readouterr()

    code = main(["--db", str(source), "due"])
    sortie = capsys.readouterr().out

    assert code == 0, "un échec de sauvegarde a fait échouer le rapport du matin"
    assert "Rien à trancher" in sortie or "attend" in sortie, (
        "le rapport du matin a disparu à cause de la sauvegarde")
    assert "échoué" in sortie, "l'échec est silencieux : on croira le journal copié"
    assert "disque plein" in sortie
