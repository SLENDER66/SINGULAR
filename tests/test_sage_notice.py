"""« Notice. » — chaque phrase doit être un fait tiré du journal.

Le Sage a le droit d'être dur ; il n'a pas le droit d'être faux. Ces tests
portent donc sur deux choses : ce qu'il dit quand il y a quelque chose à dire,
et son silence quand il n'y a rien. Un rapport qui trouve toujours un reproche
n'est plus lu.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from singular.journal import DecisionJournal, Tier
from singular.sage import build_notice
from singular.sage.notice import NoticeItem

NOW = datetime(2026, 9, 6, 9, 0, tzinfo=UTC)


def _journal(tmp_path):
    return DecisionJournal(tmp_path / "journal.db")


def _add(journal, *, tier=Tier.REVENUS, probability=0.6, hours=4.0, days=14, now=NOW, title="Une décision"):
    return journal.add(title=title, action="faire la chose", predicted="le résultat observable",
                       probability=probability, tier=tier, cost_hours=hours, horizon_days=days, now=now)


def _titles(notice) -> list[str]:
    return [item.title for item in notice.items]


# --- le journal vide ---------------------------------------------------------

def test_an_empty_journal_is_told_once_and_not_scolded_twice(tmp_path):
    """Sans entrées, « aucune décision sur Stabilité » dirait deux fois la même chose."""
    notice = build_notice(_journal(tmp_path), now=NOW)
    assert _titles(notice) == ["Le journal est vide"]
    assert notice.headline == "Notice. Le journal est vide."


# --- ce qui attend un verdict ------------------------------------------------

def test_an_overdue_decision_comes_first(tmp_path):
    journal = _journal(tmp_path)
    entry = _add(journal, days=7)
    notice = build_notice(journal, now=NOW + timedelta(days=9))

    first = notice.items[0]
    assert first.title == "À trancher aujourd'hui"
    assert first.entry_ids == (entry.entry_id,)
    assert first.action == f"resolve {entry.entry_id}"


def test_a_late_verdict_is_critical_and_says_why(tmp_path):
    journal = _journal(tmp_path)
    _add(journal, days=7)
    notice = build_notice(journal, now=NOW + timedelta(days=20))

    first = notice.items[0]
    assert first.severity == "CRITIQUE"
    assert "13 jours" in first.detail
    assert "préfère ne pas voir" in first.detail


def test_the_delay_is_counted_from_the_report_not_from_the_machine(tmp_path):
    """Un rapport daté d'un autre jour affichait « en retard de 0 jour »."""
    journal = _journal(tmp_path)
    _add(journal, days=7)
    notice = build_notice(journal, now=NOW + timedelta(days=12))
    assert "5 jours" in notice.items[0].detail


def test_one_overdue_decision_is_written_in_the_singular(tmp_path):
    journal = _journal(tmp_path)
    _add(journal, days=7)
    detail = build_notice(journal, now=NOW + timedelta(days=9)).items[0].detail
    assert "1 décision a dépassé son horizon" in detail
    assert "Elle attend depuis 2 jours" in detail


# --- les rangs de la constitution --------------------------------------------

def test_the_two_founding_ranks_are_named_when_empty(tmp_path):
    journal = _journal(tmp_path)
    _add(journal, tier=Tier.PATRIMOINE, hours=30)
    _add(journal, tier=Tier.PATRIMOINE, hours=30)
    notice = build_notice(journal, now=NOW)

    item = next(item for item in notice.items if item.title.startswith("Aucune décision sur"))
    assert item.severity == "ATTENTION"
    assert item.title == "Aucune décision sur Stabilité et Revenus"
    assert "60h sont allées ailleurs" in item.detail


def test_a_single_missing_rank_is_written_in_the_singular(tmp_path):
    journal = _journal(tmp_path)
    _add(journal, tier=Tier.STABILITE)
    _add(journal, tier=Tier.PATRIMOINE)
    item = next(item for item in build_notice(journal, now=NOW).items
                if item.title.startswith("Aucune décision sur"))
    assert item.title == "Aucune décision sur Revenus"
    assert "Ce rang n’a reçu" in item.detail


