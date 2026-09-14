"""Son écart a une date, et le rapport ne la portait pas.

`calibration_verdict` mesure toute la vie du journal d'un seul bloc. Quelqu'un
qui se surestimait de trente points il y a trois mois et qui ne se surestime
plus lisait donc, chaque matin, « tu te surestimes de +15 % — baisse tes
probabilités d'autant ». Suivre ce conseil aurait dérèglé un jugement devenu
juste, et `notice.py` écrit déjà, pour le petit échantillon, que corriger un
jugement juste c'est le dérégler. Le défaut était le même, une tranche de temps
plus loin.

Ce fichier garde les deux bords de la correction, et c'est le second qui compte :

* on ne conclut pas « c'est corrigé » parce que l'écart récent n'est plus
  démontré. Une moitié récente muette est une moitié sans preuve. Il faut
  démontrer que l'écart est devenu petit, ce qui est une autre question et
  demande nettement plus de verdicts ;
* on ne conclut pas non plus « il a corrigé » quand il n'y avait rien à
  corriger : la première moitié doit avoir montré un écart que le hasard
  n'explique pas.

Tout passe par le vrai journal — un test qui fabrique un rapport à la main
prouve la formule, pas la chaîne qui la nourrit.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from singular.journal import DecisionJournal, Tier
from singular.sage import build_notice
from singular.sage.notice import (
    CALIBRATION_GAP,
    CALIBRATION_HASARD,
    CALIBRATION_MINIMUM,
    _calibration_item,
    calibration_progression,
    chance_d_un_ecart_moindre,
)

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def _journal(tmp_path, paris):
    """Un journal réel, ses paris dans l'ordre où ils ont été pris."""
    journal = DecisionJournal(tmp_path / "journal.db")
    for index, (probability, gagne) in enumerate(paris):
        entry = journal.add(title=f"Pari {index}", action="faire", predicted="le résultat",
                            probability=probability, tier=Tier.REVENUS, cost_hours=2,
                            horizon_days=7, now=NOW + timedelta(days=index))
        journal.resolve(entry.entry_id, happened=gagne, now=NOW + timedelta(days=index + 8))
    return journal


def _surconfiance(nombre):
    """Des paris annoncés à 90 % dont moins de la moitié arrivent."""
    return [(0.9, index % 2 == 0) for index in range(nombre)]


def _juste(nombre):
    """Des paris annoncés à 60 % dont six sur dix arrivent."""
    return [(0.6, index % 10 < 6) for index in range(nombre)]


# --- l'absence de preuve n'est pas la preuve de l'absence --------------------

def test_un_petit_echantillon_juste_ne_demontre_rien():
    """Dix verdicts parfaitement calibrés ne démontrent pas un écart petit.

    C'est le piège que ce fichier existe pour fermer. Sur dix paris, presque
    aucun écart n'est démontrable : se taire parce que la preuve manque et
    appeler ce silence « c'est corrigé » serait déclarer victoire sur du bruit.
    """
    assert chance_d_un_ecart_moindre([0.6] * 10, 6, CALIBRATION_GAP) > CALIBRATION_HASARD


def test_assez_de_verdicts_justes_demontrent_un_ecart_petit():
    """Avec de quoi conclure, la démonstration arrive — sinon la règle serait morte.

    Un seuil qu'aucune donnée réelle ne franchit ne protège de rien : il rend
    seulement la phrase impossible. Il faut environ quarante verdicts.
    """
    assert chance_d_un_ecart_moindre([0.6] * 60, 36, CALIBRATION_GAP) <= CALIBRATION_HASARD


def test_un_ecart_reel_ne_se_declare_jamais_petit():
    """Soixante paris à 90 % dont la moitié arrivent : l'écart est là, et il reste.

    Le test d'équivalence doit pouvoir échouer sur des données abondantes,
    sinon il ne mesure que la taille de l'échantillon.
    """
    assert chance_d_un_ecart_moindre([0.9] * 60, 30, CALIBRATION_GAP) > CALIBRATION_HASARD


def test_une_probabilite_sous_la_borne_ne_fait_pas_exploser_le_calcul():
    """`0,10 - 0,15` n'est pas une probabilité, et la limite est assumée.

    Elle entre à zéro, la valeur réalisable la plus proche. Ce qui compte ici
    est qu'aucune valeur impossible ne circule et que le résultat reste une
    probabilité.
    """
    chance = chance_d_un_ecart_moindre([0.1, 0.05, 0.0, 1.0], 1, CALIBRATION_GAP)
    assert 0.0 <= chance <= 1.0


