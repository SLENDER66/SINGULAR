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
from datetime import datetime

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

    def truquee(journal):
        lignes, chaine = vraie(journal)
        # C'est **la copie** qu'on ampute, et le test le dit par le chemin plutot
        # que par le rang de l'appel. Il comptait « tout appel apres le premier »,
        # ce qui etait un raccourci pour « la copie » tant qu'il n'y avait que
        # deux lectures. La verification distingue maintenant une copie infidele
        # d'un journal qui a bouge pendant la copie, donc elle relit la source une
        # troisieme fois -- et le raccourci amputait cette relecture-la aussi,
        # faisant passer ce cas pour une ecriture concurrente.
        if ".partielle" in str(journal.path):
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


# --- ce que le remplacement ne doit jamais coûter -----------------------------

def _trois_decisions(tmp_path) -> pathlib.Path:
    _journal(tmp_path / "journal.db", 3)
    return tmp_path / "journal.db"


def test_un_renommage_final_qui_echoue_ne_detruit_pas_la_sauvegarde_precedente(
        tmp_path, monkeypatch) -> None:
    """Le vrai risque n'est pas de perdre une histoire, c'est d'en écraser une.

    Ce module cite cette phrase d'`A_FAIRE.md` pour justifier d'écrire *à côté*
    du journal et jamais par-dessus. Le remplacement final la contredisait : il
    supprimait l'ancienne sauvegarde du même horodatage, puis renommait la
    nouvelle. Si ce renommage échoue -- disque plein, permission, système de
    fichiers qui refuse -- le nettoyage efface la partielle alors que l'ancienne
    vient d'être détruite, et le dossier reste **vide**.

    Mesuré avant la correction : une sauvegarde vérifiée disparaissait pour
    laisser la place à une sauvegarde qui n'arrive jamais. L'ancienne est
    maintenant écartée sous un nom caché, et remise à sa place si quoi que ce
    soit échoue.
    """
    from singular import sauvegarde as module

    source = _trois_decisions(tmp_path)
    dossier = tmp_path / "sauvegardes"
    quand = datetime(2026, 9, 15, 12, 0, 0)
    premiere = sauvegarder(source, dossier=dossier, maintenant=quand)
    assert premiere.dossier.exists()
    contenu = sorted(p.name for p in premiere.dossier.iterdir())

    vrai_replace = module.os.replace

    def renommage_final_casse(src, dst):
        if ".partielle" in str(src):
            raise OSError("le renommage final échoue")
        return vrai_replace(src, dst)

    monkeypatch.setattr(module.os, "replace", renommage_final_casse)
    with pytest.raises(OSError):
        sauvegarder(source, dossier=dossier, maintenant=quand)
    monkeypatch.undo()

    assert premiere.dossier.exists(), "la sauvegarde vérifiée a été effacée"
    assert sorted(p.name for p in premiere.dossier.iterdir()) == contenu
    assert sorted(p.name for p in dossier.iterdir()) == [premiere.dossier.name], (
        "rien d'autre ne doit traîner : ni partielle, ni dossier écarté")


def test_un_remplacement_reussi_ne_laisse_pas_l_ancienne_derriere(tmp_path) -> None:
    """Sinon chaque sauvegarde du même horodatage doublerait la place occupée."""
    source = _trois_decisions(tmp_path)
    dossier = tmp_path / "sauvegardes"
    quand = datetime(2026, 9, 15, 12, 0, 0)

    sauvegarder(source, dossier=dossier, maintenant=quand)
    seconde = sauvegarder(source, dossier=dossier, maintenant=quand)

    assert seconde.dossier.exists()
    assert sorted(p.name for p in dossier.iterdir()) == [seconde.dossier.name], (
        "le dossier écarté doit être retiré une fois le remplacement fait")


def test_une_decision_ecrite_pendant_la_copie_ne_dit_pas_que_la_copie_est_infidele(
        tmp_path, monkeypatch) -> None:
    """Deux causes, une seule inquiétante, et elles disaient la même phrase.

    La photographie de la source est prise avant la copie. Si une décision est
    écrite entre les deux — le serveur du Sage tourne en tâche de fond — la copie
    contient une ligne de plus que la photographie, et la comparaison échoue.

    Le comportement est correct : rien n'est gardé, la sauvegarde précédente est
    intacte, une relance passe. C'est la phrase qui était fausse. « La copie ne
    rend pas la même chose que l'original » sur le seul fichier irremplaçable du
    dépôt fait craindre une corruption, pour un événement bénin. La copie est
    fidèle — à un instant plus tard.
    """
    from singular import sauvegarde as module

    source = _trois_decisions(tmp_path)
    dossier = tmp_path / "sauvegardes"
    avant = sauvegarder(source, dossier=dossier, maintenant=datetime(2026, 9, 15, 10, 0, 0))

    vrai_copier = module._copier

    def copier_pendant_qu_on_ecrit(origine, vers):
        _journal(source, 1)
        return vrai_copier(origine, vers)

    monkeypatch.setattr(module, "_copier", copier_pendant_qu_on_ecrit)
    with pytest.raises(SauvegardeRefusee) as refus:
        sauvegarder(source, dossier=dossier, maintenant=datetime(2026, 9, 15, 11, 0, 0))
    monkeypatch.undo()

    assert refus.value.reason == "journal_modifie", (
        "une écriture concurrente n'est pas une copie infidèle")
    assert avant.dossier.exists(), "et la sauvegarde précédente n'a rien coûté"
    assert sauvegarder(source, dossier=dossier,
                       maintenant=datetime(2026, 9, 15, 12, 0, 0)).decisions == 4, (
        "une relance doit passer : c'est toute la différence avec une vraie infidélité")