def test_a_rank_that_could_not_have_been_filled_yet_is_not_held_against_you(tmp_path):
    """La fondation a deux rangs ; une décision ne peut pas en occuper deux.

    C'était la phrase d'en-tête du rapport, en ATTENTION, le lendemain de la
    première décision réelle de Thomas : « Aucune décision sur Stabilité ». Il
    venait d'écrire une ligne. Le constat ne décrivait pas sa conduite, il
    décrivait le fait qu'on ne peut pas remplir deux cases avec un jeton — et
    aucun geste de sa part n'aurait pu l'éviter ce matin-là.

    Le même défaut avait déjà été payé sur « heures engagées sans verdict » et
    corrigé à un seul endroit. Le voici tenu aux deux.
    """
    journal = _journal(tmp_path)
    _add(journal, tier=Tier.REVENUS, hours=4.0, probability=0.75)

    assert not any(item.title.startswith("Aucune décision sur")
                   for item in build_notice(journal, now=NOW + timedelta(days=1)).items)


def test_ailleurs_counts_only_the_hours_that_actually_went_elsewhere(tmp_path):
    """« 4h sont allées ailleurs » nommait les heures posées sur la fondation.

    Le détail comptait `hours_total`, donc tout le journal, Revenus compris —
    alors que Revenus *est* le second rang de la fondation. La phrase appelait
    « ailleurs » exactement l'endroit où les heures étaient.

    Sans heures hors fondation, il reste un fait à savoir, pas un reproche à
    faire : le rang manque, on le dit, en INFO, sans chiffre inventé.
    """
    journal = _journal(tmp_path)
    _add(journal, tier=Tier.REVENUS, hours=4.0)
    _add(journal, tier=Tier.REVENUS, hours=6.0)

    tout_sur_la_fondation = next(item for item in build_notice(journal, now=NOW).items
                                 if item.title.startswith("Aucune décision sur"))
    assert tout_sur_la_fondation.severity == "INFO"
    assert "ailleurs" not in tout_sur_la_fondation.detail
    assert "10h" not in tout_sur_la_fondation.detail

    _add(journal, tier=Tier.PATRIMOINE, hours=7.0)
    avec_un_ailleurs = next(item for item in build_notice(journal, now=NOW).items
                            if item.title.startswith("Aucune décision sur"))
    assert avec_un_ailleurs.severity == "ATTENTION"
    assert "7h sont allées ailleurs" in avec_un_ailleurs.detail, avec_un_ailleurs.detail


def test_nothing_is_said_when_both_founding_ranks_are_served(tmp_path):
    journal = _journal(tmp_path)
    _add(journal, tier=Tier.STABILITE)
    _add(journal, tier=Tier.REVENUS)
    assert not any(item.title.startswith("Aucune décision sur")
                   for item in build_notice(journal, now=NOW).items)


# --- ce que vaut la confiance ------------------------------------------------

def _verdicts(journal, *, combien, reussites, probability):
    """`combien` paris à la même probabilité, dont `reussites` gagnés."""
    for index in range(combien):
        entry = _add(journal, probability=probability, tier=Tier.REVENUS,
                     title=f"Décision {index}")
        journal.resolve(entry.entry_id, happened=index < reussites,
                        now=NOW + timedelta(days=1))


def _calibration(journal):
    return next((item for item in build_notice(journal, now=NOW + timedelta(days=2)).items
                 if "estimes" in item.title or "annonces plus" in item.title
                 or "arrive plus" in item.title), None)


def test_overconfidence_is_named_once_there_is_enough_to_say_it(tmp_path):
    """Quatre paris à 90 % tous perdus : le hasard ne fait pas ça."""
    journal = _journal(tmp_path)
    _verdicts(journal, combien=4, reussites=0, probability=0.9)
    _add(journal, tier=Tier.STABILITE)

    item = _calibration(journal)
    assert item is not None and "surestimes" in item.title
    assert item.severity == "ATTENTION"
    assert "90%" in item.detail and "0%" in item.detail
    # 0,1^4 = 1/10 000, vérifiable à la main.
    assert "une fois sur 10\u202f000" in item.detail, item.detail


def test_three_verdicts_do_not_prove_anything_and_the_report_says_so(tmp_path):
    """« Sur 3 verdicts, ce n'est plus de la malchance » — c'en était.

    Un pari sur trois gagné quand on en annonçait trois quarts : le hasard seul
    produit cet écart une fois sur six. L'outil l'affirmait pourtant comme un
    fait, et enchaînait sur « baisse tes probabilités ». Corriger un jugement
    que rien ne montre faux, c'est le dérégler — sur la seule question pour
    laquelle ce journal existe.

    Le compte est vérifiable à la main : sur trois paris à 75 %, obtenir 0 ou 1
    réussite vaut 0,25³ + 3 × 0,75 × 0,25² = 0,015625 + 0,140625, soit 15,6 %.
    """
    journal = _journal(tmp_path)
    _verdicts(journal, combien=3, reussites=1, probability=0.75)

    item = _calibration(journal)
    assert item is not None, "l'écart doit rester visible : il veut le voir"
    assert item.severity == "INFO", "un constat, pas un reproche"
    assert "surestimes" not in item.title
    assert "une fois sur 6" in item.detail, item.detail
    assert "plus de la malchance" not in item.detail
    assert "Baisse tes probabilités" not in item.detail