def test_une_borne_nulle_ne_demontre_rien():
    """Demander « son biais est-il inférieur à zéro ? » n'a pas de réponse.

    Fail-closed : la borne dégénérée rend 1.0, donc rien n'est jamais démontré,
    plutôt que de rendre 0.0 et de tout démontrer.
    """
    assert chance_d_un_ecart_moindre([0.6] * 60, 36, 0.0) == 1.0
    assert chance_d_un_ecart_moindre([], 0, CALIBRATION_GAP) == 1.0


# --- les deux moitiés ---------------------------------------------------------

def test_pas_de_progression_sans_deux_moities_dignes_de_ce_nom(tmp_path):
    """En dessous de deux fois le minimum, couper le journal n'apprend rien."""
    journal = _journal(tmp_path, _surconfiance(2 * CALIBRATION_MINIMUM - 1))
    assert calibration_progression(journal.review(now=NOW + timedelta(days=60))) is None


def test_la_coupe_suit_l_ordre_des_decisions(tmp_path):
    """La première moitié est celle des décisions prises en premier.

    C'est l'instant du jugement qui compte, pas celui du verdict : une
    prédiction vaut ce qu'elle valait quand elle a été écrite.
    """
    journal = _journal(tmp_path, _surconfiance(40) + _juste(40))
    progression = calibration_progression(journal.review(now=NOW + timedelta(days=200)))
    assert progression["debut"]["verdicts"] == 40
    assert progression["recent"]["verdicts"] == 40
    assert progression["debut"]["gap"] > CALIBRATION_GAP
    assert abs(progression["recent"]["gap"]) < CALIBRATION_GAP


def test_un_rapport_sans_resultats_ne_produit_aucune_progression():
    """Fail-closed : deux listes qui ne s'alignent pas ne se recoupent pas.

    Un rapport tronqué, une base d'une autre version, une main qui fabrique le
    dictionnaire : aucun de ces cas ne doit rendre une progression plausible.
    """
    assert calibration_progression({"resolved_probabilities": [0.6] * 20}) is None
    assert calibration_progression(
        {"resolved_probabilities": [0.6] * 20, "resolved_outcomes": [1] * 19}) is None
    assert calibration_progression({}) is None


def test_la_correction_exige_un_ecart_demontre_au_depart(tmp_path):
    """On ne corrige pas ce qu'on n'a jamais eu.

    Quelqu'un de juste depuis le premier jour n'a rien corrigé. Sans cette
    condition, le simple fait d'avoir beaucoup de verdicts justes récents
    aurait produit une phrase de félicitations, qui est exactement la flatterie
    que ce dépôt refuse.
    """
    journal = _journal(tmp_path, _juste(120))
    progression = calibration_progression(journal.review(now=NOW + timedelta(days=300)))
    assert progression["debut"]["conclusive"] is False
    assert progression["corrige"] is False


def test_la_correction_se_demontre_quand_elle_a_eu_lieu(tmp_path):
    """Surconfiance franche, puis justesse prolongée : c'est corrigé, et c'est dit."""
    journal = _journal(tmp_path, _surconfiance(60) + _juste(60))
    progression = calibration_progression(journal.review(now=NOW + timedelta(days=300)))
    assert progression["debut"]["conclusive"] is True
    assert progression["recent"]["equivalence"] <= CALIBRATION_HASARD
    assert progression["corrige"] is True


def test_une_surconfiance_jamais_corrigee_reste_une_surconfiance(tmp_path):
    """Le même défaut du premier au dernier jour ne devient pas une amélioration."""
    journal = _journal(tmp_path, _surconfiance(120))
    progression = calibration_progression(journal.review(now=NOW + timedelta(days=300)))
    assert progression["corrige"] is False


# --- ce que le Sage en dit ----------------------------------------------------

def test_le_conseil_disparait_quand_l_ecart_est_corrige(tmp_path):
    """Le reproche est remplacé, pas accompagné.

    C'est tout l'objet : l'ancienne phrase disait « baisse tes probabilités
    d'autant » à quelqu'un qui les avait déjà baissées.
    """
    journal = _journal(tmp_path, _surconfiance(60) + _juste(60))
    item = _calibration_item(journal.review(now=NOW + timedelta(days=300)))
    assert item.severity == "INFO"
    assert "Baisse tes probabilités" not in item.detail
    assert "déjà corrigé" in item.title
    assert item.title.startswith("Ton écart"), (
        "le titre devient l'en-tête « Notice. <titre>. » : il doit tenir seul")