def test_une_copie_vraiment_infidele_le_dit_encore(tmp_path, monkeypatch) -> None:
    """Sans ça, le test ci-dessus aurait pu vider le refus de son sens.

    La source ne bouge pas ; c'est la copie qui est fausse. Le refus doit rester
    `copie_infidele`, celui qui dit qu'il ne faut pas se fier au fichier écrit.
    """
    from singular import sauvegarde as module

    source = _trois_decisions(tmp_path)
    vrai_copier = module._copier

    def copier_une_source_amputee(origine, vers):
        vrai_copier(origine, vers)
        base = sqlite3.connect(vers)
        base.execute("DELETE FROM journal_entries")
        base.commit()
        base.close()

    monkeypatch.setattr(module, "_copier", copier_une_source_amputee)
    with pytest.raises(SauvegardeRefusee) as refus:
        sauvegarder(source, dossier=tmp_path / "sauvegardes")

    assert refus.value.reason == "copie_infidele"


def test_chaque_refus_de_sauvegarde_a_une_phrase_pour_l_ecran() -> None:
    """La ligne de commande lit `REFUS_DE_SAUVEGARDE[raison]` : une raison sans
    phrase y lèverait un `KeyError` devant l'utilisateur, au pire moment.

    Les raisons sont lues dans le code plutôt qu'écrites ici : une quatrième
    ajoutée demain sans sa phrase fait rougir la suite.
    """
    import ast

    from singular.sauvegarde import REFUS_DE_SAUVEGARDE

    arbre = ast.parse((RACINE_DEPOT / "singular/sauvegarde.py").read_text(encoding="utf-8"))
    levees = {noeud.args[0].value for noeud in ast.walk(arbre)
              if isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name)
              and noeud.func.id == "SauvegardeRefusee" and noeud.args
              and isinstance(noeud.args[0], ast.Constant)}

    assert levees, "plus aucun refus levé : ce test ne prouve plus rien"
    sans_phrase = sorted(levees - set(REFUS_DE_SAUVEGARDE))
    assert not sans_phrase, (
        f"ces raisons sont levées sans phrase pour l'écran : {sans_phrase}")


def test_un_actif_fichier_copie_de_travers_est_refuse(tmp_path, monkeypatch) -> None:
    """Le second actif irremplaçable a sa propre vérification, et rien ne l'essayait.

    `journal.db` passe par l'API de sauvegarde de SQLite et se relit comme un
    journal ; `candidatures.json` est un fichier ordinaire, confronté à son
    original par empreinte. Le cas nominal était couvert — le fichier revient
    octet pour octet — mais pas le refus. Neutralisé, une copie tronquée ou
    absente était annoncée comme une sauvegarde vérifiée.
    """
    from singular import sauvegarde as module

    source = _trois_decisions(tmp_path)
    candidatures = tmp_path / "candidatures.json"
    candidatures.write_text('{"envoyees": [{"entreprise": "Une boîte"}]}', encoding="utf-8")

    def copier_de_travers(origine, vers):
        vers.write_text("ce n'est pas ce qu'il y avait dedans", encoding="utf-8")

    monkeypatch.setattr(module, "_copier_fichier", copier_de_travers)
    with pytest.raises(SauvegardeRefusee) as refus:
        sauvegarder(source, dossier=tmp_path / "sauvegardes")

    assert refus.value.reason == "copie_infidele"
    assert _restes(tmp_path / "sauvegardes") == [], (
        "une copie non vérifiée est restée : elle serait prise pour une sauvegarde")