def test_ten_verdicts_can_still_be_luck_and_the_report_admits_it(tmp_path):
    """Le nombre de verdicts ne suffit pas : c'est l'écart ET le nombre."""
    journal = _journal(tmp_path)
    _verdicts(journal, combien=10, reussites=5, probability=0.75)

    item = _calibration(journal)
    assert item is not None and item.severity == "INFO"
    assert "trop peu pour en conclure" in item.detail


def test_a_sure_bet_that_failed_is_not_diluted_by_the_long_shots(tmp_path):
    """Deux paris à 5 %, un à 95 %, aucun tenu. C'est le 95 % qui parle.

    Une moyenne les ramène tous à 35 % et efface exactement ce qui compte :
    perdre deux paris à 5 % est banal, perdre celui à 95 % ne l'est pas. Le
    calcul exact donne une chance sur 21 et conclut ; la moyenne donnerait
    une chance sur 3 et se tairait.

    Ce test passe par la Notice, pas par la fonction : c'est le branchement
    qu'il tient. Un raccourci par la moyenne laisserait la fonction juste et
    le rapport faux, ce qui est le pire des deux.
    """
    journal = _journal(tmp_path)
    for index, probability in enumerate((0.05, 0.05, 0.95)):
        entry = _add(journal, probability=probability, tier=Tier.REVENUS,
                     title=f"Pari {index}")
        journal.resolve(entry.entry_id, happened=False, now=NOW + timedelta(days=1))

    item = _calibration(journal)
    assert item is not None
    assert item.severity == "ATTENTION", "le pari sûr qui tombe doit se dire"
    assert "surestimes" in item.title
    # 0,95 × 0,95 × 0,05 = 0,0475, soit une fois sur 21.
    assert "une fois sur 21" in item.detail, item.detail


def test_the_chance_of_luck_is_exact_even_when_the_bets_differ(tmp_path):
    """Une moyenne aurait approximé la réponse à la seule question qui compte.

    Deux paris à 50 % et deux à 90 % n'ont pas la même distribution que quatre
    paris à 70 %, et c'est justement là qu'un raccourci se paierait.
    """
    from singular.sage.notice import chance_du_hasard

    # Un seul pari à 100 %... impossible dans le journal, mais la fonction doit
    # rester bornée : une certitude tenue n'a rien d'improbable.
    assert chance_du_hasard([0.5], 1) == pytest.approx(1.0)
    # Deux paris à 50 %, aucun gagné : (0,5)² = 0,25 des deux côtés = 0,5.
    assert chance_du_hasard([0.5, 0.5], 0) == pytest.approx(0.5)
    # Quatre paris à 90 %, aucun gagné : 0,1^4.
    assert chance_du_hasard([0.9] * 4, 0) == pytest.approx(1e-4, rel=1e-9)
    # Probabilités mêlées : le calcul exact, pas celui de leur moyenne.
    melange = chance_du_hasard([0.5, 0.5, 0.9, 0.9], 0)
    moyenne = chance_du_hasard([0.7] * 4, 0)
    assert melange != pytest.approx(moyenne), "la moyenne n'est pas la bonne réponse"
    assert melange == pytest.approx(0.5 * 0.5 * 0.1 * 0.1)


def test_two_verdicts_are_not_enough_to_call_someone_overconfident(tmp_path):
    """En dessous du seuil, l'écart s'explique aussi bien par l'échantillon."""
    journal = _journal(tmp_path)
    for index in range(2):
        entry = _add(journal, probability=0.9, title=f"Décision {index}")
        journal.resolve(entry.entry_id, happened=False, now=NOW + timedelta(days=1))
    assert not any("surestimes" in item.title
                   for item in build_notice(journal, now=NOW + timedelta(days=2)).items)


# --- l'intégrité passe avant tout --------------------------------------------

def test_a_broken_chain_outranks_everything_else(tmp_path):
    journal = _journal(tmp_path)
    entry = _add(journal, days=7)
    with journal._connect() as conn:
        conn.execute("UPDATE journal_entries SET probability=0.05 WHERE entry_id=?", (entry.entry_id,))

    notice = build_notice(journal, now=NOW + timedelta(days=30))
    assert notice.items[0].title == "La chaîne du journal est rompue"
    assert notice.severity == "CRITIQUE"