def test_le_chiffre_recent_accompagne_le_reproche(tmp_path):
    """Tant que rien n'est démontré, on donne le fait sans le conclure.

    La moitié récente est un chiffre, pas un verdict : elle se lit avant de
    corriger, et elle empêche de corriger d'après un passé qui n'est plus.
    """
    journal = _journal(tmp_path, _surconfiance(20) + _juste(20))
    item = _calibration_item(journal.review(now=NOW + timedelta(days=200)))
    assert item.severity == "ATTENTION"
    # « Tes 30 plus récentes » serait faux si cinquante décisions plus fraîches
    # attendaient encore un verdict : ce sont les plus récentes *tranchées*.
    assert "plus récentes tranchées" in item.detail
    assert "d'autant" not in item.detail


def test_sans_deux_moities_la_phrase_d_origine_ne_bouge_pas(tmp_path):
    """Un journal trop court garde le conseil chiffré : il n'a qu'un chiffre."""
    journal = _journal(tmp_path, [(0.95, index == 0) for index in range(5)])
    item = _calibration_item(journal.review(now=NOW + timedelta(days=60)))
    assert "Baisse tes probabilités d'autant" in item.detail
    assert "plus récentes" not in item.detail


def test_aucun_ecart_ne_s_affiche_a_moins_zero(tmp_path):
    """« -0 % » est un chiffre que personne n'écrit à la main."""
    journal = _journal(tmp_path, _surconfiance(20) + _juste(20))
    item = _calibration_item(journal.review(now=NOW + timedelta(days=200)))
    assert "-0%" not in item.detail


def test_la_notice_porte_la_progression_pour_les_interfaces(tmp_path):
    """La règle n'a qu'un domicile : les interfaces la lisent, ne la refont pas.

    `test_une_seule_regle_par_phrase.py` raconte cinq fois où une interface a
    gardé sa copie d'une règle corrigée ailleurs. La progression arrive donc
    dans la Notice dès sa construction.
    """
    journal = _journal(tmp_path, _surconfiance(60) + _juste(60))
    notice = build_notice(journal, now=NOW + timedelta(days=300))
    assert notice.progression is not None
    assert notice.as_dict()["progression"]["corrige"] is True


def test_un_journal_vide_ne_parle_pas_de_progression(tmp_path):
    """Rien à mesurer, rien à dire — et surtout pas une exception."""
    journal = DecisionJournal(tmp_path / "vide.db")
    notice = build_notice(journal, now=NOW)
    assert notice.progression is None


# --- ce qu'un état incohérent ne doit pas pouvoir obtenir ---------------------

def test_la_coupe_suit_la_date_du_jugement_pas_l_ordre_d_ecriture(tmp_path):
    """Une reprise de journal écrit d'anciennes décisions après des récentes.

    `python3 -m singular import` rapatrie trois mois du PC dans le journal du
    Mac : les entrées entrent après celles d'aujourd'hui, en portant leur date
    d'origine. Couper d'après l'ordre d'écriture mettrait le passé du côté
    récent et inverserait exactement la phrase. La coupe suit `created_at`,
    c'est-à-dire l'instant où le jugement a été porté.
    """
    journal = DecisionJournal(tmp_path / "journal.db")
    ordre_d_ecriture = list(enumerate(_juste(40))) + list(enumerate(_surconfiance(40)))
    for rang, (index, (probability, gagne)) in enumerate(ordre_d_ecriture):
        # Les justes sont récents, les surconfiants sont anciens ; l'écriture
        # fait l'inverse.
        jour = index + (0 if rang >= 40 else 100)
        entry = journal.add(title=f"Pari {rang}", action="faire", predicted="le résultat",
                            probability=probability, tier=Tier.REVENUS, cost_hours=2,
                            horizon_days=7, now=NOW + timedelta(days=jour))
        journal.resolve(entry.entry_id, happened=gagne, now=NOW + timedelta(days=jour + 8))

    progression = calibration_progression(journal.review(now=NOW + timedelta(days=300)))
    assert progression["debut"]["gap"] > CALIBRATION_GAP, "le passé n'est pas du bon côté"
    assert abs(progression["recent"]["gap"]) < CALIBRATION_GAP
    assert journal.verify(), "la chaîne doit rester intacte quel que soit l'ordre des dates"