def test_un_actif_fichier_non_copie_du_tout_est_refuse(tmp_path, monkeypatch) -> None:
    """L'autre moitié du même garde : la cible n'existe même pas."""
    from singular import sauvegarde as module

    source = _trois_decisions(tmp_path)
    (tmp_path / "candidatures.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(module, "_copier_fichier", lambda origine, vers: None)
    with pytest.raises(SauvegardeRefusee) as refus:
        sauvegarder(source, dossier=tmp_path / "sauvegardes")

    assert refus.value.reason == "copie_infidele"


def test_la_sauvegarde_annonce_la_vraie_tete_de_chaine(tmp_path) -> None:
    """Le champ existait, et il valait la chaîne vide à tous les coups.

    `_empreinte_de_tete` la cherchait dans `export_rows()`, qui ne porte que les
    colonnes d'affichage — ni `fingerprint`, ni `previous_fingerprint`. Le
    `.get(..., "")` rendait donc `""`, toujours. Personne ne lisait ce champ,
    donc rien ne rougissait : une sauvegarde annonçait une empreinte qu'elle
    n'avait pas.

    C'est l'empreinte qui permet de dire « cette copie est bien celle de ce
    journal-là ». Vide, elle ne dit rien.
    """
    source = _trois_decisions(tmp_path)
    journal = DecisionJournal(source, lecture_seule=True)

    faite = sauvegarder(source, dossier=tmp_path / "sauvegardes")

    assert faite.empreinte, "une sauvegarde sans empreinte ne prouve rien"
    assert faite.empreinte == journal.head_fingerprint()
    assert faite.empreinte == DecisionJournal(faite.journal,
                                              lecture_seule=True).head_fingerprint(), (
        "et la copie doit porter la même tête que la source")


def test_une_copie_dont_la_chaine_est_cassee_est_refusee(tmp_path, monkeypatch) -> None:
    """La moitié « chaîne » du garde de fidélité, que les lignes ne peuvent pas voir.

    Les deux moitiés ne regardent pas la même chose, et c'est mesurable :
    `export_rows()` ne porte aucune empreinte, donc une copie dont les empreintes
    ont été réécrites rend **exactement les mêmes lignes** que la source. Seul le
    verdict de chaîne la distingue.

    Sans cette moitié, une copie dont la chaîne ne se vérifie plus serait
    annoncée comme une sauvegarde fidèle — et c'est précisément la propriété pour
    laquelle ce journal existe.
    """
    from singular import sauvegarde as module

    source = _trois_decisions(tmp_path)
    vrai_copier = module._copier

    def copier_puis_casser_la_chaine(origine, vers):
        vrai_copier(origine, vers)
        base = sqlite3.connect(vers)
        base.execute("UPDATE journal_entries SET fingerprint='0' * 64")
        base.commit()
        base.close()

    monkeypatch.setattr(module, "_copier", copier_puis_casser_la_chaine)
    with pytest.raises(SauvegardeRefusee) as refus:
        sauvegarder(source, dossier=tmp_path / "sauvegardes")

    assert refus.value.reason == "copie_infidele"
    assert _restes(tmp_path / "sauvegardes") == []


def test_un_journal_falsifie_pendant_la_copie_n_accuse_pas_la_copie(tmp_path, monkeypatch) -> None:
    """La moitié « chaîne » de la relecture, et elle décide seule.

    Quand la copie ne correspond pas, la source est relue pour savoir laquelle
    des deux a bougé. Deux moitiés : les lignes, et le verdict de chaîne. Les
    lignes couvrent le cas courant — une décision ajoutée pendant la copie.

    Le verdict de chaîne couvre celui que les lignes ne peuvent pas voir :
    `export_rows()` ne porte aucune empreinte, donc une falsification qui
    réécrit les empreintes de la **source** laisse les lignes identiques. Sans
    cette moitié, la sauvegarde accuserait la copie — « la copie ne rend pas la
    même chose que l'original » — alors que c'est l'original qui a été touché.
    Accuser la copie enverrait chercher le défaut à l'endroit où il n'est pas.
    """
    from singular import sauvegarde as module

    source = _trois_decisions(tmp_path)
    vrai_copier = module._copier

    def falsifier_la_source_puis_copier(origine, vers):
        base = sqlite3.connect(origine)
        base.execute("UPDATE journal_entries SET fingerprint='0' * 64")
        base.commit()
        base.close()
        vrai_copier(origine, vers)

    monkeypatch.setattr(module, "_copier", falsifier_la_source_puis_copier)
    with pytest.raises(SauvegardeRefusee) as refus:
        sauvegarder(source, dossier=tmp_path / "sauvegardes")

    assert refus.value.reason == "journal_modifie", (
        "c'est la source qui a bougé, pas la copie qui est infidèle")
    assert _restes(tmp_path / "sauvegardes") == []


def test_l_ecran_montre_la_tete_de_chaine_de_la_copie(tmp_path, capsys) -> None:
    """Une empreinte calculee et jamais montree n'est lue par personne.

    Elle valait la chaine vide depuis toujours, et rien ne l'a dit parce que rien
    ne l'affichait : `Sauvegarde.empreinte` etait construite, puis abandonnee.
    Corrigee, elle ne servait toujours a rien tant qu'elle restait interne.

    Montree, elle sert : celui qui retrouve un dossier de sauvegarde peut
    comparer cette tete a celle de son journal et savoir si c'est bien la copie
    qu'il croit. Un chiffre affiche est un chiffre qu'on peut prendre en defaut.
    """
    from singular.__main__ import main

    source = _trois_decisions(tmp_path)
    tete = DecisionJournal(source, lecture_seule=True).head_fingerprint()
    assert tete, "le cas n'a de sens que si le journal a une tete"
    capsys.readouterr()

    code = main(["--db", str(source), "sauvegarde", "--vers", str(tmp_path / "s")])
    sortie = capsys.readouterr().out

    assert code == 0
    assert tete[:16] in sortie, (
        "l'ecran ne montre pas la tete de chaine : l'empreinte reste invisible, "
        "donc invérifiable")