def test_an_ordinary_journal_does_not_report_a_broken_chain(tmp_path):
    """Le mécanisme d'intégrité ne doit pas accuser l'usage normal."""
    journal = _journal(tmp_path)
    _add(journal, hours=60, tier=Tier.STABILITE)
    _add(journal, hours=2.5, tier=Tier.REVENUS)
    assert not any("chaîne" in item.title for item in build_notice(journal, now=NOW).items)


# --- la forme ----------------------------------------------------------------

def test_a_notice_item_refuses_an_unknown_severity():
    with pytest.raises(ValueError, match="gravité inconnue"):
        NoticeItem("URGENT", "titre", "détail")


def test_the_report_is_serialisable(tmp_path):
    journal = _journal(tmp_path)
    _add(journal)
    payload = build_notice(journal, now=NOW).as_dict()
    assert payload["headline"].startswith("Notice.")
    assert payload["severity"] in {"CRITIQUE", "ATTENTION", "INFO"}
    assert isinstance(payload["items"], list)
    assert payload["report"]["decisions"] == 1


# --- ce qu'on ne reproche pas à quelqu'un qui commence ------------------------

def test_the_first_decision_is_not_accused_of_confusing_activity_with_results(tmp_path):
    """Le cas réel du premier soir, et il était faux.

    Une décision enregistrée, quatre heures engagées, échéance dans deux
    semaines. Le Sage répondait « 4h engagées sans verdict — contre 0h qui ont
    produit ce que tu attendais. C'est la définition que ta constitution donne
    de confondre activité et résultat. »

    Rien n'aurait pu être tranché : l'horizon n'était pas atteint. Le reproche
    était impossible à éviter, il tombait sur la toute première ligne écrite,
    et il comparait à un ensemble vide. Un rapport qui accuse dès qu'on
    commence n'est plus lu — et il avait tort.
    """
    journal = _journal(tmp_path)
    _add(journal, tier=Tier.REVENUS, hours=4.0, days=14, probability=0.75)
    titles = _titles(build_notice(journal, now=NOW + timedelta(days=1)))

    assert not any("engagées sans verdict" in title for title in titles), titles
    # Et rien d'autre non plus : « Aucune décision sur Stabilité » tenait la
    # même place et faisait la même faute, sur la même ligne écrite le même
    # soir. Voir `test_a_rank_that_could_not_have_been_filled_yet...`.
    assert titles == ["1 décision ouverte"]


def test_hours_without_a_verdict_are_reported_once_a_verdict_exists(tmp_path):
    """L'autre côté : dès qu'il y a de quoi comparer, l'observation revient.

    Sans ce test, mettre la règle en silence permanent passerait au vert.
    """
    journal = _journal(tmp_path)
    _add(journal, tier=Tier.STABILITE, hours=80.0, days=60, title="Gros chantier")
    settled = _add(journal, tier=Tier.REVENUS, hours=2.0, days=20, title="Client")
    journal.resolve(settled.entry_id, happened=True, now=NOW + timedelta(days=1))

    titles = _titles(build_notice(journal, now=NOW + timedelta(days=2)))
    assert any("engagées sans verdict" in title for title in titles), titles


def test_never_settling_anything_is_still_caught_by_the_overdue_rule(tmp_path):
    """La contre-vérification : le silence ne doit pas laisser passer l'abandon.

    Quelqu'un qui enregistre des décisions et n'en tranche jamais aucune ne
    doit pas gagner le silence du Sage. Ce n'est plus l'observation sur les
    heures qui le dit — c'est le retard, qui est plus fort et qui nomme le
    geste à faire.
    """
    journal = _journal(tmp_path)
    for index in range(3):
        _add(journal, tier=Tier.STABILITE, hours=30.0, days=7, title=f"Chantier {index}")

    notice = build_notice(journal, now=NOW + timedelta(days=40))
    assert notice.items[0].title == "À trancher aujourd'hui"
    assert notice.items[0].severity == "CRITIQUE"


# --- le jour du verdict ------------------------------------------------------