def test_un_resultat_hors_de_zero_un_ne_gonfle_pas_le_compte():
    """Plus de réussites que de verdicts donnerait une probabilité impossible.

    Le journal n'écrit que 0 ou 1. Un rapport d'une autre version, ou fabriqué,
    ne doit pas pour autant produire un chiffre qui n'a pas de sens.
    """
    progression = calibration_progression({
        "resolved_probabilities": [0.6] * 20,
        "resolved_outcomes": [7] * 20,
    })
    assert progression["recent"]["gap"] == round(0.6 - 1.0, 2)
    assert 0.0 <= progression["recent"]["equivalence"] <= 1.0


# --- la ligne de statut dit la même chose que le Sage -------------------------

def test_la_ligne_de_statut_ne_contredit_pas_le_sage(tmp_path):
    """Chaque terminal ouvert affiche cette ligne. Elle affichait l'écart d'une vie.

    Sans ça, le Sage aurait dit « tu l'as déjà corrigé » pendant que le prompt
    de chaque fenêtre répétait « calibration +20% ». Deux réponses à la même
    question sur le même écran : c'est le défaut que ce dépôt a déjà payé cinq
    fois, et la sixième aurait été la plus visible de toutes.
    """
    journal = _journal(tmp_path, _surconfiance(60) + _juste(60))
    moment = NOW + timedelta(days=300)
    ligne = journal.summary_line(now=moment)
    item = _calibration_item(journal.review(now=moment))

    assert "corrigee" in ligne, ligne
    assert "déjà corrigé" in item.title
    assert item.title.startswith("Ton écart"), (
        "le titre devient l'en-tête « Notice. <titre>. » : il doit tenir seul")
    assert "+20%" not in ligne, "la ligne affiche encore le total d'une vie"


def test_la_ligne_de_statut_montre_un_ecart_prouve_sous_le_seuil_voyant(tmp_path):
    """Dix points établis sur deux cents verdicts : la Notice conclut, la ligne aussi.

    Elle se taisait, parce qu'elle gardait la version d'avant le 9 septembre de
    la règle — « assez de verdicts, et quinze points d'écart ».
    """
    journal = _journal(tmp_path, [(0.6, index % 10 < 5) for index in range(200)])
    moment = NOW + timedelta(days=400)
    assert journal.review(now=moment)["overconfidence"] == 0.10
    assert "calibration" in journal.summary_line(now=moment)
    assert _calibration_item(journal.review(now=moment)) is not None


def test_la_ligne_de_statut_se_tait_sur_un_ecart_petit_et_incertain(tmp_path):
    """Ce qui n'est ni démontré ni voyant ne s'affiche nulle part."""
    journal = _journal(tmp_path, [(0.6, index % 10 < 6) for index in range(10)])
    assert "calibration" not in journal.summary_line(now=NOW + timedelta(days=60))


# --- ce que reçoit la faculté qui coûte des jetons ----------------------------

def test_le_contexte_envoye_au_modele_porte_l_ecart_recent(tmp_path):
    """`analyse` envoyait le chiffre d'une vie, seul.

    Un modèle qui lit « overconfidence: 0.2 » conseille de baisser les
    probabilités, même quand l'observation juste au-dessus, dans le même texte,
    dit que c'est corrigé. Deux réponses à la même question : c'est le défaut
    des interfaces, transporté dans la seule faculté qui coûte de l'argent.

    `--blanc` affiche ce texte sans appeler personne : ce qui s'ajoute ici se
    relit avant de partir.
    """
    from singular.analyse import contexte_pour_analyse

    journal = _journal(tmp_path, _surconfiance(60) + _juste(60))
    contexte = contexte_pour_analyse(build_notice(journal, now=NOW + timedelta(days=300)).as_dict())

    assert "calibration_recente" in contexte
    assert '"ecart_corrige": true' in contexte
    assert "déjà corrigé" in contexte, "l'observation aussi doit partir"