def test_le_matin_de_l_echeance_le_rapport_demande_le_verdict(tmp_path):
    """La promesse d'`A_FAIRE.md` : « la carte passera en haut, À trancher ».

    Elle ne passait pas en haut le jour dit. `due_at` portait l'heure
    d'écriture, donc une décision prise un soir n'échoyait qu'au soir du
    quatorzième jour ; le matin, le rapport se contentait d'un INFO « la
    prochaine échéance tombe aujourd'hui », noyé dans la liste. Le seul geste
    que cet outil réclame à son auteur lui était demandé un jour trop tard,
    systématiquement.

    Ce test tient la phrase d'en-tête, parce que c'est elle qu'on lit sur un
    téléphone avant de reposer l'appareil.
    """
    journal = _journal(tmp_path)
    soir = datetime(2026, 9, 6, 20, 0, tzinfo=UTC)
    journal.add(title="Postuler", action="candidature", predicted="Un entretien",
                probability=0.75, tier=Tier.REVENUS, cost_hours=4,
                horizon_days=14, now=soir)

    veille = build_notice(journal, now=datetime(2026, 9, 19, 8, 0, tzinfo=UTC))
    assert "À trancher" not in veille.headline, "réclamé la veille"

    jour_dit = build_notice(journal, now=datetime(2026, 9, 20, 7, 0, tzinfo=UTC))
    assert jour_dit.headline == "Notice. À trancher aujourd'hui."
    tranche = jour_dit.items[0]
    assert tranche.severity == "ATTENTION"
    assert "depuis aujourd'hui" in tranche.detail


def test_le_passage_en_critique_arrive_bien_apres_une_semaine(tmp_path):
    """La phrase dit « passé une semaine ». Le compte doit dire la même chose.

    Il comptait une demi-journée de moins à chaque fois — assez pour que le
    huitième jour soit annoncé comme le septième, et pour que l'escalade
    tombe un jour après ce que la phrase promet.
    """
    journal = _journal(tmp_path)
    soir = datetime(2026, 9, 6, 20, 0, tzinfo=UTC)
    journal.add(title="Postuler", action="candidature", predicted="Un entretien",
                probability=0.75, tier=Tier.REVENUS, cost_hours=4,
                horizon_days=14, now=soir)

    sept = build_notice(journal, now=datetime(2026, 9, 27, 8, 0, tzinfo=UTC)).items[0]
    assert "depuis 7 jours" in sept.detail
    assert sept.severity == "ATTENTION", "sept jours, c'est le seuil, pas au-delà"

    huit = build_notice(journal, now=datetime(2026, 9, 28, 8, 0, tzinfo=UTC)).items[0]
    assert "depuis 8 jours" in huit.detail
    assert huit.severity == "CRITIQUE"
    assert "Passé une semaine" in huit.detail


# --- ce que le rapport met dans la bouche de la constitution ------------------

def test_the_report_only_attributes_to_the_constitution_what_it_says(tmp_path):
    """Une phrase qui parle au nom de sa constitution doit dire vrai.

    « C'est la définition que ta constitution donne de confondre activité et
    résultat » : elle n'en donne aucune. Le document nomme le piège dans sa
    mission — « sans confondre activité et résultat » — et s'arrête là. Le
    seuil, lui, est un choix de ce rapport.

    Ce n'est pas un détail de ton. Un outil qui invoque un document que son
    auteur a écrit lui-même, pour lui prêter une règle qu'il ne contient pas,
    rend cette règle inattaquable : on ne discute pas sa propre constitution.
    C'est la provenance, appliquée aux phrases plutôt qu'aux données.
    """
    import pathlib
    import re

    racine = pathlib.Path(__file__).resolve().parent.parent
    texte_constitution = (racine / "constitution.md").read_text(encoding="utf-8")
    source = (racine / "singular/sage/notice.py").read_text(encoding="utf-8")

    # Les affirmations restantes, et ce qui les fonde dans le document.
    fondees = {
        "Ta constitution ouvre sur": "Stabilité → Revenus",
        "La constitution demande de juger une décision sur": "levier, coût",
    }
    for phrase, appui in fondees.items():
        assert phrase in source, f"« {phrase} » a disparu : ce test ne la garde plus"
        for morceau in appui.split(", "):
            assert morceau in texte_constitution, (
                f"« {phrase} » s'appuie sur « {morceau} », absent de constitution.md")

    interdites = [r"la définition que ta constitution", r"ta constitution définit"]
    for motif in interdites:
        assert not re.search(motif, source), (
            f"le rapport prête une définition à constitution.md ({motif!r}), "
            "qui n'en donne aucune")


# --- la carte doit nommer la decision dont elle donne le retard ---------------

def test_la_carte_du_retard_nomme_la_decision_dont_elle_compte_les_jours(tmp_path) -> None:
    """Le nombre venait d'un `max()`, l'action de `overdue[0]` : deux décisions.

    `python3 -m singular due` listait une décision en retard d'un jour au-dessus
    d'une décision en retard de trente-neuf, et finissait en lui donnant la
    commande pour trancher la première. La Notice se contredisait dans une seule
    phrase : « la plus ancienne attend depuis 39 jours », puis `resolve` sur une
    autre.

    Il faut un horizon long pris **avant** un horizon court pour que l'ordre du
    retard et l'ordre d'écriture se séparent. C'est pour ça que personne ne
    l'avait vu, et que les vecteurs de parité ne le voyaient pas non plus.

    Le port Swift, lui, triait déjà par échéance et avait raison.
    """
    from datetime import UTC, datetime, timedelta

    from singular.journal import DecisionJournal, Tier
    from singular.sage.notice import build_notice

    maintenant = datetime.now(UTC)
    journal = DecisionJournal(tmp_path / "journal.db")
    tot = journal.add(title="Écrite en premier, échue en dernier", action="a", predicted="b",
                      probability=0.6, tier=Tier.REVENUS, cost_hours=1, horizon_days=59,
                      now=maintenant - timedelta(days=60))
    tard = journal.add(title="Écrite ensuite, échue depuis longtemps", action="a", predicted="b",
                       probability=0.6, tier=Tier.REVENUS, cost_hours=1, horizon_days=1,
                       now=maintenant - timedelta(days=40))

    echues = journal.due(now=maintenant)
    retards = [e.overdue_days(maintenant) for e in echues]
    assert retards == sorted(retards, reverse=True), (
        f"`due()` rend {retards} : la plus en retard doit venir en tête, "
        "sinon l'écran et la Notice pointent la mauvaise décision")
    assert echues[0].entry_id == tard.entry_id
    assert tot.entry_id in {e.entry_id for e in echues}, "les deux sont bien en retard"

    carte = next(item for item in build_notice(journal, now=maintenant).items
                 if item.title == "À trancher aujourd'hui")
    pire = max(e.overdue_days(maintenant) for e in echues)
    assert f"depuis {pire} jours" in carte.detail
    assert carte.action == f"resolve {tard.entry_id}", (
        "la carte donne le retard d'une décision et la commande d'une autre")
    assert carte.entry_ids[0] == tard.entry_id


def test_la_carte_dit_le_retard_et_pas_l_anciennete() -> None:
    """« La plus ancienne » nommait la mauvaise, une fois l'ordre corrigé.

    Le témoin de la phrase : ce que le nombre mesure est un retard.
    """
    import pathlib

    source = (pathlib.Path(__file__).resolve().parent.parent
              / "singular/sage/notice.py").read_text(encoding="utf-8")
    swift = (pathlib.Path(__file__).resolve().parent.parent
             / "ios/SingularSage/Core/Notice.swift").read_text(encoding="utf-8")
    for texte, nom in ((source, "notice.py"), (swift, "Notice.swift")):
        assert "La plus en retard attend" in texte, nom
        assert "La plus ancienne attend" not in texte, (
            f"{nom} : « la plus ancienne » n'est pas « la plus en retard »")


# --- l'argent, sur cinq dollars -----------------------------------------------

def _budget(reste, *, credit=5.0, alerte=None):
    """Le bilan tel que `parle.bilan()` le rend, reduit a ce qui est lu ici."""
    return {"credit_usd": credit, "alerte_usd": alerte,
            "restant_au_mieux_usd": reste, "restant_usd": reste}


def test_sans_tarifs_ecrits_la_notice_ne_parle_pas_d_argent(tmp_path) -> None:
    """Le depot ne connait aucun prix, et il ne commence pas par en inventer un."""
    from singular.journal import DecisionJournal
    from singular.sage.notice import build_notice

    journal = DecisionJournal(tmp_path / "j.db")
    for budget in (None, {"credit_usd": None, "restant_au_mieux_usd": None}):
        titres = [i.title for i in build_notice(journal, budget=budget).items]
        assert not any("API" in t for t in titres), titres


def test_sans_seuil_ecrit_elle_se_tait_jusqu_a_zero(tmp_path) -> None:
    """Une ligne d'argent tous les matins serait du bruit.

    « C'est bas » est un chiffre sur son argent : cinq dollars ne se decoupent
    pas de la meme facon selon qu'on veut dix conversations ou une recherche
    d'offres, et lui seul le sait. Le seuil vit donc dans son fichier de
    tarifs, a cote de ses prix -- et sans lui, elle ne juge pas.
    """
    from singular.journal import DecisionJournal
    from singular.sage.notice import build_notice

    journal = DecisionJournal(tmp_path / "j.db")

    muette = build_notice(journal, budget=_budget(0.10)).items
    assert not any("API" in i.title for i in muette), "sans seuil, pas de reproche"

    epuise = build_notice(journal, budget=_budget(0.0)).items
    assert any(i.severity == "CRITIQUE" and "API" in i.title for i in epuise), (
        "zero n'est pas un jugement : la faculte suivante refusera")