def test_un_journal_court_n_envoie_pas_de_calibration_recente(tmp_path):
    """Rien à couper, rien à envoyer : pas de clé vide ni de `null` à interpréter."""
    from singular.analyse import contexte_pour_analyse

    journal = _journal(tmp_path, _surconfiance(4))
    contexte = contexte_pour_analyse(build_notice(journal, now=NOW + timedelta(days=60)).as_dict())
    assert "calibration_recente" not in contexte


def test_une_borne_degeneree_ne_demontre_jamais_rien() -> None:
    """Le trou penchait du mauvais côté, et c'est ce qui en faisait un défaut.

    `borne <= 0` gardait le zéro et le négatif. Avec l'infini, toutes les
    probabilités se ramenaient aux bornes et la fonction rendait **zéro** —
    c'est-à-dire « écart démontré petit, avec certitude ». Une entrée dégénérée
    donnait le verdict le plus permissif possible, alors que la règle du dépôt
    dit de refuser quand il y a ambiguïté.
    """
    for borne in (float("nan"), float("inf"), float("-inf"), 0.0, -0.1, 1.0, 1.5):
        assert chance_d_un_ecart_moindre([0.6] * 20, 12, borne) == 1.0, borne
    assert chance_d_un_ecart_moindre([0.6] * 20, 12, CALIBRATION_GAP) < 1.0, (
        "la borne réelle doit continuer de calculer quelque chose")


def test_le_serveur_sert_la_progression_a_l_app(tmp_path):
    """Le dernier maillon : sans lui, la vignette du téléphone ne basculerait jamais.

    `Notice.as_dict()` porte la progression et `renderFigures` sait la lire. Entre
    les deux il y a `/api/notice`, et rien ne garantissait que la clé traverse :
    une liste blanche ajoutée au serveur un jour aurait rendu la bascule muette
    sans faire rougir quoi que ce soit. C'est le mode d'échec que ce dépôt
    connaît le mieux.
    """
    from singular.sage.server import SageApp

    journal = _journal(tmp_path, _surconfiance(60) + _juste(60))
    charge = SageApp(journal, token="un-jeton-de-test-suffisamment-long").notice()

    assert charge["progression"] is not None
    assert charge["progression"]["corrige"] is True
    assert charge["progression"]["recent"]["verdicts"] == 60


def test_un_ecart_recent_encore_demontre_n_est_pas_un_ecart_corrige(tmp_path):
    """Trouvé en attaquant mes deux premières conditions, pas en les relisant.

    « L'écart récent est démontré inférieur à quinze points » ne veut pas dire
    « il n'y a plus d'écart ». Sur quatre cents verdicts, un écart de dix points
    passe le test d'équivalence **et** se démontre par `chance_du_hasard`. Le
    Sage aurait alors tenu deux phrases contradictoires sur le même écran — « ton
    écart récent est de +10 %, c'est prouvé » et « c'est corrigé, ne corrige
    pas » — ce qui est exactement le défaut que ce fichier existe pour fermer.

    Ce que le lecteur doit lire dans ce cas est le reproche ordinaire, qui pointe
    le chiffre récent : il s'est amélioré, il lui reste dix points, et c'est de
    ces dix points-là qu'il doit corriger.
    """
    journal = _journal(tmp_path, _surconfiance(400) + [(0.7, index % 10 < 6) for index in range(400)])
    progression = calibration_progression(journal.review(now=NOW + timedelta(days=900)))

    assert progression["debut"]["conclusive"], "la première moitié montrait bien un écart"
    assert progression["recent"]["equivalence"] <= CALIBRATION_HASARD, (
        "l'écart récent est bien démontré sous les quinze points")
    assert progression["recent"]["conclusive"], "et il est pourtant lui-même démontré"
    assert not progression["corrige"], (
        "une moitié récente qui démontre encore un écart n'est pas un écart corrigé")

    item = _calibration_item(journal.review(now=NOW + timedelta(days=900)))
    assert "déjà corrigé" not in item.title
    assert "plus récentes tranchées" in item.detail, (
        "le reproche doit pointer le chiffre récent, qui est celui à corriger")


def test_une_moitie_recente_sans_ecart_demontre_reste_un_ecart_corrige(tmp_path):
    """L'autre bord : la troisième condition ne doit pas tout éteindre."""
    journal = _journal(tmp_path, _surconfiance(60) + _juste(60))
    progression = calibration_progression(journal.review(now=NOW + timedelta(days=300)))
    assert not progression["recent"]["conclusive"]
    assert progression["corrige"]