def test_le_seuil_vient_de_son_fichier(tmp_path) -> None:
    from singular.journal import DecisionJournal
    from singular.sage.notice import build_notice

    journal = DecisionJournal(tmp_path / "j.db")

    assert not any("API" in i.title
                   for i in build_notice(journal, budget=_budget(2.0, alerte=1.0)).items)
    bas = [i for i in build_notice(journal, budget=_budget(0.65, alerte=1.0)).items
           if "API" in i.title]
    assert [i.severity for i in bas] == ["ATTENTION"]
    assert "0.65" in bas[0].detail and "5.00" in bas[0].detail


def test_elle_dit_ce_qui_continue_sans_cle(tmp_path) -> None:
    """La promesse centrale du depot, dite au moment ou elle compte.

    Apprendre que son credit est epuise sans savoir ce qui s'arrete ferait
    croire que l'outil s'arrete. C'est l'inverse : le moteur deterministe n'a
    jamais rien coute.
    """
    from singular.journal import DecisionJournal
    from singular.sage.notice import build_notice

    journal = DecisionJournal(tmp_path / "j.db")
    for reste in (0.0, 0.20):
        dit = [i for i in build_notice(journal, budget=_budget(reste, alerte=1.0)).items
               if "API" in i.title]
        assert "sans clé" in dit[0].detail


def test_un_modele_sans_tarif_n_eteint_pas_l_observation(tmp_path) -> None:
    """`restant_usd` vaut None des qu'un modele employe n'a pas de prix.

    C'est `restant_au_mieux_usd` qui est lu, pour la meme raison que dans la
    garde du Sage : sinon l'observation s'eteint en silence le jour ou il
    essaie un modele qu'il n'a pas tarife.
    """
    from singular.journal import DecisionJournal
    from singular.sage.notice import build_notice

    journal = DecisionJournal(tmp_path / "j.db")
    budget = {"credit_usd": 5.0, "alerte_usd": 1.0,
              "restant_usd": None, "restant_au_mieux_usd": 0.40}

    dit = [i for i in build_notice(journal, budget=budget).items if "API" in i.title]
    assert [i.severity for i in dit] == ["ATTENTION"]


def test_la_notice_se_construit_avec_les_facultes_desinstallees(tmp_path) -> None:
    """Elle juge un chiffre qu'on lui tend ; elle ne va pas le chercher.

    Importer `parle` depuis la Notice mettrait le rapport du matin a la merci
    d'un paquet absent. Le temoin : le module ne nomme jamais la faculte.
    """
    import ast
    import pathlib

    source = (pathlib.Path(__file__).resolve().parent.parent
              / "singular" / "sage" / "notice.py").read_text(encoding="utf-8")
    for noeud in ast.walk(ast.parse(source)):
        if isinstance(noeud, ast.ImportFrom):
            assert "parle" not in (noeud.module or ""), "la Notice importe la faculte"
        elif isinstance(noeud, ast.Import):
            assert not any("parle" in a.name for a in noeud.names)


# --- la recherche d'emploi, jugee sur les faits du Scout ----------------------

def _faits_de(statut, combien, age):
    from singular.collecte import Fait
    return (Fait("candidatures", f"{combien} en « {statut} »", "/x.json", "2026-09-11",
                 mesure={"statut": statut, "combien": combien, "age_max": age}),)


def test_les_seuils_disent_la_meme_chose_que_le_prototype() -> None:
    """Deuxieme domicile assume, garde comme les autres.

    `proto/suivi_candidatures.py` doit tourner seul dans a-Shell et a donc
    interdiction d'importer le paquet. Les seuils sont en double, comme la
    table des libelles et la phrase du conflit -- et une copie qu'on ne peut
    pas eviter se garde par un test, pas par la vigilance.
    """
    import importlib.util
    import pathlib

    from singular.sage import notice as moteur

    chemin = pathlib.Path(__file__).resolve().parent.parent / "proto/suivi_candidatures.py"
    spec = importlib.util.spec_from_file_location("suivi_seuils", chemin)
    suivi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(suivi)

    assert moteur.RELANCE_JOURS == suivi.JOURS_AVANT_RELANCE
    assert moteur.CLASSEMENT_JOURS == suivi.JOURS_AVANT_CLASSEMENT
    assert moteur.ENVOI_JOURS == suivi.JOURS_AVANT_ENVOI


def test_sous_le_seuil_la_recherche_ne_dit_rien(tmp_path) -> None:
    """Le reproche premature a deja coute une fois dans ce depot."""
    from singular.journal import DecisionJournal
    from singular.sage.notice import RELANCE_JOURS, build_notice

    journal = DecisionJournal(tmp_path / "j.db")
    faits = _faits_de("envoyee", 2, RELANCE_JOURS - 1)

    assert not [i for i in build_notice(journal, faits=faits).items
                if i.title == "Ta recherche d'emploi"]


def test_au_seuil_elle_le_dit(tmp_path) -> None:
    from singular.journal import DecisionJournal
    from singular.sage.notice import RELANCE_JOURS, build_notice

    journal = DecisionJournal(tmp_path / "j.db")
    dit = [i for i in build_notice(journal, faits=_faits_de("envoyee", 2, RELANCE_JOURS)).items
           if i.title == "Ta recherche d'emploi"]

    assert [i.severity for i in dit] == ["ATTENTION"]
    assert f"plus de {RELANCE_JOURS} jours" in dit[0].detail


def test_un_fait_non_verifie_ne_declenche_rien(tmp_path) -> None:
    """On ne conseille pas sur ce qu'on n'a pas pu etablir.

    Le fait porte ici un age **et** le doute. C'est deliberement une forme que
    le Scout ne produit pas aujourd'hui -- sa branche non verifiee n'ecrit pas
    d'age -- et c'est tout l'interet : sans ca, le test passait parce que l'age
    manquait, pas parce que le doute etait respecte, et la garde pouvait sauter
    sans que rien ne tombe. Elle tient pour le jour ou une source de plus
    ramenera un fait date mais incertain.
    """
    from singular.collecte import Fait
    from singular.journal import DecisionJournal
    from singular.sage.notice import RELANCE_JOURS, build_notice

    journal = DecisionJournal(tmp_path / "j.db")
    doute = Fait("candidatures", "2 en « envoyée », source incertaine", "/x.json",
                 "2026-09-11", verifie=False,
                 mesure={"statut": "envoyee", "combien": 2, "age_max": RELANCE_JOURS + 30})

    assert not [i for i in build_notice(journal, faits=(doute,)).items
                if i.title == "Ta recherche d'emploi"], (
        "un age largement au-dessus du seuil, mais non verifie : on se tait")

    # Le temoin : le meme fait, tenu pour etabli, declenche bien.
    sur = Fait(doute.sujet, doute.texte, doute.source, doute.date,
               verifie=True, mesure=doute.mesure)
    assert [i for i in build_notice(journal, faits=(sur,)).items
            if i.title == "Ta recherche d'emploi"]


def test_aucun_nom_d_entreprise_ne_part_vers_le_modele(tmp_path) -> None:
    """Le `detail` de chaque observation est recopie dans ce qui part.

    `contexte_pour_analyse` envoie titre et detail de chaque item. Ses
    candidatures ne sont pas dans ce qu'il a choisi d'envoyer : une observation
    qui nommerait l'employeur les sortirait de sa machine sans qu'il l'ait
    decide. Des nombres et des ages suffisent a savoir quoi faire.
    """
    from singular.collecte import Fait
    from singular.journal import DecisionJournal
    from singular.sage.notice import build_notice

    journal = DecisionJournal(tmp_path / "j.db")
    faits = (Fait("candidatures", "1 en « envoyée »", "/x.json", "2026-09-11",
                  mesure={"statut": "envoyee", "combien": 1, "age_max": 40,
                          "entreprise": "BE Fluides Occitanie"}),)

    dit = [i for i in build_notice(journal, faits=faits).items
           if i.title == "Ta recherche d'emploi"]

    assert dit, "le seuil est franchi, l'observation doit exister"
    assert "Occitanie" not in dit[0].detail
    assert "Fluides" not in dit[0].detail


def test_sans_suivi_de_candidatures_rien_ne_change(tmp_path) -> None:
    """Le temoin : l'app doit s'ouvrir pareil chez quelqu'un qui n'a pas de suivi."""
    from singular.journal import DecisionJournal
    from singular.sage.notice import build_notice

    journal = DecisionJournal(tmp_path / "j.db")

    assert not [i for i in build_notice(journal, faits=()).items
                if i.title == "Ta recherche d'emploi"]
